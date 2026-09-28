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
    )


def _obrigatoria(nome: str) -> str:
    valor = os.getenv(nome)
    if not valor:
        raise RuntimeError(f"variável {nome} não definida no .env (veja o .env.example)")
    return valor
