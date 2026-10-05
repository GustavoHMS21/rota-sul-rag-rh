// Página do funcionário: envia a pergunta para a API e mostra a resposta com a fonte.
// Todo texto vindo da API é inserido com textContent (nunca innerHTML), para não executar HTML.

const formulario = document.getElementById("formulario");
const campoPublico = document.getElementById("publico");
const campoPergunta = document.getElementById("pergunta");
const contador = document.getElementById("contador");
const botaoEnviar = document.getElementById("enviar");
const rotuloEnviar = botaoEnviar.querySelector("span");
const sugestoes = document.getElementById("sugestoes");
const status = document.getElementById("status");
const resultado = document.getElementById("resultado");
const tituloResposta = document.getElementById("resposta-titulo");
const textoResposta = document.getElementById("texto-resposta");
const fontes = document.getElementById("fontes");
const avaliacao = document.getElementById("avaliacao");
const obrigado = document.getElementById("obrigado");
const trechos = document.getElementById("trechos");
const listaTrechos = document.getElementById("lista-trechos");

const CHAVE_PUBLICO = "rotasul-publico";
const TITULOS = {
  respondida: "Resposta",
  nao_encontrado: "Não encontrei nas políticas",
  dado_pessoal: "Assunto individual",
};
const EMAIL = /([\w.+-]+@[\w-]+(?:\.[\w-]+)+)/;
const TENTATIVAS = 3; // envio original + 2 reenvios com a mesma Idempotency-Key
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

campoPergunta.addEventListener("input", atualizarContador);

// Os assuntos frequentes só preenchem a pergunta; o funcionário revisa e envia.
sugestoes.addEventListener("click", (evento) => {
  const chip = evento.target.closest("button[data-pergunta]");
  if (!chip) return;
  campoPergunta.value = chip.dataset.pergunta;
  atualizarContador();
  campoPergunta.focus();
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
  rotuloEnviar.textContent = "Consultando...";
  resultado.hidden = true;
  mostrarStatus("Consultando as políticas...");

  try {
    const resposta = await enviarPergunta({ pergunta, publico: campoPublico.value || null });
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrarStatus(mensagemDeErro(resposta.status, dados), true);
      return;
    }
    mostrarStatus("");
    mostrarResposta(dados);
  } catch {
    mostrarStatus("Não foi possível consultar as políticas agora. Tente de novo em instantes.", true);
  } finally {
    botaoEnviar.disabled = false;
    rotuloEnviar.textContent = "Perguntar";
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

// Envia a pergunta com uma Idempotency-Key nova e, se a rede falhar, reenvia com a MESMA chave.
// Se a primeira tentativa chegou ao servidor, ele devolve a resposta já pronta em vez de
// responder e registrar a pergunta duas vezes. 409 = a primeira ainda está sendo respondida.
async function enviarPergunta(corpo) {
  const chave = gerarChave();
  for (let tentativa = 1; ; tentativa++) {
    try {
      const resposta = await fetch("/api/perguntas", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": chave },
        body: JSON.stringify(corpo),
      });
      if (resposta.status !== 409 || tentativa >= TENTATIVAS) return resposta;
    } catch (erro) {
      if (tentativa >= TENTATIVAS) throw erro;
    }
    await esperar(1000 * tentativa);
  }
}

function gerarChave() {
  if (crypto.randomUUID) return crypto.randomUUID();
  // Fora de contexto seguro (http sem ser localhost), randomUUID não existe.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function esperar(milissegundos) {
  return new Promise((resolver) => setTimeout(resolver, milissegundos));
}

function mostrarResposta(dados) {
  idDaResposta = dados.id;
  resultado.classList.toggle("recusa", dados.tipo !== "respondida");
  tituloResposta.textContent = TITULOS[dados.tipo] ?? "Resposta";
  renderizarTexto(textoResposta, dados.resposta);

  fontes.replaceChildren();
  if (dados.fontes.length) {
    const rotulo = document.createElement("span");
    rotulo.className = "fontes-rotulo";
    rotulo.textContent = dados.fontes.length > 1 ? "Fontes" : "Fonte";
    fontes.append(rotulo, ...dados.fontes.map(criarSeloDeFonte));
  }

  // Sem id (o registro falhou), não há onde guardar a avaliação.
  avaliacao.hidden = !dados.id;
  obrigado.hidden = true;
  for (const b of avaliacao.querySelectorAll("button")) b.setAttribute("aria-pressed", "false");

  // Mostra só o texto oficial das seções citadas, uma vez cada.
  const citados = new Map();
  for (const trecho of dados.trechos) {
    if (dados.fontes.includes(trecho.fonte) && !citados.has(trecho.fonte)) {
      citados.set(trecho.fonte, trecho);
    }
  }
  listaTrechos.replaceChildren(...[...citados.values()].map(criarTrecho));
  trechos.hidden = citados.size === 0;
  trechos.open = false;

  resultado.hidden = false;
  resultado.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// O texto às vezes separa públicos em linhas começando com "- " e usa **negrito**.
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
      preencherComLinks(item, linha.slice(2));
      lista.append(item);
    } else {
      lista = null;
      const paragrafo = document.createElement("p");
      preencherComLinks(paragrafo, linha);
      alvo.append(paragrafo);
    }
  }
}

// Transforma e-mails do texto em links mailto, sem interpretar HTML.
function preencherComLinks(alvo, texto) {
  for (const [indice, parte] of texto.split(EMAIL).entries()) {
    if (!parte) continue;
    if (indice % 2 === 1) {
      const link = document.createElement("a");
      link.href = `mailto:${parte}`;
      link.textContent = parte;
      alvo.append(link);
    } else {
      alvo.append(parte);
    }
  }
}

function criarSeloDeFonte(fonte) {
  const selo = document.createElement("span");
  selo.className = "selo-fonte";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const desenho = document.createElementNS("http://www.w3.org/2000/svg", "path");
  desenho.setAttribute("d", "M7 3h7l4 4v14H7z M14 3v4h4 M10 12h5 M10 16h5");
  svg.append(desenho);
  selo.append(svg, fonte);
  return selo;
}

function criarTrecho(trecho) {
  const bloco = document.createElement("article");
  bloco.className = "trecho";
  const cabecalho = document.createElement("h3");
  cabecalho.className = "trecho-cabecalho";
  cabecalho.textContent = trecho.titulo;
  const origem = document.createElement("span");
  origem.textContent = trecho.fonte;
  cabecalho.append(origem);
  const texto = document.createElement("p");
  texto.textContent = trecho.texto;
  bloco.append(cabecalho, texto);
  return bloco;
}

function atualizarContador() {
  contador.textContent = `${campoPergunta.value.length}/500`;
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
