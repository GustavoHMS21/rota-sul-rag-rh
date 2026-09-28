"""Avaliação da resposta final (busca + modelo) contra o gabarito (evals/perguntas.json).

Para cada pergunta, confere:
- comportamento: respondeu quando devia responder e recusou quando devia recusar;
- fatos: os trechos obrigatórios do gabarito aparecem na resposta;
- proibidos: nenhuma regra de outro público aparece na resposta;
- fonte: a resposta cita a seção esperada.

Fatos e proibidos são conferidos por texto (sem diferenciar maiúsculas). O modelo reescreve com as
próprias palavras, então um fato ausente pode ser só outra redação ("três" em vez de "3"): os casos
reprovados precisam ser lidos antes de qualquer conclusão.

Uso: uv run python -m rotasul_rh.avaliacao_geracao
Com o plano gratuito do Groq (8.000 tokens por minuto), as 51 perguntas levam de 10 a 20 minutos.
"""

import json
import re
import time
from pathlib import Path

from rotasul_rh.config import carregar_config
from rotasul_rh.geracao import RESPONDIDA, ErroGeracao, responder

RAIZ = Path(__file__).parents[2]
GABARITO = RAIZ / "evals" / "perguntas.json"
PASTA_SAIDA = RAIZ / "evals" / "resultados"
DEVE_RESPONDER = {"responder", "separar_publicos"}
_ESPERA_NO_LIMITE_SEGUNDOS = 20
_TENTATIVAS_NO_LIMITE = 10


def avaliar() -> dict:
    config = carregar_config()
    perguntas = json.loads(GABARITO.read_text(encoding="utf-8"))

    casos = []
    for numero, pergunta in enumerate(perguntas, start=1):
        print(f"[{numero}/{len(perguntas)}] {pergunta['id']}", flush=True)
        casos.append(_avaliar_caso(pergunta, config))

    return {"modelo": config.groq_model, "resumo": _resumir(casos), "casos": casos}


def _avaliar_caso(pergunta: dict, config) -> dict:
    inicio = time.perf_counter()
    resposta = _responder_esperando_o_limite(pergunta, config)
    segundos = round(time.perf_counter() - inicio, 1)

    deve_responder = pergunta["comportamento"] in DEVE_RESPONDER
    respondeu = resposta.tipo == RESPONDIDA
    texto = _normalizar(resposta.texto)
    return {
        "id": pergunta["id"],
        "tipo": pergunta["tipo"],
        "publico": pergunta["publico"],
        "pergunta": pergunta["pergunta"],
        "resposta": resposta.texto,
        "tipo_da_resposta": resposta.tipo,
        "fontes_citadas": resposta.ids_das_fontes,
        "fontes_esperadas": pergunta["fontes"],
        "trechos": [t.id for t in resposta.trechos],
        "motivo_da_troca": resposta.motivo_da_troca,
        "segundos": segundos,
        "comportamento_ok": respondeu == deve_responder,
        "fatos_ausentes": [f for f in pergunta["fatos"] if _normalizar(f) not in texto]
        if respondeu
        else [],
        "proibidos_presentes": [p for p in pergunta["proibidos"] if _normalizar(p) in texto],
        "fonte_ok": (not deve_responder)
        or any(f in pergunta["fontes"] for f in resposta.ids_das_fontes),
    }


def _responder_esperando_o_limite(pergunta: dict, config):
    """Quando o limite de tokens por minuto é atingido, espera e tenta de novo."""
    for tentativa in range(1, _TENTATIVAS_NO_LIMITE + 1):
        try:
            return responder(pergunta["pergunta"], pergunta["publico"], config, tentativas=5)
        except ErroGeracao as erro:
            if "limite" not in str(erro) or tentativa == _TENTATIVAS_NO_LIMITE:
                raise
            print(
                f"    limite do Groq atingido; esperando {_ESPERA_NO_LIMITE_SEGUNDOS} s", flush=True
            )
            time.sleep(_ESPERA_NO_LIMITE_SEGUNDOS)
    raise AssertionError("inalcançável")


def _resumir(casos: list[dict]) -> dict:
    com_resposta = [c for c in casos if c["fontes_esperadas"]]
    sem_resposta = [c for c in casos if not c["fontes_esperadas"]]
    respondidas_certas = [c for c in com_resposta if c["tipo_da_resposta"] == RESPONDIDA]
    return {
        "perguntas": len(casos),
        "comportamento_ok": sum(c["comportamento_ok"] for c in casos),
        # Os dois erros de comportamento têm pesos diferentes para a Rota Sul:
        "respondeu_o_que_devia_recusar": sum(
            1 for c in sem_resposta if c["tipo_da_resposta"] == RESPONDIDA
        ),
        "recusou_o_que_devia_responder": len(com_resposta) - len(respondidas_certas),
        "fonte_ok": sum(c["fonte_ok"] for c in com_resposta),
        "com_todos_os_fatos": sum(1 for c in respondidas_certas if not c["fatos_ausentes"]),
        "com_proibido": sum(1 for c in casos if c["proibidos_presentes"]),
        "respostas_trocadas_pela_verificacao": sum(1 for c in casos if c["motivo_da_troca"]),
        "segundos_por_pergunta_mediana": sorted(c["segundos"] for c in casos)[len(casos) // 2],
    }


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().split())


def _imprimir(relatorio: dict) -> None:
    r = relatorio["resumo"]
    total = r["perguntas"]
    com = total - sum(1 for c in relatorio["casos"] if not c["fontes_esperadas"])
    print(f"\nModelo: {relatorio['modelo']}")
    print(f"Comportamento certo:            {r['comportamento_ok']}/{total}")
    print(f"  respondeu o que devia recusar:  {r['respondeu_o_que_devia_recusar']}")
    print(f"  recusou o que devia responder:  {r['recusou_o_que_devia_responder']}")
    print(f"Fonte certa:                    {r['fonte_ok']}/{com}")
    print(f"Respostas com todos os fatos:   {r['com_todos_os_fatos']}/{com}")
    print(f"Respostas com regra proibida:   {r['com_proibido']}")
    print(f"Trocadas pela verificação:      {r['respostas_trocadas_pela_verificacao']}")
    print(f"Tempo por pergunta (mediana):   {r['segundos_por_pergunta_mediana']} s")

    print("\nCasos para ler:")
    for c in relatorio["casos"]:
        problemas = []
        if not c["comportamento_ok"]:
            problemas.append(f"comportamento ({c['tipo_da_resposta']})")
        if not c["fonte_ok"]:
            problemas.append(f"fonte {c['fontes_citadas']} (esperada {c['fontes_esperadas']})")
        if c["fatos_ausentes"]:
            problemas.append(f"fatos ausentes {c['fatos_ausentes']}")
        if c["proibidos_presentes"]:
            problemas.append(f"PROIBIDO {c['proibidos_presentes']}")
        if problemas:
            print(f"\n- {c['id']} [{c['publico']}]: {'; '.join(problemas)}")
            print(f"  P: {c['pergunta']}")
            print(f"  R: {c['resposta']}")


def _arquivo_de_saida(modelo: str) -> Path:
    return PASTA_SAIDA / f"geracao-{re.sub(r'[^a-z0-9.]+', '-', modelo.lower())}.json"


if __name__ == "__main__":
    relatorio = avaliar()
    saida = _arquivo_de_saida(relatorio["modelo"])
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _imprimir(relatorio)
    print(f"\nResultado completo em {saida.relative_to(RAIZ)}")
