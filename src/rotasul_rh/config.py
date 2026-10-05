"""Configuração lida do arquivo .env (segredos nunca ficam no código)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    ollama_base_url: str
    embedding_model: str
    # Tempo que o Ollama mantém o bge-m3 na memória sem uso (padrão dele: 5 min). "-1" = sempre.
    ollama_keep_alive: str = "1h"
    # Só a geração usa o Groq; indexar e buscar funcionam sem a chave.
    groq_api_key: str | None = None
    groq_model: str | None = None
    # Chave da área do RH (/rh). Sem ela, a área fica desativada (ADR-0009).
    rh_chave_acesso: str | None = None
    # Dias que as perguntas registradas ficam guardadas antes de serem apagadas (ADR-0008).
    retencao_dias: int = 180
    # Limite de perguntas por IP e no total do dia (ADR-0013). O total protege a cota diária do
    # Groq (1.000 requisições no plano gratuito) e deixa uma sobra para a avaliação.
    limite_perguntas_por_minuto: int = 10
    limite_perguntas_por_hora: int = 60
    limite_perguntas_por_dia: int = 900

    @property
    def conninfo(self) -> str:
        """String de conexão no formato que o psycopg entende."""
        return (
            f"host={self.postgres_host} port={self.postgres_port} dbname={self.postgres_db} "
            f"user={self.postgres_user} password={self.postgres_password}"
        )


def carregar_config() -> Config:
    load_dotenv()
    return Config(
        postgres_host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=_obrigatoria("POSTGRES_DB"),
        postgres_user=_obrigatoria("POSTGRES_USER"),
        postgres_password=_obrigatoria("POSTGRES_PASSWORD"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "bge-m3"),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "1h"),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL") or None,
        rh_chave_acesso=os.getenv("RH_CHAVE_ACESSO") or None,
        retencao_dias=int(os.getenv("RETENCAO_DIAS", "180")),
        limite_perguntas_por_minuto=int(os.getenv("LIMITE_PERGUNTAS_POR_MINUTO", "10")),
        limite_perguntas_por_hora=int(os.getenv("LIMITE_PERGUNTAS_POR_HORA", "60")),
        limite_perguntas_por_dia=int(os.getenv("LIMITE_PERGUNTAS_POR_DIA", "900")),
    )


def _obrigatoria(nome: str) -> str:
    valor = os.getenv(nome)
    if not valor:
        raise RuntimeError(f"variável {nome} não definida no .env (veja o .env.example)")
    return valor
