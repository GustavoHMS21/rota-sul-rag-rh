import pytest

from rotasul_rh.idempotencia import ChaveEmAndamento, ChaveReutilizada, Idempotencia

CORPO = {"pergunta": "Posso vender férias?", "publico": "administrativo"}


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


def test_chave_nova_processa_e_o_reenvio_recebe_a_resposta_guardada():
    idempotencia = Idempotencia()

    assert idempotencia.iniciar("chave-1", CORPO) is None
    idempotencia.concluir("chave-1", "resposta")

    assert idempotencia.iniciar("chave-1", dict(CORPO)) == "resposta"


def test_reenvio_durante_o_processamento_recebe_em_andamento():
    idempotencia = Idempotencia()
    idempotencia.iniciar("chave-1", CORPO)

    with pytest.raises(ChaveEmAndamento):
        idempotencia.iniciar("chave-1", CORPO)


def test_mesma_chave_com_outra_pergunta_e_recusada():
    idempotencia = Idempotencia()
    idempotencia.iniciar("chave-1", CORPO)
    idempotencia.concluir("chave-1", "resposta")

    with pytest.raises(ChaveReutilizada):
        idempotencia.iniciar("chave-1", {**CORPO, "publico": "motorista"})


def test_falha_libera_a_chave_para_um_reenvio_de_verdade():
    idempotencia = Idempotencia()
    idempotencia.iniciar("chave-1", CORPO)

    idempotencia.desistir("chave-1")

    assert idempotencia.iniciar("chave-1", CORPO) is None


def test_chave_vence_depois_da_validade():
    relogio = Relogio()
    idempotencia = Idempotencia(validade_segundos=600, relogio=relogio)
    idempotencia.iniciar("chave-1", CORPO)
    idempotencia.concluir("chave-1", "resposta")

    relogio.agora = 600

    assert idempotencia.iniciar("chave-1", CORPO) is None  # tratada como nova
