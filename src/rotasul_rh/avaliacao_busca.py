"""Avaliação da busca contra o gabarito (evals/perguntas.json). Não usa LLM.

Mede, para as perguntas com resposta, se a seção certa volta entre os primeiros resultados (hit@k
e MRR) e se o filtro de público deixa passar regras de outro público. Para achar a nota mínima de
similaridade, compara o 1º resultado das perguntas com e sem resposta.

Uso: uv run python -m rotasul_rh.avaliacao_busca
"""

import json
from pathlib import Path
from statistics import mean

from rotasul_rh.busca import Resultado, buscar
from rotasul_rh.config import carregar_config

RAIZ = Path(__file__).parents[2]
GABARITO = RAIZ / "evals" / "perguntas.json"
SAIDA = RAIZ / "evals" / "resultados" / "busca.json"
K = 3
SEM_RESPOSTA = {"dado_pessoal", "nao_encontrado"}


def avaliar() -> dict:
    config = carregar_config()
    perguntas = json.loads(GABARITO.read_text(encoding="utf-8"))

    casos = []
    for p in perguntas:
        resultados = buscar(p["pergunta"], p["publico"], config, k=K)
        casos.append(_avaliar_caso(p, resultados))

    com_resposta = [c for c in casos if c["tem_resposta"]]
    # Só as recusas de verdade entram na comparação de similaridade; os casos de manipulação
    # (sem fonte esperada, mas que podem ser respondidos com a regra real) ficam de fora.
    sem_resposta = [c for c in casos if c["comportamento"] in SEM_RESPOSTA]
    return {
        "k": K,
        "resumo": {
            "perguntas_com_resposta": len(com_resposta),
            "hit@1": _proporcao(c["posicao"] == 1 for c in com_resposta),
            f"hit@{K}": _proporcao(c["posicao"] is not None for c in com_resposta),
            "mrr": round(mean(1 / c["posicao"] if c["posicao"] else 0 for c in com_resposta), 3),
            "vazamentos_de_publico": sum(1 for c in casos if c["proibidos_visiveis"]),
        },
        "similaridade_do_1o": {
            "com_resposta": _faixa(c["similaridade_1o"] for c in com_resposta),
            "sem_resposta": _faixa(c["similaridade_1o"] for c in sem_resposta),
        },
        "casos": casos,
    }


def _avaliar_caso(pergunta: dict, resultados: list[Resultado]) -> dict:
    ids_de_secao = [f"{r.codigo}#{r.secao}" for r in resultados]
    posicao = next(
        (i for i, secao in enumerate(ids_de_secao, start=1) if secao in pergunta["fontes"]), None
    )
    texto_recuperado = " ".join(" ".join(r.texto.split()) for r in resultados)
    return {
        "id": pergunta["id"],
        "tipo": pergunta["tipo"],
        "publico": pergunta["publico"],
        "comportamento": pergunta["comportamento"],
        "tem_resposta": bool(pergunta["fontes"]),
        "fontes_esperadas": pergunta["fontes"],
        "recuperados": [r.id for r in resultados],
        "similaridades": [round(r.similaridade, 3) for r in resultados],
        "similaridade_1o": round(resultados[0].similaridade, 3),
        "posicao": posicao,  # posição da 1ª fonte esperada no top k (None = não veio)
        "proibidos_visiveis": [p for p in pergunta["proibidos"] if p in texto_recuperado],
    }


def _proporcao(valores) -> float:
    valores = list(valores)
    return round(sum(valores) / len(valores), 3)


def _faixa(valores) -> dict:
    valores = sorted(valores)
    return {"min": valores[0], "mediana": valores[len(valores) // 2], "max": valores[-1]}


def _imprimir(relatorio: dict) -> None:
    r = relatorio["resumo"]
    print(f"Perguntas com resposta: {r['perguntas_com_resposta']}")
    print(f"hit@1: {r['hit@1']:.0%}   hit@{K}: {r[f'hit@{K}']:.0%}   MRR: {r['mrr']:.3f}")
    print(f"Vazamentos de público: {r['vazamentos_de_publico']}")

    s = relatorio["similaridade_do_1o"]
    for grupo in ("com_resposta", "sem_resposta"):
        f = s[grupo]
        print(
            f"Similaridade do 1º, {grupo}: min {f['min']}  mediana {f['mediana']}  max {f['max']}"
        )

    print(f"\nPerguntas com resposta fora do 1º lugar (esperado -> recuperado, top {K}):")
    for c in relatorio["casos"]:
        if c["tem_resposta"] and c["posicao"] != 1:
            lugar = f"{c['posicao']}º" if c["posicao"] else "fora"
            print(f"  [{lugar}] {c['id']}: {c['fontes_esperadas']} -> {c['recuperados']}")

    print("\nPerguntas sem resposta (similaridade do 1º e o que veio):")
    for c in sorted(relatorio["casos"], key=lambda c: -c["similaridade_1o"]):
        if c["comportamento"] in SEM_RESPOSTA:
            print(f"  {c['similaridade_1o']:.3f}  {c['id']} -> {c['recuperados'][0]}")

    print("\nVazamentos de público:")
    for c in relatorio["casos"]:
        if c["proibidos_visiveis"]:
            print(f"  {c['id']} ({c['publico']}): {c['proibidos_visiveis']}")


if __name__ == "__main__":
    relatorio = avaliar()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _imprimir(relatorio)
    print(f"\nResultado completo em {SAIDA.relative_to(RAIZ)}")
