"""Leitura das políticas em formato docx.

Transforma um arquivo .docx numa lista de `Secao`, preservando o que o texto corrido perderia:
os títulos de seção (estilo "Título 1" do Word), as listas e as tabelas.
"""

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from rotasul_rh.leitura_comum import (
    CABECALHO,
    TITULO_SECAO,
    SecaoBruta,
    montar_secoes,
    nome_da_politica,
    tabela_para_texto,
)
from rotasul_rh.modelos import Secao


def ler_docx(caminho: Path) -> list[Secao]:
    """Lê uma política .docx e devolve suas seções, na ordem do documento."""
    documento = Document(str(caminho))

    nome = ""
    cabecalho = None
    secoes_brutas: list[SecaoBruta] = []

    # iter_inner_content() percorre parágrafos e tabelas na ordem em que aparecem no arquivo.
    for bloco in documento.iter_inner_content():
        if isinstance(bloco, Table):
            if secoes_brutas:
                linhas = [[celula.text for celula in linha.cells] for linha in bloco.rows]
                secoes_brutas[-1][2].append(tabela_para_texto(linhas))
            continue

        texto = bloco.text.strip()
        if not texto:
            continue

        estilo = _estilo(bloco)
        if estilo == "Title":
            nome = nome_da_politica(texto)
        elif estilo.startswith("Heading"):
            titulo = TITULO_SECAO.match(texto)
            if titulo is None:
                raise ValueError(f"{caminho.name}: título de seção sem número: {texto!r}")
            secoes_brutas.append((int(titulo["numero"]), titulo["titulo"], []))
        elif cabecalho is None and texto.startswith("Código:"):
            cabecalho = CABECALHO.search(texto)
        elif secoes_brutas:
            # Itens de lista viram "- item", para o modelo enxergar a enumeração.
            linha = f"- {texto}" if estilo.startswith("List") else texto
            secoes_brutas[-1][2].append(linha)

    return montar_secoes(caminho, nome, cabecalho, secoes_brutas)


def _estilo(paragrafo: Paragraph) -> str:
    """Nome interno do estilo ("Heading1", "ListBullet", "Title"...), igual em qualquer idioma."""
    return paragrafo.style.style_id if paragrafo.style is not None else ""
