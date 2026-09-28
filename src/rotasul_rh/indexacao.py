"""Indexação: lê as políticas, gera os chunks e os embeddings e grava tudo no banco.

Uso: uv run python -m rotasul_rh.indexacao
"""

import hashlib
import time
from dataclasses import dataclass

from rotasul_rh.banco import conectar
from rotasul_rh.chunking import gerar_chunks
from rotasul_rh.config import Config, carregar_config
from rotasul_rh.embeddings import gerar_embeddings
from rotasul_rh.politicas import ler_politicas


@dataclass(frozen=True)
class ResultadoIndexacao:
    total: int  # chunks gravados
    gerados: int  # embeddings pedidos ao Ollama (o resto foi reaproveitado do banco)


def indexar(config: Config) -> ResultadoIndexacao:
    """Substitui todo o conteúdo da tabela pelos chunks atuais.

    Gerar embeddings na CPU é a parte lenta (cerca de 30 a 50 s para 57 chunks). Por isso, cada
    chunk guarda um hash do texto que gerou o seu vetor: se o texto e o modelo não mudaram, o vetor
    já gravado é reaproveitado e só o que mudou vai para o Ollama.

    Apagar e regravar numa única transação garante que rodar duas vezes não duplica nada, e que uma
    falha no meio não deixa o banco pela metade: ou tudo entra, ou nada muda.
    """
    chunks = gerar_chunks(ler_politicas())
    textos = [c.texto_para_embedding for c in chunks]
    hashes = [_hash_embedding(texto, config.embedding_model) for texto in textos]

    with conectar(config) as conexao:
        ja_gerados = dict(
            conexao.execute(
                "SELECT hash_embedding, embedding FROM chunks WHERE hash_embedding IS NOT NULL"
            ).fetchall()
        )

        # {hash: texto} só dos chunks sem vetor reaproveitável.
        faltando = {h: t for t, h in zip(textos, hashes, strict=True) if h not in ja_gerados}
        if faltando:
            novos = gerar_embeddings(list(faltando.values()), config)
            ja_gerados.update(zip(faltando.keys(), novos, strict=True))

        linhas = [
            (
                c.id,
                c.secao.codigo,
                c.secao.nome,
                c.secao.versao,
                c.secao.vigencia,
                c.secao.numero,
                c.secao.titulo,
                sorted(c.publicos),
                c.texto,
                c.secao.arquivo,
                ja_gerados[hash_],
                hash_,
            )
            for c, hash_ in zip(chunks, hashes, strict=True)
        ]

        with conexao.transaction():
            conexao.execute("DELETE FROM chunks")
            with conexao.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO chunks (id, codigo, nome, versao, vigencia, secao, titulo,
                                        publicos, texto, arquivo, embedding, hash_embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    linhas,
                )
    return ResultadoIndexacao(total=len(linhas), gerados=len(faltando))


def _hash_embedding(texto: str, modelo: str) -> str:
    """O modelo entra no hash: trocar de modelo invalida todos os vetores (não são comparáveis)."""
    return hashlib.sha256(f"{modelo}\n{texto}".encode()).hexdigest()


if __name__ == "__main__":
    inicio = time.perf_counter()
    resultado = indexar(carregar_config())
    reaproveitados = resultado.total - resultado.gerados
    print(
        f"{resultado.total} chunks indexados em {time.perf_counter() - inicio:.1f} s "
        f"({resultado.gerados} embeddings gerados, {reaproveitados} reaproveitados)"
    )
