# ADR-0008: Interface web e registro anônimo das perguntas

- **Status:** aceito
- **Data:** 2026-09-28
- **Responsável pela decisão:** Gustavo

## Contexto

O assistente respondia só pela linha de comando. O objetivo do projeto é um assistente web: o
funcionário escreve a pergunta, escolhe o público e recebe a resposta com a fonte. A interface usa
FastAPI e uma página HTML simples (ADR-0002).

Além de responder, é importante guardar as respostas:

- **Auditoria:** a Rota Sul já teve uma reclamação trabalhista por uma resposta errada por escrito.
  Guardar o que o assistente respondeu, com a fonte e o modelo, permite provar o que foi dito.
- **Melhoria contínua:** respostas ruins viram casos do gabarito.
- **Informação para o RH:** perguntas sem resposta mostram lacunas nas políticas.

Mas os funcionários vão digitar dados pessoais ("meu CPF é...", informações de saúde), e dado de
saúde é dado sensível pela LGPD.

## Opções consideradas para o registro

### Opção A: Guardar tudo como veio

- Prós: simples.
- Contras: guarda dados pessoais e sensíveis sem necessidade.

### Opção B: Guardar de forma anônima, com máscara e prazo

- Prós: mantém o valor de auditoria e de melhoria; nada identifica quem perguntou; reduz dados
  pessoais no texto; os registros não ficam para sempre.
- Contras: a máscara por padrões de texto não pega tudo (um nome ou uma doença escrita por extenso
  passam); números no formato de telefone fixo são mascarados mesmo quando não são telefone.

### Opção C: Não guardar o texto da pergunta

- Prós: máxima proteção.
- Contras: perde quase todo o valor de auditoria e de melhoria.

## Decisão

Opção B.

**Registro** (tabela `interacoes`): data e hora, pergunta mascarada, público escolhido, tipo da
resposta, resposta mostrada, fontes citadas, trechos consultados com a similaridade, modelo, motivo
da troca pela resposta padrão (se houve), tempo de resposta e a avaliação 👍/👎 do funcionário.

**Anonimato e LGPD:**

- nada identifica quem perguntou: sem usuário, IP ou navegador (a autenticação do funcionário ficou
  de fora, ADR-0009);
- CPF, e-mail e telefone são trocados por `[CPF]`, `[E-MAIL]` e `[TELEFONE]` antes de gravar;
  mascarar a mais é o erro mais seguro;
- os registros com mais de `RETENCAO_DIAS` (padrão 180) são apagados a cada nova gravação;
- a tela avisa que as perguntas são registradas de forma anônima e pede para não informar dados
  pessoais.

**Falha no registro não derruba o atendimento:** se a gravação falhar, o funcionário recebe a
resposta mesmo assim (sem a opção de avaliar), e o erro vai para o log do servidor.

**Interface:**

| Rota | Função |
|---|---|
| `GET /` | página do funcionário |
| `POST /api/perguntas` | pergunta e público → resposta, fontes e trechos consultados |
| `POST /api/perguntas/{id}/avaliacao` | 👍/👎 |
| `GET /api/saude` | estado do banco, do Ollama e da configuração do Groq |
| `GET /rh`, `GET /api/rh/*` | área do RH (ADR-0009) |
| `GET /docs` | documentação automática da API |

- Entrada validada pelo Pydantic antes do RAG: pergunta de 3 a 500 caracteres (protege o limite de
  tokens do Groq) e público restrito às opções da tela.
- Erros viram códigos HTTP com mensagem amigável, sem detalhes internos: 422 (entrada inválida), 429
  (limite do Groq), 503 (Ollama, banco ou Groq indisponível).
- Página em HTML, CSS e JavaScript puro, servida pelo próprio FastAPI; o texto da API entra na
  página com `textContent`, nunca como HTML, para não executar conteúdo vindo de fora.
- Os trechos consultados aparecem numa seção recolhível ("Ver trechos das políticas consultados"),
  para transparência e para a demonstração do RAG.
- O público escolhido fica guardado no navegador (`localStorage`), para não ser escolhido de novo.

## Consequências

- O texto do aviso na tela diz "180 dias"; se `RETENCAO_DIAS` mudar, o aviso precisa mudar junto.
- A máscara não reconhece dados pessoais escritos por extenso (nomes, doenças). Uma camada com
  reconhecimento de entidades (NER) seria o próximo passo, se o uso real mostrar necessidade.
- O registro permite medir, com dados reais, as decisões tomadas com o gabarito (por exemplo, a taxa
  de recusas do ADR-0006).
