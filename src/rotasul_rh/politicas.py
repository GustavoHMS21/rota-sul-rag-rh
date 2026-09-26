"""Ponto de entrada da leitura: escolhe o leitor pelo formato do arquivo."""

from pathlib import Path

from rotasul_rh.leitor_docx import ler_docx
from rotasul_rh.leitor_pdf import ler_pdf
from rotasul_rh.modelos import Secao

PASTA_POLITICAS = Path(__file__).parents[2] / "data" / "politicas"

_LEITORES = {".docx": ler_docx, ".pdf": ler_pdf}


def ler_politica(caminho: Path) -> list[Secao]:
    """Lê uma política em qualquer formato suportado."""
    leitor = _LEITORES.get(caminho.suffix.lower())
    if leitor is None:
        raise ValueError(f"{caminho.name}: formato não suportado ({caminho.suffix})")
    return leitor(caminho)


def ler_politicas(pasta: Path = PASTA_POLITICAS) -> list[Secao]:
    """Lê todas as políticas da pasta, em ordem de código."""
    arquivos = sorted(p for p in pasta.iterdir() if p.suffix.lower() in _LEITORES)
    return [secao for arquivo in arquivos for secao in ler_politica(arquivo)]
