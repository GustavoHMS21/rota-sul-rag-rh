"""Testes da API com o cliente de testes do FastAPI. Não chamam o Groq, o Ollama nem o banco:
responder() e o registro são trocados por versões falsas."""

import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rotasul_rh import api
from rotasul_rh.busca import Resultado
from rotasul_rh.config import Config
from rotasul_rh.embeddings import ErroEmbedding
from rotasul_rh.geracao import ErroGeracao, ErroLimite, Resposta
from rotasul_rh.idempotencia import Idempotencia
from rotasul_rh.limites import Limitador, Regra

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
def cliente(monkeypatch):
    # Estado em memória zerado a cada teste: um teste não herda as contagens do outro.
    api._limitadores_de_perguntas.cache_clear()
    monkeypatch.setattr(api, "_idempotencia", Idempotencia())
    monkeypatch.setattr(api, "_falhas_na_chave_do_rh", Limitador([Regra(5, 15 * 60)]))
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


def test_saude_sem_chave_so_diz_que_falhou(cliente):
    resposta = cliente.get("/api/saude")

    # Na configuração de teste, banco e Ollama apontam para endereços sem serviço.
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "falha"}  # sem revelar qual peça nem a arquitetura


def test_saude_com_a_chave_do_rh_aponta_o_que_esta_fora(cliente):
    resposta = cliente.get("/api/saude", headers={"X-Chave-RH": CHAVE_RH})

    assert resposta.status_code == 503
    assert resposta.json()["ollama"] == "sem conexão"
    assert resposta.json()["groq"] == "ok"


def test_saude_com_chave_errada_conta_para_o_bloqueio(cliente):
    """Se não contasse, a saúde seria um jeito de testar chaves sem limite."""
    for _ in range(5):
        assert cliente.get("/api/saude", headers={"X-Chave-RH": "chute"}).status_code == 401

    assert cliente.get("/api/rh/resumo", headers={"X-Chave-RH": CHAVE_RH}).status_code == 429


def test_chave_com_acento_e_recusada_sem_derrubar_o_servidor(cliente):
    """compare_digest com texto fora do ASCII levantava TypeError (500)."""
    resposta = cliente.get("/api/rh/resumo", headers={"X-Chave-RH": "chave-errada-é".encode()})

    assert resposta.status_code == 401


# ---------------------------------------------------------------- cabeçalhos de segurança


@pytest.mark.parametrize("caminho", ["/", "/rh", "/static/app.js", "/api/saude"])
def test_cabecalhos_de_seguranca_em_todas_as_respostas(cliente, caminho):
    cabecalhos = cliente.get(caminho).headers

    assert "default-src 'self'" in cabecalhos["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in cabecalhos["Content-Security-Policy"]
    assert cabecalhos["X-Content-Type-Options"] == "nosniff"
    assert cabecalhos["X-Frame-Options"] == "DENY"
    assert cabecalhos["Referrer-Policy"] == "no-referrer"


def test_area_do_rh_nao_fica_em_cache(cliente, monkeypatch):
    monkeypatch.setattr(api.registro, "resumir", lambda config: {"total": 3})

    resposta = cliente.get("/api/rh/resumo", headers={"X-Chave-RH": CHAVE_RH})

    assert resposta.headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------- idempotência e limites


def _contar_respostas(monkeypatch, *erros):
    """Troca responder() por uma versão que levanta os erros dados, em ordem, e depois responde.
    Devolve a lista de chamadas."""
    chamadas = []
    pendentes = list(erros)

    def responder_falso(pergunta, publico, config):
        chamadas.append(pergunta)
        if pendentes:
            raise pendentes.pop(0)
        return RESPOSTA

    monkeypatch.setattr(api, "responder", responder_falso)
    monkeypatch.setattr(api.registro, "registrar", lambda *_: ID)
    return chamadas


def test_reenvio_com_a_mesma_chave_devolve_a_resposta_sem_perguntar_de_novo(cliente, monkeypatch):
    chamadas = _contar_respostas(monkeypatch)
    corpo = {"pergunta": "Posso vender férias?", "publico": "administrativo"}
    cabecalhos = {"Idempotency-Key": "4f9c2a10-0000-4000-8000-000000000001"}

    primeira = cliente.post("/api/perguntas", json=corpo, headers=cabecalhos)
    reenvio = cliente.post("/api/perguntas", json=corpo, headers=cabecalhos)

    assert primeira.status_code == reenvio.status_code == 200
    assert reenvio.json() == primeira.json()
    assert reenvio.headers["Idempotent-Replayed"] == "true"
    assert len(chamadas) == 1  # o modelo foi chamado (e a pergunta registrada) uma vez só


def test_mesma_chave_com_outra_pergunta_e_recusada(cliente, monkeypatch):
    _contar_respostas(monkeypatch)
    cabecalhos = {"Idempotency-Key": "chave-1"}
    cliente.post("/api/perguntas", json={"pergunta": "Posso vender férias?"}, headers=cabecalhos)

    resposta = cliente.post(
        "/api/perguntas", json={"pergunta": "Como peço EPI?"}, headers=cabecalhos
    )

    assert resposta.status_code == 422


def test_falha_libera_a_chave_e_o_reenvio_tenta_de_verdade(cliente, monkeypatch):
    chamadas = _contar_respostas(monkeypatch, ErroGeracao("groq fora"))
    corpo = {"pergunta": "Posso vender férias?"}
    cabecalhos = {"Idempotency-Key": "chave-1"}

    assert cliente.post("/api/perguntas", json=corpo, headers=cabecalhos).status_code == 503
    assert cliente.post("/api/perguntas", json=corpo, headers=cabecalhos).status_code == 200
    assert len(chamadas) == 2


def test_limite_por_ip_devolve_429_com_retry_after(cliente, monkeypatch):
    chamadas = _contar_respostas(monkeypatch)
    api.app.dependency_overrides[api.obter_config] = lambda: replace(
        _config(), limite_perguntas_por_minuto=2
    )
    corpo = {"pergunta": "Posso vender férias?"}

    cliente.post("/api/perguntas", json={"pergunta": ""})  # inválida (422): não conta
    respostas = [cliente.post("/api/perguntas", json=corpo) for _ in range(3)]

    assert [r.status_code for r in respostas] == [200, 200, 429]
    assert 0 < int(respostas[2].headers["Retry-After"]) <= 60
    assert "muitas perguntas" in respostas[2].json()["detail"]
    assert len(chamadas) == 2  # a barrada não chegou ao modelo


def test_teto_do_dia_vale_para_todos_os_ips(cliente, monkeypatch):
    _contar_respostas(monkeypatch)
    api.app.dependency_overrides[api.obter_config] = lambda: replace(
        _config(), limite_perguntas_por_dia=1
    )
    corpo = {"pergunta": "Posso vender férias?"}

    assert cliente.post("/api/perguntas", json=corpo).status_code == 200
    resposta = cliente.post("/api/perguntas", json=corpo)

    assert resposta.status_code == 429
    assert "rh@rotasul.com.br" in resposta.json()["detail"]


def test_chave_do_rh_errada_cinco_vezes_bloqueia_ate_a_certa(cliente, monkeypatch):
    monkeypatch.setattr(api.registro, "resumir", lambda config: {"total": 3})

    for _ in range(5):
        errada = cliente.get("/api/rh/resumo", headers={"X-Chave-RH": "chute"})
        assert errada.status_code == 401
    certa = cliente.get("/api/rh/resumo", headers={"X-Chave-RH": CHAVE_RH})

    assert certa.status_code == 429
    assert int(certa.headers["Retry-After"]) > 0
