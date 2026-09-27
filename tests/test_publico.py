import pytest

from rotasul_rh.publico import (
    ADMINISTRATIVO,
    MOTORISTA,
    OPERACAO,
    publico_do_paragrafo,
    publico_do_titulo,
    publico_do_usuario,
)


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("Administrativo (matriz em Campinas)", ADMINISTRATIVO),
        ("Operação (CDs de Jundiaí e Sumaré)", OPERACAO),
        ("Motoristas", MOTORISTA),
        ("Fracionamento", None),
        ("Quem pode", None),
    ],
)
def test_publico_do_titulo(titulo, esperado):
    assert publico_do_titulo(titulo) == esperado


@pytest.mark.parametrize(
    ("paragrafo", "esperado"),
    [
        ("Administrativo (matriz): o colaborador combina as datas.", ADMINISTRATIVO),
        ("Operação (CDs de Jundiaí e Sumaré): a escala anual.", OPERACAO),
        ("Operação (CDs): refeição servida no refeitório.", OPERACAO),
        # Começam com "rótulo:", mas não são públicos.
        ("Operadora: VidaPlena Saúde.", None),
        ("Motivo: Casamento; Dias sem desconto: Até 3 dias consecutivos.", None),
        ("Saldo máximo positivo: 40 horas.", None),
        # Cita um público no meio do texto, sem ser o dono do parágrafo.
        ("A empresa pode conceder férias coletivas ao administrativo da matriz.", None),
    ],
)
def test_publico_do_paragrafo(paragrafo, esperado):
    assert publico_do_paragrafo(paragrafo) == esperado


@pytest.mark.parametrize(
    ("usuario", "esperado"),
    [
        ("operacao_5x2", OPERACAO),
        ("operacao_6x1", OPERACAO),
        ("administrativo", ADMINISTRATIVO),
        (None, None),
    ],
)
def test_publico_do_usuario(usuario, esperado):
    assert publico_do_usuario(usuario) == esperado


def test_publico_do_usuario_desconhecido():
    with pytest.raises(ValueError):
        publico_do_usuario("diretoria")
