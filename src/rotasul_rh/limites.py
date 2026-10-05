"""Limite de requisições em memória, com janela deslizante.

Usado para as perguntas (por IP e no total do dia, para não esgotar a cota do Groq) e para as
tentativas erradas da chave do RH (força bruta).

Janela deslizante: guarda o horário de cada requisição aceita e conta só as que estão dentro da
janela. Na janela fixa ("10 por minuto do relógio"), 10 pedidos às 9h00min59s e mais 10 às
9h01min00s passariam todos; aqui, não.

O estado fica na memória de um processo: vale enquanto a API roda num processo só (um uvicorn).
Com vários processos ou servidores, ele precisaria ir para um armazenamento compartilhado (Redis).
LGPD: a chave (o IP) só existe aqui, enquanto a janela dura; não vai para o log nem para o banco.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

# De quanto em quanto tempo as chaves sem requisição recente são esquecidas.
_INTERVALO_DE_LIMPEZA_SEGUNDOS = 60


@dataclass(frozen=True)
class Regra:
    maximo: int
    janela_segundos: float


class Limitador:
    def __init__(self, regras: list[Regra], relogio: Callable[[], float] = time.monotonic):
        self._regras = regras
        self._maior_janela = max(r.janela_segundos for r in regras)
        self._relogio = relogio
        self._horarios: dict[str, deque[float]] = {}
        self._ultima_limpeza = relogio()
        # A API atende várias requisições ao mesmo tempo, em threads diferentes.
        self._trava = threading.Lock()

    def tentar(self, chave: str) -> float | None:
        """Conta a requisição, se ela couber em todas as regras, e devolve None. Se não couber,
        não conta e devolve quantos segundos faltam para caber (vai no cabeçalho Retry-After)."""
        with self._trava:
            agora = self._relogio()
            espera = self._espera(chave, agora)
            if espera is None:
                self._horarios.setdefault(chave, deque()).append(agora)
            return espera

    def espera(self, chave: str) -> float | None:
        """Só consulta: None se a próxima requisição cabe; senão, os segundos que faltam."""
        with self._trava:
            return self._espera(chave, self._relogio())

    def registrar(self, chave: str) -> None:
        """Conta uma ocorrência sem consultar (ex.: uma chave do RH errada)."""
        with self._trava:
            self._horarios.setdefault(chave, deque()).append(self._relogio())

    def _espera(self, chave: str, agora: float) -> float | None:
        self._limpar(agora)
        horarios = self._horarios.get(chave)
        if not horarios:
            return None
        # Os horários estão em ordem: os mais velhos que a maior janela não contam mais.
        while horarios and horarios[0] <= agora - self._maior_janela:
            horarios.popleft()

        espera = 0.0
        for regra in self._regras:
            dentro = sum(1 for h in horarios if h > agora - regra.janela_segundos)
            if dentro >= regra.maximo:
                # Cabe de novo quando a requisição que está em `maximo` posições do fim sair da
                # janela.
                saida = horarios[len(horarios) - regra.maximo] + regra.janela_segundos
                espera = max(espera, saida - agora)
        return espera or None

    def _limpar(self, agora: float) -> None:
        """Esquece as chaves sem requisição dentro da maior janela, para a memória não crescer
        com IPs que não voltaram."""
        if agora - self._ultima_limpeza < _INTERVALO_DE_LIMPEZA_SEGUNDOS:
            return
        self._ultima_limpeza = agora
        vencidas = [
            chave
            for chave, horarios in self._horarios.items()
            if not horarios or horarios[-1] <= agora - self._maior_janela
        ]
        for chave in vencidas:
            del self._horarios[chave]
