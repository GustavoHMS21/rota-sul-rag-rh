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
    publicos: list[str]
    similaridade: float  # de -1 a 1; quanto maior, mais parecido

    @property
    def fonte(self) -> str:
        return f"{self.codigo}, {self.nome}, seção {self.secao}"


# <=> é a distância de cosseno do pgvector (0 = mesma direção). Similaridade = 1 - distância.
# Público nulo (não informado) desliga o filtro; senão, só entram chunks daquele público.
_CONSULTA = """
SELECT id, codigo, nome, secao, titulo, texto, publicos,
       1 - (embedding <=> %(vetor)s::vector) AS similaridade
FROM chunks
WHERE %(publico)s::text IS NULL OR %(publico)s = ANY(publicos)
ORDER BY embedding <=> %(vetor)s::vector
LIMIT %(k)s
"""


# 5 trechos: na avaliação, a seção certa estava entre os 5 primeiros em 100% das perguntas do
# gabarito (97% entre os 3 primeiros). Ver ADR-0007.
K_PADRAO = 5


def buscar(
    pergunta: str, publico: str | None, config: Config, k: int = K_PADRAO
) -> list[Resultado]:
    """Os k chunks mais parecidos com a pergunta que valem para o público de quem pergunta.

    `publico` é o público da tela ("administrativo", "operacao_5x2", ...) ou None (não informado).
    """
    vetor = gerar_embedding(pergunta, config)
    parametros = {"vetor": vetor, "publico": publico_do_usuario(publico), "k": k}
    with conectar(config) as conexao:
        linhas = conexao.execute(_CONSULTA, parametros).fetchall()
    return [Resultado(*linha) for linha in linhas]


# Seções que dizem quem tem direito à política inteira. Elas só aparecem na busca quando a
# pergunta fala de "quem" ("Trabalho no CD, posso..."); numa pergunta curta ("Posso fazer home
# office?"), o modelo recebia só "Como funciona" e respondia "sim" para quem não é elegível.
TITULOS_DE_ELEGIBILIDADE = ["Quem pode", "Abrangência", "Quem recebe"]

_CONSULTA_ELEGIBILIDADE = """
SELECT id, codigo, nome, secao, titulo, texto, publicos,
       1 - (embedding <=> %(vetor)s::vector) AS similaridade
FROM chunks
WHERE codigo = ANY(%(codigos)s)
  AND titulo = ANY(%(titulos)s)
  AND (%(publico)s::text IS NULL OR %(publico)s = ANY(publicos))
ORDER BY codigo, secao
"""


def buscar_contexto(
    pergunta: str, publico: str | None, config: Config, k: int = K_PADRAO
) -> list[Resultado]:
    """Trechos enviados ao modelo: a busca normal mais a seção de elegibilidade de cada política
    encontrada (expansão de contexto, ADR-0007). As seções de elegibilidade vêm primeiro, para o
    modelo ler quem tem direito antes de ler como a regra funciona.
    """
    vetor = gerar_embedding(pergunta, config)
    publico_dos_chunks = publico_do_usuario(publico)
    with conectar(config) as conexao:
        encontrados = [
            Resultado(*linha)
            for linha in conexao.execute(
                _CONSULTA, {"vetor": vetor, "publico": publico_dos_chunks, "k": k}
            ).fetchall()
        ]
        codigos = list(dict.fromkeys(r.codigo for r in encontrados))
        elegibilidade = [
            Resultado(*linha)
            for linha in conexao.execute(
                _CONSULTA_ELEGIBILIDADE,
                {
                    "vetor": vetor,
                    "codigos": codigos,
                    "titulos": TITULOS_DE_ELEGIBILIDADE,
                    "publico": publico_dos_chunks,
                },
            ).fetchall()
        ]

    ids_de_elegibilidade = {r.id for r in elegibilidade}
    return elegibilidade + [r for r in encontrados if r.id not in ids_de_elegibilidade]


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("pergunta")
    argumentos.add_argument("--publico", default=None)
    argumentos.add_argument("-k", type=int, default=K_PADRAO)
    entrada = argumentos.parse_args()

    for resultado in buscar(entrada.pergunta, entrada.publico, carregar_config(), entrada.k):
        print(f"{resultado.similaridade:.3f}  {resultado.id}  ({resultado.titulo})")
