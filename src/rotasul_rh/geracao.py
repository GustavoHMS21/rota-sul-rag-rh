"""Geração da resposta: busca os trechos, pergunta ao modelo no Groq e verifica a resposta.

Uso: uv run python -m rotasul_rh.geracao "Posso vender minhas férias?" --publico administrativo

A verificação não depende de o modelo obedecer ao prompt: qualquer resposta que cite uma fonte fora
dos trechos buscados, venha sem fonte ou em formato inválido é trocada pela resposta padrão.
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass, field

import groq

from rotasul_rh.busca import Resultado, buscar_contexto
from rotasul_rh.config import Config, carregar_config
from rotasul_rh.prompt import RESPOSTA_PADRAO, montar_mensagens

log = logging.getLogger(__name__)

RESPONDIDA = "respondida"
NAO_ENCONTRADO = "nao_encontrado"
DADO_PESSOAL = "dado_pessoal"
_TIPOS = {RESPONDIDA, NAO_ENCONTRADO, DADO_PESSOAL}

# Temperatura 0: a mesma pergunta deve ter sempre a mesma resposta (ADR-0007).
_TEMPERATURA = 0
# O Qwen responde com 75 a 300 tokens. O Groq desconta este teto do limite de tokens por minuto
# antes de responder: com 2048, cada pergunta "ocupava" ~3.300 tokens dos 8.000 por minuto e a
# segunda ou terceira pergunta seguida recebia 429. Uma resposta maior que o teto sai com o JSON
# cortado e vira a resposta padrão na verificação (falha segura).
_MAX_TOKENS_DE_SAIDA = 512


class ErroGeracao(RuntimeError):
    pass


class ErroLimite(ErroGeracao):
    """O limite de uso do Groq (tokens por minuto ou requisições por dia) foi atingido."""


@dataclass(frozen=True)
class Resposta:
    tipo: str  # respondida | nao_encontrado | dado_pessoal
    texto: str
    fontes: list[str]  # citações prontas: "POL-RH-004, Banco de Horas, seção 5"
    ids_das_fontes: list[str]  # "POL-RH-004#5"
    trechos: list[Resultado] = field(repr=False)
    # Preenchido quando a verificação trocou a resposta do modelo pela padrão.
    motivo_da_troca: str | None = None


def responder(pergunta: str, publico: str | None, config: Config, tentativas: int = 2) -> Resposta:
    """Responde à pergunta de quem tem o público informado (ou None, se não informou)."""
    trechos = buscar_contexto(pergunta, publico, config)
    conteudo = _perguntar_ao_modelo(
        montar_mensagens(pergunta, publico, trechos), config, tentativas
    )
    resposta = interpretar(conteudo, trechos)
    if resposta.motivo_da_troca:
        # Pode ser só um modelo mal comportado, ou o começo de um problema: vale olhar.
        log.warning(
            "resposta do modelo trocada pela padrão",
            extra={"evento": "verificacao", "motivo": resposta.motivo_da_troca},
        )
    return resposta


def interpretar(conteudo: str, trechos: list[Resultado]) -> Resposta:
    """Lê o JSON do modelo e verifica tudo o que dá para verificar sem depender dele."""
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError:
        return _padrao(NAO_ENCONTRADO, trechos, "JSON inválido")
    if not isinstance(dados, dict):
        return _padrao(NAO_ENCONTRADO, trechos, "JSON inválido")

    tipo = dados.get("tipo")
    if tipo not in _TIPOS:
        return _padrao(NAO_ENCONTRADO, trechos, f"tipo desconhecido: {tipo!r}")
    if tipo != RESPONDIDA:
        return _padrao(tipo, trechos)

    texto = dados.get("resposta")
    if not isinstance(texto, str) or not texto.strip():
        return _padrao(NAO_ENCONTRADO, trechos, "resposta vazia")

    fontes = dados.get("fontes")
    if not isinstance(fontes, list) or not fontes:
        return _padrao(NAO_ENCONTRADO, trechos, "resposta sem fonte")

    por_id = {f"{t.codigo}#{t.secao}": t for t in trechos}
    # Alguns modelos devolvem o identificador com os colchetes do prompt: "[POL-RH-003#5]".
    ids = list(dict.fromkeys(str(f).strip().strip("[]").strip() for f in fontes))
    inventadas = [i for i in ids if i not in por_id]
    if inventadas:
        return _padrao(NAO_ENCONTRADO, trechos, f"fonte fora dos trechos: {inventadas}")

    return Resposta(
        tipo=RESPONDIDA,
        texto=texto.strip(),
        fontes=[por_id[i].fonte for i in ids],
        ids_das_fontes=ids,
        trechos=trechos,
    )


def _padrao(tipo: str, trechos: list[Resultado], motivo: str | None = None) -> Resposta:
    return Resposta(
        tipo=tipo,
        texto=RESPOSTA_PADRAO,
        fontes=[],
        ids_das_fontes=[],
        trechos=trechos,
        motivo_da_troca=motivo,
    )


def _perguntar_ao_modelo(mensagens: list[dict], config: Config, tentativas: int) -> str:
    if not config.groq_api_key:
        raise ErroGeracao("GROQ_API_KEY não definida no .env")
    if not config.groq_model:
        raise ErroGeracao("GROQ_MODEL não definido no .env")

    # max_retries: o SDK repete sozinho em erros temporários, respeitando o tempo de espera que o
    # Groq pede quando o limite de tokens por minuto é atingido.
    cliente = groq.Groq(api_key=config.groq_api_key, max_retries=tentativas)
    inicio = time.perf_counter()
    try:
        conclusao = cliente.chat.completions.create(
            model=config.groq_model,
            messages=mensagens,
            temperature=_TEMPERATURA,
            response_format={"type": "json_object"},
            max_completion_tokens=_MAX_TOKENS_DE_SAIDA,
        )
    except groq.AuthenticationError as erro:
        raise ErroGeracao("A chave do Groq foi recusada. Confira a GROQ_API_KEY no .env.") from erro
    except groq.NotFoundError as erro:
        raise ErroGeracao(
            f"O modelo {config.groq_model!r} não existe no Groq. Confira o GROQ_MODEL no .env."
        ) from erro
    except groq.RateLimitError as erro:
        raise ErroLimite(
            "O limite de uso do Groq foi atingido. Tente de novo em alguns instantes."
        ) from erro
    except groq.APIConnectionError as erro:
        raise ErroGeracao("Não consegui falar com o Groq. Confira a internet.") from erro
    except groq.APIStatusError as erro:
        raise ErroGeracao(f"O Groq devolveu um erro ({erro.status_code}).") from erro

    uso = conclusao.usage
    log.info(
        "modelo respondeu",
        extra={
            "evento": "groq",
            "segundos": round(time.perf_counter() - inicio, 3),
            "modelo": config.groq_model,
            "tokens_entrada": getattr(uso, "prompt_tokens", None),
            "tokens_saida": getattr(uso, "completion_tokens", None),
            "fim": conclusao.choices[0].finish_reason,
        },
    )
    return conclusao.choices[0].message.content or ""


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("pergunta")
    argumentos.add_argument("--publico", default=None)
    entrada = argumentos.parse_args()

    resposta = responder(entrada.pergunta, entrada.publico, carregar_config())
    print(resposta.texto)
    for fonte in resposta.fontes:
        print(f"Fonte: {fonte}")
    if resposta.motivo_da_troca:
        print(f"(resposta do modelo descartada: {resposta.motivo_da_troca})")
    print("\nTrechos usados:")
    for trecho in resposta.trechos:
        print(f"  {trecho.similaridade:.3f}  {trecho.id}")
