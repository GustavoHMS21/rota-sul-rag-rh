"""API web do assistente (FastAPI) e as páginas HTML (ADR-0002, ADR-0008, ADR-0009).

Uso: uv run uvicorn rotasul_rh.api:app --reload --reload-dir src
(--reload reinicia o servidor quando o código muda; --reload-dir src vigia só o código, e não a
.venv, que tem mais de 1.500 arquivos de bibliotecas e nunca muda.)
Depois, abra http://127.0.0.1:8000 (funcionário), http://127.0.0.1:8000/rh (RH) ou
http://127.0.0.1:8000/docs (documentação automática da API).
"""

import logging
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from rotasul_rh import registro
from rotasul_rh.banco import conectar
from rotasul_rh.config import Config, carregar_config
from rotasul_rh.embeddings import ErroEmbedding, aquecer_modelo
from rotasul_rh.geracao import ErroGeracao, ErroLimite, responder
from rotasul_rh.logs import configurar_logs, id_da_requisicao, novo_id_de_requisicao

log = logging.getLogger(__name__)
ESTATICOS = Path(__file__).parent / "static"


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    """Na subida, carrega o bge-m3 no Ollama em segundo plano: sem isso, a primeira pergunta
    espera cerca de 2,5 s pelo carregamento do modelo. Em segundo plano para não atrasar a subida;
    se o Ollama estiver fora, a primeira pergunta e o /api/saude mostram o problema."""
    configurar_logs()
    log.info("servidor iniciado", extra={"evento": "inicio"})
    threading.Thread(target=_aquecer, daemon=True).start()
    yield


def _aquecer() -> None:
    try:
        aquecer_modelo(obter_config())
    except Exception:
        log.warning("não consegui aquecer o modelo de embeddings", exc_info=True)


app = FastAPI(
    title="Assistente de Políticas de RH: Rota Sul Logística",
    description=(
        "Responde dúvidas de funcionários com base nas políticas oficiais, citando a fonte. "
        "Empresa fictícia; projeto de portfólio."
    ),
    version="0.1.0",
    lifespan=ciclo_de_vida,
)
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


@app.middleware("http")
async def acompanhar_requisicao(request: Request, call_next):
    """Dá um código a cada requisição (logs, cabeçalho X-Request-ID e mensagens de erro) e
    registra o resultado das chamadas à API. As páginas e arquivos estáticos não entram no log."""
    codigo = novo_id_de_requisicao()
    inicio = time.perf_counter()
    try:
        resposta = await call_next(request)
    except Exception:
        log.exception("erro não tratado", extra={"evento": "erro", "rota": request.url.path})
        resposta = JSONResponse(
            {"detail": _com_codigo("Algo deu errado no assistente.")}, status_code=500
        )
    resposta.headers["X-Request-ID"] = codigo
    if request.url.path.startswith("/api/"):
        log.info(
            "requisição concluída",
            extra={
                "evento": "requisicao",
                "metodo": request.method,
                "rota": request.url.path,
                "status": resposta.status_code,
                "segundos": round(time.perf_counter() - inicio, 3),
            },
        )
    return resposta


def _com_codigo(mensagem: str) -> str:
    """Mensagem de erro para o funcionário, com o código que liga a reclamação ao log."""
    return f"{mensagem} Se falar com o RH, informe o código {id_da_requisicao()}."


@lru_cache
def obter_config() -> Config:
    """Lida uma vez; nos testes, substituída por app.dependency_overrides."""
    return carregar_config()


ConfigDep = Annotated[Config, Depends(obter_config)]
Publico = Literal["administrativo", "operacao_5x2", "operacao_6x1", "motorista"]


# ---------------------------------------------------------------- funcionário


class PerguntaEntrada(BaseModel):
    pergunta: str = Field(min_length=3, max_length=500, examples=["Posso vender minhas férias?"])
    publico: Publico | None = Field(default=None, description="Vazio = não informado")


class Trecho(BaseModel):
    fonte: str
    titulo: str
    texto: str
    similaridade: float


class RespostaSaida(BaseModel):
    id: uuid.UUID | None = Field(description="Id do registro; vazio se o registro falhou")
    tipo: Literal["respondida", "nao_encontrado", "dado_pessoal"]
    resposta: str
    fontes: list[str]
    trechos: list[Trecho]


class AvaliacaoEntrada(BaseModel):
    util: bool


@app.get("/", include_in_schema=False)
def pagina_do_funcionario() -> FileResponse:
    return FileResponse(ESTATICOS / "index.html")


