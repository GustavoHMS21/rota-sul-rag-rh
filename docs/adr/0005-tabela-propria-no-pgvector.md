# ADR-0005: Tabela própria no pgvector, sem LlamaIndex

- **Status:** aceito
- **Data:** 2026-09-27
- **Responsável pela decisão:** Gustavo

## Contexto

Os 57 chunks (ADR-0004) precisam virar vetores do bge-m3 e ser gravados no PostgreSQL com pgvector.
A busca precisa filtrar pelo público de quem pergunta (regra 5): um chunk entra se o público da
pessoa está na lista de públicos do chunk.

A stack inicial previa o LlamaIndex como pipeline de RAG. Com a leitura (ADR-0003) e o chunking
(ADR-0004) feitos no projeto, sobrariam para ele só a gravação e a busca.

## Opções consideradas

### Opção 1: `PGVectorStore` do LlamaIndex

- Prós: menos código (cerca de 40 linhas); tabela, gravação e busca prontas; busca híbrida disponível;
  nome conhecido no mercado.
- Contras: a tabela é genérica e os nossos campos ficam num JSON (`metadata_`); o filtro de público
  precisa ser traduzido para os filtros do LlamaIndex; o SQL fica escondido, o que dificulta entender
  por que a busca trouxe um chunk errado; uma dependência grande para pouco trabalho.

### Opção 2: Tabela própria com `psycopg` e `pgvector`

- Prós: uma coluna por campo, com `publicos text[]` nativo; o filtro de público é uma linha de SQL;
  tudo visível no banco, o que ajuda a depurar e a avaliar a busca; menos dependências.
- Contras: mais código (cerca de 130 linhas); busca híbrida, se necessária, precisa ser feita à mão
  com o `tsvector` do Postgres.

## Decisão

Opção 2. O LlamaIndex sai da stack: os embeddings vêm de uma chamada HTTP ao Ollama e, na geração, a
resposta virá do SDK do Groq.

Detalhes da implementação:

- **Distância de cosseno** (`<=>`), a medida padrão para embeddings de texto; a similaridade exibida é
  `1 - distância`.
- **Sem índice vetorial (HNSW):** com dezenas de chunks, comparar com todos é mais rápido que usar
  índice. Rever quando a base passar de alguns milhares de chunks.
- **Reindexação em uma transação:** apaga e regrava tudo; rodar de novo não duplica, e uma falha no
  meio não deixa o banco pela metade.
- **`truncate: false` no Ollama:** um texto maior que o contexto do modelo é recusado com erro, em vez
  de ter o final cortado em silêncio. Isso fecha a conferência de tokens que ficou pendente no
  ADR-0004.
- **Um único pedido de embeddings para todos os chunks:** 57 chunks levam cerca de 30 a 50 s na CPU.
- **Endereços em `127.0.0.1`, não `localhost`:** no Windows, `localhost` resolve primeiro para `::1`
  (IPv6), mas o Postgres (Docker) e o Ollama escutam só em IPv4. Medido:
  - Postgres: a conexão ficava pendurada por mais de 2 minutos; com `127.0.0.1`, 0,03 s. A conexão
    também tem timeout de 10 s, para falhar rápido em vez de travar.
  - Ollama: cada embedding de pergunta levava 2,17 s (o Windows insiste por cerca de 2 s na porta
    fechada do IPv6 antes de tentar o IPv4); com `127.0.0.1`, 0,08 s. Esses 2 s seriam somados a
    toda pergunta feita ao assistente.
- **Reaproveitamento de embeddings:** cada chunk guarda um hash (SHA-256) do texto do embedding e do
  nome do modelo. A indexação só pede ao Ollama os vetores do que mudou: reindexar sem mudanças caiu
  de 44 s para 0,4 s. Como o modelo entra no hash, trocar de modelo regenera tudo.

## Consequências

- `indexar()` e `buscar(pergunta, publico)` são a interface usada pelas etapas seguintes.
- Os testes que usam banco e Ollama são marcados como integração e rodam só com
  `uv run pytest -m integracao`.
- Trocar o modelo de embeddings exige reindexar tudo: vetores de modelos diferentes não são
  comparáveis, e a busca devolveria resultados ruins sem dar erro.
- Primeiras buscas mostram a pergunta fora das políticas ("reembolso de viagem") com similaridade
  máxima de 0,52, contra 0,63 a 0,70 nas perguntas com resposta. A nota mínima para responder "não
  encontrei" será definida com o gabarito, na etapa de avaliação da busca.
