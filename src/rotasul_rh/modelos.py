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


@dataclass(frozen=True)
class Chunk:
    """Pedaço de uma seção que vira um vetor no banco.

    Normalmente é a seção inteira. Ela só é dividida quando tem parágrafos de públicos diferentes
    ou quando passa do teto de tokens.
    """

    id: str  # ex.: "POL-RH-003#6-administrativo"
    secao: Secao
    texto: str  # conteúdo do chunk, sem o cabeçalho
    publicos: frozenset[str]  # a quem a regra se aplica: "administrativo", "operacao", "motorista"

    @property
    def cabecalho(self) -> str:
        """Contexto que vai na frente do texto no embedding, para o vetor saber de onde ele vem."""
        s = self.secao
        return f"Política de {s.nome} ({s.codigo}) | Seção {s.numero}: {s.titulo}"

    @property
    def texto_para_embedding(self) -> str:
        return f"{self.cabecalho}\n{self.texto}"
