import pytest

from rotasul_rh.config import Config, carregar_config
from rotasul_rh.embeddings import ErroEmbedding, gerar_embeddings

_CONFIG_SEM_OLLAMA = Config(
    postgres_host="127.0.0.1",
    postgres_port=5432,
    postgres_db="x",
    postgres_user="x",
    postgres_password="x",
    ollama_base_url="http://127.0.0.1:9",  # porta onde nada responde
    embedding_model="bge-m3",
)


def test_ollama_fora_do_ar_gera_erro_claro():
    with pytest.raises(ErroEmbedding, match="Ollama não respondeu"):
        gerar_embeddings(["teste"], _CONFIG_SEM_OLLAMA)


@pytest.mark.integracao
def test_texto_maior_que_o_contexto_e_recusado_e_nao_truncado():
    with pytest.raises(ErroEmbedding, match="exceeds the context length"):
        gerar_embeddings(["palavra " * 6000], carregar_config())
