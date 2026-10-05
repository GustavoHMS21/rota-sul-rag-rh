"""Testes dos logs (ADR-0011). Não chamam o Groq, o Ollama nem o banco."""

import json
import logging
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rotasul_rh import api, geracao
from rotasul_rh.busca import Resultado
from rotasul_rh.config import Config
from rotasul_rh.geracao import ErroGeracao
from rotasul_rh.logs import FormatoJson, FormatoTexto, _RetryDoGroqComoAviso, configurar_logs

TRECHO = Resultado(
    "POL-RH-003#8", "POL-RH-003", "Férias", 8, "Abono", "Até um terço.", ["administrativo"], 0.64
)
PERGUNTA_SENSIVEL = "Tenho diabetes e meu CPF é 123.456.789-00. Posso vender férias?"


def _registro(mensagem="evento", nivel=logging.INFO, **extras) -> logging.LogRecord:
    registro = logging.makeLogRecord(
        {"name": "rotasul_rh.teste", "levelno": nivel, "levelname": logging.getLevelName(nivel)}
    )
    registro.msg = mensagem
    registro.req = "a1b2c3d4"
    registro.__dict__.update(extras)
    return registro


def test_formato_json_tem_hora_nivel_codigo_e_campos_extras():
    evento = json.loads(
        FormatoJson().format(_registro("busca concluída", evento="busca", trechos=6))
    )

    assert evento["nivel"] == "INFO"
    assert evento["req"] == "a1b2c3d4"
    assert evento["mensagem"] == "busca concluída"
    assert evento["evento"] == "busca" and evento["trechos"] == 6
    assert "T" in evento["hora"]  # data e hora no formato ISO


def test_formato_json_guarda_o_traceback():
    try:
        raise ValueError("falhou")
    except ValueError:
        registro = _registro("falha", logging.ERROR)
        registro.exc_info = sys.exc_info()

    evento = json.loads(FormatoJson().format(registro))

    assert "Traceback" in evento["erro"] and "ValueError: falhou" in evento["erro"]


def test_formato_texto_mostra_codigo_e_campos():
    linha = FormatoTexto().format(_registro("modelo respondeu", segundos=0.84))

    assert "[a1b2c3d4]" in linha and "modelo respondeu | segundos=0.84" in linha


def test_retry_do_groq_vira_aviso():
    registro = _registro("Retrying request to /openai/v1/chat/completions in 2.000000 seconds")

    _RetryDoGroqComoAviso().filter(registro)

    assert registro.levelname == "WARNING"


def test_configurar_duas_vezes_nao_duplica_e_grava_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_NIVEL", "INFO")
    raiz = logging.getLogger()
    antes = list(raiz.handlers)
    try:
        configurar_logs(tmp_path)
        configurar_logs(tmp_path)  # o --reload chama de novo
        nossos = [h for h in raiz.handlers if getattr(h, "_rotasul", False)]
        assert len(nossos) == 2  # terminal e arquivo, uma vez só

        logging.getLogger("rotasul_rh.teste").info("gravado", extra={"evento": "teste"})
        for handler in nossos:
            handler.flush()
        linha = (tmp_path / "app.log").read_text(encoding="utf-8").strip().splitlines()[-1]
        assert json.loads(linha)["evento"] == "teste"
    finally:
        for handler in [h for h in raiz.handlers if h not in antes]:
            raiz.removeHandler(handler)
            handler.close()


# ---------------------------------------------------------------- caminho completo pela API


class _GroqFalso:
    """Cliente do Groq de mentira: devolve sempre a mesma resposta válida."""

    def __init__(self):
        conteudo = json.dumps(
            {"tipo": "respondida", "resposta": "Sim, até um terço.", "fontes": ["POL-RH-003#8"]}
        )
        conclusao = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=conteudo), finish_reason="stop")
            ],
            usage=SimpleNamespace(prompt_tokens=1280, completion_tokens=40),
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_: conclusao))


def _config() -> Config:
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
    )


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(geracao, "buscar_contexto", lambda *_: [TRECHO])
    monkeypatch.setattr(geracao, "_cliente", lambda *_: _GroqFalso())
    monkeypatch.setattr(
        api.registro, "registrar", lambda *_: "29876b73-ae1d-4379-8cc1-8ba2c07899fb"
    )
    api._limitadores_de_perguntas.cache_clear()  # contagens zeradas a cada teste
    api.app.dependency_overrides[api.obter_config] = _config
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_uma_pergunta_gera_eventos_com_o_mesmo_codigo_e_sem_o_texto(cliente, caplog):
    caplog.set_level(logging.INFO)

    resposta = cliente.post(
        "/api/perguntas", json={"pergunta": PERGUNTA_SENSIVEL, "publico": "administrativo"}
    )

    assert resposta.status_code == 200
    codigo = resposta.headers["X-Request-ID"]
    eventos = {getattr(r, "evento", None): r for r in caplog.records}
    assert {"pergunta", "groq", "resposta", "requisicao"} <= set(eventos)
    assert all(r.req == codigo for r in caplog.records if hasattr(r, "req"))
    assert eventos["pergunta"].caracteres == len(PERGUNTA_SENSIVEL)
    assert eventos["groq"].tokens_entrada == 1280
    assert eventos["resposta"].fontes == ["POL-RH-003#8"]

    # LGPD: nenhum pedaço da pergunta (nem da resposta) em nenhuma linha, em nenhum formato.
    for registro in caplog.records:
        registro.req = codigo
        for linha in (FormatoJson().format(registro), FormatoTexto().format(registro)):
            for trecho in ("diabetes", "123.456.789-00", "Posso vender", "Sim, até um terço"):
                assert trecho not in linha


def test_erro_mostra_ao_funcionario_o_mesmo_codigo_do_log(cliente, monkeypatch, caplog):
    def responder_com_erro(*_):
        raise ErroGeracao("O Groq devolveu um erro (500).")

    monkeypatch.setattr(api, "responder", responder_com_erro)

    resposta = cliente.post("/api/perguntas", json={"pergunta": "Posso vender férias?"})

    codigo = resposta.headers["X-Request-ID"]
    assert resposta.status_code == 503
    assert f"informe o código {codigo}" in resposta.json()["detail"]
    falha = next(r for r in caplog.records if getattr(r, "evento", None) == "falha")
    assert falha.levelname == "ERROR" and falha.exc_info  # com o traceback
