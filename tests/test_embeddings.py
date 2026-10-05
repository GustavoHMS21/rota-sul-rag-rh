import httpx
import pytest

from rotasul_rh import embeddings
from rotasul_rh.config import Config, carregar_config
from rotasul_rh.embeddings import (
    DIMENSAO,
    TIMEOUT_PERGUNTA,
    ErroEmbedding,
    gerar_embedding,
    gerar_embeddings,
)

_CONFIG_SEM_OLLAMA = Config(
    postgres_host="127.0.0.1",
    postgres_port=5432,
    postgres_db="x",
    postgres_user="x",
    postgres_password="x",
    ollama_base_url="http://127.0.0.1:9",  # porta onde nada responde
    embedding_model="bge-m3",
)
_VETOR = [0.0] * DIMENSAO


@pytest.fixture
def ollama(monkeypatch):
    """Troca o httpx.post por um roteiro: cada chamada consome o próximo item, que é uma exceção
    a levantar ou o código HTTP a devolver. Anota as chamadas e as esperas (sem dormir de fato)."""
    estado = {"roteiro": [], "chamadas": [], "esperas": []}

    def post_falso(url, json, timeout):
        estado["chamadas"].append(timeout)
        passo = estado["roteiro"].pop(0)
        if isinstance(passo, Exception):
            raise passo
        if passo == 200:
            return httpx.Response(200, json={"embeddings": [_VETOR for _ in json["input"]]})
        return httpx.Response(passo, text="erro do Ollama")

    monkeypatch.setattr(embeddings.httpx, "post", post_falso)
    monkeypatch.setattr(embeddings.time, "sleep", estado["esperas"].append)
    return estado


def test_ollama_fora_do_ar_gera_erro_claro():
    with pytest.raises(ErroEmbedding, match="Ollama não respondeu"):
        gerar_embeddings(["teste"], _CONFIG_SEM_OLLAMA)


def test_pergunta_usa_o_limite_curto(ollama):
    ollama["roteiro"] = [200]

    assert gerar_embedding("Posso vender férias?", _CONFIG_SEM_OLLAMA) == _VETOR
    assert ollama["chamadas"] == [TIMEOUT_PERGUNTA]


@pytest.mark.parametrize(
    "falha", [httpx.ReadTimeout("lento"), httpx.ConnectError("recusada"), 503]
)
def test_falha_temporaria_na_pergunta_e_repetida_uma_vez(ollama, falha):
    ollama["roteiro"] = [falha, 200]

    assert gerar_embedding("Posso vender férias?", _CONFIG_SEM_OLLAMA) == _VETOR
    assert len(ollama["chamadas"]) == 2
    assert len(ollama["esperas"]) == 1
    assert 0.25 <= ollama["esperas"][0] <= 0.75  # 0,5 s com sorteio de ±50%


def test_desiste_depois_da_nova_tentativa_com_erro_tratavel(ollama):
    """Antes, o tempo esgotado escapava como httpx.ReadTimeout e virava 500 na API."""
    ollama["roteiro"] = [httpx.ReadTimeout("lento"), httpx.ReadTimeout("lento")]

    with pytest.raises(ErroEmbedding, match="tempo limite"):
        gerar_embedding("Posso vender férias?", _CONFIG_SEM_OLLAMA)
    assert len(ollama["chamadas"]) == 2


def test_erro_4xx_nao_e_repetido(ollama):
    ollama["roteiro"] = [404]

    with pytest.raises(ErroEmbedding, match="recusou o pedido \\(404\\)"):
        gerar_embedding("Posso vender férias?", _CONFIG_SEM_OLLAMA)
    assert len(ollama["chamadas"]) == 1
    assert ollama["esperas"] == []


def test_indexacao_nao_repete_por_padrao(ollama):
    ollama["roteiro"] = [httpx.ReadTimeout("lento")]

    with pytest.raises(ErroEmbedding):
        gerar_embeddings(["a", "b"], _CONFIG_SEM_OLLAMA)
    assert len(ollama["chamadas"]) == 1


@pytest.mark.integracao
def test_texto_maior_que_o_contexto_e_recusado_e_nao_truncado():
    with pytest.raises(ErroEmbedding, match="exceeds the context length"):
        gerar_embeddings(["palavra " * 6000], carregar_config())
