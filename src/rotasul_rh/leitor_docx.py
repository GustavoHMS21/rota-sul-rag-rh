"""Leitura das políticas em formato docx.

Transforma um arquivo .docx numa lista de `Secao`, preservando o que o texto corrido perderia:
os títulos de seção (estilo "Título 1" do Word), as listas e as tabelas.
"""

import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from rotasul_rh.modelos import Secao

# "Código: POL-RH-003   |   Versão: 4.0   |   Vigência: 01/06/2026"
_CABECALHO = re.compile(
    r"Código:\s*(?P<codigo>POL-RH-\d{3}).*?"
    r"Versão:\s*(?P<versao>[\d.]+).*?"
    r"Vigência:\s*(?P<vigencia>\d{2}/\d{2}/\d{4})",
    re.DOTALL,
)
# "5. Fracionamento"
_TITULO_SECAO = re.compile(r"^(?P<numero>\d+)\.\s+(?P<titulo>.+)$")


def ler_docx(caminho: Path) -> list[Secao]:
    """Lê uma política .docx e devolve suas seções, na ordem do documento."""
    documento = Document(str(caminho))

    nome = ""
    cabecalho = None
    secoes_brutas: list[tuple[int, str, list[str]]] = []  # (número, título, blocos de texto)

    # iter_inner_content() percorre parágrafos e tabelas na ordem em que aparecem no arquivo.
    for bloco in documento.iter_inner_content():
        if isinstance(bloco, Table):
            if secoes_brutas:
                secoes_brutas[-1][2].append(_tabela_para_texto(bloco))
            continue

        texto = bloco.text.strip()
        if not texto:
            continue

        estilo = _estilo(bloco)
        if estilo == "Title":
            nome = texto.removeprefix("Política de ").strip()
        elif estilo.startswith("Heading"):
            titulo = _TITULO_SECAO.match(texto)
            if titulo is None:
                raise ValueError(f"{caminho.name}: título de seção sem número: {texto!r}")
            secoes_brutas.append((int(titulo["numero"]), titulo["titulo"], []))
        elif cabecalho is None and texto.startswith("Código:"):
            cabecalho = _CABECALHO.search(texto)
        elif secoes_brutas:
            # Itens de lista viram "- item", para o modelo enxergar a enumeração.
            linha = f"- {texto}" if estilo.startswith("List") else texto
            secoes_brutas[-1][2].append(linha)

    if not nome:
        raise ValueError(f"{caminho.name}: título da política não encontrado")
    if cabecalho is None:
        raise ValueError(f"{caminho.name}: cabeçalho com código, versão e vigência não encontrado")

    return [
        Secao(
            codigo=cabecalho["codigo"],
            nome=nome,
            versao=cabecalho["versao"],
            vigencia=cabecalho["vigencia"],
            numero=numero,
            titulo=titulo,
            texto="\n".join(blocos),
            arquivo=caminho.name,
        )
        for numero, titulo, blocos in secoes_brutas
    ]


def _estilo(paragrafo: Paragraph) -> str:
    """Nome interno do estilo ("Heading1", "ListBullet", "Title"...), igual em qualquer idioma."""
    return paragrafo.style.style_id if paragrafo.style is not None else ""


def _tabela_para_texto(tabela: Table) -> str:
    """Converte cada linha da tabela numa frase "cabeçalho: valor; cabeçalho: valor."

    Exemplo, na tabela de faltas da Política de Férias:
    "Faltas injustificadas no período aquisitivo: De 6 a 14; Dias de férias: 24 dias corridos."
    Assim cada valor fica junto do nome da sua coluna, e a informação não se perde no chunking.
    """
    linhas = [[celula.text.strip() for celula in linha.cells] for linha in tabela.rows]
    cabecalho, *dados = linhas
    frases = []
    for linha in dados:
        pares = zip(cabecalho, linha, strict=True)
        frases.append("; ".join(f"{coluna}: {valor}" for coluna, valor in pares) + ".")
    return "\n".join(frases)
