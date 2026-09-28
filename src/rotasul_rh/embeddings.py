"""Geração de embeddings com o bge-m3 rodando no Ollama."""

import httpx

from rotasul_rh.config import Config

DIMENSAO = 1024  # tamanho do vetor do bge-m3
# Indexar os 57 chunks num lote leva cerca de 50 s na CPU; a folga cobre máquinas mais lentas.
_TIMEOUT_SEGUNDOS = 600


class ErroEmbedding(RuntimeError):
    pass


def gerar_embeddings(textos: list[str], config: Config) -> list[list[float]]:
    """Devolve um vetor por texto, na mesma ordem.

    `truncate: False` faz o Ollama recusar um texto maior que o contexto do modelo, em vez de
    cortar o final em silêncio (e deixar esse final fora do vetor).

    `keep_alive` diz ao Ollama por quanto tempo manter o modelo na memória depois do pedido. O
    padrão dele é 5 minutos; depois disso, a próxima pergunta espera cerca de 2,5 s para o modelo
    ser carregado de novo (contra 0,07 s com ele já carregado).
    """
    try:
        resposta = httpx.post(
            f"{config.ollama_base_url}/api/embed",
            json={
                "model": config.embedding_model,
                "input": textos,
                "truncate": False,
                "keep_alive": config.ollama_keep_alive,
            },
            timeout=_TIMEOUT_SEGUNDOS,
        )
    except httpx.ConnectError as erro:
        raise ErroEmbedding(
            f"Ollama não respondeu em {config.ollama_base_url}. Ele está aberto?"
        ) from erro

    if resposta.status_code != 200:
        raise ErroEmbedding(f"Ollama recusou o pedido ({resposta.status_code}): {resposta.text}")

    vetores = resposta.json()["embeddings"]
    if len(vetores) != len(textos) or any(len(v) != DIMENSAO for v in vetores):
        raise ErroEmbedding("Ollama devolveu vetores em número ou tamanho inesperado")
    return vetores


def gerar_embedding(texto: str, config: Config) -> list[float]:
    return gerar_embeddings([texto], config)[0]


def aquecer_modelo(config: Config) -> None:
    """Carrega o modelo na memória do Ollama antes da primeira pergunta de verdade."""
    gerar_embedding("aquecimento", config)
