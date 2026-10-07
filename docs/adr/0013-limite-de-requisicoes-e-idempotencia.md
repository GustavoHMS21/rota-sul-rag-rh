# ADR-0013: Limite de perguntas, bloqueio da chave do RH e idempotência

- **Status:** aceito
- **Data:** 2026-10-05
- **Responsável pela decisão:** Gustavo

## Contexto

Três brechas apareciam quando o sistema era pensado sob carga ou uso mal-intencionado:

- **Nenhum limite em `/api/perguntas`.** O plano gratuito do Groq dá 1.000 requisições por dia. Um
  script esgotaria essa cota em minutos e tiraria o assistente do ar para todos (a ADR-0009 já
  deixava isso como pendência para quando o sistema fosse publicado).
- **Nenhuma proteção contra força bruta na chave do RH.** Uma chave errada só gerava um aviso no log;
  dava para tentar chaves sem limite.
- **O POST de perguntas não era idempotente.** Se a rede caísse depois de a pergunta chegar ao
  servidor, a página não sabia se ela tinha sido respondida. Reenviar chamava o modelo de novo
  (custo e cota) e registrava a pergunta duas vezes.

Restrição: a ADR-0008 promete que nada identifica quem perguntou. Um limite por IP não pode gravar o
IP em lugar nenhum.

## Opções consideradas

### Limite de requisições

#### Opção 1: Próprio, em memória, com janela deslizante

- Prós: cerca de 50 linhas, sem dependência; algoritmo visível e testado.
- Contras: o estado vale para um processo só.

#### Opção 2: Biblioteca slowapi

- Prós: decorators prontos (`@limiter.limit("10/minute")`) e troca fácil para Redis.
- Contras: dependência nova, de manutenção lenta; exige mudar a assinatura das rotas.

#### Opção 3: Redis

- Prós: correto para vários processos ou servidores.
- Contras: mais um contêiner e mais um ponto de falha para um sistema que roda num processo só.

### Onde guardar as chaves de idempotência

#### Opção 1: Memória, por 10 minutos

- Prós: simples; reenvios acontecem em segundos.
- Contras: reiniciar o servidor apaga as chaves (o reenvio vira uma pergunta nova, que é o
  comportamento de antes, não pior); vale para um processo só.

#### Opção 2: Postgres

- Prós: sobrevive a reinício e vale para vários processos.
- Contras: o registro passaria a ter duas fases (gravar "em andamento" antes de chamar o Groq,
  completar depois) e mudaria o esquema.

### Valores do limite

- 10 por minuto e 60 por hora por IP, mais 900 por dia no total;
- só por IP, sem teto total (mais simples, mas vários IPs juntos ainda esgotam a cota do Groq);
- 5 por minuto e 30 por hora por IP, mais 900 por dia (protege mais, mas pode barrar um computador
  compartilhado de um CD em horário de pico).

## Decisão

1. **Limite próprio, em memória, com janela deslizante (Opção 1).** Guarda o horário de cada
   requisição aceita e conta só as que estão dentro da janela. Na janela fixa ("10 por minuto do
   relógio"), 10 pedidos às 9h00min59s e mais 10 às 9h01min00s passariam todos; aqui, não. Uma trava
   protege o estado entre threads, uma requisição barrada não conta (insistir não prolonga o
   bloqueio), e a cada minuto os IPs sem requisição recente são esquecidos, para a memória não
   crescer.
2. **Valores: 10 por minuto e 60 por hora por IP, mais 900 nas últimas 24 h no total,** configuráveis
   no `.env` (`LIMITE_PERGUNTAS_POR_MINUTO`, `_POR_HORA`, `_POR_DIA`). A folga por IP é para os
   computadores compartilhados dos CDs; o teto total deixa 100 das 1.000 requisições diárias do Groq
   para a avaliação.
3. **Resposta 429 com `Retry-After`** (segundos até poder tentar de novo) e mensagem amigável. O teto
   total orienta a falar com o RH por e-mail.
4. **O limite é conferido dentro da rota, depois da validação da entrada.** Numa dependência do
   FastAPI, ele rodaria antes da validação, e uma pergunta inválida (422), que nem chega ao Groq,
   gastaria cota.
5. **O IP fica só na memória,** enquanto a janela dura. Não vai para o log (o evento `limite`
   registra só o escopo: IP ou total) nem para o banco, o que mantém a ADR-0008.
6. **Força bruta na chave do RH:** 5 chaves erradas do mesmo IP em 15 minutos bloqueiam o IP até o
   erro mais antigo sair da janela, **inclusive para a chave certa**. Se a chave certa passasse
   durante o bloqueio, quem está tentando saberia quando acertou.
7. **Idempotência em memória por 10 minutos (Opção 1),** com o cabeçalho `Idempotency-Key`, nome do
   rascunho de padrão da IETF. O cabeçalho é opcional: sem ele, a API funciona como antes.
   - Chave nova: a pergunta é processada e a resposta fica guardada.
   - Chave conhecida, já respondida: devolve a mesma resposta, com `Idempotent-Replayed: true`, sem
     chamar o modelo nem registrar de novo.
   - Chave conhecida, ainda em andamento: 409.
   - Chave conhecida com outra pergunta: 422 (uso errado da chave).
   - Se a pergunta falhar (503, 429), a chave é liberada: o reenvio tenta de verdade, em vez de
     receber o mesmo erro guardado.
   - Para comparar as perguntas, guarda só o hash do corpo, nunca o texto.
8. **A idempotência vem antes do limite:** um reenvio já respondido não custa nada e não conta.
9. **A página gera uma chave (UUID) por envio** e, em falha de rede ou 409, reenvia até 2 vezes com a
   mesma chave, esperando 1 s e depois 2 s. É exatamente o cenário que a idempotência torna seguro.

## Consequências

- O POST de avaliação (útil ou não) já era idempotente por natureza: repetir o `UPDATE` dá o mesmo
  resultado.
- **Tudo vale para um processo só.** Com vários processos ou servidores, o limite e as chaves de
  idempotência precisam ir para um armazenamento compartilhado (Redis); até lá, a app roda com um
  único processo uvicorn.
- Reiniciar o servidor zera as contagens e as chaves.
- Atrás de um proxy reverso, todos chegariam com o IP do proxy; o IP real atrás do proxy é tratado na
  ADR-0016. A ADR-0015 acrescentou o `/api/saude` à mesma conferência da chave do RH, com o mesmo
  bloqueio.
- Com 220 funcionários e 350 perguntas por mês, os limites não devem ser sentidos; se um CD reclamar
  de bloqueio em horário de pico, o ajuste é no `.env`, sem mudar código.
