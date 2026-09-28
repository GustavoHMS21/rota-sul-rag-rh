# ADR-0007: Geração da resposta com Qwen no Groq, JSON verificado e contexto de elegibilidade

- **Status:** aceito
- **Data:** 2026-09-28
- **Responsável pela decisão:** Gustavo

## Contexto

Com a busca pronta (ADR-0005) e as perguntas sem resposta decididas pelo modelo (ADR-0006), falta
gerar a resposta: o modelo de linguagem lê os trechos e escreve para o funcionário, citando a fonte.

A stack inicial previa o Llama 3.3 70B (`llama-3.3-70b-versatile`) no Groq, mas ele não existe mais
no catálogo. Modelos disponíveis e testados em português, com saída JSON:

| Modelo | Tempo (1 pergunta) | Tokens de saída | Observação |
|---|---|---|---|
| `qwen/qwen3.8-27b` | ~0,3 s | 64 | responde direto |
| `openai/gpt-oss-20b` | ~0,5 s | 261 | modelo de raciocínio (gasta tokens "pensando") |
| `openai/gpt-oss-120b` | ~0,8 s | 199 | o maior; modelo de raciocínio |

Plano gratuito do Groq (igual para os três): 1.000 requisições por dia e 8.000 tokens por minuto.

## Decisões

1. **Modelo `qwen/qwen3.8-27b`**, configurável em `GROQ_MODEL` no `.env`. Mais rápido e econômico
   com o limite de tokens por minuto; empatou com o GPT-OSS 120B no teste manual com perguntas
   difíceis. A troca é uma linha no `.env`, e o eval (`uv run python -m rotasul_rh.avaliacao_geracao`)
   mede qualquer candidato.
2. **Temperatura 0:** a mesma pergunta deve ter sempre a mesma resposta (houve reclamação trabalhista
   por resposta errada por escrito, e o problema de origem era cada analista responder de um jeito).
3. **k = 5 trechos:** a seção certa estava entre os 5 primeiros em 100% das perguntas do gabarito
   (97% entre os 3 primeiros; "licença-paternidade" só aparece em 5º).
4. **Resposta em JSON** (`tipo`, `resposta`, `fontes`), com o modo JSON do Groq. O código verifica a
   resposta sem depender do modelo: fonte fora dos trechos buscados, resposta sem fonte, tipo
   desconhecido ou JSON inválido fazem a resposta ser trocada pela padrão. A citação exibida é
   montada pelo código a partir do trecho, não escrita pelo modelo.
5. **SDK oficial do Groq (`groq`)**, com tratamento de chave inválida, modelo inexistente, limite de
   uso e falta de conexão.
6. **Expansão de contexto com a seção de elegibilidade.** Quando a busca traz um trecho de uma
   política, a seção que diz quem tem direito a ela ("Quem pode", "Abrangência", "Quem recebe") entra
   no contexto, antes dos outros trechos. A função `buscar()` continua pura (a avaliação da busca a
   usa); a geração usa `buscar_contexto()`.
7. **Prompt com a diferença entre dado pessoal e situação contada:** "tive 10 faltas, quantos dias de
   férias vou ter?" é respondida com a regra; "quantos dias de férias eu ainda tenho?" depende do
   sistema da empresa e é recusada.

As decisões 6 e 7 vieram do eval: o gabarito ganhou a pergunta "Posso fazer home office?" (versão
curta, público operação), descoberta num teste manual.

## Resultado do eval (51 perguntas do gabarito)

| Medida | Antes de 6 e 7 | Depois |
|---|---|---|
| Comportamento certo (respondeu ou recusou quando devia) | 50/51 | **51/51** |
| Respondeu o que devia recusar | 0 | **0** |
| Recusou o que devia responder | 1 | **0** |
| Fonte certa | 38/40 | **40/40** |
| Resposta com regra de outro público | 1 | **0** |
| Respostas trocadas pela verificação | 0 | 0 |

Os dois erros corrigidos:

- "Posso fazer home office?" (operação): respondia "Sim, até 2 dias por semana". A seção "Quem pode"
  não vinha na busca para a pergunta curta. Agora: "Não, colaboradores da operação dos CDs não são
  elegíveis para home office."
- "Tive 10 faltas sem justificativa. Quantos dias de férias vou ter?": era recusada como dado pessoal.
  Agora: "24 dias corridos".

As escalas 5x2 e 6x1, que dividem o mesmo trecho (ADR-0004), foram separadas corretamente pelo prompt.

## Consequências

- **A checagem de fatos por texto exato é rígida demais:** 28 de 40 respostas contêm todos os fatos
  literalmente, mas a leitura das 12 restantes mostra que 9 estão certas com outra redação ("o prazo
  para compensar as horas do banco é de 6 meses"). As 3 realmente incompletas omitem um detalhe não
  perguntado diretamente (o 1/3 do pagamento de férias, os 40% do adiantamento, a carência de 90 dias
  depois do prazo). Melhorias possíveis: fatos reduzidos ao essencial (números e prazos) ou um segundo
  modelo como avaliador (LLM-as-judge).
- O tempo por pergunta no eval (cerca de 11 s) é efeito do limite de 8.000 tokens por minuto com
  perguntas disparadas em sequência; uma pergunta isolada leva cerca de 1 s.
- Modelos são descontinuados: o eval é o que permite trocar de modelo com segurança.
- A lista de títulos de elegibilidade é fixa; uma política nova com outro título ("Elegibilidade",
  "Público-alvo") precisa ser acrescentada.

## Revisão (2026-09-28): latência no uso real

Com a interface rodando, apareceram duas demoras que o eval não mostrava:

- **Partida a frio do Ollama.** O Ollama tira o bge-m3 da memória depois de 5 minutos sem uso, e a
  pergunta seguinte esperava de 2,2 a 2,7 s pelo carregamento (contra 0,07 s com o modelo
  carregado). Correção: a API aquece o modelo em segundo plano ao subir, e cada pedido de embedding
  informa `keep_alive` (padrão de 1 hora, configurável em `OLLAMA_KEEP_ALIVE`). "Para sempre" (`-1`)
  foi descartado porque ocuparia cerca de 1,2 GB de RAM mesmo com a API desligada.
- **Erro 429 do Groq na segunda ou terceira pergunta seguida.** Cada pergunta usa cerca de 1.350
  tokens, mas o pedido reservava `max_completion_tokens = 2048` (folga pensada para modelos de
  raciocínio), e o Groq desconta essa reserva do limite de 8.000 tokens por minuto antes de
  responder. Correção: teto de 512 tokens de saída. A resposta mais longa medida (separação por
  público) usou 205 tokens. Uma resposta acima do teto sai com o JSON cortado e vira a resposta
  padrão na verificação (falha segura). Com a correção, 5 perguntas seguidas foram respondidas entre
  1 e 2 s cada.
