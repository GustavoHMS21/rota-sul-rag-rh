"""Estruturas de dados compartilhadas pelos leitores de políticas."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Secao:
    """Uma seção numerada de uma política, com o texto já limpo.

    É a unidade que sai da leitura dos documentos. As etapas seguintes (público, chunking e
    embeddings) partem daqui.
    """

    codigo: str  # ex.: "POL-RH-003"
    nome: str  # ex.: "Férias"
    versao: str  # ex.: "4.0"
    vigencia: str  # ex.: "01/06/2026"
    numero: int  # ex.: 5
    titulo: str  # ex.: "Fracionamento"
    texto: str
    arquivo: str  # nome do arquivo de origem

    @property
    def fonte(self) -> str:
        """Referência usada na citação da resposta: "POL-RH-003, Férias, seção 5"."""
        return f"{self.codigo}, {self.nome}, seção {self.numero}"
