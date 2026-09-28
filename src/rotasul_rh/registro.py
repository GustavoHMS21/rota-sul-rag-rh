"""Registro anônimo das perguntas e respostas (ADR-0008).

Para que serve: auditoria (o que o assistente respondeu por escrito, com qual fonte e modelo),
melhoria contínua (respostas ruins viram casos do gabarito) e informação para o RH (perguntas sem
resposta mostram lacunas nas políticas).

Cuidados da LGPD:
- nada identifica quem perguntou: sem usuário, IP ou navegador;
- CPF, e-mail e telefone são trocados por marcadores antes de gravar;
- os registros são apagados depois do prazo de retenção (RETENCAO_DIAS, padrão 180).
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from psycopg.types.json import Jsonb

from rotasul_rh.banco import conectar
from rotasul_rh.config import Config
from rotasul_rh.geracao import Resposta

# A ordem importa: o CPF vem antes do telefone, que também é uma sequência de dígitos.
_DADOS_PESSOAIS = [
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "[E-MAIL]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    (re.compile(r"(\+?55\s?)?(\(?\d{2}\)?\s?)?9?\d{4}[-\s]?\d{4}\b"), "[TELEFONE]"),
]


def mascarar_dados_pessoais(texto: str) -> str:
    """ "Meu CPF é 123.456.789-00" -> "Meu CPF é [CPF]"."""
    for padrao, marcador in _DADOS_PESSOAIS:
        texto = padrao.sub(marcador, texto)
    return texto


def registrar(
    pergunta: str, publico: str | None, resposta: Resposta, milissegundos: int, config: Config
) -> uuid.UUID:
    """Grava a interação (já mascarada) e apaga as que passaram do prazo. Devolve o id."""
    trechos = [
        {"id": t.id, "fonte": t.fonte, "similaridade": round(t.similaridade, 3)}
        for t in resposta.trechos
    ]
    with conectar(config) as conexao, conexao.transaction():
        (id_,) = conexao.execute(
            """
            INSERT INTO interacoes (pergunta, publico, tipo, resposta, fontes, trechos, modelo,
                                    motivo_da_troca, milissegundos)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                mascarar_dados_pessoais(pergunta),
                publico,
                resposta.tipo,
                resposta.texto,
                resposta.ids_das_fontes,
                Jsonb(trechos),
                config.groq_model,
                resposta.motivo_da_troca,
                milissegundos,
            ),
        ).fetchone()
        _apagar_vencidas(conexao, config.retencao_dias)
    return id_


def avaliar(id_: uuid.UUID, util: bool, config: Config) -> bool:
    """Guarda o 👍/👎 do funcionário. False se a interação não existe (ou já foi apagada)."""
    with conectar(config) as conexao, conexao.transaction():
        cursor = conexao.execute(
            "UPDATE interacoes SET avaliacao_util = %s, avaliada_em = now() WHERE id = %s",
            (util, id_),
        )
        return cursor.rowcount == 1


@dataclass(frozen=True)
class Interacao:
    id: uuid.UUID
    criado_em: datetime
    pergunta: str
    publico: str | None
    tipo: str
    resposta: str
    fontes: list[str]
    milissegundos: int
    avaliacao_util: bool | None


def listar(config: Config, tipo: str | None = None, limite: int = 50) -> list[Interacao]:
    """As interações mais recentes, opcionalmente só de um tipo (respondida, nao_encontrado...)."""
    with conectar(config) as conexao:
        linhas = conexao.execute(
            """
            SELECT id, criado_em, pergunta, publico, tipo, resposta, fontes, milissegundos,
                   avaliacao_util
            FROM interacoes
            WHERE %(tipo)s::text IS NULL OR tipo = %(tipo)s
            ORDER BY criado_em DESC
            LIMIT %(limite)s
            """,
            {"tipo": tipo, "limite": limite},
        ).fetchall()
    return [Interacao(*linha) for linha in linhas]


def resumir(config: Config) -> dict:
    """Números da área do RH: total, recusas e avaliações."""
    with conectar(config) as conexao:
        total, respondidas, nao_encontrado, dado_pessoal, uteis, nao_uteis = conexao.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE tipo = 'respondida'),
                   count(*) FILTER (WHERE tipo = 'nao_encontrado'),
                   count(*) FILTER (WHERE tipo = 'dado_pessoal'),
                   count(*) FILTER (WHERE avaliacao_util),
                   count(*) FILTER (WHERE NOT avaliacao_util)
            FROM interacoes
            """
        ).fetchone()
    return {
        "total": total,
        "respondidas": respondidas,
        "nao_encontrado": nao_encontrado,
        "dado_pessoal": dado_pessoal,
        "avaliacoes_uteis": uteis,
        "avaliacoes_nao_uteis": nao_uteis,
        "retencao_dias": config.retencao_dias,
    }


def _apagar_vencidas(conexao, retencao_dias: int) -> None:
    conexao.execute(
        "DELETE FROM interacoes WHERE criado_em < now() - make_interval(days => %s)",
        (retencao_dias,),
    )
