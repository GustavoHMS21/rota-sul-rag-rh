# ADR-0009: Funcionário sem login e área do RH protegida por chave

- **Status:** aceito
- **Data:** 2026-09-28
- **Responsável pela decisão:** Gustavo

## Contexto

Com as perguntas registradas (ADR-0008), surgem dois perfis: o funcionário, que pergunta, e o RH,
que lê o histórico. O histórico não pode ficar aberto. O sistema roda só localmente (ADR-0001).

- **Autenticação:** quem é você.
- **Autorização:** o que você pode fazer.

## Opções consideradas

### Opção A: Funcionário sem login; área do RH protegida por uma chave

- Prós: simples; combina com o registro anônimo (se o sistema não sabe quem perguntou, não há como
  vazar quem perguntou o quê).
- Contras: não identifica o funcionário, então o público continua sendo escolhido na tela; uma chave
  única para todo o RH, sem saber qual analista acessou.

### Opção B: Login com usuário e senha, com papéis (funcionário e RH)

- Prós: autenticação completa; o público viria do cadastro, sem ser escolhido na tela.
- Contras: bem mais código (tabela de usuários, senha com hash, sessão); alguém precisa criar as
  contas; o registro passaria a identificar a pessoa, o que pesa mais na LGPD.

### Opção C: Login corporativo (SSO com Microsoft ou Google)

- Prós: é o que uma empresa real usaria.
- Contras: exige uma conta corporativa configurada; inviável num portfólio local.

## Decisão

Opção A, neste primeiro projeto.

- A página e a API do funcionário são abertas.
- As rotas `/api/rh/*` exigem o cabeçalho `X-Chave-RH` igual a `RH_CHAVE_ACESSO` do `.env`. A
  comparação usa `secrets.compare_digest`, em tempo constante, para o tempo de resposta não dar
  pistas da chave.
- Sem `RH_CHAVE_ACESSO` definida, a área do RH fica desativada (503), em vez de aberta.
- A página `/rh` em si é pública (não contém dados); ela pede a chave e a guarda só na aba do
  navegador (`sessionStorage`), que a apaga ao ser fechada.
- A hospedagem continua local (ADR-0001). A etapa seguinte prepara um `docker compose` que sobe o
  sistema inteiro com um comando; o deploy público fica para um ADR futuro.

## Consequências

- A dependência `exigir_chave_do_rh` concentra a autorização: trocar para a Opção B significa trocar
  essa função e a página de entrada, sem mexer nas rotas.
- A chave precisa ser forte e ficar só no `.env` (fora do Git). Sugestão para gerar:
  `uv run python -c "import secrets; print(secrets.token_urlsafe(24))"`.
- Sem HTTPS (tudo local), a chave trafega em texto claro na máquina. Num deploy, HTTPS é
  obrigatório.
- Se o sistema for publicado, a página do funcionário precisará de limite de perguntas por IP, para
  ninguém esgotar o limite diário do Groq (1.000 requisições no plano gratuito).
