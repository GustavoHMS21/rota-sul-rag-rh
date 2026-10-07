# ADR-0015: Padrões seguros para produção: cabeçalhos, /docs, saúde e contêiner

- **Status:** aceito
- **Data:** 2026-10-05
- **Responsável pela decisão:** Gustavo

## Contexto

A aplicação estava pronta para rodar, mas com padrões de desenvolvimento que, publicados, expõem
mais do que deveriam:

- **Nenhum cabeçalho de segurança.** O texto vindo da API já entrava na página com `textContent`
  (ADR-0008), mas não havia segunda camada contra XSS. A chave do RH fica no `sessionStorage` da aba,
  e um script injetado poderia lê-la e enviá-la para fora. A página também podia ser embutida em
  outro site (clickjacking).
- **`/docs`, `/redoc` e `/openapi.json` abertos.** A documentação automática descreve a API inteira
  para qualquer visitante.
- **`/api/saude` contava demais.** Dizia para qualquer um qual peça estava fora ("ollama: sem
  conexão", "groq: chave ausente"), o que revela a arquitetura e o estado de cada dependência.
- **O contêiner rodava como root,** sem healthcheck, e as respostas anunciavam o servidor
  (`server: uvicorn`).
- Ao revisar a conferência da chave do RH, apareceu um bug antigo: `secrets.compare_digest` com texto
  fora do ASCII levanta `TypeError`. Uma chave com acento derrubava a requisição com erro 500, sem
  contar como tentativa errada.

## Opções consideradas

### O que fazer com o /docs

#### Opção 1: Ligado só em desenvolvimento

- Prós: seguro por padrão (quem esquecer de configurar não expõe nada); o README continua valendo,
  porque o `.env.example` vem com desenvolvimento.
- Contras: em produção, a documentação só existe no código.

#### Opção 2: Protegido pela chave do RH

- Prós: continua existindo em produção.
- Contras: o navegador não manda o cabeçalho da chave sozinho; abrir o `/docs` fica incômodo, para
  pouco ganho.

#### Opção 3: Aberto

- Prós: simples; o código já é público no GitHub.
- Contras: a API se descreve inteira para qualquer visitante em produção.

### O que o /api/saude mostra

#### Opção 1: Só ok ou falha; o detalhe com a chave do RH

- Prós: basta para um healthcheck; quem está de fora não descobre a arquitetura nem qual peça caiu.
- Contras: depurar exige a chave.

#### Opção 2: Detalhe só para quem acessa da própria máquina

- Prós: prático.
- Contras: atrás de um proxy, toda requisição parece vir da própria máquina, e o detalhe vaza.

#### Opção 3: Como estava

- Prós: o mais útil para depurar.
- Contras: expõe a arquitetura e o estado de cada dependência.

## Decisão

1. **Cabeçalhos de segurança em todas as respostas,** aplicados pelo middleware que já existia:
   - `Content-Security-Policy`: script, estilo, imagem e conexões só do próprio servidor
     (`default-src 'self'`), imagem também de `data:` (o desenho da estrada no CSS),
     `object-src` e `base-uri` bloqueados, `form-action 'self'` e `frame-ancestors 'none'`. Mesmo
     que um script fosse injetado, ele não rodaria nem enviaria a chave do RH para fora. As páginas
     não têm script nem estilo inline, condição para essa política funcionar;
   - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (contra clickjacking, para
     navegadores sem `frame-ancestors`), `Referrer-Policy: no-referrer` e `Permissions-Policy`
     desligando câmera, microfone e localização;
   - `Cache-Control: no-store` em `/api/rh/*`: nem o navegador nem um proxy no caminho guardam cópia
     das perguntas.
2. **`/docs` só em desenvolvimento (Opção 1):** as rotas de documentação só existem com
   `AMBIENTE=desenvolvimento` no `.env`; qualquer outro valor, ou nenhum, desliga. O Swagger usa
   arquivos de CDN e script inline, então a CSP não se aplica a essas rotas, que só existem em
   desenvolvimento.
3. **`/api/saude`: só ok ou falha; o detalhe com a chave do RH (Opção 1).** Sem chave, responde
   `{"status": "ok"}` (200) ou `{"status": "falha"}` (503). Com a chave, mostra o estado de cada
   dependência. A chave passa pela mesma conferência da área do RH, com o bloqueio contra força bruta
   da ADR-0013: sem isso, a saúde seria um jeito de testar chaves sem limite.
4. **A chave do RH é comparada em bytes,** o que corrige o erro 500 com caracteres fora do ASCII.
5. **Contêiner endurecido:** usuário `app` sem privilégios (uid 1000), com o código e as dependências
   só para leitura e a pasta `logs/` como única gravável; `HEALTHCHECK` no `/api/saude`; e
   `--no-server-header`, para as respostas não anunciarem o servidor.

## Consequências

- Se a app for explorada, quem entrar não é root no contêiner.
- Toda mudança futura nas páginas precisa respeitar a CSP: nada de `<script>` ou `style=""` inline,
  nem arquivos de outros domínios. Um erro de CSP aparece no console do navegador.
- O HSTS (obrigar HTTPS no navegador) ficou de fora: só faz sentido com HTTPS, e entra junto com ele
  no deploy (ADR-0016).
- O healthcheck do contêiner mede prontidão, não só vida: sem a chave do Groq ou com o Ollama fora, o
  contêiner aparece como `unhealthy`, mesmo com o processo de pé.
- Quem desenvolve precisa de `AMBIENTE=desenvolvimento` no `.env` para ver o `/docs`. A ADR-0016
  passou a usar a mesma variável para o formato dos logs.
