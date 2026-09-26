"""Leitura das políticas em formato pdf.

O PDF não guarda parágrafos nem estilos, só a posição e a fonte de cada letra. Este leitor usa o
pdfplumber para reconstruir a estrutura a partir dessas informações:

- título da seção: linha em negrito, tamanho 13, começando por "número. ";
- parágrafo: linhas seguidas com pouco espaço entre si (4,5 pt; entre parágrafos, 10,5 pt);
- item de lista: linha que começa com o marcador;
- tabela: reconhecida pelas bordas desenhadas;
- cabeçalho e rodapé repetidos em toda página: descartados pela posição.
"""

from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page

from rotasul_rh.leitura_comum import (
    CABECALHO,
    TITULO_SECAO,
    SecaoBruta,
    montar_secoes,
    nome_da_politica,
    tabela_para_texto,
)
from rotasul_rh.modelos import Secao

# Faixa, em pontos, no topo e no pé da página onde ficam cabeçalho e rodapé (página A4 = 842 pt).
_MARGEM = 60
# Espaço vertical acima do qual uma linha começa um novo parágrafo.
_ESPACO_ENTRE_PARAGRAFOS = 7
_TAMANHO_TITULO_POLITICA = 18
_TAMANHO_TITULO_SECAO = 12
# O marcador de lista não tem caractere equivalente no PDF, e o pdfplumber o devolve assim.
_MARCADOR = "(cid:127)"
_FIM_DE_FRASE = (".", ":", ";", "!", "?")


@dataclass(frozen=True)
class _Linha:
    texto: str
    topo: float
    base: float
    negrito: bool
    tamanho: float


def ler_pdf(caminho: Path) -> list[Secao]:
    """Lê uma política .pdf e devolve suas seções, na ordem do documento."""
    nome = ""
    cabecalho = None
    secoes_brutas: list[SecaoBruta] = []

    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            # Base (parte de baixo) da linha anterior, para medir o espaço até a linha atual.
            # Começa vazia em cada página e depois de cada tabela.
            base_anterior: float | None = None

            for item in _itens_da_pagina(pagina):
                if isinstance(item, list):  # tabela
                    if secoes_brutas:
                        secoes_brutas[-1][2].append(tabela_para_texto(item))
                    base_anterior = None
                    continue

                linha = item
                titulo = TITULO_SECAO.match(linha.texto)
                if linha.negrito and linha.tamanho >= _TAMANHO_TITULO_POLITICA:
                    nome = nome_da_politica(linha.texto)
                elif linha.negrito and linha.tamanho >= _TAMANHO_TITULO_SECAO and titulo:
                    secoes_brutas.append((int(titulo["numero"]), titulo["titulo"], []))
                elif cabecalho is None and linha.texto.startswith("Código:"):
                    cabecalho = CABECALHO.search(linha.texto)
                elif secoes_brutas:
                    _adicionar_linha(secoes_brutas[-1][2], linha, base_anterior)

                base_anterior = linha.base

    return montar_secoes(caminho, nome, cabecalho, secoes_brutas)


def _itens_da_pagina(pagina: Page) -> list[_Linha | list[list[str]]]:
    """Linhas de texto e tabelas da página, de cima para baixo, sem cabeçalho e rodapé."""
    tabelas = pagina.find_tables()
    itens: list[tuple[float, _Linha | list[list[str]]]] = [
        (tabela.bbox[1], tabela.extract()) for tabela in tabelas
    ]

    for bruta in pagina.extract_text_lines():
        topo, base = bruta["top"], bruta["bottom"]
        if topo < _MARGEM or topo > pagina.height - _MARGEM:
            continue  # cabeçalho ou rodapé
        if any(t.bbox[1] <= topo and base <= t.bbox[3] for t in tabelas):
            continue  # texto de dentro da tabela, que já entrou pela própria tabela

        primeira_letra = bruta["chars"][0]
        linha = _Linha(
            texto=bruta["text"].strip(),
            topo=topo,
            base=base,
            negrito="Bold" in primeira_letra["fontname"],
            tamanho=primeira_letra["size"],
        )
        itens.append((topo, linha))

    itens.sort(key=lambda par: par[0])
    return [item for _, item in itens]


def _adicionar_linha(blocos: list[str], linha: _Linha, base_anterior: float | None) -> None:
    """Junta a linha ao parágrafo anterior ou começa um bloco novo (parágrafo ou item de lista)."""
    if linha.texto.startswith(_MARCADOR):
        blocos.append("- " + linha.texto.removeprefix(_MARCADOR).strip())
    elif _continua_bloco_anterior(blocos, linha, base_anterior):
        blocos[-1] = f"{blocos[-1]} {linha.texto}"
    else:
        blocos.append(linha.texto)


def _continua_bloco_anterior(blocos: list[str], linha: _Linha, base_anterior: float | None) -> bool:
    if not blocos:
        return False
    if base_anterior is None:
        # Primeira linha da página: continua o parágrafo que ficou sem terminar na página anterior.
        return not blocos[-1].endswith(_FIM_DE_FRASE)
    return linha.topo - base_anterior < _ESPACO_ENTRE_PARAGRAFOS
