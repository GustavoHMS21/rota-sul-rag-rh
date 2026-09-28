# ADR-0006: Perguntas sem resposta decididas pelo LLM, sem nota mínima na busca

- **Status:** aceito
- **Data:** 2026-09-27
- **Responsável pela decisão:** Gustavo

## Contexto

A busca sempre devolve os chunks mais parecidos, mesmo quando a pergunta não tem resposta nas
políticas. As regras de negócio 3 (não sabe, diz que não sabe) e 4 (dados pessoais não são
respondidos) precisam de um mecanismo para recusar.

A avaliação da busca (`uv run python -m rotasul_rh.avaliacao_busca`, resultado em
`evals/resultados/busca.json`) mediu a similaridade do 1º resultado nas 50 perguntas do gabarito:

| Grupo | Mínima | Mediana | Máxima |
|---|---|---|---|
| Com resposta (39) | 0,438 | 0,691 | 0,786 |
| Sem resposta (11) | 0,438 | 0,580 | 0,689 |

Efeito de um corte ("abaixo de X, responder que não encontrou"):

| Corte | Fora das políticas recusadas | Dado pessoal recusado | Recusas indevidas |
|---|---|---|---|
| 0,50 | 2 de 6 | 0 de 5 | 1 de 39 |
| 0,55 | 4 de 6 | 0 de 5 | 1 de 39 |
| 0,60 | 6 de 6 | 0 de 5 | 6 de 39 |
| 0,65 | 6 de 6 | 2 de 5 | 11 de 39 |
| 0,70 | 6 de 6 | 5 de 5 | 23 de 39 |

As faixas se sobrepõem: "Minha botina estragou. Preciso pagar pela nova?" (tem resposta) e "Qual o
valor do salário mínimo em 2026?" (não tem) tiveram a mesma similaridade, 0,438. E as perguntas de
dado pessoal ficam altas ("Qual o meu saldo no banco de horas?": 0,656), porque falam do mesmo assunto
das seções. A similaridade mede o assunto, não se a pergunta pode ser respondida.

## Opções consideradas

### Opção A: Corte fixo de 0,60 na busca

- Prós: recusa todas as perguntas fora das políticas antes de chegar ao LLM.
- Contras: recusa 15% das perguntas legítimas; não resolve dado pessoal.

### Opção B: Sem corte; o LLM decide pelo conteúdo dos trechos

- Prós: o modelo lê os trechos e percebe quando eles não respondem, ou quando a pergunta pede um dado
  individual ("meu saldo") que nenhuma política tem.
- Contras: depende de o modelo obedecer ao prompt.

### Opção C: Opção B com checagem de dado pessoal por palavras-chave antes do LLM

- Prós: camada extra e barata para a regra 4.
- Contras: lista de palavras é frágil ("quanto eu tenho de banco?" escapa).

## Decisão

Opção B. A busca não aplica nota mínima; o prompt da geração instrui o modelo a usar a resposta padrão
quando os trechos não respondem à pergunta e quando ela pede dados individuais.

## Consequências

- A etapa de geração precisa medir, com as 11 perguntas sem resposta do gabarito, se o modelo recusa
  quando deve. Se falhar em dado pessoal, a Opção C é acrescentada.
- A similaridade continua sendo registrada em cada busca, para monitorar e rever a decisão com dados
  de uso real.
- Achados da avaliação da busca, sem mudança por enquanto (evitar ajustar o sistema para acertar
  perguntas específicas do gabarito):
  - hit@1 87%, hit@3 97%, hit@5 100%, MRR 0,919.
  - "Licença-paternidade" só aparece em 5º: a seção de faltas justificadas tem 8 motivos numa tabela,
    e o vetor fica diluído. Busca híbrida (palavra exata) ou uma linha de tabela por chunk resolveriam.
  - "Botina estragou" tem similaridade baixa porque a política diz "EPI danificado". Sinônimos ou busca
    híbrida ajudariam.
  - Para quem é do CD, "Como funciona" do Home Office (até 2 dias) chega junto com "Quem pode" (não
    elegível), porque vale para todos. O prompt precisa priorizar a elegibilidade.
