# ADR-0002: Interface com FastAPI e página HTML simples

- **Status:** aceito
- **Data:** 2026-09-26
- **Responsável pela decisão:** Gustavo

## Contexto

O assistente precisa de uma tela em que o funcionário digita a pergunta e recebe a resposta com a fonte
citada. Pelo ADR-0001, tudo roda localmente, então a interface serve para testar e demonstrar o sistema,
não para atender usuários reais.

## Opções consideradas

### Opção 1: FastAPI com uma página HTML simples

- Prós: separa a API (lógica do RAG) da tela; a API pode ser testada com pytest sem abrir navegador;
  gera documentação automática em `/docs`; a tela pode ser trocada no futuro sem mexer no RAG; mostra
  desenho de API no portfólio.
- Contras: exige escrever um pouco de HTML e JavaScript para chamar a API.

### Opção 2: Streamlit

- Prós: a tela fica pronta com pouco código, tudo em Python.
- Contras: mistura lógica e tela no mesmo script; mais difícil de testar; não expõe uma API que outro
  sistema possa usar; mostra menos engenharia.

### Opção 3: Gradio

- Prós: pronto para chat com pouco código; integra bem com o Hugging Face Spaces.
- Contras: os mesmos da Opção 2; a vantagem do Spaces não se aplica, já que o deploy ficou fora da v1.

## Decisão

Opção 1. A API fica no centro do sistema, e a página HTML é só uma forma de chamá-la.

## Consequências

- O RAG é escrito como código Python independente da web; o FastAPI só o expõe por um endpoint
  (por exemplo, `POST /perguntas`).
- Os testes de ponta a ponta usam o cliente de testes do FastAPI, sem navegador.
- A página HTML é servida pelo próprio FastAPI, sem framework de front-end.
- Entram como dependências `fastapi` e `uvicorn` (servidor), na etapa da interface.
