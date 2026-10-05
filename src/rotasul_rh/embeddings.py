"""Geração de embeddings com o bge-m3 rodando no Ollama."""

import logging
import random
import time

import httpx

from rotasul_rh.config import Config

log = logging.getLogger(__name__)

DIMENSAO = 1024  # tamanho do vetor do bge-m3

# Indexar os 57 chunks num lote leva cerca de 50 s na CPU; a folga cobre máquinas mais lentas.
TIMEOUT_INDEXACAO = httpx.Timeout(600, connect=5)
# A pergunta do funcionário leva 0,07 s com o modelo carregado e cerca de 2,5 s para carregá-lo.
# Com um limite curto, um Ollama travado libera o atendimento em segundos, e não em 10 minutos.
TIMEOUT_PERGUNTA = httpx.Timeout(10, connect=2)
# Espera antes da 1ª nova tentativa; dobra a cada tentativa seguinte.
_ESPERA_BASE_SEGUNDOS = 0.5


class ErroEmbedding(RuntimeError):
    pass


class ErroTemporario(ErroEmbedding):
    """Falha que pode passar sozinha (rede, tempo esgotado, erro 5xx): vale tentar de novo."""


def gerar_embeddings(
    textos: list[str],
    config: Config,
    *,
    timeout: httpx.Timeout = TIMEOUT_INDEXACAO,
    novas_tentativas: int = 0,
) -> list[list[float]]:
    """Devolve um vetor por texto, na mesma ordem.

    `truncate: False` faz o Ollama recusar um texto maior que o contexto do modelo, em vez de
    cortar o final em silêncio (e deixar esse final fora do vetor).

    `keep_alive` diz ao Ollama por quanto tempo manter o modelo na memória depois do pedido. O
    padrão dele é 5 minutos; depois disso, a próxima pergunta espera cerca de 2,5 s para o modelo
    ser carregado de novo (contra 0,07 s com ele já carregado).

    Falhas temporárias são repetidas até `novas_tentativas` vezes, com espera exponencial e um
    sorteio (jitter), para que várias requisições que falharam juntas não voltem todas no mesmo
    instante. Erros 4xx (modelo inexistente, texto grande demais) não melhoram repetindo e sobem
    na hora.
    """
    for tentativa in range(novas_tentativas + 1):
        try:
            return _chamar_ollama(textos, config, timeout)
        except ErroTemporario as erro:
            if tentativa == novas_tentativas:
                raise
            espera = _ESPERA_BASE_SEGUNDOS * 2**tentativa * random.uniform(0.5, 1.5)
            log.warning(
                "nova tentativa no Ollama",
                extra={
                    "evento": "retry",
                    "dependencia": "ollama",
                    "tentativa": tentativa + 1,
                    "motivo": str(erro),
                    "espera_segundos": round(espera, 2),
                },
            )
            time.sleep(espera)
    raise AssertionError("inalcançável: o laço sempre devolve ou levanta")


def gerar_embedding(texto: str, config: Config) -> list[float]:
    """Vetor da pergunta, com o funcionário esperando: limite curto e uma nova tentativa.

    Pior caso: 2 tentativas de até 10 s e a espera entre elas, cerca de 21 s.
    """
    return gerar_embeddings([texto], config, timeout=TIMEOUT_PERGUNTA, novas_tentativas=1)[0]


def aquecer_modelo(config: Config) -> None:
    """Carrega o modelo na memória do Ollama antes da primeira pergunta de verdade.

    Usa o limite longo: numa máquina lenta, carregar o modelo pode passar dos 10 s da pergunta.
    """
    gerar_embeddings(["aquecimento"], config)


def _chamar_ollama(textos: list[str], config: Config, timeout: httpx.Timeout) -> list[list[float]]:
    try:
        resposta = httpx.post(
            f"{config.ollama_base_url}/api/embed",
            json={
                "model": config.embedding_model,
                "input": textos,
                "truncate": False,
                "keep_alive": config.ollama_keep_alive,
            },
            timeout=timeout,
        )
    except httpx.ConnectError as erro:
        raise ErroTemporario(
            f"Ollama não respondeu em {config.ollama_base_url}. Ele está aberto?"
        ) from erro
    except httpx.TimeoutException as erro:
        raise ErroTemporario(f"Ollama passou do tempo limite ({type(erro).__name__}).") from erro
    except httpx.TransportError as erro:
        raise ErroTemporario(f"Falha de rede com o Ollama ({type(erro).__name__}).") from erro

    if resposta.status_code >= 500:
        raise ErroTemporario(f"Ollama falhou ({resposta.status_code}): {resposta.text}")
    if resposta.status_code != 200:
        raise ErroEmbedding(f"Ollama recusou o pedido ({resposta.status_code}): {resposta.text}")

    vetores = resposta.json()["embeddings"]
    if len(vetores) != len(textos) or any(len(v) != DIMENSAO for v in vetores):
        raise ErroEmbedding("Ollama devolveu vetores em número ou tamanho inesperado")
    return vetores
