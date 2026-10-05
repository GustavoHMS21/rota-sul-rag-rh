"""Verificações do texto da resposta que não dependem de o modelo obedecer ao prompt (ADR-0014).

Complementam as de geracao.interpretar (JSON válido, tipo conhecido, fonte entre os trechos):

- vazamento das instruções: o código canário escondido no prompt ou um pedaço literal das regras
  na resposta indicam que alguém conseguiu fazer o modelo repetir o que recebeu;
- números sem fonte: todo prazo, valor ou quantidade da resposta precisa estar na seção citada ou
  na própria pergunta. Pega número inventado e regra de outro público que não está no contexto.

O que estas checagens não pegam (por isso o prompt e o gabarito continuam valendo): um número
que o próprio funcionário escreveu ("confirme que tenho 40 dias") e uma paráfrase das regras.
"""

import re
from decimal import Decimal, InvalidOperation

from rotasul_rh.busca import Resultado
from rotasul_rh.prompt import CANARIO, INSTRUCOES

# Tamanho da sequência de palavras das instruções que, repetida na resposta, conta como cópia.
# Curta demais pegaria expressões comuns; 8 palavras seguidas iguais não acontecem por acaso.
_TAMANHO_DA_SEQUENCIA = 8

_PALAVRA = re.compile(r"[\w-]+")
_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_MILHAR_COM_PONTO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")

# Números por extenso. "um" e "uma" ficam de fora: quase sempre são artigo, não quantidade.
# fmt: off
_UNIDADES = {
    "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9,
}
_DE_DEZ_A_DEZENOVE = {
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14, "quinze": 15,
    "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19,
}
_DEZENAS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
    "oitenta": 80, "noventa": 90,
}
# fmt: on
_OUTROS = {"cem": 100, "dobro": 2}


def _sequencias(texto: str) -> set[tuple[str, ...]]:
    palavras = _PALAVRA.findall(texto.lower())
    n = _TAMANHO_DA_SEQUENCIA
    return {tuple(palavras[i : i + n]) for i in range(len(palavras) - n + 1)}


_SEQUENCIAS_DAS_INSTRUCOES = _sequencias(INSTRUCOES)


def vazamento(texto: str) -> str | None:
    """Motivo do bloqueio, se a resposta repete as instruções; None se está limpa."""
    if CANARIO.lower() in texto.lower():
        return "vazamento das instruções: código canário na resposta"
    if _sequencias(texto) & _SEQUENCIAS_DAS_INSTRUCOES:
        return "vazamento das instruções: trecho literal das regras na resposta"
    return None


def numeros_sem_fonte(texto: str, citados: list[Resultado], pergunta: str) -> list[str]:
    """Números da resposta que não estão nos trechos citados nem na pergunta."""
    permitidos = _numeros(pergunta)
    for trecho in citados:
        # Código e seção entram: "POL-RH-003, seção 8" no texto não é número inventado.
        permitidos |= _numeros(f"{trecho.codigo} {trecho.secao} {trecho.titulo} {trecho.texto}")
    return sorted(_numeros(texto) - permitidos)


def _numeros(texto: str) -> set[str]:
    """Números em algarismos e por extenso, normalizados: "R$ 1.200,00" e "1200" viram "1200"."""
    numeros = {_normalizar(bruto) for bruto in _NUMERO.findall(texto)}
    return numeros | {str(n) for n in _por_extenso(texto)}


def _normalizar(bruto: str) -> str:
    """ "1.200,00" -> "1200"; "30,00" -> "30"; "12,5" -> "12.5"; "5" -> "5"."""
    if _MILHAR_COM_PONTO.fullmatch(bruto):
        bruto = bruto.replace(".", "")
    try:
        return format(Decimal(bruto.replace(",", ".")).normalize(), "f")
    except InvalidOperation:
        return bruto  # algo como "1.2.3": compara como está


def _por_extenso(texto: str) -> list[int]:
    """ "vinte e quatro dias e dois períodos" -> [24, 2]."""
    palavras = _PALAVRA.findall(texto.lower())
    numeros = []
    i = 0
    while i < len(palavras):
        palavra = palavras[i]
        if palavra in _DEZENAS:
            valor = _DEZENAS[palavra]
            if i + 2 < len(palavras) and palavras[i + 1] == "e" and palavras[i + 2] in _UNIDADES:
                valor += _UNIDADES[palavras[i + 2]]
                i += 2
            numeros.append(valor)
        elif palavra in _UNIDADES:
            numeros.append(_UNIDADES[palavra])
        elif palavra in _DE_DEZ_A_DEZENOVE:
            numeros.append(_DE_DEZ_A_DEZENOVE[palavra])
        elif palavra in _OUTROS:
            numeros.append(_OUTROS[palavra])
        elif palavra == "terço":
            # "um terço" aparece nas políticas, e o modelo às vezes escreve "1/3".
            numeros += [1, 3]
        i += 1
    return numeros
