// Página do funcionário: envia a pergunta para a API e mostra a resposta com a fonte.
// Todo texto vindo da API é inserido com textContent (nunca innerHTML), para não executar HTML.

const formulario = document.getElementById("formulario");
const campoPublico = document.getElementById("publico");
const campoPergunta = document.getElementById("pergunta");
const contador = document.getElementById("contador");
const botaoEnviar = document.getElementById("enviar");
const status = document.getElementById("status");
const resultado = document.getElementById("resultado");
const textoResposta = document.getElementById("texto-resposta");
const fontes = document.getElementById("fontes");
const avaliacao = document.getElementById("avaliacao");
const obrigado = document.getElementById("obrigado");
const trechos = document.getElementById("trechos");
const listaTrechos = document.getElementById("lista-trechos");

const CHAVE_PUBLICO = "rotasul-publico";
let idDaResposta = null;

// Lembra o público escolhido neste navegador. O armazenamento pode estar bloqueado (janela
// anônima, por exemplo), então a página funciona igual sem ele.
try {
  const salvo = localStorage.getItem(CHAVE_PUBLICO);
  if (salvo !== null) campoPublico.value = salvo;
} catch {}
campoPublico.addEventListener("change", () => {
  try { localStorage.setItem(CHAVE_PUBLICO, campoPublico.value); } catch {}
});

campoPergunta.addEventListener("input", () => {
  contador.textContent = `${campoPergunta.value.length}/500`;
});

// Enter envia; Shift+Enter quebra a linha.
campoPergunta.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.shiftKey) {
    evento.preventDefault();
    formulario.requestSubmit();
  }
});

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const pergunta = campoPergunta.value.trim();
  if (pergunta.length < 3) {
    mostrarStatus("Escreva sua dúvida antes de perguntar.", true);
    campoPergunta.focus();
    return;
  }

  botaoEnviar.disabled = true;
  resultado.hidden = true;
  mostrarStatus("Consultando as políticas...");

  try {
    const resposta = await fetch("/api/perguntas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta, publico: campoPublico.value || null }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrarStatus(mensagemDeErro(resposta.status, dados), true);
      return;
    }
    mostrarStatus("");
    mostrarResposta(dados);
  } catch {
    mostrarStatus("Não foi possível falar com o assistente. Confira se o servidor está rodando.", true);
  } finally {
    botaoEnviar.disabled = false;
  }
});

avaliacao.addEventListener("click", async (evento) => {
  const botao = evento.target.closest("button[data-util]");
  if (!botao || !idDaResposta) return;
  const util = botao.dataset.util === "true";
  for (const b of avaliacao.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b === botao));
  }
  try {
    const resposta = await fetch(`/api/perguntas/${idDaResposta}/avaliacao`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ util }),
    });
    obrigado.hidden = !resposta.ok;
  } catch {}
});

function mostrarResposta(dados) {
  idDaResposta = dados.id;
  resultado.classList.toggle("recusa", dados.tipo !== "respondida");
  renderizarTexto(textoResposta, dados.resposta);

  fontes.replaceChildren();
  if (dados.fontes.length) {
    const rotulo = document.createElement("strong");
    rotulo.textContent = dados.fontes.length > 1 ? "Fontes: " : "Fonte: ";
    fontes.append(rotulo, dados.fontes.join("; "));
  }

  // Sem id (o registro falhou), não há onde guardar a avaliação.
  avaliacao.hidden = !dados.id;
  obrigado.hidden = true;
  for (const b of avaliacao.querySelectorAll("button")) b.setAttribute("aria-pressed", "false");

  listaTrechos.replaceChildren(...dados.trechos.map(criarTrecho));
  trechos.hidden = dados.trechos.length === 0;
  trechos.open = false;

  resultado.hidden = false;
}

// O modelo às vezes separa públicos em linhas começando com "- " e usa **negrito**.
// Linhas "- " viram itens de lista; os asteriscos são removidos.
function renderizarTexto(alvo, texto) {
  alvo.replaceChildren();
  let lista = null;
  for (const bruta of texto.split("\n")) {
    const linha = bruta.replaceAll("**", "").trim();
    if (!linha) { lista = null; continue; }
    if (linha.startsWith("- ")) {
      if (!lista) { lista = document.createElement("ul"); alvo.append(lista); }
      const item = document.createElement("li");
      item.textContent = linha.slice(2);
      lista.append(item);
    } else {
      lista = null;
      const paragrafo = document.createElement("p");
      paragrafo.textContent = linha;
      alvo.append(paragrafo);
    }
  }
}

function criarTrecho(trecho) {
  const bloco = document.createElement("div");
  bloco.className = "trecho";
  const cabecalho = document.createElement("div");
  cabecalho.className = "trecho-cabecalho";
  const titulo = document.createElement("div");
  titulo.textContent = `${trecho.fonte}: ${trecho.titulo}`;
  const similaridade = document.createElement("span");
  similaridade.textContent = `similaridade ${trecho.similaridade.toFixed(2)}`;
  cabecalho.append(titulo, similaridade);
  const texto = document.createElement("p");
  texto.textContent = trecho.texto;
  bloco.append(cabecalho, texto);
  return bloco;
}

function mensagemDeErro(codigo, dados) {
  if (codigo === 422) return "Escreva uma pergunta de 3 a 500 caracteres.";
  if (typeof dados?.detail === "string") return dados.detail;
  return "Algo deu errado. Tente de novo.";
}

function mostrarStatus(texto, erro = false) {
  status.textContent = texto;
  status.classList.toggle("erro", erro);
}
