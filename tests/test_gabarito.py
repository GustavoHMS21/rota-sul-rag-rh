"""Confere se o gabarito de avaliação (evals/perguntas.json) é fiel às políticas.

O gabarito é a régua que vai medir o assistente. Se ele citar uma seção que não existe ou um fato
que não está no texto, a medição fica errada. Estes testes impedem isso.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from rotasul_rh.politicas import ler_politicas

GABARITO = Path(__file__).parent.parent / "evals" / "perguntas.json"
PERGUNTAS = json.loads(GABARITO.read_text(encoding="utf-8"))

TIPOS = {
    "direta",
    "tabela",
    "multi_politica",
    "regra_substituida",
    "publico",
    "publico_ambiguo",
    "dado_pessoal",
    "fora_das_politicas",
    "documento_ausente",
}
COMPORTAMENTOS = {"responder", "separar_publicos", "dado_pessoal", "nao_encontrado"}
PUBLICOS = {None, "administrativo", "operacao", "operacao_5x2", "operacao_6x1", "motorista"}
RESPOSTA_PADRAO = (
    "Não encontrei essa informação nas políticas. Fale com o RH pelo e-mail rh@rotasul.com.br."
)


def _normalizar(texto: str) -> str:
    return " ".join(texto.split())


@pytest.fixture(scope="module")
def secoes_por_fonte() -> dict[str, str]:
    """{"POL-RH-003#5": texto da seção}"""
    return {f"{s.codigo}#{s.numero}": _normalizar(s.texto) for s in ler_politicas()}


def _ids(pergunta: dict) -> str:
    return pergunta["id"]


def test_ids_sao_unicos():
    repetidos = [i for i, n in Counter(p["id"] for p in PERGUNTAS).items() if n > 1]
    assert not repetidos


def test_cobre_todas_as_politicas(secoes_por_fonte):
    codigos_citados = {f.split("#")[0] for p in PERGUNTAS for f in p["fontes"]}
    todos_os_codigos = {f.split("#")[0] for f in secoes_por_fonte}
    assert codigos_citados == todos_os_codigos


@pytest.mark.parametrize("pergunta", PERGUNTAS, ids=_ids)
def test_campos_validos(pergunta):
    assert pergunta["pergunta"].strip()
    assert pergunta["tipo"] in TIPOS
    assert pergunta["comportamento"] in COMPORTAMENTOS
    assert pergunta["publico"] in PUBLICOS


@pytest.mark.parametrize("pergunta", PERGUNTAS, ids=_ids)
def test_fontes_e_fatos_existem_nas_politicas(pergunta, secoes_por_fonte):
    if pergunta["comportamento"] in {"dado_pessoal", "nao_encontrado"}:
        assert pergunta["fontes"] == []
        assert pergunta["fatos"] == []
        assert pergunta["resposta_esperada"] == RESPOSTA_PADRAO
        return

    assert pergunta["fontes"], "pergunta respondível precisa de ao menos uma fonte"
    for fonte in pergunta["fontes"]:
        assert fonte in secoes_por_fonte, f"seção inexistente: {fonte}"

    texto_das_fontes = " ".join(secoes_por_fonte[f] for f in pergunta["fontes"])
    for fato in pergunta["fatos"]:
        assert _normalizar(fato) in texto_das_fontes, f"fato fora da fonte: {fato!r}"


@pytest.mark.parametrize("pergunta", PERGUNTAS, ids=_ids)
def test_proibidos_sao_regras_reais_de_outro_publico(pergunta, secoes_por_fonte):
    """Um "proibido" é uma regra que existe, mas vale para outro público. Não pode ser inventado."""
    todo_o_texto = " ".join(secoes_por_fonte.values())
    for proibido in pergunta["proibidos"]:
        assert _normalizar(proibido) in todo_o_texto, f"proibido inexistente: {proibido!r}"
        assert proibido not in pergunta["fatos"]
