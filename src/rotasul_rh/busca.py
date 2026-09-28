"""Busca semântica: os chunks mais parecidos com a pergunta, filtrados pelo público.

Uso: uv run python -m rotasul_rh.busca "Posso vender minhas férias?" --publico administrativo
"""

import argparse
from dataclasses import dataclass

from rotasul_rh.banco import conectar
from rotasul_rh.config import Config, carregar_config
from rotasul_rh.embeddings import gerar_embedding
from rotasul_rh.publico import publico_do_usuario


@dataclass(frozen=True)
class Resultado:
    id: str
    codigo: str
    nome: str
    secao: int
    titulo: str
    texto: str
    similaridade: float  # de -1 a 1; quanto maior, mais parecido

    @property
    def fonte(self) -> str:
        return f"{self.codigo}, {self.nome}, seção {self.secao}"


# <=> é a distância de cosseno do pgvector (0 = mesma direção). Similaridade = 1 - distância.
# Público nulo (não informado) desliga o filtro; senão, só entram chunks daquele público.
_CONSULTA = """
SELECT id, codigo, nome, secao, titulo, texto, 1 - (embedding <=> %(vetor)s::vector) AS similaridade
FROM chunks
WHERE %(publico)s::text IS NULL OR %(publico)s = ANY(publicos)
ORDER BY embedding <=> %(vetor)s::vector
LIMIT %(k)s
"""


def buscar(pergunta: str, publico: str | None, config: Config, k: int = 3) -> list[Resultado]:
    """Os k chunks mais parecidos com a pergunta que valem para o público de quem pergunta.

    `publico` é o público da tela ("administrativo", "operacao_5x2", ...) ou None (não informado).
    """
    vetor = gerar_embedding(pergunta, config)
    parametros = {"vetor": vetor, "publico": publico_do_usuario(publico), "k": k}
    with conectar(config) as conexao:
        linhas = conexao.execute(_CONSULTA, parametros).fetchall()
    return [Resultado(*linha) for linha in linhas]


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("pergunta")
    argumentos.add_argument("--publico", default=None)
    argumentos.add_argument("-k", type=int, default=3)
    entrada = argumentos.parse_args()

    for resultado in buscar(entrada.pergunta, entrada.publico, carregar_config(), entrada.k):
        print(f"{resultado.similaridade:.3f}  {resultado.id}  ({resultado.titulo})")
