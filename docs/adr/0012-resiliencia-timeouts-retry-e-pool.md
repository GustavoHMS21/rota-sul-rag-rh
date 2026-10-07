# ADR-0012: Resiliência: timeouts por uso, retry no Ollama e pool de conexões

- **Status:** aceito
- **Data:** 2026-10-05
- **Responsável pela decisão:** Gustavo

## Contexto

Uma revisão do código mostrou como o sistema se comportava quando uma dependência falhava ou
ficava lenta:

- **A pergunta usava o timeout da indexação.** O embedding da pergunta e o da indexação passavam
  pela mesma função, com limite de 600 s (indexar 57 trechos na CPU leva uns 50 s). Com o Ollama
  travado, a requisição do funcionário ficava presa até 10 minutos, ocupando uma das 40 threads do
  servidor.
- **O tempo esgotado virava erro 500.** O código tratava só `httpx.ConnectError`; um
  `httpx.ReadTimeout` escapava e chegava ao funcionário como "algo deu errado" (500), em vez de
  "indisponível" (503) como os outros erros de dependência.
- **Nenhuma nova tentativa no Ollama.** Uma falha de rede passageira já virava erro para o
  funcionário.
- **O esquema do banco era criado a cada conexão.** O `conectar()` rodava `CREATE EXTENSION` e
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` sempre que abria uma conexão, e cada pergunta abre duas
  (busca e registro): uma ida e volta a mais ao banco por requisição, e o `ALTER TABLE` pede bloqueio
  exclusivo da tabela mesmo quando a coluna já existe, o que enfileirava buscas simultâneas.
- **Uma conexão nova por chamada, sem pool,** e um cliente do Groq novo a cada pergunta, sem
  reaproveitar a conexão HTTPS e sem timeout explícito.

## Opções consideradas

### Retry no Ollama

#### Opção 1: Laço próprio

- Prós: cerca de 15 linhas; o critério de quando repetir fica explícito e testado; sem dependência.
- Contras: código próprio para manter.

#### Opção 2: Biblioteca tenacity

- Prós: decorator pronto e muito usado.
- Contras: uma dependência nova para um único ponto de retry; o critério fica espalhado em
  parâmetros do decorator.

#### Opção 3: Retry do transporte do httpx (`HTTPTransport(retries=1)`)

- Prós: uma linha.
- Contras: repete só falha de conexão; não cobre tempo esgotado nem erro 5xx, e não tem espera
  configurável.

### Criação do esquema

#### Opção 1: Uma vez por processo, antes do pool

- Prós: resolve o custo e o bloqueio por requisição com mudança pequena.
- Contras: o esquema continua sem versão; a próxima mudança de tabela pede outra solução.

#### Opção 2: Migrações versionadas (arquivos SQL numerados e tabela de controle)

- Prós: é como sistemas reais evoluem o banco; o `ALTER TABLE` do `hash_embedding` já mostra a
  necessidade.
- Contras: mais código e mais conceito para duas tabelas.

### Pool de conexões

#### Opção 1: Pool global, com o `conectar()` de sempre

- Prós: busca, registro e indexação não mudam; o pool fica escondido no `banco.py`.
- Contras: estado global no módulo.

#### Opção 2: Pool injetado como parâmetro

- Prós: mais explícito e fácil de testar.
- Contras: muda a assinatura da busca, do registro e dos scripts de avaliação.

#### Opção 3: Sem pool

- Prós: tirando o esquema de cada conexão, abrir uma conexão local custa poucos milissegundos.
- Contras: não acompanha carga maior.

## Decisão

1. **Timeouts por uso.** Pergunta: 2 s para conectar e 10 s para ler (0,07 s com o modelo carregado,
   cerca de 2,5 s para carregá-lo). Indexação: 5 s e 600 s. O aquecimento do modelo na subida usa o
   limite longo, porque numa máquina lenta carregar o modelo pode passar de 10 s.
2. **Falha temporária e permanente são tratadas diferente.** Erro de rede, tempo esgotado e resposta
   5xx viram `ErroTemporario`; um 4xx (modelo inexistente, texto grande demais) sobe na hora, porque
   repetir não resolve. Os dois são `ErroEmbedding`, que a API transforma em 503.
3. **Retry com laço próprio (Opção 1)** só no embedding da pergunta: uma nova tentativa, com espera
   de 0,5 s mais ou menos 50% de sorteio (jitter), para várias requisições que falharam juntas não
   voltarem no mesmo instante. Cada nova tentativa vai para o log como `evento=retry`. A indexação
   não repete por padrão: um lote de 50 s que esgotou o tempo não deve recomeçar sozinho.
4. **Cliente do Groq criado uma vez e reaproveitado,** com 20 s por tentativa e 2 novas tentativas
   feitas pelo próprio SDK (conexão, tempo esgotado, 429 e 5xx, respeitando a espera que o Groq
   pede). O tempo esgotado ganhou mensagem própria.
5. **Esquema criado uma vez por processo, antes do pool (Opção 1).** A API cria na subida, em segundo
   plano; os scripts, na primeira conexão. Uma trava garante uma criação só, mesmo com várias
   requisições ao mesmo tempo; se o banco estiver fora, nada fica pela metade e a requisição seguinte
   tenta de novo.
6. **Pool `psycopg_pool` global (Opção 1),** de 1 a 10 conexões: o FastAPI atende até 40 requisições
   ao mesmo tempo, mas cada pergunta usa o banco por poucos milissegundos. O pool testa a conexão
   antes de entregá-la (se o Postgres reiniciou, troca a conexão morta por uma nova), espera no máximo
   10 s por uma conexão livre (depois, 503) e é fechado na saída da API e no fim dos scripts.

Pior caso de espera do funcionário: cerca de 21 s no Ollama (2 tentativas de 10 s e a espera entre
elas) e cerca de 60 s no Groq (3 tentativas de 20 s).

## Consequências

- Um Ollama travado libera o atendimento em segundos, e não em 10 minutos.
- Com o Postgres reiniciando, a pergunta seguinte funciona sem intervenção.
- Não há disjuntor (circuit breaker): com o Groq fora, cada pergunta ainda espera as novas
  tentativas antes de falhar. É a próxima melhoria de resiliência se o Groq instável virar rotina.
- A próxima mudança de tabela deve vir com migrações versionadas (Opção 2), em vez de outro
  `ADD COLUMN IF NOT EXISTS`.
- O pool é por processo: com vários processos, o total de conexões é 10 vezes o número deles, e o
  limite de conexões do Postgres precisa acompanhar.
