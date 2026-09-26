# Briefing: Assistente de Políticas de RH

> Caso simulado para portfólio. A Rota Sul Logística Ltda. é uma empresa fictícia.

## Cliente

**Rota Sul Logística Ltda.**: transportadora e operadora logística com sede em Campinas (SP).

- **Funcionários:** 220
  - 58 no administrativo da matriz (regime híbrido)
  - 104 no CD de Jundiaí (operação em turnos e motoristas)
  - 58 no CD de Sumaré (operação em turnos e motoristas)
- **Contato:** Carla Mendes, gerente de RH

## Problema

- O time de RH tem 3 pessoas e recebe cerca de **350 perguntas por mês** sobre políticas internas:
  férias, banco de horas, benefícios, home office, atestados, uniforme e EPI, adiantamento salarial.
- As analistas gastam cerca de **40% do tempo** respondendo essas perguntas.
- Cada analista responde de um jeito, e não há padronização.
- Já houve **reclamação trabalhista** por causa de uma resposta errada dada por escrito.

## Objetivo

Um assistente web em que o funcionário faz uma pergunta em linguagem natural e recebe uma resposta
baseada **apenas nas políticas oficiais**, com a **fonte citada**.

## Regras de negócio da v1

1. **Somente as políticas.** Responder apenas com base nas políticas em `data/politicas/`. Nunca usar
   conhecimento geral do modelo para completar uma resposta.
2. **Fonte sempre citada.** Toda resposta cita código da política, nome e seção
   (ex.: POL-RH-004, Banco de Horas, seção 5).
3. **Não sabe, diz que não sabe.** Se a resposta não estiver nas políticas, dizer que não sabe e
   orientar: "Não encontrei essa informação nas políticas. Fale com o RH pelo e-mail
   rh@rotasul.com.br."
4. **Dados pessoais não são respondidos.** Perguntas sobre dados pessoais (saldo de férias, holerite,
   saldo do banco de horas, valores individuais) não são respondidas. O sistema reconhece esse tipo de
   pergunta e devolve a mesma orientação de procurar o RH.
5. **Sem mistura de públicos.** Algumas regras variam conforme o público (administrativo da matriz,
   operação dos CDs em escala 5x2 ou 6x1, motoristas). A resposta não pode misturar regras de públicos
   diferentes.

## Políticas oficiais

| Código | Nome | Formato |
|---|---|---|
| POL-RH-003 | Férias | docx |
| POL-RH-004 | Banco de Horas | docx |
| POL-RH-005 | Home Office e Trabalho Híbrido | docx |
| POL-RH-006 | Benefícios | pdf |
| POL-RH-008 | Atestados e Faltas | pdf |
| POL-RH-009 | Uniforme e EPI | pdf |
| POL-RH-010 | Adiantamento Salarial | docx |

## Fora do escopo da v1 (roadmap)

- Integração com o sistema de folha de pagamento
- Painel para o RH subir documentos
- Envio automático de e-mail ao RH
- Atendimento por WhatsApp
- Várias empresas no mesmo sistema (multi-tenant)
