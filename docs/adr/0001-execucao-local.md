# ADR-0001: Execução apenas local

- **Status:** aceito
- **Data:** 2026-09-26
- **Responsável pela decisão:** Gustavo

## Contexto

O assistente é um projeto de portfólio. A stack usa o Groq (na nuvem) para o modelo de linguagem, o
Ollama com `bge-m3` (local) para os embeddings e o PostgreSQL com pgvector (Docker) como banco.

O `bge-m3` precisa de cerca de 1,5 a 2 GB de RAM para rodar. Os planos gratuitos mais comuns de
hospedagem (Render, Railway, Fly.io) oferecem 512 MB, então publicar o sistema exigiria trocar peças da
stack ou usar uma plataforma específica.

## Opções consideradas

### Opção 1: Só local, com demonstração no README

- Prós: custo zero; nenhuma mudança na stack; um único ambiente para configurar; as políticas não saem
  da máquina.
- Contras: quem visita o repositório não consegue testar sem instalar Docker, Ollama e uv; a
  demonstração fica limitada a vídeo, GIF ou capturas de tela.

### Opção 2: Local para desenvolver e demo pública no Hugging Face Spaces

- Prós: link público para testar; o plano gratuito do Spaces tem RAM suficiente para o `bge-m3`;
  demonstra habilidade de deploy.
- Contras: dois ambientes e dois `.env`; exige banco gerenciado (Neon ou Supabase); o app "dorme"
  sem uso e demora a acordar; mais trabalho antes de o RAG estar maduro.

### Opção 3: Tudo por API, hospedado no Render com banco no Neon

- Prós: app leve e fácil de hospedar.
- Contras: troca o `bge-m3` local por embeddings por API; mais uma chave e mais um fornecedor; as
  políticas passam a sair da máquina.

## Decisão

Opção 1. O objetivo agora é a qualidade do RAG (leitura dos documentos, chunking, busca e respostas
com fonte), e não a infraestrutura. Rodar só local mantém a stack como foi definida e evita trabalho de
deploy antes de haver algo que valha a pena publicar.

## Consequências

- O README precisa de instruções claras para rodar do zero e de uma demonstração (GIF ou vídeo curto).
- Não há deploy na v1. Se isso mudar, um novo ADR substitui este, e a Opção 2 é o caminho mais
  provável.
- A interface é decidida em um ADR separado.
