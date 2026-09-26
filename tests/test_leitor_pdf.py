from pathlib import Path

import pytest

from rotasul_rh.leitor_pdf import ler_pdf

POLITICAS = Path(__file__).parent.parent / "data" / "politicas"
BENEFICIOS = POLITICAS / "POL-RH-006_Politica_de_Beneficios.pdf"
ATESTADOS = POLITICAS / "POL-RH-008_Politica_de_Atestados_e_Faltas.pdf"


def test_le_metadados_do_cabecalho():
    secao = ler_pdf(BENEFICIOS)[0]

    assert secao.codigo == "POL-RH-006"
    assert secao.nome == "Benefícios"
    assert secao.versao == "5.0"
    assert secao.vigencia == "01/01/2026"


def test_separa_as_secoes_pelos_titulos_em_negrito():
    secoes = ler_pdf(BENEFICIOS)

    assert [s.numero for s in secoes] == list(range(1, 9))
    assert secoes[1].titulo == "Vale-refeição"
    assert secoes[1].fonte == "POL-RH-006, Benefícios, seção 2"


def test_descarta_cabecalho_e_rodape_das_paginas():
    texto = "\n".join(s.texto for s in ler_pdf(BENEFICIOS))

    assert "Recursos Humanos POL-RH-006" not in texto
    assert "Documento interno" not in texto
    assert "Página" not in texto


def test_junta_as_linhas_de_um_paragrafo_e_separa_paragrafos():
    vale_refeicao = ler_pdf(BENEFICIOS)[1].texto.split("\n")

    assert vale_refeicao[0] == (
        "Administrativo (matriz): R$ 38,00 por dia útil trabalhado, creditado no cartão até o "
        "último dia útil do mês anterior."
    )
    assert vale_refeicao[1].startswith("Operação (CDs):")


def test_itens_de_lista_viram_linhas_com_hifen():
    odontologico = ler_pdf(BENEFICIOS)[4].texto

    assert "- cônjuge ou companheiro(a);" in odontologico
    assert (
        "- filhos de 21 até 24 anos incompletos que estejam cursando ensino superior ou técnico, "
        "mediante comprovante de matrícula renovado a cada semestre."
    ) in odontologico


def test_secao_que_continua_na_pagina_seguinte_fica_inteira():
    inclusao = ler_pdf(BENEFICIOS)[5]

    assert inclusao.titulo == "Inclusão de dependentes"
    assert inclusao.texto.startswith("A inclusão é feita pelo formulário de benefícios")


def test_celula_quebrada_em_duas_linhas_fica_numa_frase_so():
    tabela = ler_pdf(BENEFICIOS)[7].texto

    assert (
        "Benefício: Coparticipação saúde; Titular: 30% por uso, até R$ 150,00 por mês; "
        "Por dependente: 30% por uso, somado ao limite do titular."
    ) in tabela


def test_texto_depois_da_tabela_continua_na_secao():
    tabela = ler_pdf(BENEFICIOS)[7].texto

    assert tabela.endswith("Valores válidos de 1º de janeiro a 31 de dezembro de 2026.")


def test_tabela_de_faltas_justificadas():
    faltas = ler_pdf(ATESTADOS)[3].texto

    assert "Motivo: Casamento; Dias sem desconto: Até 3 dias consecutivos." in faltas


@pytest.mark.parametrize("arquivo", sorted(POLITICAS.glob("*.pdf")), ids=lambda p: p.stem)
def test_todas_as_politicas_pdf_sao_lidas(arquivo):
    secoes = ler_pdf(arquivo)

    assert secoes
    assert [s.numero for s in secoes] == list(range(1, len(secoes) + 1))
    assert all(s.codigo in arquivo.name for s in secoes)
    assert all(s.titulo and s.texto for s in secoes)
