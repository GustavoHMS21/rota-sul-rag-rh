# ADR-0016: Produção na Oracle Cloud Always Free, atrás de um proxy reverso

- **Status:** aceito
- **Data:** 2026-10-07
- **Responsável pela decisão:** Gustavo
- **Substitui:** ADR-0001 (execução apenas local)

## Contexto

A ADR-0001 manteve o sistema só local enquanto a prioridade era a qualidade do RAG. Com o RAG
avaliado (61/61 no comportamento e 43/43 na fonte, no gabarito de 61 perguntas) e as proteções de
falha, carga e segurança no lugar, o objetivo passa a ser aprender o ciclo completo de produção:
servidor, HTTPS, entrega contínua, backup e monitoramento.

Duas restrições guiam a escolha:

- **Custo zero.** Projeto de portfólio, sem orçamento: só serviços com plano gratuito real.
- **Cerca de 4 GB de RAM.** Três peças ficam ligadas o tempo todo: o bge-m3 no Ollama (~2 GB), o
  Postgres com as políticas e o registro de perguntas, e a app. A imagem do Ollama tem 9,3 GB e o
  modelo, 1,2 GB, então o disco também precisa de uns 20 GB.

Sair do `127.0.0.1` também traz problemas que não existiam:

- a chave do RH não pode trafegar sem HTTPS;
- o HTTPS fica num proxy na frente da app, e aí toda requisição chega à app com o IP do proxy. O
  limite de perguntas e o bloqueio da chave do RH são por IP (ADR-0013): sem o IP real, os 220
  funcionários dividiriam um único limite de 10 perguntas por minuto, e 5 chaves erradas de
  qualquer pessoa bloqueariam o RH inteiro;
- os logs eram gravados num arquivo dentro do contêiner (ADR-0011), que é descartado a cada deploy;
- o log de acesso do uvicorn grava o IP de cada requisição. Atrás de um proxy que repassa o IP real,
  passaria a gravar o IP de cada funcionário, o que a ADR-0008 proíbe.

## Opções consideradas

Descartadas de saída, por memória ou por não terem plano gratuito: AWS, Google Cloud e Azure
(máquinas gratuitas de 1 GB, que não carregam o bge-m3), Render e Koyeb (512 MB), Railway e Fly.io
(sem plano gratuito para contas novas). Na AWS, um servidor equivalente custaria cerca de US$ 30 a
45 por mês; o formato gerenciado (Fargate, RDS e load balancer), de US$ 70 a 110.

### Opção 1: Oracle Cloud Always Free, com o Docker Compose atual

- Prós: servidor Linux de verdade, gratuito sem prazo, com até 4 núcleos e 24 GB de RAM ARM; roda o
  mesmo `docker-compose.yml` do desenvolvimento, com o Caddy na frente para o HTTPS; ensina o ciclo
  inteiro (SSH, firewall, DNS, TLS, proxy, entrega contínua, backup).
- Contras: o cadastro pede cartão para validação e pode ser recusado; a capacidade gratuita pode
  faltar na região; a Oracle pode recuperar máquinas gratuitas ociosas; o processador é ARM, então
  todas as imagens precisam ter versão ARM; a administração do servidor (atualizações, firewall,
  disco) fica por nossa conta.

### Opção 2: Hugging Face Spaces + Neon

- Prós: nada para administrar; HTTPS e endereço prontos; 16 GB de RAM no Space gratuito; Postgres
  com pgvector no plano gratuito do Neon.
- Contras: o Space dorme sem uso e, ao acordar, carrega o bge-m3 de novo; o disco é apagado a cada
  reinício; é um contêiner só, então o Ollama teria de ir junto com a app; ensina mais PaaS do que
  infraestrutura.

### Opção 3: O próprio computador + túnel (Tailscale Funnel)

- Prós: nenhuma mudança de infraestrutura; endereço HTTPS fixo sem abrir porta no roteador.
- Contras: só fica no ar com o computador ligado; não ensina servidor, entrega contínua nem backup
  remoto; não é um ambiente de produção.

## Decisão

1. **Hospedagem: Oracle Cloud Always Free (Opção 1),** numa máquina ARM, com o Docker Compose do
   projeto. Se o cadastro ou a capacidade falharem, o plano B é a Opção 2.