@app.post("/api/perguntas", response_model=RespostaSaida, tags=["funcionário"])
def perguntar(entrada: PerguntaEntrada, config: ConfigDep) -> RespostaSaida:
    """Responde à pergunta com base nas políticas e registra a interação de forma anônima."""
    pergunta = entrada.pergunta.strip()
    if len(pergunta) < 3:
        raise HTTPException(422, "Escreva uma pergunta.")

    # Só metadados: o texto da pergunta nunca vai para o log (LGPD, ADR-0011).
    log.info(
        "pergunta recebida",
        extra={"evento": "pergunta", "publico": entrada.publico, "caracteres": len(pergunta)},
    )
    inicio = time.perf_counter()
    try:
        resposta = responder(pergunta, entrada.publico, config)
    except ErroLimite as erro:
        log.warning("limite do Groq esgotado", extra={"evento": "falha", "motivo": str(erro)})
        raise HTTPException(
            429, _com_codigo("Muitas perguntas agora. Tente em alguns instantes.")
        ) from erro
    except (ErroGeracao, ErroEmbedding, RuntimeError) as erro:
        log.exception("falha ao responder", extra={"evento": "falha"})
        raise HTTPException(
            503, _com_codigo("O assistente está indisponível no momento.")
        ) from erro
    milissegundos = round((time.perf_counter() - inicio) * 1000)

    # O registro não pode derrubar o atendimento: se falhar, a resposta sai mesmo assim.
    try:
        id_ = registro.registrar(pergunta, entrada.publico, resposta, milissegundos, config)
    except Exception:
        log.exception("falha ao registrar a interação", extra={"evento": "falha"})
        id_ = None

    log.info(
        "resposta entregue",
        extra={
            "evento": "resposta",
            "tipo": resposta.tipo,
            "fontes": resposta.ids_das_fontes,
            "interacao": str(id_) if id_ else None,
            "segundos": round(milissegundos / 1000, 3),
        },
    )

    return RespostaSaida(
        id=id_,
        tipo=resposta.tipo,
        resposta=resposta.texto,
        fontes=resposta.fontes,
        trechos=[
            Trecho(fonte=t.fonte, titulo=t.titulo, texto=t.texto, similaridade=t.similaridade)
            for t in resposta.trechos
        ],
    )


@app.post("/api/perguntas/{id_}/avaliacao", status_code=204, tags=["funcionário"])
def avaliar_resposta(id_: uuid.UUID, entrada: AvaliacaoEntrada, config: ConfigDep) -> None:
    """Guarda o 👍 (util=true) ou 👎 (util=false) do funcionário."""
    if not registro.avaliar(id_, entrada.util, config):
        raise HTTPException(404, "Pergunta não encontrada.")


@app.get("/api/saude", tags=["operação"])
def saude(config: ConfigDep) -> JSONResponse:
    """Confere as dependências. 200 se tudo está de pé; 503 e o detalhe se algo falhou."""
    verificacoes = {
        "banco": _verificar_banco(config),
        "ollama": _verificar_ollama(config),
        "groq": "ok" if config.groq_api_key and config.groq_model else "chave ou modelo ausente",
    }
    tudo_ok = all(v == "ok" for v in verificacoes.values())
    return JSONResponse(verificacoes, status_code=200 if tudo_ok else 503)


def _verificar_banco(config: Config) -> str:
    try:
        with conectar(config) as conexao:
            (chunks,) = conexao.execute("SELECT count(*) FROM chunks").fetchone()
    except Exception:
        return "sem conexão"
    return "ok" if chunks else "sem chunks (rode a indexação)"


def _verificar_ollama(config: Config) -> str:
    try:
        modelos = httpx.get(f"{config.ollama_base_url}/api/tags", timeout=3).json()["models"]
    except Exception:
        return "sem conexão"
    nomes = {m["name"].split(":")[0] for m in modelos}
    return "ok" if config.embedding_model in nomes else f"modelo {config.embedding_model} ausente"


# ---------------------------------------------------------------- RH


def exigir_chave_do_rh(
    config: ConfigDep, x_chave_rh: Annotated[str | None, Header()] = None
) -> None:
    """Autorização da área do RH (ADR-0009): chave no cabeçalho X-Chave-RH."""
    if not config.rh_chave_acesso:
        raise HTTPException(503, "Área do RH desativada: defina RH_CHAVE_ACESSO no .env.")
    # compare_digest compara em tempo constante: o tempo de resposta não dá pistas da chave.
    if not x_chave_rh or not secrets.compare_digest(x_chave_rh, config.rh_chave_acesso):
        # Várias tentativas seguidas podem ser alguém tentando adivinhar a chave.
        log.warning("chave do RH inválida", extra={"evento": "acesso_negado"})
        raise HTTPException(401, "Chave do RH inválida.")


RH = [Depends(exigir_chave_do_rh)]


class InteracaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # aceita a dataclass registro.Interacao

    id: uuid.UUID
    criado_em: datetime
    pergunta: str
    publico: str | None
    tipo: str
    resposta: str
    fontes: list[str]
    milissegundos: int
    avaliacao_util: bool | None


@app.get("/rh", include_in_schema=False)
def pagina_do_rh() -> FileResponse:
    return FileResponse(ESTATICOS / "rh.html")


@app.get("/api/rh/resumo", dependencies=RH, tags=["RH"])
def resumo_do_rh(config: ConfigDep) -> dict:
    """Totais por tipo de resposta e avaliações dos funcionários."""
    return registro.resumir(config)


@app.get("/api/rh/interacoes", dependencies=RH, response_model=list[InteracaoSaida], tags=["RH"])
def interacoes_do_rh(
    config: ConfigDep,
    tipo: Literal["respondida", "nao_encontrado", "dado_pessoal"] | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[registro.Interacao]:
    """Perguntas e respostas registradas (anônimas), das mais recentes para as mais antigas."""
    return registro.listar(config, tipo, limite)
