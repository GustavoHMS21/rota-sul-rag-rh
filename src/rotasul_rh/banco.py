"""Conexão com o PostgreSQL e criação da tabela de chunks."""

import psycopg
from pgvector.psycopg import register_vector

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


_TIMEOUT_CONEXAO_SEGUNDOS = 10


def conectar(config: Config) -> psycopg.Connection:
    """Abre a conexão, garante a extensão pgvector e a tabela, e registra o tipo vector."""
    try:
        # Sem timeout, um endereço errado deixa a conexão pendurada por minutos em vez de falhar.
        conexao = psycopg.connect(config.conninfo, connect_timeout=_TIMEOUT_CONEXAO_SEGUNDOS)
    except psycopg.OperationalError as erro:
        raise RuntimeError(
            f"Não consegui conectar ao Postgres em {config.postgres_host}:{config.postgres_port}. "
            "O Docker está aberto e o banco de pé (docker compose ps)?"
        ) from erro

    with conexao.transaction():
        conexao.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conexao.execute(_ESQUEMA)
    # Ensina o psycopg a converter lista de números <-> tipo vector do Postgres.
    register_vector(conexao)
    return conexao
