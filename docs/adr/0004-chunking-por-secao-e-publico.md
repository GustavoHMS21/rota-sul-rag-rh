# ADR-0004: Chunking por seção, com etiqueta de público

- **Status:** aceito
- **Data:** 2026-09-27
- **Responsável pela decisão:** Gustavo

## Contexto

A leitura (ADR-0003) entrega 53 seções. Medidas com o próprio bge-m3 (contagem real de tokens):

| | Tokens |
|---|---|
| Menor seção | 20 |
| Mediana | 59 |
| 90% das seções têm até | 137 |
| Maior seção (POL-RH-004, seção 5) | 309 |
| Todas as políticas juntas | 4.270 |

Limites que existem no sistema:

- **bge-m3:** aceita até 8.192 tokens, mas o Ollama carrega o modelo com `num_ctx` 4.096 por padrão.
  O que passa do limite é cortado sem aviso e fica fora do vetor.
- **Groq (plano gratuito):** limita tokens por minuto; chunks maiores gastam o limite mais rápido.
- **Qualidade da busca:** o embedding resume o chunk inteiro num único vetor. Chunks grandes misturam
  assuntos e diluem o vetor; chunks pequenos perdem o contexto ("O prazo para compensar é de 90 dias"
  sozinho não diz que a regra é da operação).

A regra de negócio 5 proíbe misturar regras de públicos diferentes (administrativo, operação,
motoristas).

## Opções consideradas

### Tamanho do chunk

- **Seção inteira:** assunto único e citação exata; a maior seção cabe com folga. Escolhida.
- **Pedaços de tamanho fixo (`SentenceSplitter`, 256 tokens):** corta seções no meio e separa regras do
  seu contexto.
- **Parágrafo:** mesmo problema, em escala maior.

### Como respeitar a regra 5

- **Só no prompt:** depende de o modelo obedecer.
- **Etiqueta de público no chunk e filtro na busca:** a regra de outro público nem chega ao modelo, mas
  não separa as escalas 5x2 e 6x1, que estão na mesma tabela.
- **Etiqueta e prompt:** o filtro tira os outros públicos; o prompt separa as escalas. Escolhida.

### Como saber o público de quem pergunta

- **Campo de seleção na tela** (Administrativo, CD 5x2, CD 6x1, Motorista, Não informar): escolhida.
- Deduzir pelo texto da pergunta: falha quando a pessoa não diz de onde é.
- Perguntar de volta: exige conversa em várias trocas.

## Decisão

1. **Um chunk por seção**, com um **cabeçalho de contexto** na frente do texto do embedding:
   `Política de Banco de Horas (POL-RH-004) | Seção 5: Operação (CDs de Jundiaí e Sumaré)`.
2. **Teto de 512 tokens por chunk.** Hoje nenhuma seção chega perto. Acima dele, a seção é dividida
   entre parágrafos, sem cortar nenhum, e um parágrafo sozinho acima do teto gera erro em vez de ser
   truncado em silêncio. Sem tamanho mínimo e sem overlap: os cortes seguem fronteiras naturais.
3. **Contagem de tokens estimada por caractere (0,4 token/caractere).** Medido nos chunks: média 0,27 e
   pior caso 0,364. Por palavra a variação é maior (1,36 a 2,44 tokens/palavra, com o pior caso nas
   tabelas). O maior chunk (342 tokens reais) fica estimado em 493, abaixo do teto.
4. **Etiqueta de público conservadora:** um trecho só é restrito quando o texto diz isso explicitamente:
   - título da seção ("5. Operação (CDs...)", "6. Motoristas") → o chunk é desse público;
   - parágrafo que começa com o público ("Administrativo (matriz): ...") → a seção vira um chunk por
     público citado, cada um com os seus parágrafos e os parágrafos gerais; os públicos não citados
     recebem um chunk só com os parágrafos gerais (sufixo `-geral`);
   - todo o resto vale para todos.

   Políticas inteiras não são etiquetadas: a seção "Quem pode" do Home Office precisa chegar a quem é
   do CD, porque é ela que diz que a operação não é elegível.
5. **As escalas 5x2 e 6x1 são tratadas pelo prompt**, porque dividem o mesmo chunk.

## Consequências

- 53 seções viram 57 chunks: POL-RH-003 seção 6 (como pedir férias) e POL-RH-006 seção 2
  (vale-refeição) foram divididas por público.
- Um teste cruza o chunking com o gabarito: para cada pergunta, os chunks visíveis ao público de quem
  pergunta contêm todos os fatos esperados e nenhum proibido. As duas perguntas de escala (5x2 e 6x1)
  ficam marcadas como falha esperada, documentando o limite do item 5; o eval da geração mede se o
  prompt resolve.
- A estimativa de tokens é uma aproximação. Na indexação, o Ollama devolve a contagem real, que deve
  ser conferida contra o `num_ctx`.
- **Ponto em aberto para o RH:** as políticas não dizem se motoristas contam como "operação" nas
  seções que separam administrativo e operação (como pedir férias, vale-refeição). Hoje o motorista
  recebe só os parágrafos gerais dessas seções.
- O valor de 512 é uma hipótese razoável, não um número definitivo: a busca será medida com o
  gabarito (hit@k), e o teto pode ser revisto com esses números.
