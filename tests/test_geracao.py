"""Testes da verificação da resposta e do prompt. Não chamam o Groq."""

import json
from types import SimpleNamespace

import groq
import httpx
import pytest

from rotasul_rh import geracao
from rotasul_rh.busca import Resultado
from rotasul_rh.config import Config
from rotasul_rh.geracao import DADO_PESSOAL, NAO_ENCONTRADO, RESPONDIDA, ErroGeracao, interpretar
from rotasul_rh.prompt import RESPOSTA_PADRAO, montar_mensagens

TODOS = ["administrativo", "motorista", "operacao"]
TRECHOS = [
    Resultado(
        "POL-RH-003#5", "POL-RH-003", "Férias", 5, "Fracionamento", "Até três períodos.", TODOS, 0.7
    ),
    Resultado(
        "POL-RH-004#5", "POL-RH-004", "Banco de Horas", 5, "Operação", "Tabela.", ["operacao"], 0.6
    ),
]


def _json(**campos) -> str:
    return json.dumps(campos, ensure_ascii=False)


def test_resposta_valida_ganha_a_citacao_montada_pelo_codigo():
    resposta = interpretar(
        _json(tipo="respondida", resposta="Sim, em até três períodos.", fontes=["POL-RH-003#5"]),
        TRECHOS,
    )

    assert resposta.tipo == RESPONDIDA
    assert resposta.texto == "Sim, em até três períodos."
    assert resposta.fontes == ["POL-RH-003, Férias, seção 5"]
    assert resposta.motivo_da_troca is None


def test_aceita_identificador_com_colchetes():
    resposta = interpretar(
        _json(tipo="respondida", resposta="Sim.", fontes=["[POL-RH-003#5]"]), TRECHOS
    )

    assert resposta.ids_das_fontes == ["POL-RH-003#5"]


@pytest.mark.parametrize(
    ("conteudo", "motivo"),
    [
        ("isto não é json", "JSON inválido"),
        ("[1, 2]", "JSON inválido"),
        (_json(tipo="talvez", resposta="x", fontes=["POL-RH-003#5"]), "tipo desconhecido"),
        (_json(tipo="respondida", resposta="", fontes=["POL-RH-003#5"]), "resposta vazia"),
        (_json(tipo="respondida", resposta="Sim.", fontes=[]), "resposta sem fonte"),
        # O modelo citou uma seção que não estava entre os trechos: fonte inventada.
        (_json(tipo="respondida", resposta="Sim.", fontes=["POL-RH-003#9"]), "fonte fora"),
        (
            _json(tipo="respondida", resposta="Sim.", fontes=["POL-RH-003#5", "POL-RH-007#1"]),
            "fonte fora",
        ),
    ],
)
def test_resposta_que_nao_passa_na_verificacao_vira_a_padrao(conteudo, motivo):
    resposta = interpretar(conteudo, TRECHOS)

    assert resposta.texto == RESPOSTA_PADRAO
    assert resposta.fontes == []
    assert motivo in resposta.motivo_da_troca


@pytest.mark.parametrize("tipo", [NAO_ENCONTRADO, DADO_PESSOAL])
def test_recusa_do_modelo_vira_a_padrao_mesmo_com_texto(tipo):
    resposta = interpretar(_json(tipo=tipo, resposta="Você tem 12 dias.", fontes=[]), TRECHOS)

    assert resposta.tipo == tipo
    assert resposta.texto == RESPOSTA_PADRAO
    assert resposta.motivo_da_troca is None


def test_prompt_identifica_publico_e_trechos():
    sistema, usuario = montar_mensagens("Trabalhei no sábado?", "operacao_6x1", TRECHOS)

    assert sistema["role"] == "system" and "SOMENTE" in sistema["content"]
    assert (
        "Público de quem pergunta: Operação dos CDs de Jundiaí e Sumaré, escala 6x1"
        in (usuario["content"])
    )
    assert (
        "[POL-RH-003#5] Política de Férias, seção 5: Fracionamento (vale para: todos"
        in (usuario["content"])
    )
    assert "(vale para: operacao)" in usuario["content"]
    assert usuario["content"].endswith("<pergunta>Trabalhei no sábado?</pergunta>")


CONFIG = Config(
    postgres_host="127.0.0.1",
    postgres_port=5432,
    postgres_db="x",
    postgres_user="x",
    postgres_password="x",
    ollama_base_url="http://127.0.0.1:9",
    embedding_model="bge-m3",
    groq_api_key="chave-de-teste",
    groq_model="qwen/qwen3.8-27b",
)


def test_cliente_do_groq_e_criado_uma_vez_com_limite_de_tempo():
    """Criar o cliente não chama a rede; reaproveitá-lo mantém a conexão HTTPS aberta."""
    geracao._cliente.cache_clear()
    try:
        cliente = geracao._cliente("chave-de-teste", 2)

        assert geracao._cliente("chave-de-teste", 2) is cliente
        assert cliente.timeout == 20
        assert cliente.max_retries == 2
    finally:
        geracao._cliente.cache_clear()


def test_groq_sem_responder_vira_erro_de_geracao(monkeypatch):
    def criar(**_):
        raise groq.APITimeoutError(request=httpx.Request("POST", "https://api.groq.com"))

    cliente_lento = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=criar)))
    monkeypatch.setattr(geracao, "_cliente", lambda *_: cliente_lento)

    with pytest.raises(ErroGeracao, match="passou de 20 s"):
        geracao._perguntar_ao_modelo([], CONFIG, tentativas=2)
