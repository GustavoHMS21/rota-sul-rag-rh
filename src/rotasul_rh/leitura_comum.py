"""Regras de leitura compartilhadas pelos leitores de docx e de pdf."""

import re
from pathlib import Path

from rotasul_rh.modelos import Secao

# Seção ainda em montagem: (número, título, blocos de texto: parágrafos, itens de lista e tabelas).
SecaoBruta = tuple[int, str, list[str]]

# "Código: POL-RH-003   |   Versão: 4.0   |   Vigência: 01/06/2026"
CABECALHO = re.compile(
    r"Código:\s*(?P<codigo>POL-RH-\d{3}).*?"
    r"Versão:\s*(?P<versao>[\d.]+).*?"
    r"Vigência:\s*(?P<vigencia>\d{2}/\d{2}/\d{4})",
    re.DOTALL,
)
# "5. Fracionamento"
TITULO_SECAO = re.compile(r"^(?P<numero>\d+)\.\s+(?P<titulo>.+)$")


def nome_da_politica(titulo: str) -> str:
    """ "Política de Férias" -> "Férias"."""
    return titulo.removeprefix("Política de ").strip()


def montar_secoes(
    caminho: Path, nome: str, cabecalho: re.Match[str] | None, secoes_brutas: list[SecaoBruta]
) -> list[Secao]:
    """Valida o que o leitor encontrou e transforma as seções brutas em `Secao`."""
    if not nome:
        raise ValueError(f"{caminho.name}: título da política não encontrado")
    if cabecalho is None:
        raise ValueError(f"{caminho.name}: cabeçalho com código, versão e vigência não encontrado")
    if not secoes_brutas:
        raise ValueError(f"{caminho.name}: nenhuma seção numerada encontrada")

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


def tabela_para_texto(linhas: list[list[str]]) -> str:
    """Converte cada linha da tabela numa frase "cabeçalho: valor; cabeçalho: valor."

    Exemplo, na tabela de faltas da Política de Férias:
    "Faltas injustificadas no período aquisitivo: De 6 a 14; Dias de férias: 24 dias corridos."
    Assim cada valor fica junto do nome da sua coluna, e a informação não se perde no chunking.
    A primeira linha é o cabeçalho. Quebras de linha dentro da célula viram espaço.
    """
    limpas = [[" ".join(celula.split()) for celula in linha] for linha in linhas]
    cabecalho, *dados = limpas
    frases = []
    for linha in dados:
        pares = zip(cabecalho, linha, strict=True)
        frases.append("; ".join(f"{coluna}: {valor}" for coluna, valor in pares) + ".")
    return "\n".join(frases)
