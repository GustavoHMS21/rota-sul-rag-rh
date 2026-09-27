"""Públicos da Rota Sul e as regras para reconhecer a quem um trecho de política se aplica.

A regra é conservadora: um trecho só é restrito a um público quando o texto diz isso
explicitamente, no título da seção ("5. Operação (CDs de Jundiaí e Sumaré)") ou no começo do
parágrafo ("Administrativo (matriz): ..."). Todo o resto vale para todos.

Etiquetar políticas inteiras seria um erro: a seção "Quem pode" do Home Office precisa chegar a quem
é do CD, porque é ela que diz que a operação não é elegível.
"""

import re

ADMINISTRATIVO = "administrativo"
OPERACAO = "operacao"
MOTORISTA = "motorista"
TODOS = frozenset({ADMINISTRATIVO, OPERACAO, MOTORISTA})

# Como o texto das políticas nomeia cada público.
_NOMES = [
    (re.compile(r"^Administrativo\b"), ADMINISTRATIVO),
    (re.compile(r"^Operação\b"), OPERACAO),
    (re.compile(r"^Motoristas?\b"), MOTORISTA),
]
# "Administrativo (matriz): o colaborador..." -> o parágrafo inteiro é desse público.
_PREFIXO_DE_PARAGRAFO = re.compile(r"^(?P<nome>[^:()]+)(\([^)]*\))?\s*:")


def publico_do_usuario(publico: str | None) -> str | None:
    """Público de quem pergunta -> público dos chunks. As escalas 5x2 e 6x1 são da operação.

    A diferença entre 5x2 e 6x1 fica dentro da mesma seção (e do mesmo chunk), então quem separa
    as duas é o prompt, não o filtro.
    """
    if publico in (f"{OPERACAO}_5x2", f"{OPERACAO}_6x1"):
        return OPERACAO
    if publico is None or publico in TODOS:
        return publico
    raise ValueError(f"público desconhecido: {publico!r}")


def publico_do_titulo(titulo: str) -> str | None:
    """ "Operação (CDs de Jundiaí e Sumaré)" -> "operacao"; "Fracionamento" -> None."""
    return _publico_pelo_nome(titulo)


def publico_do_paragrafo(paragrafo: str) -> str | None:
    """ "Administrativo (matriz): ..." -> "administrativo"; parágrafo comum -> None."""
    prefixo = _PREFIXO_DE_PARAGRAFO.match(paragrafo)
    return _publico_pelo_nome(prefixo["nome"].strip()) if prefixo else None


def _publico_pelo_nome(texto: str) -> str | None:
    for padrao, publico in _NOMES:
        if padrao.match(texto):
            return publico
    return None
