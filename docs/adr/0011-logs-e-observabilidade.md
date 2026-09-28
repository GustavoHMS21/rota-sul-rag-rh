# ADR-0011: Logs estruturados com código por requisição, sem o texto das perguntas

- **Status:** aceito
- **Data:** 2026-09-28
- **Responsável pela decisão:** Gustavo

## Contexto

Até aqui, um erro aparecia só no terminal do servidor, sem data e hora, e se perdia quando o
terminal era fechado. Não dava para responder perguntas como:

- quando o erro aconteceu e quantas vezes;
- se o Groq precisou de novas tentativas (o SDK repete em silêncio quando recebe 429);
- em qual fase a pergunta demorou (embedding, banco ou modelo);
- qual requisição corresponde à reclamação de um funcionário ("deu erro às 14h").

Sem log, a investigação depende de reproduzir o problema. Problemas intermitentes, como o limite de
uso do Groq com várias pessoas perguntando ao mesmo tempo, dificilmente se repetem num teste.

## Decisão

1. **Código por requisição.** Cada chamada ganha um código curto (`a1b2c3d4`) guardado numa
   `ContextVar`, que aparece em todas as linhas de log da requisição, no cabeçalho `X-Request-ID` e
   na mensagem de erro mostrada ao funcionário ("Se falar com o RH, informe o código a1b2c3d4").
2. **Dois destinos:**
   - terminal: texto legível, com data, hora, nível, código e campos;
   - arquivo `logs/app.log`: uma linha JSON por evento, trocado à meia-noite e apagado depois de
     `LOG_DIAS` dias (padrão 14). A pasta fica fora do Git e da imagem Docker.
3. **Eventos registrados:** pergunta recebida (público e número de caracteres), busca (tempo do
   embedding, tempo do banco, trechos e similaridade máxima), modelo (tempo, tokens de entrada e de
   saída, motivo de parada), resposta entregue (tipo, fontes, id da interação), requisição concluída
   (rota, status, tempo), falhas com o traceback, resposta trocada pela verificação, tentativa de
   acesso à área do RH com chave errada, e as novas tentativas do SDK do Groq, promovidas de INFO
   para WARNING.
4. **Nunca o texto da pergunta ou da resposta.** A pergunta pode ter dado de saúde, e o arquivo de
   log não tem a máscara nem o prazo de 180 dias do banco (ADR-0008). O log guarda o id da
   interação, que liga ao registro mascarado quando for preciso ver o texto. Um teste faz uma
   pergunta com CPF e doença pelo caminho completo da API e confere que nenhum trecho dela aparece em
   nenhuma linha, nos dois formatos.
5. **Falhas só no log, não no banco,** por enquanto. O banco continua com as respostas entregues.

Como investigar:

```powershell
Select-String -Path logs\*.log -Pattern "a1b2c3d4"          # a história de uma requisição
Select-String -Path logs\*.log -Pattern '"nivel": "WARNING"' # novas tentativas, trocas, acessos negados
Select-String -Path logs\*.log -Pattern '"nivel": "ERROR"'   # falhas, com o traceback
```

## O que o log já mostrou

Uma rajada de 6 perguntas ao mesmo tempo (servidor local, plano gratuito do Groq):

| Requisição | Novas tentativas | Tempo total |
|---|---|---|
| 85a3c4a4 | 0 | 1,1 s |
| 7430eb99 | 0 | 0,8 s |
| dc1d4ce1 | 1 | 2,3 s |
| 95e2c96f | 1 | 25,3 s |
| 724cb417 | 1 | 29,3 s |
| c8725e71 | 2 | 30,8 s |

Todas foram respondidas, mas três pessoas esperaram de 25 a 31 segundos, porque o Groq pediu para
esperar até o limite de 8.000 tokens por minuto liberar. Sem o log, isso apareceria só como "às
vezes fica lento". Ficou registrado em `docs/melhorias.md` como limite de capacidade.

## Consequências

- Métricas (erros por hora, tempo médio por dia) e alertas ficam para depois: exigem ferramentas como
  Prometheus e Grafana. O formato JSON já é o que essas ferramentas leem.
- No modo Docker completo, o arquivo fica dentro do contêiner; a saída de texto aparece em
  `docker compose logs app`.
- Os campos do log são metadados; qualquer campo novo precisa passar pelo mesmo critério (nada do
  texto da pergunta ou da resposta).
