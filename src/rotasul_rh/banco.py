"""Conexão com o PostgreSQL: criação do esquema e pool de conexões."""

import atexit
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool, PoolTimeout

from rotasul_rh.config import Config
from rotasul_rh.embeddings import DIMENSAO

# Sem índice vetorial (HNSW): com dezenas de chunks, comparar com todos é mais rápido que usar
# índice. Rever quando a base passar de alguns milhares de chunks (ADR-0005).
_ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS chunks (
    id         text PRIMARY KEY,
    codigo     text NOT NULL,
    nome       text NOT NULL,
    versao     text NOT NULL,
    vigencia   text NOT NULL,
    secao      integer NOT NULL,
    titulo     text NOT NULL,
    publicos   text[] NOT NULL,
    texto      text NOT NULL,
    arquivo    text NOT NULL,
    embedding  vector({DIMENSAO}) NOT NULL
);
-- Impressão digital do texto que gerou o embedding (e do modelo), para a indexação só pedir ao
-- Ollama os vetores do que mudou. Adicionada depois da criação da tabela, por isso o ALTER.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS hash_embedding text;

-- Registro anônimo das perguntas e respostas (ADR-0008): nada identifica quem perguntou
-- (sem usuário, IP ou navegador). CPF, e-mail e telefone são mascarados antes de gravar, e os
-- registros são apagados depois do prazo de retenção.
CREATE TABLE IF NOT EXISTS interacoes (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    criado_em        timestamptz NOT NULL DEFAULT now(),
    pergunta         text NOT NULL,
    publico          text,
    tipo             text NOT NULL,
    resposta         text NOT NULL,
    fontes           text[] NOT NULL,
    trechos          jsonb NOT NULL,
    modelo           text NOT NULL,
    motivo_da_troca  text,
    milissegundos    integer NOT NULL,
    avaliacao_util   boolean,
    avaliada_em      timestamptz
);
CREATE INDEX IF NOT EXISTS interacoes_criado_em ON interacoes (criado_em);
"""

# Vale para abrir uma conexão nova e para esperar uma livre no pool. Sem limite, um endereço
# errado ou um pool esgotado deixariam a requisição pendurada em vez de falhar.
_TIMEOUT_CONEXAO_SEGUNDOS = 10
# O FastAPI atende até 40 requisições ao mesmo tempo (uma thread cada), mas cada pergunta usa o
# banco por poucos milissegundos: 10 conexões sobram para 220 funcionários.
_CONEXOES_MINIMO = 1
_CONEXOES_MAXIMO = 10

# Um pool por banco (conninfo). Na prática é um só; os testes de integração podem usar outro.
_pools: dict[str, ConnectionPool] = {}
_trava = threading.Lock()


def criar_esquema(config: Config) -> None:
    """Cria a extensão pgvector e as tabelas, se ainda não existirem.

    Roda uma vez por processo, antes de o pool abrir a primeira conexão. Antes, rodava a cada
    conexão: uma ida e volta a mais ao banco em toda requisição, e o ALTER TABLE pede bloqueio
    exclusivo da tabela mesmo quando a coluna já existe, o que enfileirava buscas simultâneas.
    """
    with _abrir_conexao_avulsa(config) as conexao, conexao.transaction():
        conexao.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conexao.execute(_ESQUEMA)


def preparar_banco(config: Config) -> None:
    """Cria o esquema e abre o pool agora, na subida da API, em vez de na primeira pergunta."""
    _obter_pool(config)


@contextmanager
def conectar(config: Config) -> Iterator[psycopg.Connection]:
    """Empresta uma conexão do pool. No fim do bloco ela volta para o pool, com commit se o bloco
    terminou bem e rollback se deu erro."""
    pool = _obter_pool(config)
    try:
        with pool.connection(timeout=_TIMEOUT_CONEXAO_SEGUNDOS) as conexao:
            yield conexao
    except PoolTimeout as erro:
        raise RuntimeError(_mensagem_sem_banco(config)) from erro


def fechar_pools() -> None:
    """Fecha todas as conexões. Chamada na saída da API e, nos scripts, no fim do processo."""
    with _trava:
        for pool in _pools.values():
            pool.close()
        _pools.clear()


atexit.register(fechar_pools)


def _obter_pool(config: Config) -> ConnectionPool:
    pool = _pools.get(config.conninfo)
    if pool is not None:
        return pool
    with _trava:
        # Outra thread pode ter criado o pool enquanto esta esperava a trava.
        if config.conninfo not in _pools:
            # Antes do pool: o register_vector de cada conexão precisa do tipo vector já criado.
            # Se o banco estiver fora, o erro sobe e a próxima requisição tenta de novo.
            criar_esquema(config)
            _pools[config.conninfo] = ConnectionPool(
                config.conninfo,
                min_size=_CONEXOES_MINIMO,
                max_size=_CONEXOES_MAXIMO,
                kwargs={"connect_timeout": _TIMEOUT_CONEXAO_SEGUNDOS},
                configure=_configurar,
                # Testa a conexão antes de entregá-la: se o banco reiniciou, o pool troca a
                # conexão morta por uma nova em vez de devolver erro na requisição.
                check=ConnectionPool.check_connection,
                name="rotasul",
                open=True,
            )
        return _pools[config.conninfo]


def _configurar(conexao: psycopg.Connection) -> None:
    """Roda em cada conexão nova do pool: ensina o psycopg a converter lista <-> vector.

    O register_vector consulta o banco, o que abre uma transação; o pool só aceita a conexão de
    volta sem transação aberta, por isso o commit.
    """
    register_vector(conexao)
    conexao.commit()


def _abrir_conexao_avulsa(config: Config) -> psycopg.Connection:
    try:
        return psycopg.connect(config.conninfo, connect_timeout=_TIMEOUT_CONEXAO_SEGUNDOS)
    except psycopg.OperationalError as erro:
        raise RuntimeError(_mensagem_sem_banco(config)) from erro


def _mensagem_sem_banco(config: Config) -> str:
    return (
        f"Não consegui conectar ao Postgres em {config.postgres_host}:{config.postgres_port}. "
        "O Docker está aberto e o banco de pé (docker compose ps)?"
    )
