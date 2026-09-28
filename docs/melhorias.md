# Melhorias futuras

Pontos conhecidos que não bloqueiam a v1. Cada um diz de onde veio e como seria medido.

## Busca

### Perguntas curtas sobre linhas de tabela ("licença-paternidade")

- **Sintoma:** "Quantos dias de licença-paternidade?" recebe "Não encontrei essa informação nas
  políticas", embora a resposta esteja na POL-RH-008, seção 4 (5 dias consecutivos). A versão
  "Quantos dias de licença-paternidade eu tenho?" é respondida corretamente.
- **Causa:** a seção de faltas justificadas é uma tabela com 8 motivos num único chunk; o vetor fica
  diluído entre os 8 assuntos, e a frase curta não traz a seção para os 5 trechos enviados ao modelo.
  Na avaliação da busca, a versão longa já aparecia só em 5º lugar (ADR-0006).
- **Comportamento atual:** seguro. O assistente diz que não encontrou, em vez de inventar.
- **Caminhos:**
  - busca híbrida: somar ao vetor uma busca por palavra exata (`tsvector` do Postgres, em
    português), que acharia o termo "licença-paternidade";
  - uma linha de tabela por chunk: cada motivo ganha o próprio vetor (com o cabeçalho de contexto
    da seção).
- **Como medir:** acrescentar a versão curta ao gabarito e comparar hit@k (avaliação da busca) e o
  eval da geração antes e depois.

### Vocabulário diferente da política ("botina estragou" x "EPI danificado")

- Similaridade baixa (0,438) porque a política usa outras palavras. Busca híbrida ou uma lista de
  sinônimos ajudariam. Origem: ADR-0006.

## Avaliação

- **Fatos por texto exato são rígidos demais:** 28 de 42 respostas passam, mas 40 estão completas
  quando lidas (outra redação). Reduzir os fatos ao essencial (números e prazos) ou usar um segundo
  modelo como avaliador (LLM-as-judge). Origem: ADR-0007.
- **Mais casos de manipulação:** tentativas em outro idioma ou escondidas em textos longos. Os 7
  casos atuais estão no gabarito desde o ADR-0010.

## Qualidade e operação

- **Capacidade no plano gratuito do Groq:** o limite de 8.000 tokens por minuto comporta umas 4 ou
  5 perguntas por minuto. Numa rajada de 6 perguntas simultâneas, três pessoas esperaram de 25 a 31
  segundos (medido pelos logs, ADR-0011). Caminhos: plano pago, fila com aviso de espera na tela,
  cache para perguntas repetidas ou prompt menor. Origem: ADR-0011.
- **Métricas e alertas** (erros por hora, tempo médio por dia) sobre os logs em JSON, com
  ferramentas como Prometheus e Grafana. Origem: ADR-0011.
- **CI no GitHub** (testes rápidos e ruff a cada push).
- **Máscara de dados pessoais:** não reconhece nomes e doenças escritos por extenso; reconhecimento
  de entidades (NER) seria o próximo passo. Origem: ADR-0008.
- **Aviso de retenção na tela** diz "180 dias" fixo; deveria vir de `RETENCAO_DIAS`. Origem: ADR-0008.

## Perguntas para o negócio (RH)

- **Motorista conta como "operação"** nas seções que separam administrativo e operação (como pedir
  férias, vale-refeição)? Hoje o motorista recebe só os parágrafos gerais. Origem: ADR-0004.
- **Política de Jornada de Motoristas** é citada no Banco de Horas, mas não está na base.
