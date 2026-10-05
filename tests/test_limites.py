"""Testes do limite de requisições, com um relógio falso (nenhum teste espera de verdade)."""

import threading

import pytest

from rotasul_rh.limites import Limitador, Regra


class Relogio:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += segundos


@pytest.fixture
def relogio():
    return Relogio()


def test_aceita_ate_o_maximo_e_diz_quanto_esperar(relogio):
    limitador = Limitador([Regra(3, 60)], relogio)

    assert [limitador.tentar("ip") for _ in range(3)] == [None, None, None]
    relogio.avancar(10)

    assert limitador.tentar("ip") == pytest.approx(50)  # a 1ª sai da janela em 60 - 10 s


def test_janela_deslizante_libera_quando_a_mais_antiga_sai(relogio):
    limitador = Limitador([Regra(2, 60)], relogio)
    limitador.tentar("ip")
    relogio.avancar(30)
    limitador.tentar("ip")

    relogio.avancar(29)
    assert limitador.tentar("ip") is not None
    relogio.avancar(1)  # 60 s depois da 1ª
    assert limitador.tentar("ip") is None


def test_vale_a_regra_mais_restritiva(relogio):
    limitador = Limitador([Regra(10, 60), Regra(12, 3600)], relogio)
    for _ in range(10):
        limitador.tentar("ip")
    relogio.avancar(60)
    assert limitador.tentar("ip") is None
    assert limitador.tentar("ip") is None

    # 12 na hora: o minuto já liberou, mas a hora não.
    assert limitador.tentar("ip") == pytest.approx(3600 - 60)


def test_requisicao_barrada_nao_conta(relogio):
    limitador = Limitador([Regra(1, 60)], relogio)
    limitador.tentar("ip")
    for _ in range(50):
        limitador.tentar("ip")  # insistir não estende o bloqueio

    relogio.avancar(60)
    assert limitador.tentar("ip") is None


def test_cada_chave_tem_a_sua_conta(relogio):
    limitador = Limitador([Regra(1, 60)], relogio)

    assert limitador.tentar("10.0.0.1") is None
    assert limitador.tentar("10.0.0.2") is None
    assert limitador.tentar("10.0.0.1") is not None


def test_consultar_nao_conta_e_registrar_conta(relogio):
    limitador = Limitador([Regra(2, 900)], relogio)

    assert limitador.espera("ip") is None
    limitador.registrar("ip")
    assert limitador.espera("ip") is None
    limitador.registrar("ip")
    assert limitador.espera("ip") == pytest.approx(900)


def test_chaves_antigas_sao_esquecidas(relogio):
    limitador = Limitador([Regra(5, 60)], relogio)
    for indice in range(100):
        limitador.tentar(f"10.0.0.{indice}")

    relogio.avancar(120)
    limitador.tentar("10.0.1.1")

    assert list(limitador._horarios) == ["10.0.1.1"]


def test_requisicoes_simultaneas_nao_passam_do_maximo():
    limitador = Limitador([Regra(10, 60)])
    largada = threading.Barrier(30)
    aceitas = []

    def requisicao():
        largada.wait()
        if limitador.tentar("ip") is None:
            aceitas.append(1)

    threads = [threading.Thread(target=requisicao) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(aceitas) == 10
