# ADR-0003: Leitor próprio de documentos com python-docx e pypdf

- **Status:** aceito
- **Data:** 2026-09-26
- **Responsável pela decisão:** Gustavo

## Contexto

As políticas estão em docx (4) e pdf (3). Para citar a fonte ("POL-RH-004, Banco de Horas, seção 5") e
não misturar públicos, a leitura precisa preservar:

- as seções numeradas (no docx, parágrafos com estilo "Título 1");
- os metadados do cabeçalho (código, versão, vigência);
- as tabelas, como a de faltas x dias de férias e a de horas extras por escala (5x2 x 6x1);
- as listas de condições.

## Opções consideradas

### Opção 1: Leitores prontos do LlamaIndex (`SimpleDirectoryReader`)

- Prós: uma linha de código lê a pasta inteira.
- Contras: devolve texto corrido; perde os títulos de seção e achata as tabelas, separando cada valor
  do nome da sua coluna. A estrutura teria de ser reconstruída depois, a partir de texto sem marcação.

### Opção 2: Leitor próprio com `python-docx` e `pypdf`

- Prós: controle total sobre seções, tabelas e listas; fácil de testar com as políticas reais; o
  resultado pode ser entregue ao LlamaIndex com metadados nas etapas seguintes.
- Contras: mais código para escrever e manter; um leitor por formato.

### Opção 3: Docling ou Unstructured

- Prós: detectam layout, tabelas e títulos automaticamente.
- Contras: dependências pesadas (algumas usam modelos de visão); exagero para 7 documentos bem
  formatados; comportamento difícil de entender e de depurar.

## Decisão

Opção 2. Os documentos são poucos e bem estruturados, e a qualidade da citação depende de preservar
essa estrutura desde a leitura.

## Consequências

- Cada leitor devolve uma lista de `Secao` (`src/rotasul_rh/modelos.py`), o formato comum às etapas
  seguintes.
- Cada linha de tabela vira uma frase "coluna: valor; coluna: valor.", para que cada valor continue
  junto do nome da sua coluna depois do chunking.
- Documentos com outra formatação (sem estilos de título, por exemplo) exigem ajuste no leitor; os
  testes com as políticas reais mostram quando isso acontece.
- O LlamaIndex continua na stack, mas só entra a partir do chunking e da indexação.
