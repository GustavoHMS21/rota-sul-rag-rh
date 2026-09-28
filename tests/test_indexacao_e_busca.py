"""Testes de integração: precisam do Postgres (Docker) e do Ollama rodando.

Rodar com: uv run pytest -m integracao
"""

import pytest

from rotasul_rh.banco import conectar
from rotasul_rh.busca import buscar
from rotasul_rh.chunking import gerar_chunks
from rotasul_rh.config import carregar_config
from rotasul_rh.indexacao import indexar
from rotasul_rh.politicas import ler_politicas

pytestmark = pytest.mark.integracao


@pytest.fixture(scope="module")
def config():
    return carregar_config()


@pytest.fixture(scope="module")
def indexado(config):
    """Indexa uma vez para todos os testes do módulo."""
    return indexar(config)


def test_grava_um_registro_por_chunk(config, indexado):
    total_de_chunks = len(gerar_chunks(ler_politicas()))

    with conectar(config) as conexao:
        linhas, ids = conexao.execute("SELECT count(*), count(DISTINCT id) FROM chunks").fetchone()

    assert indexado.total == total_de_chunks
    assert linhas == ids == total_de_chunks


def test_indexar_de_novo_nao_duplica_e_reaproveita_os_vetores(config, indexado):
    segunda = indexar(config)

    with conectar(config) as conexao:
        (linhas,) = conexao.execute("SELECT count(*) FROM chunks").fetchone()

    assert linhas == indexado.total
    assert segunda.gerados == 0  # nada mudou: nenhum embedding novo pedido ao Ollama


def test_chunk_alterado_gera_so_o_seu_embedding(config, indexado):
    with conectar(config) as conexao:
        conexao.execute("UPDATE chunks SET hash_embedding = 'alterado' WHERE id = 'POL-RH-003#5'")
        conexao.commit()

    resultado = indexar(config)

    assert resultado.gerados == 1


def test_busca_encontra_a_secao_certa(config, indexado):
    resultados = buscar("Posso vender parte das minhas férias?", None, config)

    assert resultados[0].id == "POL-RH-003#8"
    assert resultados[0].fonte == "POL-RH-003, Férias, seção 8"
    assert resultados[0].similaridade > resultados[-1].similaridade


def test_filtro_de_publico_nao_deixa_passar_outro_publico(config, indexado):
    resultados = buscar("Como peço férias?", "administrativo", config, k=10)
    ids = [r.id for r in resultados]

    assert "POL-RH-003#6-administrativo" in ids
    assert "POL-RH-003#6-operacao" not in ids
    assert "POL-RH-004#5" not in ids  # seção só da operação


def test_escala_da_tela_vira_filtro_da_operacao(config, indexado):
    ids = [r.id for r in buscar("Como peço férias?", "operacao_6x1", config, k=10)]

    assert "POL-RH-003#6-operacao" in ids
    assert "POL-RH-003#6-administrativo" not in ids
