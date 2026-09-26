from pathlib import Path

import pytest

from rotasul_rh.leitor_docx import ler_docx

POLITICAS = Path(__file__).parent.parent / "data" / "politicas"
FERIAS = POLITICAS / "POL-RH-003_Politica_de_Ferias.docx"
BANCO_DE_HORAS = POLITICAS / "POL-RH-004_Politica_de_Banco_de_Horas.docx"


def test_le_metadados_do_cabecalho():
    secao = ler_docx(FERIAS)[0]

    assert secao.codigo == "POL-RH-003"
    assert secao.nome == "Férias"
    assert secao.versao == "4.0"
    assert secao.vigencia == "01/06/2026"
    assert secao.arquivo == FERIAS.name


def test_separa_as_secoes_pelos_titulos():
    secoes = ler_docx(FERIAS)

    assert [s.numero for s in secoes] == list(range(1, 12))
    assert secoes[4].titulo == "Fracionamento"
    assert secoes[4].fonte == "POL-RH-003, Férias, seção 5"


def test_itens_de_lista_viram_linhas_com_hifen():
    fracionamento = ler_docx(FERIAS)[4]

    assert "- um dos períodos tenha no mínimo 14 dias corridos;" in fracionamento.texto


def test_tabela_de_duas_colunas_vira_frases():
    direito_a_ferias = ler_docx(FERIAS)[2]

    assert (
        "Faltas injustificadas no período aquisitivo: De 6 a 14; Dias de férias: 24 dias corridos."
        in direito_a_ferias.texto
    )


def test_tabela_de_tres_colunas_mantem_cada_valor_com_sua_escala():
    operacao = ler_docx(BANCO_DE_HORAS)[4]

    assert "Situação: Trabalho no sábado; Escala 5x2 (segunda a sexta): Entra no banco" in (
        operacao.texto
    )


def test_tabela_fica_entre_os_paragrafos_da_sua_secao():
    direito_a_ferias = ler_docx(FERIAS)[2].texto

    tabela = direito_a_ferias.index("Até 5")
    assert direito_a_ferias.index("artigo 130 da CLT") < tabela
    assert tabela < direito_a_ferias.index("Faltas justificadas")


@pytest.mark.parametrize("arquivo", sorted(POLITICAS.glob("*.docx")), ids=lambda p: p.stem)
def test_todas_as_politicas_docx_sao_lidas(arquivo):
    secoes = ler_docx(arquivo)

    assert secoes
    assert all(s.codigo in arquivo.name for s in secoes)
    assert all(s.titulo and s.texto for s in secoes)
