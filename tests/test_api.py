"""Testes da API com o cliente de testes do FastAPI. Não chamam o Groq, o Ollama nem o banco:
responder() e o registro são trocados por versões falsas."""

import uuid

import pytest
from fastapi.testclient import TestClient

from rotasul_rh import api
from rotasul_rh.busca import Resultado
from rotasul_rh.config import Config
from rotasul_rh.embeddings import ErroEmbedding
from rotasul_rh.geracao import ErroGeracao, ErroLimite, Resposta

CHAVE_RH = "chave-de-teste"
ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
TRECHO = Resultado(
    "POL-RH-003#8", "POL-RH-003", "Férias", 8, "Abono", "Até um terço.", ["administrativo"], 0.64
)
RESPOSTA = Resposta(
    tipo="respondida",
    texto="Sim, até um terço das férias.",
    fontes=["POL-RH-003, Férias, seção 8"],
    ids_das_fontes=["POL-RH-003#8"],
    trechos=[TRECHO],
)


def _config(chave_rh: str | None = CHAVE_RH) -> Config:
    return Config(
        postgres_host="127.0.0.1",
        postgres_port=5432,
        postgres_db="x",
        postgres_user="x",
        postgres_password="x",
        ollama_base_url="http://127.0.0.1:9",
        embedding_model="bge-m3",
        groq_api_key="x",
        groq_model="qwen/qwen3.8-27b",
        rh_chave_acesso=chave_rh,
    )


@pytest.fixture
def chamadas(monkeypatch):
    """Troca responder() e o registro por versões falsas e anota como foram chamados."""
    anotadas = {}

    def responder_falso(pergunta, publico, config):
        anotadas["responder"] = (pergunta, publico)
        return RESPOSTA

    def registrar_falso(pergunta, publico, resposta, milissegundos, config):
        anotadas["registrar"] = (pergunta, publico, resposta.tipo)
        return ID

    monkeypatch.setattr(api, "responder", responder_falso)
    monkeypatch.setattr(api.registro, "registrar", registrar_falso)
    return anotadas


@pytest.fixture
def cliente():
    api.app.dependency_overrides[api.obter_config] = _config
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_pagina_do_funcionario(cliente):
    resposta = cliente.get("/")

    assert resposta.status_code == 200
    assert "Assistente de Políticas de RH" in resposta.text


def test_pergunta_valida_devolve_resposta_fontes_e_trechos(cliente, chamadas):
    resposta = cliente.post(
        "/api/perguntas", json={"pergunta": "  Posso vender férias?  ", "publico": "administrativo"}
    )

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["id"] == str(ID)
    assert dados["tipo"] == "respondida"
    assert dados["fontes"] == ["POL-RH-003, Férias, seção 8"]
    assert dados["trechos"][0]["fonte"] == "POL-RH-003, Férias, seção 8"
    # A pergunta chega sem os espaços das pontas, e o registro recebe o mesmo que o assistente.
    assert chamadas["responder"] == ("Posso vender férias?", "administrativo")
    assert chamadas["registrar"] == ("Posso vender férias?", "administrativo", "respondida")


def test_publico_nao_informado_vira_none(cliente, chamadas):
    cliente.post("/api/perguntas", json={"pergunta": "Posso vender férias?", "publico": None})

    assert chamadas["responder"][1] is None


@pytest.mark.parametrize(
    "corpo",
    [
        {"pergunta": ""},
        {"pergunta": "   "},
        {"pergunta": "x" * 501},
        {"pergunta": "Posso vender férias?", "publico": "diretoria"},
        {},
    ],
)
def test_entrada_invalida_e_recusada_antes_do_rag(cliente, chamadas, corpo):
    resposta = cliente.post("/api/perguntas", json=corpo)

    assert resposta.status_code == 422
    assert "responder" not in chamadas


@pytest.mark.parametrize(
    ("erro", "codigo"),
    [
        (ErroLimite("limite"), 429),
        (ErroGeracao("groq fora"), 503),
        (ErroEmbedding("Ollama passou do tempo limite (ReadTimeout)."), 503),
        (RuntimeError("banco fora"), 503),
    ],
)
def test_falhas_viram_codigos_http_com_mensagem_amigavel(cliente, monkeypatch, erro, codigo):
    def responder_com_erro(*_):
        raise erro

    monkeypatch.setattr(api, "responder", responder_com_erro)

    resposta = cliente.post("/api/perguntas", json={"pergunta": "Posso vender férias?"})

    assert resposta.status_code == codigo
    assert "groq" not in resposta.json()["detail"].lower()  # sem detalhes internos


def test_falha_no_registro_nao_derruba_a_resposta(cliente, chamadas, monkeypatch):
    def registrar_com_erro(*_):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(api.registro, "registrar", registrar_com_erro)

    resposta = cliente.post("/api/perguntas", json={"pergunta": "Posso vender férias?"})

    assert resposta.status_code == 200
    assert resposta.json()["id"] is None
    assert resposta.json()["resposta"] == RESPOSTA.texto


def test_avaliacao(cliente, monkeypatch):
    monkeypatch.setattr(api.registro, "avaliar", lambda id_, util, config: id_ == ID)

    assert cliente.post(f"/api/perguntas/{ID}/avaliacao", json={"util": True}).status_code == 204
    outro = uuid.uuid4()
    assert cliente.post(f"/api/perguntas/{outro}/avaliacao", json={"util": True}).status_code == 404


@pytest.mark.parametrize("cabecalhos", [{}, {"X-Chave-RH": "errada"}])
def test_area_do_rh_exige_a_chave(cliente, cabecalhos):
    for caminho in ("/api/rh/resumo", "/api/rh/interacoes"):
        assert cliente.get(caminho, headers=cabecalhos).status_code == 401


def test_area_do_rh_desativada_sem_chave_configurada(cliente):
    api.app.dependency_overrides[api.obter_config] = lambda: _config(chave_rh=None)

    resposta = cliente.get("/api/rh/resumo", headers={"X-Chave-RH": "qualquer"})

    assert resposta.status_code == 503


def test_area_do_rh_com_a_chave(cliente, monkeypatch):
    monkeypatch.setattr(api.registro, "resumir", lambda config: {"total": 3})
    monkeypatch.setattr(api.registro, "listar", lambda config, tipo, limite: [])

    cabecalhos = {"X-Chave-RH": CHAVE_RH}
    assert cliente.get("/api/rh/resumo", headers=cabecalhos).json() == {"total": 3}
    assert cliente.get("/api/rh/interacoes", headers=cabecalhos).json() == []
    assert cliente.get("/rh").status_code == 200  # a página em si é pública; os dados, não


def test_saude_aponta_o_que_esta_fora(cliente):
    resposta = cliente.get("/api/saude")

    # Na configuração de teste, banco e Ollama apontam para endereços sem serviço.
    assert resposta.status_code == 503
    assert resposta.json()["ollama"] == "sem conexão"
    assert resposta.json()["groq"] == "ok"
