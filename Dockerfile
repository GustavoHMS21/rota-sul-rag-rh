# Imagem da app: API, páginas web e o comando de indexação.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Dependências primeiro: mudar o código não reinstala tudo.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Usuário sem privilégios (ADR-0015): se a app for explorada, quem entrar não é root no contêiner.
# O código e a .venv continuam do root (só leitura para a app); a única pasta gravável é logs/.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/logs \
    && chown app /app/logs
USER app

EXPOSE 8000
# /api/saude sem chave: 200 se banco, Ollama e Groq estão ok; 503 (e o urlopen falha) se não.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4)"]
# --no-server-header: as respostas não anunciam o servidor ("server: uvicorn").
CMD ["uvicorn", "rotasul_rh.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
