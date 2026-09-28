// Área do RH: lê o resumo e as perguntas registradas, enviando a chave no cabeçalho X-Chave-RH.
// A chave fica no sessionStorage (só nesta aba). Texto da API entra com textContent.

const entrada = document.getElementById("entrada");
const campoChave = document.getElementById("chave");
const status = document.getElementById("status");
const painel = document.getElementById("painel");
const numeros = document.getElementById("numeros");
const campoTipo = document.getElementById("tipo");
const linhas = document.getElementById("linhas");
const vazio = document.getElementById("vazio");

const CHAVE_SESSAO = "rotasul-chave-rh";
const PUBLICOS = {
  administrativo: "Administrativo",
  operacao_5x2: "CD 5x2",
  operacao_6x1: "CD 6x1",
  motorista: "Motorista",
};
const TIPOS = {
  respondida: "Respondida",
  nao_encontrado: "Não encontrado",
  dado_pessoal: "Dado pessoal",
};

let chave = null;
try { chave = sessionStorage.getItem(CHAVE_SESSAO); } catch {}
if (chave) carregar();

entrada.addEventListener("submit", (evento) => {
  evento.preventDefault();
  chave = campoChave.value.trim();
  try { sessionStorage.setItem(CHAVE_SESSAO, chave); } catch {}
  carregar();
});

document.getElementById("atualizar").addEventListener("click", carregar);
campoTipo.addEventListener("change", carregar);
document.getElementById("sair").addEventListener("click", () => {
  try { sessionStorage.removeItem(CHAVE_SESSAO); } catch {}
  chave = null;
  painel.hidden = true;
  entrada.hidden = false;
  campoChave.value = "";
});

async function carregar() {
  mostrarStatus("Carregando...");
  const tipo = campoTipo.value ? `&tipo=${campoTipo.value}` : "";
  try {
    const [resumo, interacoes] = await Promise.all([
      buscar("/api/rh/resumo"),
      buscar(`/api/rh/interacoes?limite=200${tipo}`),
    ]);
    mostrarResumo(resumo);
    mostrarInteracoes(interacoes);
    entrada.hidden = true;
    painel.hidden = false;
    mostrarStatus("");
  } catch (erro) {
    mostrarStatus(erro.message, true);
    if (erro.status === 401) {
      try { sessionStorage.removeItem(CHAVE_SESSAO); } catch {}
      entrada.hidden = false;
      painel.hidden = true;
    }
  }
}

async function buscar(caminho) {
  const resposta = await fetch(caminho, { headers: { "X-Chave-RH": chave ?? "" } });
  const dados = await resposta.json();
  if (!resposta.ok) {
    const erro = new Error(typeof dados.detail === "string" ? dados.detail : "Falha ao carregar.");
    erro.status = resposta.status;
    throw erro;
  }
  return dados;
}

function mostrarResumo(r) {
  const recusas = r.nao_encontrado + r.dado_pessoal;
  const percentual = r.total ? Math.round((recusas / r.total) * 100) : 0;
  const itens = [
    [r.total, "perguntas registradas"],
    [r.respondidas, "respondidas"],
    [`${recusas} (${percentual}%)`, "encaminhadas ao RH"],
    [r.avaliacoes_uteis, "👍 ajudou"],
    [r.avaliacoes_nao_uteis, "👎 não ajudou"],
  ];
  numeros.replaceChildren(
    ...itens.map(([valor, rotulo]) => {
      const bloco = document.createElement("div");
      bloco.className = "numero";
      const b = document.createElement("b");
      b.textContent = valor;
      const span = document.createElement("span");
      span.textContent = rotulo;
      bloco.append(b, span);
      return bloco;
    }),
  );
}

function mostrarInteracoes(interacoes) {
  vazio.hidden = interacoes.length > 0;
  linhas.replaceChildren(
    ...interacoes.map((i) => {
      const tr = document.createElement("tr");
      const tipo = document.createElement("span");
      tipo.className = `etiqueta ${i.tipo}`;
      tipo.textContent = TIPOS[i.tipo] ?? i.tipo;
      const avaliacao = i.avaliacao_util === null ? "" : i.avaliacao_util ? "👍" : "👎";
      const celulas = [
        new Date(i.criado_em).toLocaleString("pt-BR"),
        PUBLICOS[i.publico] ?? "Não informado",
        i.pergunta,
        tipo,
        i.resposta,
        i.fontes.join(", "),
        avaliacao,
      ];
      for (const [indice, valor] of celulas.entries()) {
        const td = document.createElement("td");
        if (indice === 4) td.className = "resposta-curta";
        if (valor instanceof Node) td.append(valor);
        else td.textContent = valor;
        tr.append(td);
      }
      return tr;
    }),
  );
}

function mostrarStatus(texto, erro = false) {
  status.textContent = texto;
  status.classList.toggle("erro", erro);
}