2. **Proxy reverso na frente da app, e o IP real aceito só quando vem dele.** O Caddy (etapa P3)
   recebe o HTTPS e repassa a requisição, informando o IP real no cabeçalho `X-Forwarded-For`.
   Quem lê o cabeçalho é o uvicorn, antes da app, e só quando a conexão vem de um endereço em
   `FORWARDED_ALLOW_IPS`:
   - a rede interna do Compose ganhou uma faixa fixa (`172.28.0.0/24`), e o Caddy terá o IP
     `172.28.0.10`, o único na lista;
   - de qualquer outro endereço, o cabeçalho é ignorado: senão, qualquer um trocaria de "IP" a
     cada requisição para escapar do limite. Por isso não se usa `*` (confiar em todos);
   - o uvicorn lê o cabeçalho da direita para a esquerda e fica com o primeiro IP que não é de
     proxy. Um IP falso que o atacante escreva à esquerda não conta, porque o Caddy acrescenta o
     IP real no fim;
   - o código da app não mudou: `_ip()` continua usando `request.client.host`, que o uvicorn já
     entrega corrigido. Três testes passam as requisições pelo mesmo middleware do uvicorn e provam
     que cada funcionário tem o seu limite atrás do proxy, que o cabeçalho falsificado vindo de fora
     é ignorado e que o IP falso à esquerda não engana.

3. **Logs em produção: uma linha JSON por evento na saída padrão, sem arquivo.** Um contêiner é
   descartável, e o arquivo interno sumiria a cada deploy; o que sai na saída padrão o Docker guarda
   do lado de fora (`docker compose logs`). Cada serviço tem rotação de até 5 arquivos de 10 MB,
   para não encher o disco. JSON é o formato que ferramentas de busca e alerta de logs leem. Em
   desenvolvimento, nada muda (texto no terminal e `logs/app.log`, ADR-0011). A escolha entre os dois
   modos vem de `AMBIENTE`: só `desenvolvimento` liga o modo de desenvolvimento; qualquer outro
   valor, ou nenhum, é produção, o mesmo padrão seguro que já desliga o `/docs` (ADR-0015).

4. **Log de acesso do uvicorn desligado (`--no-access-log`).** Com o IP real chegando, cada linha
   desse log identificaria o funcionário (ADR-0008 e ADR-0011). Ele era redundante: o middleware da
   app já registra cada chamada à API com rota, status e tempo, sem o IP.

5. **Privacidade: o aviso da página não muda.** Para responder, o texto da pergunta e os trechos das
   políticas vão para a API do Groq, um fornecedor nos EUA. A página não diz isso: a decisão foi
   manter a tela sem menção a IA e registrar o envio no README e nesta ADR. Num sistema real, a LGPD
   pede transparência sobre o compartilhamento com terceiros, e o aviso de privacidade precisaria
   informá-lo.

6. **Imagem ARM conferida no CI.** As imagens base do Python, do pgvector e do Ollama têm versão
   ARM (conferido no Docker Hub). Um job novo do CI, "Imagem ARM (produção)", constrói a imagem
   numa máquina ARM do GitHub (gratuita para repositório público), sobe a API e confere que o
   `/api/saude` responde. Um problema de arquitetura aparece no CI, e não no servidor. Publicar a
   imagem fica para a entrega contínua (P4).

## Consequências

- **Uma instância só.** O limite de perguntas e a idempotência vivem na memória do processo
  (ADR-0013). Duas cópias da app teriam contagens separadas, e o limite dobraria sem ninguém
  perceber. Escalar exige mover esse estado para um armazenamento compartilhado (Redis).
- **O `FORWARDED_ALLOW_IPS` e o IP do proxy andam juntos.** Se um mudar sem o outro, o limite volta
  a ser um só para todos (proxy fora da lista) ou fica burlável (lista larga demais).
- **A administração do servidor é nossa:** atualizações de segurança do sistema, firewall, espaço em
  disco e certificados. É o custo de aprender e de não pagar.
- **Riscos da Oracle:** a máquina pode ser recuperada por ociosidade ou faltar capacidade. A
  mitigação é o plano B e os backups fora do servidor (P5).
- **Ficam para as próximas etapas,** cada uma com a sua ADR quando houver decisão: o servidor e o
  acesso por SSH (P2), domínio, HTTPS e HSTS (P3), entrega contínua (P4), backup e monitoramento
  (P5) e teste de carga (P6).
- **ADRs afetadas:** a ADR-0001 é substituída; a ADR-0011 continua valendo em desenvolvimento, mas
  em produção os logs vão para a saída padrão; a pendência da ADR-0009 (limite por IP quando o
  sistema fosse publicado) passa a funcionar também atrás do proxy.
