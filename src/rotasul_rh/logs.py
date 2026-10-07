"""Configuração dos logs (ADR-0011).

Em desenvolvimento (AMBIENTE=desenvolvimento):
- terminal: texto legível, com data, hora e o código da requisição;
- arquivo `logs/app.log`: uma linha JSON por evento, trocado à meia-noite e apagado depois de
  LOG_DIAS dias (padrão 14).

Em produção (ADR-0016): só JSON na saída padrão. Num contêiner, um arquivo interno se perderia a
cada deploy; o Docker guarda a saída padrão, com rotação definida no docker-compose.yml.

- Cada requisição ganha um código curto (`req`) que aparece em todas as suas linhas de log, no
  cabeçalho X-Request-ID e na mensagem de erro mostrada ao funcionário.

LGPD: o log guarda só metadados (público, tamanho da pergunta, tempos, tipo da resposta, fontes).
O texto da pergunta e da resposta nunca vai para o log; quando for preciso vê-lo, o id da interação
liga a linha de log ao registro mascarado no banco (ADR-0008).
"""

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from rotasul_rh.config import em_desenvolvimento

PASTA_LOGS = Path(__file__).parents[2] / "logs"

_id_requisicao: ContextVar[str] = ContextVar("id_requisicao", default="-")

# Atributos que todo LogRecord já tem; o que vier além disso é um campo extra do evento.
_ATRIBUTOS_PADRAO = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "req"}


def novo_id_de_requisicao() -> str:
    """Código curto o bastante para o funcionário ditar ao RH: "a1b2c3d4"."""
    codigo = uuid.uuid4().hex[:8]
    _id_requisicao.set(codigo)
    return codigo


def id_da_requisicao() -> str:
    return _id_requisicao.get()


class _FiltroDeRequisicao(logging.Filter):
    def filter(self, registro: logging.LogRecord) -> bool:
        registro.req = _id_requisicao.get()
        return True


class _RetryDoGroqComoAviso(logging.Filter):
    """O SDK do Groq registra cada nova tentativa como INFO; aqui ela vira WARNING."""

    def filter(self, registro: logging.LogRecord) -> bool:
        if registro.getMessage().startswith("Retrying request"):
            registro.levelno, registro.levelname = logging.WARNING, "WARNING"
        return True


def _campos_extras(registro: logging.LogRecord) -> dict:
    return {k: v for k, v in vars(registro).items() if k not in _ATRIBUTOS_PADRAO}


class FormatoJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        evento = {
            "hora": datetime.fromtimestamp(registro.created).isoformat(timespec="milliseconds"),
            "nivel": registro.levelname,
            "req": getattr(registro, "req", "-"),
            "origem": registro.name,
            "mensagem": registro.getMessage(),
            **_campos_extras(registro),
        }
        if registro.exc_info:
            evento["erro"] = self.formatException(registro.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


class FormatoTexto(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)-7s [%(req)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
        )

    def format(self, registro: logging.LogRecord) -> str:
        linha = super().format(registro)
        extras = _campos_extras(registro)
        if extras:
            campos = " ".join(f"{k}={v}" for k, v in extras.items())
            primeira, _, resto = linha.partition("\n")
            linha = f"{primeira} | {campos}" + (f"\n{resto}" if resto else "")
        return linha


def configurar_logs(pasta: Path = PASTA_LOGS, producao: bool | None = None) -> None:
    """Liga os logs. Pode ser chamada de novo (reload) sem duplicar.

    `producao`: None decide pelo AMBIENTE do .env; os testes passam True ou False.
    """
    if producao is None:
        producao = not em_desenvolvimento()
    nivel = os.getenv("LOG_NIVEL", "INFO").upper()
    dias = int(os.getenv("LOG_DIAS", "14"))

    raiz = logging.getLogger()
    for handler in [h for h in raiz.handlers if getattr(h, "_rotasul", False)]:
        raiz.removeHandler(handler)
        handler.close()
    raiz.setLevel(nivel)

    if producao:
        # Uma linha JSON por evento na saída padrão, que é o que o Docker coleta.
        saida = logging.StreamHandler(sys.stdout)
        saida.setFormatter(FormatoJson())
        handlers = [saida]
    else:
        terminal = logging.StreamHandler()
        terminal.setFormatter(FormatoTexto())
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = TimedRotatingFileHandler(
            pasta / "app.log", when="midnight", backupCount=dias, encoding="utf-8"
        )
        arquivo.setFormatter(FormatoJson())
        handlers = [terminal, arquivo]

    for handler in handlers:
        handler._rotasul = True
        handler.addFilter(_FiltroDeRequisicao())
        # No handler, e não no logger "groq": filtros de logger não valem para os loggers filhos
        # (o retry é registrado em "groq._base_client").
        handler.addFilter(_RetryDoGroqComoAviso())
        raiz.addHandler(handler)

    # O httpx registra cada chamada HTTP em INFO; os eventos do próprio projeto já cobrem isso.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # O SDK do Groq registra as novas tentativas em INFO e o resto em DEBUG.
    logging.getLogger("groq").setLevel(logging.INFO)
