"""Divisão das seções em chunks, com etiqueta de público.

Regras (ver docs/adr/0004-chunking-por-secao-e-publico.md):

1. Cada seção vira um chunk.
2. Se o título da seção é de um público ("5. Operação (CDs...)"), o chunk é só desse público.
3. Se a seção tem parágrafos que começam com um público ("Administrativo (matriz): ..."), ela vira
   um chunk por público citado, cada um com os seus parágrafos e os parágrafos gerais. Os públicos
   não citados recebem um chunk só com os parágrafos gerais.
4. Se um chunk passar do teto de tokens, ele é dividido entre parágrafos, sem cortar nenhum.
"""

import math
from collections.abc import Iterable

from rotasul_rh.modelos import Chunk, Secao
from rotasul_rh.publico import TODOS, publico_do_paragrafo, publico_do_titulo

TETO_DE_TOKENS = 512
# Estimativa de tokens do bge-m3 por caractere. Medido nos chunks das políticas: média 0,27 e pior
# caso 0,364 (seções com tabelas, números e "R$"). Por caractere varia menos que por palavra
# (de 1,36 a 2,44 tokens por palavra). O valor exato só existe no embedding; aqui basta nunca
# subestimar.
TOKENS_POR_CARACTERE = 0.4


def gerar_chunks(secoes: Iterable[Secao]) -> list[Chunk]:
    return [chunk for secao in secoes for chunk in chunks_da_secao(secao)]


def chunks_da_secao(secao: Secao) -> list[Chunk]:
    base = f"{secao.codigo}#{secao.numero}"
    paragrafos = secao.texto.split("\n")

    chunks = []
    for sufixo, publicos, linhas in _partes_por_publico(secao, paragrafos):
        partes = _dividir_pelo_teto(secao, linhas)
        for i, parte in enumerate(partes, start=1):
            id_ = base + sufixo + (f"-parte{i}" if len(partes) > 1 else "")
            chunks.append(Chunk(id=id_, secao=secao, texto="\n".join(parte), publicos=publicos))
    return chunks


def estimar_tokens(texto: str) -> int:
    return math.ceil(len(texto) * TOKENS_POR_CARACTERE)


def _partes_por_publico(
    secao: Secao, paragrafos: list[str]
) -> list[tuple[str, frozenset[str], list[str]]]:
    """Devolve (sufixo do id, públicos, parágrafos) para cada chunk da seção."""
    publico_da_secao = publico_do_titulo(secao.titulo)
    if publico_da_secao:
        return [("", frozenset({publico_da_secao}), paragrafos)]

    publico_de = [publico_do_paragrafo(p) for p in paragrafos]
    citados = list(dict.fromkeys(p for p in publico_de if p))  # sem repetir, na ordem do texto
    if not citados:
        return [("", TODOS, paragrafos)]

    partes = []
    for publico in citados:
        linhas = [
            p for p, dono in zip(paragrafos, publico_de, strict=True) if dono in (None, publico)
        ]
        partes.append((f"-{publico}", frozenset({publico}), linhas))

    gerais = [p for p, dono in zip(paragrafos, publico_de, strict=True) if dono is None]
    nao_citados = TODOS - set(citados)
    if gerais and nao_citados:
        partes.append(("-geral", frozenset(nao_citados), gerais))
    return partes


def _dividir_pelo_teto(secao: Secao, paragrafos: list[str]) -> list[list[str]]:
    """Agrupa parágrafos em partes que, com o cabeçalho, cabem no teto de tokens."""
    # O cabeçalho entra em todas as partes; usa um chunk de exemplo para medir o tamanho dele.
    cabecalho = Chunk(id="", secao=secao, texto="", publicos=TODOS).cabecalho
    disponivel = TETO_DE_TOKENS - estimar_tokens(cabecalho)

    partes: list[list[str]] = [[]]
    usados = 0
    for paragrafo in paragrafos:
        tokens = estimar_tokens(paragrafo)
        if tokens > disponivel:
            raise ValueError(
                f"{secao.codigo}#{secao.numero}: um único parágrafo tem cerca de {tokens} tokens, "
                f"acima do teto de {TETO_DE_TOKENS}. Divida o parágrafo ou revise o teto."
            )
        if partes[-1] and usados + tokens > disponivel:
            partes.append([])
            usados = 0
        partes[-1].append(paragrafo)
        usados += tokens
    return partes
