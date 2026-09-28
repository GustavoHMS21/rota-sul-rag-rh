import pytest

from rotasul_rh.banco import conectar
from rotasul_rh.busca import Resultado
from rotasul_rh.config import carregar_config
from rotasul_rh.geracao import Resposta
from rotasul_rh.registro import avaliar, listar, mascarar_dados_pessoais, registrar, resumir


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Meu CPF é 123.456.789-00", "Meu CPF é [CPF]"),
        ("cpf 12345678900", "cpf [CPF]"),
        ("escreva para joao.silva@rotasul.com.br", "escreva para [E-MAIL]"),
        ("ligue (19) 99876-5432", "ligue [TELEFONE]"),
        ("fixo 19 3232-1010", "fixo [TELEFONE]"),
        ("+55 19 998765432", "[TELEFONE]"),
    ],
)
def test_mascara_dados_pessoais(texto, esperado):
    assert mascarar_dados_pessoais(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Tive 10 faltas, tenho direito a 24 dias?",
        "O vale-alimentação é R$ 450,00?",
        "A Lei nº 13.103/2015 vale para mim?",
        "Minhas férias começam em 20/12/2026.",
        "No sábado é 1 para 1,5?",
    ],
)
def test_nao_mascara_numeros_comuns_das_politicas(texto):
    assert mascarar_dados_pessoais(texto) == texto


def test_mascara_a_mais_no_formato_de_telefone_fixo():
    """Números no formato 0000-0000 são mascarados mesmo sem ser telefone. Mascarar a mais é o
    erro mais seguro para a LGPD (ADR-0008)."""
    assert mascarar_dados_pessoais("Protocolo 2026-0001") == "Protocolo [TELEFONE]"


@pytest.mark.integracao
def test_registra_anonimo_mascarado_e_avalia():
    config = carregar_config()
    trecho = Resultado("POL-RH-003#8", "POL-RH-003", "Férias", 8, "Abono", "x", ["operacao"], 0.6)
    resposta = Resposta(
        "respondida", "Sim.", ["POL-RH-003, Férias, seção 8"], ["POL-RH-003#8"], [trecho]
    )

    id_ = registrar(
        "Meu CPF é 123.456.789-00, posso vender férias?", "operacao_6x1", resposta, 900, config
    )
    try:
        registrada = next(i for i in listar(config, "respondida", 500) if i.id == id_)
        assert registrada.pergunta == "Meu CPF é [CPF], posso vender férias?"
        assert registrada.fontes == ["POL-RH-003#8"]
        assert registrada.avaliacao_util is None

        assert avaliar(id_, False, config)
        assert next(i for i in listar(config, None, 500) if i.id == id_).avaliacao_util is False
        assert resumir(config)["avaliacoes_nao_uteis"] >= 1
    finally:
        # Não deixa linhas de teste na área do RH.
        with conectar(config) as conexao:
            conexao.execute("DELETE FROM interacoes WHERE id = %s", (id_,))
            conexao.commit()
