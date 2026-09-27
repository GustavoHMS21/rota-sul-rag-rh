import json
from pathlib import Path

import pytest

from rotasul_rh.chunking import TETO_DE_TOKENS, chunks_da_secao, estimar_tokens, gerar_chunks
from rotasul_rh.modelos import Secao
from rotasul_rh.politicas import ler_politicas
from rotasul_rh.publico import ADMINISTRATIVO, MOTORISTA, OPERACAO, TODOS, publico_do_usuario

GABARITO = json.loads(
    (Path(__file__).parent.parent / "evals" / "perguntas.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def secoes():
    return ler_politicas()


@pytest.fixture(scope="module")
def chunks(secoes):
    return gerar_chunks(secoes)


@pytest.fixture(scope="module")
def por_id(chunks):
    return {c.id: c for c in chunks}


def _secao(texto: str, titulo: str = "Regras") -> Secao:
    return Secao(
        codigo="POL-RH-999",
        nome="Teste",
        versao="1.0",
        vigencia="01/01/2026",
        numero=1,
        titulo=titulo,
        texto=texto,
        arquivo="teste.docx",
    )


def test_secao_sem_publico_vira_um_chunk_para_todos(por_id):
    fracionamento = por_id["POL-RH-003#5"]

    assert fracionamento.publicos == TODOS
    assert fracionamento.texto == fracionamento.secao.texto


def test_titulo_da_secao_define_o_publico(por_id):
    assert por_id["POL-RH-004#4"].publicos == {ADMINISTRATIVO}
    assert por_id["POL-RH-004#5"].publicos == {OPERACAO}
    assert por_id["POL-RH-004#6"].publicos == {MOTORISTA}


def test_secao_com_paragrafos_de_publicos_diferentes_e_dividida(por_id):
    administrativo = por_id["POL-RH-003#6-administrativo"]
    operacao = por_id["POL-RH-003#6-operacao"]
    geral = por_id["POL-RH-003#6-geral"]

    assert "formulário de férias" in administrativo.texto
    assert "outubro" not in administrativo.texto
    assert "outubro" in operacao.texto
    assert "formulário de férias" not in operacao.texto
    # O parágrafo geral vai para todos os chunks da seção.
    aviso = "o RH envia o aviso de férias"
    assert aviso in administrativo.texto and aviso in operacao.texto and aviso in geral.texto
    # Quem não foi citado (motorista) recebe só os parágrafos gerais.
    assert geral.publicos == {MOTORISTA}
    assert geral.texto.startswith("Depois da aprovação")


def test_rotulo_que_nao_e_publico_nao_divide_a_secao(por_id):
    assert por_id["POL-RH-006#4"].publicos == TODOS  # "Operadora: VidaPlena Saúde."


def test_cabecalho_de_contexto(por_id):
    chunk = por_id["POL-RH-004#5"]

    assert chunk.cabecalho == (
        "Política de Banco de Horas (POL-RH-004) | Seção 5: Operação (CDs de Jundiaí e Sumaré)"
    )
    assert chunk.texto_para_embedding == f"{chunk.cabecalho}\n{chunk.texto}"


def test_ids_sao_unicos(chunks):
    assert len({c.id for c in chunks}) == len(chunks)


def test_nenhum_paragrafo_se_perde(secoes, chunks):
    textos = "\n".join(c.texto for c in chunks)
    for secao in secoes:
        for paragrafo in secao.texto.split("\n"):
            assert paragrafo in textos, f"{secao.fonte}: parágrafo sem chunk"


def test_todos_os_chunks_cabem_no_teto(chunks):
    assert max(estimar_tokens(c.texto_para_embedding) for c in chunks) <= TETO_DE_TOKENS
    assert not any("-parte" in c.id for c in chunks)  # hoje nenhuma seção precisa ser dividida


def test_secao_acima_do_teto_e_dividida_entre_paragrafos():
    paragrafo = "palavra " * 150  # ~1.200 caracteres, ~480 tokens estimados
    secao = _secao("\n".join([paragrafo.strip()] * 3))

    partes = chunks_da_secao(secao)

    assert [c.id for c in partes] == [f"POL-RH-999#1-parte{i}" for i in (1, 2, 3)]
    assert all(c.texto == paragrafo.strip() for c in partes)  # nenhum parágrafo cortado
    assert all(estimar_tokens(c.texto_para_embedding) <= TETO_DE_TOKENS for c in partes)


def test_paragrafo_sozinho_acima_do_teto_gera_erro():
    with pytest.raises(ValueError, match="acima do teto"):
        chunks_da_secao(_secao("palavra " * 400))


# As escalas 5x2 e 6x1 estão na mesma tabela da mesma seção (POL-RH-004#5). O filtro de público
# não separa as duas; quem separa é o prompt, e o eval mede isso (ADR-0004). strict=True: se o
# chunking passar a separar as escalas, o teste avisa para tirar a marcação.
_LIMITE_DAS_ESCALAS = pytest.mark.xfail(
    reason="5x2 e 6x1 dividem o mesmo chunk; a separação é feita pelo prompt", strict=True
)
_RESPONDIVEIS = [
    pytest.param(
        p,
        id=p["id"],
        marks=_LIMITE_DAS_ESCALAS if p["publico"] in ("operacao_5x2", "operacao_6x1") else (),
    )
    for p in GABARITO
    if p["fontes"]
]


@pytest.mark.parametrize("pergunta", _RESPONDIVEIS)
def test_publico_de_quem_pergunta_ve_os_fatos_e_nao_ve_os_proibidos(pergunta, chunks):
    """O filtro de público não pode esconder a resposta certa nem mostrar a de outro público."""
    publico = publico_do_usuario(pergunta["publico"])
    fontes = set(pergunta["fontes"])
    visiveis = [
        c
        for c in chunks
        if f"{c.secao.codigo}#{c.secao.numero}" in fontes
        and (publico is None or publico in c.publicos)
    ]
    texto = " ".join(" ".join(c.texto.split()) for c in visiveis)

    for fato in pergunta["fatos"]:
        assert fato in texto, f"fato escondido pelo filtro: {fato!r}"
    for proibido in pergunta["proibidos"]:
        assert proibido not in texto, f"regra de outro público visível: {proibido!r}"
