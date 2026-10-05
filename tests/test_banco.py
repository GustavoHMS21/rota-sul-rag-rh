"""Testes do pool de conexões. Não precisam do Postgres: o pool e o esquema são trocados por
versões falsas, e o teste de banco fora do ar aponta para uma porta onde nada responde."""

import threading

import pytest
from psycopg_pool import PoolTimeout

from rotasul_rh import banco
from rotasul_rh.config import Config

CONFIG = Config(
    postgres_host="127.0.0.1",
    postgres_port=9,  # porta onde nada responde
    postgres_db="x",
    postgres_user="x",
    postgres_password="x",
    ollama_base_url="http://127.0.0.1:9",
    embedding_model="bge-m3",
)


class _PoolFalso:
    criados = 0
    check_connection = staticmethod(lambda conexao: None)

    def __init__(self, *_, **__):
        type(self).criados += 1
        self.fechado = False

    def connection(self, timeout):
        raise PoolTimeout(f"nenhuma conexão livre em {timeout} s")

    def close(self):
        self.fechado = True


@pytest.fixture
def pool_falso(monkeypatch):
    """Anota cada criação do esquema e usa o pool falso. No fim, esquece os pools criados."""
    esquemas = []
    monkeypatch.setattr(banco, "criar_esquema", esquemas.append)
    monkeypatch.setattr(banco, "ConnectionPool", _PoolFalso)
    _PoolFalso.criados = 0
    yield esquemas
    banco.fechar_pools()


def test_esquema_e_pool_sao_criados_uma_vez_com_requisicoes_simultaneas(pool_falso):
    largada = threading.Barrier(8)

    def primeira_requisicao():
        largada.wait()  # as 8 threads pedem o pool no mesmo instante
        banco.preparar_banco(CONFIG)

    threads = [threading.Thread(target=primeira_requisicao) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(pool_falso) == 1
    assert _PoolFalso.criados == 1


def test_pool_esgotado_vira_erro_tratavel(pool_falso):
    """RuntimeError é o que a API transforma em 503 com mensagem amigável."""
    with (
        pytest.raises(RuntimeError, match="Não consegui conectar ao Postgres"),
        banco.conectar(CONFIG),
    ):
        pass


def test_fechar_pools_fecha_as_conexoes_e_esquece_o_pool(pool_falso):
    banco.preparar_banco(CONFIG)
    pool = banco._pools[CONFIG.conninfo]

    banco.fechar_pools()

    assert pool.fechado
    assert banco._pools == {}


def test_banco_fora_do_ar_nao_deixa_pool_pela_metade():
    """Sem o banco, o esquema falha antes de o pool existir; a próxima requisição tenta de novo."""
    with pytest.raises(RuntimeError, match="Não consegui conectar ao Postgres"):
        banco.preparar_banco(CONFIG)

    assert CONFIG.conninfo not in banco._pools
