"""Idempotência do POST /api/perguntas com o cabeçalho Idempotency-Key.

Se a rede cai depois que a pergunta chegou ao servidor, a página não sabe se ela foi respondida.
Reenviar sem idempotência chamaria o modelo de novo (custo e cota) e registraria a pergunta duas
vezes. Com a mesma chave, o reenvio recebe a resposta já pronta.

Comportamento (segue o rascunho de padrão da IETF para o cabeçalho Idempotency-Key):
- chave nova: a requisição é processada e a resposta fica guardada;
- chave conhecida, mesma pergunta, já respondida: devolve a resposta guardada;
- chave conhecida, ainda em andamento: 409 (o cliente espera e tenta de novo);
- chave conhecida com outra pergunta: 422 (uso errado da chave);
- se o processamento falhar (503, 429), a chave é liberada: o reenvio tenta de verdade, em vez de
  receber o mesmo erro guardado.

As chaves ficam na memória do processo por 10 minutos (reenvios acontecem em segundos). Reiniciar
o servidor as apaga: o reenvio vira uma pergunta nova, que é o comportamento de antes, não pior.
"""

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

VALIDADE_SEGUNDOS = 10 * 60


class ChaveEmAndamento(Exception):
    """A primeira requisição com esta chave ainda está sendo processada."""


class ChaveReutilizada(Exception):
    """A chave já foi usada com outra pergunta."""


@dataclass
class _Entrada:
    impressao: str
    criada_em: float
    resposta: Any = None  # None enquanto a requisição está em andamento


class Idempotencia:
    def __init__(
        self,
        validade_segundos: float = VALIDADE_SEGUNDOS,
        relogio: Callable[[], float] = time.monotonic,
    ):
        self._validade = validade_segundos
        self._relogio = relogio
        self._entradas: dict[str, _Entrada] = {}
        self._trava = threading.Lock()

    def iniciar(self, chave: str, corpo: dict) -> Any:
        """Devolve a resposta guardada, se houver. Se a chave for nova, marca como em andamento e
        devolve None (quem chamou processa e depois chama concluir ou desistir)."""
        impressao = _impressao(corpo)
        with self._trava:
            agora = self._relogio()
            self._limpar(agora)
            entrada = self._entradas.get(chave)
            if entrada is None:
                self._entradas[chave] = _Entrada(impressao, agora)
                return None
            if entrada.impressao != impressao:
                raise ChaveReutilizada(chave)
            if entrada.resposta is None:
                raise ChaveEmAndamento(chave)
            return entrada.resposta

    def concluir(self, chave: str, resposta: Any) -> None:
        with self._trava:
            entrada = self._entradas.get(chave)
            if entrada is not None:
                entrada.resposta = resposta

    def desistir(self, chave: str) -> None:
        """A requisição falhou ou foi barrada: libera a chave para um reenvio de verdade."""
        with self._trava:
            self._entradas.pop(chave, None)

    def _limpar(self, agora: float) -> None:
        vencidas = [c for c, e in self._entradas.items() if e.criada_em <= agora - self._validade]
        for chave in vencidas:
            del self._entradas[chave]


def _impressao(corpo: dict) -> str:
    """Hash do corpo da requisição: compara perguntas sem guardar o texto delas."""
    texto = json.dumps(corpo, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode()).hexdigest()
