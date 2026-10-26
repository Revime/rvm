"use strict";
/* RVM - interface no navegador. Fala com o servidor local (agente/web.py). */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const estado = {
  aba: "cortar",
  ocupada: false,
  tarefas: [],
  tarefasYt: {},
  statusAnterior: {},
  episodios: [],
  filtro: lerLocal("rvm-filtro", "pendente"),
  config: null,
  chaves: {},
  arquivo: null,
  diagFeito: false,
  telemetria: null,
  hwLimiteCritico: Number(lerLocal("rvm-hw-limite-critico", "85")) || 85,
  hwAlertaIgnoradoAte: 0,
  hwLogsExtras: [],
  hwEndpointModo: "auto",
};

const NOME_ETAPA = { baixar: "Baixando", transcrever: "Transcrevendo", escolher: "Escolhendo trechos", editar: "Montando vídeos", postar: "Enviando ao YouTube" };
const ORDEM_ETAPAS = ["baixar", "transcrever", "escolher", "editar", "postar"];
const SO_ETAPA = { refazer: "editar", postar_youtube: "postar" };
const NOME_STATUS_TAREFA = { na_fila: "Na fila", rodando: "Trabalhando", concluida: "Pronto", erro: "Deu erro", cancelada: "Cancelada" };
const NOME_STATUS_CORTE = { pendente: "Pendente", aprovado: "Aprovado", rejeitado: "Rejeitado", renderizando: "Refazendo", postado: "Postado" };
const NOME_PRIVACIDADE = { public: "Público", unlisted: "Não listado", private: "Privado" };

/* ---------------------------------------------------------------- util */
function lerLocal(k, padrao) { try { return localStorage.getItem(k) || padrao; } catch (e) { return padrao; } }
function gravarLocal(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } }

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, {
    method: opcoes.method || (opcoes.body !== undefined ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-RVM": "1" },
    body: opcoes.body !== undefined ? JSON.stringify(opcoes.body) : undefined,
  });
  let dados = null;
  try { dados = await r.json(); } catch (e) { /* sem corpo */ }
  if (!r.ok) throw new Error((dados && dados.erro) || `Erro ${r.status}`);
  return dados;
}

let avisoTimer;
function aviso(msg, duracao = 2600) {
  const el = $("#aviso");
  el.textContent = msg;
  el.classList.add("mostrar");
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => el.classList.remove("mostrar"), duracao);
}

function mmss(seg) {
  seg = Math.max(0, Math.floor(seg || 0));
  const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
}

function duracaoTexto(seg) {
  seg = Math.round(seg);
  if (seg < 60) return `${seg} s`;
  const m = Math.floor(seg / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

function caminho(obj, rota) { return rota.split(".").reduce((o, k) => (o ? o[k] : undefined), obj); }

/* ---------------------------------------------------------------- abas */
function mostrarAba() {
  const nome = (location.hash || "#cortar").slice(1).split("/")[0];
  estado.aba = ["cortar", "cortes", "ajustes", "diagnostico"].includes(nome) ? nome : "cortar";
  $$(".painel").forEach((p) => (p.hidden = p.id !== `aba-${estado.aba}`));
  $$(".abas a").forEach((a) => a.setAttribute("aria-selected", String(a.dataset.aba === estado.aba)));
  if (estado.aba === "cortes") carregarCortes();
  if (estado.aba === "ajustes") carregarAjustes();
  if (estado.aba === "diagnostico" && !estado.diagFeito) rodarDiagnostico(false);
}
window.addEventListener("hashchange", mostrarAba);

/* ================================================================ FILA */
async function carregarTarefas() {
  const d = await api("/api/tarefas");
  estado.ocupada = d.ocupada;
  estado.tarefas = d.tarefas;
  desenharFila();
  desenharMotor();
  let temPostagemAtiva = false;
  for (const t of d.tarefas) {
    if (t.tipo === "postar_youtube" && ["na_fila", "rodando"].includes(t.status)) {
      temPostagemAtiva = true;
    }
    const antes = estado.statusAnterior[t.id];
    if (antes && antes !== t.status) {
      if (t.status === "concluida" && t.tipo === "processar") aviso(`Pronto: ${t.resultado.cortes || 0} cortes de "${t.titulo}"`);
      if (t.status === "concluida" && t.tipo === "refazer") aviso("Corte refeito");
      if (t.status === "concluida" && t.tipo === "postar_youtube") {
        const url = t.resultado && t.resultado.url ? ` (${t.resultado.url})` : "";
        aviso(`✓ Vídeo publicado no YouTube com sucesso!${url}`, 4500);
      }
      if (t.status === "erro") {
        if (t.tipo === "postar_youtube") {
          aviso(`✕ Falha ao postar no YouTube: ${t.erro || "verifique o status no corte"}`, 4500);
        } else {
          aviso("Uma tarefa deu erro. Veja na fila.");
        }
      }
      if (["concluida", "erro", "cancelada"].includes(t.status)) carregarCortes();
    }
    estado.statusAnterior[t.id] = t.status;
  }
  if (temPostagemAtiva && estado.episodios.length > 0) {
    desenharCortes();
  }
}

function desenharMotor() {
  const atual = estado.tarefas.find((t) => t.status === "rodando");
  const el = $("#motor");
  el.classList.toggle("ocupado", !!atual);
  $("#motor-texto").textContent = atual
    ? `${NOME_ETAPA[atual.etapa] || "Preparando"} ${Math.round((atual.pct || 0) * 100)}%`
    : estado.tarefas.some((t) => t.status === "na_fila") ? "Na fila" : "Livre";
}

function desenharFila() {
  const lista = $("#fila");
  const tarefas = estado.tarefas;
  $("#fila-vazia").hidden = tarefas.length > 0;
  $("#limpar-fila").hidden = !tarefas.some((t) => ["concluida", "erro", "cancelada"].includes(t.status));
  const vistos = new Set();
  tarefas.forEach((t, i) => {
    let li = lista.querySelector(`[data-id="${t.id}"]`);
    if (!li) {
      li = $("#tpl-tarefa").content.firstElementChild.cloneNode(true);
      li.dataset.id = t.id;
    }
    if (lista.children[i] !== li) lista.insertBefore(li, lista.children[i] || null);
    atualizarTarefa(li, t);
    vistos.add(t.id);
  });
  $$(".tarefa", lista).forEach((li) => { if (!vistos.has(li.dataset.id)) li.remove(); });
}

function atualizarTarefa(li, t) {
  li.className = `tarefa ${t.status}`;
  $(".tarefa-titulo", li).textContent = t.titulo || t.origem;
  const sub = [];
  if (t.tipo === "refazer") sub.push("Refazer um corte");
  if (t.tipo === "postar_youtube") sub.push(t.resultado && t.resultado.url ? t.resultado.url : "Postar no YouTube");
  if (t.canal) sub.push(t.canal);
  $(".tarefa-sub", li).textContent = sub.join(", ");
  const selo = $(".selo", li);
  selo.className = `selo ${t.status}`;
  selo.textContent = NOME_STATUS_TAREFA[t.status] || t.status;

  const etapas = $(".etapas", li);
  const so = SO_ETAPA[t.tipo];
  etapas.hidden = !!so && t.status !== "rodando";
  const idx = ORDEM_ETAPAS.indexOf(t.etapa);
  $$("li", etapas).forEach((e, k) => {
    const visivel = so ? e.dataset.etapa === so : e.dataset.etapa !== "postar";
    e.style.display = visivel ? "" : "none";
    e.classList.toggle("feita", t.status === "concluida" || (idx >= 0 && k < idx));
    e.classList.toggle("atual", t.status !== "concluida" && k === idx);
    $(".barra i", e).style.width = k === idx ? `${Math.round((t.pct || 0) * 100)}%` : (k < idx ? "100%" : "0");
  });
  etapas.style.gridTemplateColumns = so ? "1fr" : "";

  let detalhe = "";
  if (t.status === "na_fila") detalhe = "Esperando a vez";
  else if (t.status === "rodando") detalhe = `${t.detalhe || NOME_ETAPA[t.etapa] || "Preparando"}, há ${duracaoTexto(Date.now() / 1000 - t.inicio)}`;
  else if (t.status === "concluida") detalhe = `Pronto em ${duracaoTexto((t.fim || 0) - (t.inicio || 0))}`;
  else if (t.status === "cancelada") detalhe = "Cancelada";
  else if (t.status === "erro") detalhe = t.etapa ? `Parou em: ${NOME_ETAPA[t.etapa].toLowerCase()}` : "";
  $(".tarefa-detalhe", li).textContent = detalhe;

  const erro = $(".tarefa-erro", li);
  erro.hidden = !t.erro;
  erro.textContent = t.erro || "";

  const acoes = $(".tarefa-acoes", li);
  const chave = `${t.status}|${t.episodio || ""}`;
  if (acoes.dataset.chave !== chave) {
    acoes.dataset.chave = chave;
    acoes.replaceChildren();
    const botao = (texto, fn) => {
      const b = document.createElement("button");
      b.className = "btn-texto";
      b.textContent = texto;
      b.onclick = fn;
      acoes.appendChild(b);
    };
    if (["na_fila", "rodando"].includes(t.status)) {
      botao("Cancelar", async () => { await api(`/api/tarefas/${t.id}/cancelar`, { body: {} }); aviso("Cancelando..."); carregarTarefas(); });
    }
    if (t.status === "concluida" && t.episodio) botao("Ver os cortes", () => irParaEpisodio(t.episodio));
    if (["erro", "cancelada"].includes(t.status) && t.tipo === "processar" && t.origem) {
      botao("Tentar de novo", async () => {
        try { await api("/api/tarefas", { body: { origem: t.origem } }); aviso("Na fila de novo"); carregarTarefas(); }
        catch (e) { aviso(e.message); }
      });
    }
  }

  const pre = $(".registro pre", li);
  const texto = (t.log || []).join("\n");
  if (pre.textContent !== texto) {
    const noFim = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
    pre.textContent = texto;
    if (noFim) pre.scrollTop = pre.scrollHeight;
  }
  $(".registro", li).hidden = !texto;
}

$(".marca").addEventListener("animationend", (e) => e.target.classList.remove("glitch"));
$("#limpar-fila").onclick = async () => { await api("/api/tarefas/limpar", { body: {} }); carregarTarefas(); };

async function cicloTarefas() {
  try { await carregarTarefas(); } catch (e) { $("#motor-texto").textContent = "Sem conexão com o RVM"; }
  setTimeout(cicloTarefas, estado.ocupada ? 1500 : 5000);
}

/* ============================================================== CORTAR */
const form = $("#form-cortar");
const zona = $("#zona-soltar");

function escolherArquivo(arquivo) {
  if (!arquivo) return;
  if (!/\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(arquivo.name)) { aviso("Formato não suportado. Use mp4, mkv, mov, webm, avi ou m4v."); return; }
  estado.arquivo = arquivo;
  $("#arquivo-nome").textContent = `${arquivo.name} (${(arquivo.size / 1e6).toFixed(0)} MB)`;
  $("#arquivo-escolhido").hidden = false;
  $("#origem").value = "";
  $("#origem").placeholder = "Vídeo do PC escolhido abaixo";
  $("#canal").focus();
}

function tirarArquivo() {
  estado.arquivo = null;
  $("#arquivo-escolhido").hidden = true;
  $("#arquivo").value = "";
  $("#origem").placeholder = "Cole o link do episódio (YouTube, etc.)";
}

$("#arquivo").onchange = (e) => escolherArquivo(e.target.files[0]);
$("#ia").addEventListener("change", () => { conferirChave(); salvarProvedor($("#ia").value); aviso(`IA escolhida: ${NOME_IA[$("#ia").value]}`); });
$("#arquivo-tirar").onclick = tirarArquivo;
$("#origem").addEventListener("input", () => { if ($("#origem").value.trim() && estado.arquivo) tirarArquivo(); });

let arrastos = 0;
document.addEventListener("dragenter", (e) => {
  if (![...(e.dataTransfer?.types || [])].includes("Files")) return;
  arrastos++;
  if (estado.aba !== "cortar") location.hash = "#cortar";
  document.body.classList.add("arrastando");
});
document.addEventListener("dragleave", () => { if (--arrastos <= 0) { arrastos = 0; document.body.classList.remove("arrastando"); } });
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  arrastos = 0;
  document.body.classList.remove("arrastando");
  const arq = e.dataTransfer?.files?.[0];
  if (arq) escolherArquivo(arq);
});

function enviarArquivo(arquivo) {
  return new Promise((resolver, rejeitar) => {
    const fd = new FormData();
    fd.append("video", arquivo);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.setRequestHeader("X-RVM", "1");
    $("#envio").hidden = false;
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const pct = Math.round((100 * e.loaded) / e.total);
      $("#envio-pct").style.width = `${pct}%`;
      $("#envio-texto").textContent = `Copiando o vídeo para o RVM: ${pct}%`;
    };
    xhr.onload = () => {
      $("#envio").hidden = true;
      let d = {};
      try { d = JSON.parse(xhr.responseText); } catch (e) { /* vazio */ }
      xhr.status === 200 ? resolver(d) : rejeitar(new Error(d.erro || `Erro ${xhr.status}`));
    };
    xhr.onerror = () => { $("#envio").hidden = true; rejeitar(new Error("Falha ao enviar o vídeo.")); };
    xhr.send(fd);
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#btn-cortar");
  const corpo = { cortes: Number($("#qtd").value) || undefined, ia: $("#ia").value, sem_legenda: $("#sem-legenda").checked };
  try {
    btn.disabled = true;
    if (estado.arquivo) {
      const canalArq = $("#canal").value.trim();
      if (!canalArq) {
        aviso("📌 Diretriz Obrigatória: Informe o nome do canal original do vídeo para prestar os créditos ao criador.", 4000);
        $("#canal").focus();
        return;
      }
      const up = await enviarArquivo(estado.arquivo);
      corpo.origem = up.caminho;
      corpo.canal = canalArq;
      corpo.link = $("#link").value.trim();
    } else {
      corpo.origem = $("#origem").value.trim();
      if (!corpo.origem) { aviso("Cole um link ou escolha um vídeo."); $("#origem").focus(); return; }
    }
    await api("/api/tarefas", { body: corpo });
    $("#origem").value = "";
    $("#canal").value = "";
    $("#link").value = "";
    tirarArquivo();
    aviso("Episódio na fila");
    carregarTarefas();
  } catch (err) {
    aviso(err.message);
  } finally {
    btn.disabled = false;
  }
});

/* ============================================================== CORTES */
async function carregarCortes() {
  try {
    estado.episodios = await api("/api/cortes");
  } catch (e) { return; }
  const pendentes = estado.episodios.reduce((n, ep) => n + ep.cortes.filter((c) => c.status === "pendente").length, 0);
  const cont = $("#cont-pendentes");
  cont.hidden = !pendentes;
  cont.textContent = pendentes;
  desenharCortes();
}

function desenharCortes() {
  const caixa = $("#episodios");
  const eps = estado.episodios;
  $("#cortes-vazio").hidden = eps.length > 0;
  const vistos = new Set();
  eps.forEach((ep, i) => {
    let sec = caixa.querySelector(`.episodio[data-ep="${CSS.escape(ep.id)}"]`);
    if (!sec) sec = criarEpisodio(ep);
    if (caixa.children[i] !== sec) caixa.insertBefore(sec, caixa.children[i] || null);
    atualizarEpisodio(sec, ep);
    vistos.add(ep.id);
  });
  $$(".episodio", caixa).forEach((s) => { if (!vistos.has(s.dataset.ep)) s.remove(); });
  aplicarFiltro();
}

function criarEpisodio(ep) {
  const sec = document.createElement("section");
  sec.className = "episodio";
  sec.dataset.ep = ep.id;
  sec.innerHTML = `
    <div class="episodio-cabeca"><h2></h2></div>
    <div class="episodio-sub"></div>
    <div class="linha-tempo" aria-label="Onde cada corte está no episódio"></div>
    <div class="lista"></div>`;
  return sec;
}

function atualizarEpisodio(sec, ep) {
  $("h2", sec).textContent = ep.titulo;
  const sub = $(".episodio-sub", sec);
  sub.replaceChildren();
  const add = (el) => sub.appendChild(el);
  const span = (t) => { const s = document.createElement("span"); s.textContent = t; return s; };
  add(span(ep.canal || "Canal não informado"));
  add(span(`${duracaoTexto(ep.duracao)} de episódio`));
  const ap = ep.cortes.filter((c) => c.status === "aprovado").length;
  add(span(`${ep.cortes.length} cortes, ${ap} aprovados`));
  if (ep.link) {
    const a = document.createElement("a");
    a.href = ep.link; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Abrir o episódio original";
    add(a);
  }
  desenharLinhaTempo($(".linha-tempo", sec), ep);

  const lista = $(".lista", sec);
  const vistos = new Set();
  ep.cortes.forEach((c, i) => {
    let card = lista.querySelector(`[data-n="${c.numero}"]`);
    if (!card) card = criarCard(ep.id, c.numero);
    if (lista.children[i] !== card) lista.insertBefore(card, lista.children[i] || null);
    atualizarCard(card, ep, c);
    vistos.add(String(c.numero));
  });
  $$("article.corte", lista).forEach((c) => { if (!vistos.has(c.dataset.n)) c.remove(); });
}

function desenharLinhaTempo(el, ep) {
  const dur = Math.max(ep.duracao || 0, ...ep.cortes.map((c) => c.fim)) || 1;
  const passos = [60, 120, 300, 600, 900, 1200, 1800, 3600];
  const maior = passos.find((p) => dur / p <= 12) || 3600;
  const menor = passos.find((p) => maior % p === 0 && dur / p <= 70) || maior;
  const partes = [`<div class="regua">`];
  for (let t = menor; t < dur; t += menor) {
    partes.push(`<i class="marca-min${t % maior === 0 ? " maior" : ""}" style="left:${(100 * t) / dur}%"></i>`);
  }
  partes.push(`</div>`);
  for (let t = maior; t < dur - maior * 0.3; t += maior) {
    partes.push(`<span class="rotulo-min" style="left:${(100 * t) / dur}%">${mmss(t)}</span>`);
  }
  el.innerHTML = partes.join("");
  for (const c of ep.cortes) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `trecho ${c.status}`;
    b.dataset.n = c.numero;
    b.style.left = `${(100 * c.inicio) / dur}%`;
    b.style.width = `${Math.max(0.5, (100 * (c.fim - c.inicio)) / dur)}%`;
    b.title = `Corte ${c.numero}: ${c.titulo} (${mmss(c.inicio)} a ${mmss(c.fim)})`;
    b.setAttribute("aria-label", b.title);
    const n = document.createElement("span");
    n.textContent = c.numero;
    b.appendChild(n);
    b.onclick = () => irParaCorte(ep.id, c.numero);
    el.appendChild(b);
  }
}

function formatarBlocoCreditoObrigatorio(canal, link) {
  const nomeCanal = (canal || "").trim() || "Criador Original";
  let bloco = `🎥 Créditos ao Criador Original: ${nomeCanal}`;
  if (link && link.trim()) bloco += `\n🔗 Episódio completo: ${link.trim()}`;
  return bloco;
}

function sincronizarCamposCreditoCard(card) {
  const inpCanal = $(".f-canal-original", card);
  const inpTela = $(".f-credito-tela", card);
  const elCredito = $(".credito", card);
  if (!inpCanal) return;
  const canal = inpCanal.value.trim() || card.dataset.canalPadrao || "Criador Original";
  const link = card.dataset.linkOriginal || "";
  if (inpTela) inpTela.value = `Créditos: ${canal}`;
  if (elCredito) elCredito.textContent = formatarBlocoCreditoObrigatorio(canal, link);
}

function validarDiretrizCreditoCorte(card) {
  const inpCanal = $(".f-canal-original", card);
  if (!inpCanal) return true;
  const val = inpCanal.value.trim();
  if (!val) {
    aviso("📌 Diretriz Obrigatória: Informe o nome do canal original para prestar os créditos ao criador.", 4000);
    inpCanal.focus();
    return false;
  }
  sincronizarCamposCreditoCard(card);
  return true;
}

function criarCard(epId, n) {
  const card = $("#tpl-corte").content.firstElementChild.cloneNode(true);
  card.dataset.ep = epId;
  card.dataset.n = n;
  card.id = `corte-${epId}-${n}`;
  const marcarSujo = () => { card.dataset.sujo = "1"; };
  $$("input, textarea", card).forEach((i) => i.addEventListener("input", marcarSujo));
  const inpCanal = $(".f-canal-original", card);
  if (inpCanal) {
    inpCanal.addEventListener("input", () => sincronizarCamposCreditoCard(card));
  }
  const titulo = $(".f-titulo", card);
  titulo.addEventListener("input", () => { $(".contador", card).textContent = `${titulo.value.length}/100`; });
  $$("[data-acao]", card).forEach((b) => (b.onclick = () => acaoCorte(card, b.dataset.acao)));
  return card;
}

function definirValor(el, valor) {
  if (document.activeElement === el) return;
  if (el.value !== String(valor)) el.value = valor;
}

function encontrarTarefaYt(epId, c) {
  const chave = `${epId}:${c.numero}`;
  const ref = estado.tarefasYt[chave];
  const tarefasYt = estado.tarefas.filter((t) => t.tipo === "postar_youtube");
  if (ref && ref.id) {
    const porId = tarefasYt.find((t) => t.id === ref.id);
    if (porId) return porId;
  }
  const porCorte = tarefasYt.find(
    (t) =>
      (t.episodio === epId && (String(t.corte) === String(c.numero) || String(t.numero) === String(c.numero))) ||
      (t.episodio === epId && t.titulo && c.titulo && t.titulo === c.titulo) ||
      (!t.episodio && t.titulo && c.titulo && t.titulo === c.titulo)
  );
  return porCorte || null;
}

function atualizarPainelStatusYt(card, ep, c) {
  const painel = $(".yt-status-painel", card);
  if (!painel) return;
  const yt = (c.postagens || {}).youtube;
  const tarefa = encontrarTarefaYt(ep.id, c);
  const chave = `${ep.id}:${c.numero}`;
  const infoLocal = estado.tarefasYt[chave];

  const icone = $(".yt-status-icone", painel);
  const titulo = $(".yt-status-titulo", painel);
  const selo = $(".yt-status-selo", painel);
  const barra = $(".yt-status-barra", painel);
  const progresso = $(".yt-status-progresso", painel);
  const detalhe = $(".yt-status-detalhe", painel);
  const acoes = $(".yt-status-acoes", painel);
  const btnAbrir = $(".yt-abrir-video", painel);

  if (tarefa && ["na_fila", "rodando"].includes(tarefa.status)) {
    painel.hidden = false;
    painel.className = `yt-status-painel ${tarefa.status}`;
    const pct = Math.round((tarefa.pct || 0) * 100);
    if (tarefa.status === "na_fila") {
      icone.textContent = "⏳";
      titulo.textContent = "Envio ao YouTube na fila";
      selo.className = "selo yt-status-selo";
      selo.textContent = "Na fila";
      barra.hidden = true;
      detalhe.textContent = "Aguardando vez na fila de processamento para iniciar o upload...";
    } else {
      icone.textContent = "↑";
      titulo.textContent = "Publicando vídeo no YouTube...";
      selo.className = "selo yt-status-selo rodando";
      selo.textContent = `Enviando ${pct}%`;
      barra.hidden = false;
      progresso.style.width = `${Math.max(5, pct)}%`;
      const tempo = tarefa.inicio ? `, há ${duracaoTexto(Date.now() / 1000 - tarefa.inicio)}` : "";
      detalhe.textContent = `${tarefa.detalhe || "Enviando arquivo e metadados ao YouTube"}${tempo}`;
    }
    acoes.hidden = true;
    return;
  }

  if (tarefa && tarefa.status === "erro") {
    painel.hidden = false;
    painel.className = "yt-status-painel erro";
    icone.textContent = "✕";
    titulo.textContent = "Falha ao publicar no YouTube";
    selo.className = "selo yt-status-selo erro";
    selo.textContent = "Erro no envio";
    barra.hidden = true;
    detalhe.textContent = tarefa.erro || "Ocorreu um erro durante o envio para o YouTube.";
    acoes.hidden = true;
    return;
  }

  if (yt || (tarefa && tarefa.status === "concluida")) {
    const url = (yt && yt.url) || (tarefa && tarefa.resultado && tarefa.resultado.url) || "";
    const agendado = (yt && yt.agendado) || (infoLocal && infoLocal.agendar) || "";
    const priv = (yt && yt.privacidade) || (infoLocal && infoLocal.privacidade) || "";
    painel.hidden = false;
    painel.className = "yt-status-painel postado";
    icone.textContent = "✓";
    barra.hidden = true;
    if (agendado) {
      const dataFmt = new Date(agendado).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
      titulo.textContent = "Vídeo enviado e agendado no YouTube";
      selo.className = "selo yt-status-selo concluida";
      selo.textContent = `Agendado • ${dataFmt}`;
      detalhe.textContent = `Status confirmado: o vídeo está no YouTube (privado até ${dataFmt}).`;
    } else {
      const nomePriv = NOME_PRIVACIDADE[priv] || "Publicado";
      titulo.textContent = "Vídeo publicado no YouTube";
      selo.className = "selo yt-status-selo concluida";
      selo.textContent = `No ar • ${nomePriv}`;
      detalhe.textContent = `Status confirmado: upload concluído no YouTube${url ? ` (${url})` : ""}.`;
    }
    if (url) {
      acoes.hidden = false;
      btnAbrir.href = url;
      card.dataset.ytUrl = url;
    } else {
      acoes.hidden = true;
    }
    return;
  }

  painel.hidden = true;
}

function atualizarCard(card, ep, c) {
  const versao = c.criado_em || "";
  const video = $("video", card);
  if (card.dataset.versao !== versao) {
    const v = encodeURIComponent(versao);
    video.poster = `/arquivo/${ep.id}/${c.capa}?v=${v}`;
    video.src = `/arquivo/${ep.id}/${c.arquivo}?v=${v}`;
    $(".baixar", card).href = `/arquivo/${ep.id}/${c.arquivo}?baixar=1`;
    const mudouVideo = !!card.dataset.versao;
    card.dataset.versao = versao;
    if (mudouVideo) delete card.dataset.sujo;
  }
  const canalOrig = (c.canal || ep.canal || "Criador Original").trim();
  const linkOrig = (c.link_original || ep.link || "").trim();
  card.dataset.canalPadrao = canalOrig;
  card.dataset.linkOriginal = linkOrig;

  if (!card.dataset.sujo) {
    definirValor($(".f-titulo", card), c.titulo || "");
    definirValor($(".f-descricao", card), c.descricao || "");
    definirValor($(".f-hashtags", card), (c.hashtags || []).join(" "));
    definirValor($(".f-gancho", card), c.gancho || "");
    definirValor($(".f-inicio", card), Number(c.inicio).toFixed(1));
    definirValor($(".f-fim", card), Number(c.fim).toFixed(1));
    if ($(".f-canal-original", card)) definirValor($(".f-canal-original", card), canalOrig);
    $(".f-legenda", card).checked = c.legenda !== false;
    $(".contador", card).textContent = `${(c.titulo || "").length}/100`;
  }
  $(".corte-num", card).textContent = `Corte ${c.numero}`;
  const temRecorte = c.layouts && (c.layouts.dividido > 0 || c.layouts.rosto > 0);
  const infoLayout = temRecorte ? " • recorte de borda detectado (use Refazer vídeo para imagem 100% íntegra)" : " • área 100% íntegra";
  $(".corte-meta", card).textContent =
    `${Math.round(c.duracao)} s, nota ${c.nota != null ? Number(c.nota).toLocaleString("pt-BR") : "?"}, a partir de ${mmss(c.inicio)}${infoLayout} • Créditos: ${canalOrig}`;
  $(".corte-motivo", card).textContent = c.motivo || "";
  $(".corte-motivo", card).hidden = !c.motivo;
  sincronizarCamposCreditoCard(card);
  $(".transcricao p", card).textContent = c.texto || "";
  card.dataset.status = c.status;
  card.className = `corte ${c.status}`;
  const selo = $(".corte-status", card);
  selo.className = `selo corte-status ${c.status}`;
  selo.textContent = NOME_STATUS_CORTE[c.status] || c.status;
  $("[data-acao='pendente']", card).hidden = !["aprovado", "rejeitado"].includes(c.status);
  const yt = (c.postagens || {}).youtube;
  const link = $(".yt-link", card);
  link.hidden = !yt;
  if (yt) link.href = yt.url;
  $("[data-acao='youtube']", card).textContent = yt ? "Postar de novo" : "Postar no YouTube";
  if (yt && yt.agendado) selo.textContent = `Agendado para ${new Date(yt.agendado).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}`;
  const renderizando = c.status === "renderizando";
  $$("[data-acao]", card).forEach((b) => { if (!["copiar", "copiar-link-yt"].includes(b.dataset.acao)) b.disabled = renderizando; });
  const erro = $(".corte-erro", card);
  erro.hidden = !c.erro;
  erro.textContent = c.erro ? `Não deu para refazer: ${c.erro}` : "";
  card.dataset.post = [c.titulo, c.descricao, c.credito, (c.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
  atualizarPainelStatusYt(card, ep, c);
}

function textosDoCard(card) {
  sincronizarCamposCreditoCard(card);
  const canal = ($(".f-canal-original", card) && $(".f-canal-original", card).value.trim()) || card.dataset.canalPadrao || "Criador Original";
  const credito = ($(".credito", card) && $(".credito", card).textContent.trim()) || formatarBlocoCreditoObrigatorio(canal, card.dataset.linkOriginal || "");
  return {
    titulo: $(".f-titulo", card).value,
    descricao: $(".f-descricao", card).value,
    hashtags: $(".f-hashtags", card).value,
    canal,
    credito,
  };
}

async function acaoCorte(card, acao) {
  const base = `/api/cortes/${encodeURIComponent(card.dataset.ep)}/${card.dataset.n}`;
  try {
    if (["copiar", "pedir-confirmacao-yt", "enviar-yt", "refazer", "salvar", "aprovado"].includes(acao)) {
      if (!validarDiretrizCreditoCorte(card)) return;
    }
    if (acao === "copiar") {
      const t = textosDoCard(card);
      const texto = [t.titulo, t.descricao, t.credito, t.hashtags].filter((x) => x && x.trim()).join("\n\n");
      await copiar(texto);
      aviso("Texto do post copiado com os créditos obrigatórios ao criador original!");
      return;
    }
    if (acao === "copiar-link-yt") {
      const url = card.dataset.ytUrl || ($(".yt-link", card) && $(".yt-link", card).href);
      if (url) {
        await copiar(url);
        aviso("Link do YouTube copiado!");
      }
      return;
    }
    if (acao === "youtube") {
      if (!estado.youtube || !estado.youtube.conectado) { aviso("Conecte o YouTube em Ajustes primeiro."); return; }
      const painel = $(".postar", card);
      painel.hidden = !painel.hidden;
      if (!painel.hidden) {
        $(".postar-form", painel).hidden = false;
        $(".postar-confirmacao", painel).hidden = true;
        $(".p-privacidade", card).value = (estado.config && estado.config.youtube && estado.config.youtube.privacidade) || "public";
        painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      return;
    }
    if (acao === "fechar-yt") {
      $(".postar", card).hidden = true;
      $(".postar-form", card).hidden = false;
      $(".postar-confirmacao", card).hidden = true;
      return;
    }
    if (acao === "voltar-edicao-yt") {
      $(".postar-form", card).hidden = false;
      $(".postar-confirmacao", card).hidden = true;
      return;
    }
    if (acao === "pedir-confirmacao-yt") {
      const tituloVal = $(".f-titulo", card).value.trim();
      if (!tituloVal) {
        aviso("Preencha o título do post antes de enviar ao YouTube.");
        $(".f-titulo", card).focus();
        return;
      }
      const quando = $(".p-agendar", card).value;
      if (quando) {
        const d = new Date(quando);
        if (d.getTime() < Date.now() + 15 * 60 * 1000) {
          aviso("Agende para pelo menos 15 minutos à frente.");
          return;
        }
        $(".conf-linha-agendamento", card).hidden = false;
        $(".conf-agendar", card).textContent = d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
      } else {
        $(".conf-linha-agendamento", card).hidden = true;
      }
      const priv = $(".p-privacidade", card).value;
      const canalCriador = ($(".f-canal-original", card) && $(".f-canal-original", card).value.trim()) || card.dataset.canalPadrao || "Criador Original";
      $(".conf-canal", card).textContent = (estado.youtube && estado.youtube.canal) || "Canal conectado";
      if ($(".conf-credito-criador", card)) {
        $(".conf-credito-criador", card).textContent = `🎥 Créditos: ${canalCriador} (Divulgação obrigatória ativa)`;
      }
      $(".conf-titulo", card).textContent = tituloVal;
      $(".conf-visibilidade", card).textContent = quando
        ? `Privado até o horário agendado (depois Público)`
        : (NOME_PRIVACIDADE[priv] || priv);
      $(".postar-form", card).hidden = true;
      $(".postar-confirmacao", card).hidden = false;
      return;
    }
    if (acao === "enviar-yt") {
      await api(base, { body: textosDoCard(card) });
      const quando = $(".p-agendar", card).value;
      let agendar;
      if (quando) {
        const d = new Date(quando);
        if (d.getTime() < Date.now() + 15 * 60 * 1000) { aviso("Agende para pelo menos 15 minutos à frente."); return; }
        agendar = d.toISOString();
      }
      const privacidade = $(".p-privacidade", card).value;
      const resp = await api(`${base}/postar`, { body: { privacidade, agendar } });
      const chave = `${card.dataset.ep}:${card.dataset.n}`;
      estado.tarefasYt[chave] = {
        id: resp && resp.id,
        privacidade,
        agendar,
        inicio: Date.now() / 1000,
      };
      delete card.dataset.sujo;
      $(".postar", card).hidden = true;
      $(".postar-form", card).hidden = false;
      $(".postar-confirmacao", card).hidden = true;
      aviso("✓ Envio confirmado! Acompanhe o status da publicação neste corte.", 4000);
      await carregarTarefas();
      await carregarCortes();
      return;
    }
    if (acao === "refazer") {
      const dCfg = await api("/api/config", {
        body: {
          video: { enquadramento: "desfocado", dois_rostos: "desfocado" },
          legenda: { tamanho: 78, palavras_por_bloco: 2, contorno: 6 },
          titulo_na_tela: { tamanho: 58 },
          credito: {
            na_tela: true,
            texto_tela: "Créditos: {canal}",
            na_descricao: "🎥 Créditos ao Criador Original: {canal}\n🔗 Episódio completo: {link}",
          },
        },
      });
      estado.config = dCfg.config;
      await api(base, { body: textosDoCard(card) });
      await api(`${base}/refazer`, {
        body: {
          gancho: $(".f-gancho", card).value,
          inicio: parseFloat($(".f-inicio", card).value),
          fim: parseFloat($(".f-fim", card).value),
          legenda: $(".f-legenda", card).checked,
        },
      });
      delete card.dataset.sujo;
      aviso("Refazendo o corte com imagem e texto 100% dentro da área segura.");
      $("video", card).pause();
    } else if (acao === "salvar") {
      await api(base, { body: textosDoCard(card) });
      delete card.dataset.sujo;
      aviso("Textos salvos");
    } else {
      await api(base, { body: { ...textosDoCard(card), status: acao } });
      delete card.dataset.sujo;
      aviso({ aprovado: "Aprovado", rejeitado: "Rejeitado", pendente: "Voltou para pendente" }[acao]);
    }
    await carregarCortes();
    carregarTarefas();
  } catch (e) {
    aviso(e.message);
  }
}

async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
  } catch (e) {
    const t = document.createElement("textarea");
    t.value = texto;
    document.body.appendChild(t);
    t.select();
    document.execCommand("copy");
    t.remove();
  }
}

function aplicarFiltro() {
  const f = estado.filtro;
  $$("#filtro button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.f === f)));
  let algum = false;
  $$(".episodio").forEach((sec) => {
    let visiveis = 0;
    $$("article.corte", sec).forEach((card) => {
      const st = card.dataset.status === "renderizando" ? "pendente" : card.dataset.status === "postado" ? "aprovado" : card.dataset.status;
      const ver = f === "todos" || st === f;
      card.hidden = !ver;
      const trecho = $(`.trecho[data-n="${card.dataset.n}"]`, sec);
      if (trecho) trecho.classList.toggle("oculto", !ver);
      if (ver) visiveis++;
    });
    sec.hidden = visiveis === 0;
    if (visiveis) algum = true;
  });
  $("#filtro-vazio").hidden = algum || estado.episodios.length === 0;
}

$$("#filtro button").forEach((b) => (b.onclick = () => {
  estado.filtro = b.dataset.f;
  gravarLocal("rvm-filtro", estado.filtro);
  aplicarFiltro();
}));

function irParaCorte(epId, n) {
  const card = document.getElementById(`corte-${epId}-${n}`);
  if (!card) return;
  if (card.hidden) { estado.filtro = "todos"; aplicarFiltro(); }
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  card.classList.remove("piscar");
  void card.offsetWidth;
  card.classList.add("piscar");
}

async function irParaEpisodio(epId) {
  location.hash = "#cortes";
  await carregarCortes();
  const sec = $(`.episodio[data-ep="${CSS.escape(epId)}"]`);
  if (sec) {
    if (sec.hidden) { estado.filtro = "todos"; aplicarFiltro(); }
    sec.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function cicloCortes() {
  const renderizando = estado.episodios.some((ep) => ep.cortes.some((c) => c.status === "renderizando"));
  try {
    if (estado.aba === "cortes" || renderizando || estado.ocupada) await carregarCortes();
  } catch (e) { /* tenta de novo */ }
  setTimeout(cicloCortes, estado.ocupada || renderizando ? 4000 : 15000);
}

/* ============================================================= AJUSTES */
const formAjustes = $("#form-ajustes");

async function carregarAjustes() {
  const d = await api("/api/config");
  estado.config = d.config;
  for (const el of $$("[data-cfg]", formAjustes)) {
    const v = caminho(d.config, el.dataset.cfg);
    if (el.dataset.cfg === "credito.na_tela") {
      el.checked = true;
      el.disabled = true;
    } else if (el.type === "checkbox") el.checked = !!v;
    else {
      if (el.tagName === "SELECT" && v != null && ![...el.options].some((o) => o.value === String(v))) {
        el.add(new Option(String(v), String(v)));
      }
      el.value = v ?? "";
    }
  }
  desenharChaves(d.chaves);
  carregarYouTube();
  $("#ajustes-estado").textContent = "";
  atualizarPrevia();
}

const CHAVE_DE = { claude: "ANTHROPIC_API_KEY", gemini: "GEMINI_API_KEY" };
const NOME_IA = { claude: "Claude", gemini: "Gemini", ollama: "Ollama" };

function conferirChave() {
  const ia = $("#ia").value;
  const chave = CHAVE_DE[ia];
  const falta = chave && estado.chaves[chave] && !estado.chaves[chave].definida;
  const el = $("#aviso-chave");
  el.hidden = !falta;
  if (falta) el.innerHTML = `Falta a chave do ${NOME_IA[ia]}. <a href="#ajustes">Salvar a chave em Ajustes</a>`;
}

async function salvarProvedor(ia) {
  try {
    const d = await api("/api/config", { body: { ia: { provedor: ia } } });
    estado.config = d.config;
    const sel = $('[data-cfg="ia.provedor"]');
    if (sel) sel.value = ia;
  } catch (e) { aviso(e.message); }
}

async function carregarYouTube() {
  try { estado.youtube = await api("/api/youtube"); } catch (e) { return; }
  const y = estado.youtube;
  const est = $("#yt-estado");
  est.textContent = y.conectado ? `Conectado ao canal ${y.canal || "(sem nome)"}` : y.tem_cliente ? "Credencial enviada. Falta conectar sua conta." : "Não conectado.";
  est.classList.toggle("ok", y.conectado);
  $("#yt-passo-arquivo").classList.toggle("feito", y.tem_cliente);
  $("#yt-arquivo-estado").textContent = y.tem_cliente ? "Credencial carregada. Só envie de novo se trocar de projeto." : "Envie o arquivo client_secret.json que você baixou do Google Cloud.";
  const con = $("#yt-conectar");
  con.textContent = y.conectado ? "Conectar outra conta" : "Conectar YouTube";
  con.classList.toggle("corte", !y.conectado);
  con.style.pointerEvents = y.tem_cliente ? "" : "none";
  con.style.opacity = y.tem_cliente ? "" : "0.45";
  $("#yt-desconectar").hidden = !y.conectado;
}

$("#yt-arquivo").onchange = async (e) => {
  const arq = e.target.files[0];
  if (!arq) return;
  const fd = new FormData();
  fd.append("arquivo", arq);
  try {
    const r = await fetch("/api/youtube/cliente", { method: "POST", headers: { "X-RVM": "1" }, body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || "Erro ao enviar");
    aviso("Credencial carregada");
  } catch (err) { aviso(err.message); }
  e.target.value = "";
  carregarYouTube();
};

$("#yt-desconectar").onclick = async () => {
  if (!confirm("Desconectar o YouTube? O RVM para de conseguir postar até você conectar de novo.")) return;
  await api("/api/youtube/desconectar", { body: {} });
  aviso("YouTube desconectado");
  carregarYouTube();
};

function desenharChaves(chaves) {
  estado.chaves = chaves;
  conferirChave();
  for (const bloco of $$(".chave")) {
    const info = chaves[bloco.dataset.chave] || {};
    const est = $(".estado-chave", bloco);
    est.textContent = info.definida ? `salva${info.final ? `, termina em ${info.final}` : ""}` : "não configurada";
    est.classList.toggle("salva", !!info.definida);
    $(".remover", bloco).hidden = !info.definida;
  }
}

$$(".chave").forEach((bloco) => {
  $(".remover", bloco).onclick = async () => {
    if (!confirm("Remover esta chave? A IA para de funcionar até você salvar outra.")) return;
    try {
      const chaves = await api("/api/chaves", { body: { [bloco.dataset.chave]: "" } });
      desenharChaves(chaves);
      aviso("Chave removida");
    } catch (e) { aviso(e.message); }
  };
  $(".salvar", bloco).onclick = async () => {
    const input = $("input", bloco);
    if (!input.value.trim()) { aviso("Cole a chave antes de salvar."); input.focus(); return; }
    try {
      const chaves = await api("/api/chaves", { body: { [bloco.dataset.chave]: input.value.trim() } });
      input.value = "";
      desenharChaves(chaves);
      aviso("Chave salva");
    } catch (e) { aviso(e.message); }
  };
});

function lerAjustes() {
  const saida = {};
  for (const el of $$("[data-cfg]", formAjustes)) {
    const [secao, chave] = el.dataset.cfg.split(".");
    saida[secao] = saida[secao] || {};
    let v = el.type === "checkbox" ? el.checked : el.value;
    if (["number", "range"].includes(el.type)) v = Number(v);
    saida[secao][chave] = v;
  }
  saida.credito = saida.credito || {};
  saida.credito.na_tela = true;
  if (!saida.credito.texto_tela || !saida.credito.texto_tela.includes("{canal}")) {
    saida.credito.texto_tela = "Créditos: {canal}";
  }
  return saida;
}

let salvarTimer;
formAjustes.addEventListener("input", (e) => {
  if (e.target.closest(".chave")) return;          // chave tem botão próprio
  $("#ajustes-estado").textContent = "Salvando...";
  atualizarPrevia();
  clearTimeout(salvarTimer);
  salvarTimer = setTimeout(() => salvarAjustes(false), 700);
});
formAjustes.addEventListener("submit", (e) => { e.preventDefault(); clearTimeout(salvarTimer); salvarAjustes(true); });

async function salvarAjustes(avisar) {
  try {
    const d = await api("/api/config", { body: lerAjustes() });
    estado.config = d.config;
    $("#ajustes-estado").textContent = "Salvo";
    $("#qtd").value = d.config.cortes.quantidade;
    $("#ia").value = d.config.ia.provedor;
    conferirChave();
    if (avisar) aviso("Ajustes salvos");
  } catch (err) { $("#ajustes-estado").textContent = "Não salvou"; aviso(err.message); }
}

function atualizarPrevia() {
  const a = lerAjustes();
  const cfg = estado.config || {};
  const em = (px) => `${(px * 0.5675) / 10.8}cqw`;      // tamanho da fonte no libass -> prévia
  const leg = $("#pv-legenda");
  leg.hidden = !a.legenda.ativar;
  leg.style.fontSize = em(a.legenda.tamanho);
  leg.style.color = a.legenda.cor;
  leg.style.webkitTextStroke = `${(a.legenda.contorno * 2) / 10.8}cqw #000`;
  leg.style.textTransform = a.legenda.maiusculas ? "uppercase" : "none";
  $(".falada", leg).style.color = a.legenda.cor_destaque;
  const tit = $("#pv-titulo");
  tit.hidden = !a.titulo_na_tela.ativar;
  tit.style.fontSize = em((cfg.titulo_na_tela && cfg.titulo_na_tela.tamanho) || 76);
  tit.innerHTML = "";
  const s = document.createElement("span");
  s.textContent = "ELE PERDEU TUDO EM UM ANO";
  s.style.background = a.titulo_na_tela.cor_fundo;
  s.style.color = a.titulo_na_tela.cor_texto;
  tit.appendChild(s);
  const cred = $("#pv-credito");
  cred.hidden = !a.credito.na_tela;
  cred.textContent = (a.credito.texto_tela || "{canal}").replaceAll("{canal}", "Nome do Podcast").replaceAll("{link}", "");
}

/* ========================================================= DIAGNÓSTICO */
async function rodarDiagnostico(testarIA) {
  const lista = $("#diag");
  lista.innerHTML = `<li><span class="carregando">${testarIA ? "Verificando tudo e testando a IA..." : "Verificando..."}</span></li>`;
  estado.diagFeito = true;
  try {
    const itens = await api(`/api/diagnostico${testarIA ? "?ia=1" : ""}`);
    lista.replaceChildren();
    const marca = { ok: "✓", aviso: "!", falta: "✕" };
    for (const i of itens) {
      const li = document.createElement("li");
      li.className = i.status;
      li.innerHTML = `<span class="marca-diag"></span><span class="nome"></span><span class="detalhe"></span>`;
      $(".marca-diag", li).textContent = marca[i.status];
      $(".marca-diag", li).setAttribute("aria-label", i.status);
      $(".nome", li).textContent = i.nome;
      $(".detalhe", li).textContent = i.detalhe || "";
      lista.appendChild(li);
    }
  } catch (e) {
    lista.innerHTML = "";
    aviso(e.message);
  }
}
$("#diag-rodar").onclick = () => rodarDiagnostico(false);
$("#diag-ia").onclick = () => rodarDiagnostico(true);

/* ====================================== MONITOR DE HARDWARE (CPU/RAM/GPU) */
function classificarUso(pct, limiteCritico, limiteAviso = 75) {
  if (pct >= limiteCritico) return "critico";
  if (pct >= limiteAviso) return "aviso";
  return "normal";
}

function registrarLogHardwareLocal(msg) {
  const h = new Date().toLocaleTimeString("pt-BR");
  estado.hwLogsExtras.push(`[${h}] ${msg}`);
  if (estado.hwLogsExtras.length > 30) estado.hwLogsExtras.shift();
}

async function obterDadosTelemetria() {
  if (estado.hwEndpointModo !== "static") {
    try {
      const r = await fetch(`/api/telemetria?t=${Date.now()}`, { cache: "no-store" });
      if (r.ok) {
        estado.hwEndpointModo = "api";
        return await r.json();
      }
      if (r.status === 404) estado.hwEndpointModo = "static";
    } catch (e) { /* tenta fallback estático */ }
  }
  const r2 = await fetch(`/static/telemetria.json?t=${Date.now()}`, { cache: "no-store" });
  if (!r2.ok) throw new Error("Sem telemetria");
  return await r2.json();
}

function atualizarMedidorIndividual(cardId, pctId, barraId, detalheId, tagId, pct, textoDetalhe, nivel, textoValorCustom = null) {
  const card = $(cardId);
  if (!card) return;
  const classeEstado = nivel === "critico" ? "estado-critico" : nivel === "aviso" ? "estado-aviso" : "estado-normal";
  card.className = `medidor-card ${classeEstado}`;
  $(pctId).textContent = textoValorCustom !== null ? textoValorCustom : `${Number(pct || 0).toFixed(1)}%`;
  $(barraId).style.width = `${Math.max(2, Math.min(100, Number(pct || 0)))}%`;
  $(detalheId).textContent = textoDetalhe;
  const tag = $(tagId);
  tag.textContent = { normal: "Normal", aviso: "Atenção", critico: "Crítico!" }[nivel] || "Normal";
}

function exibirModalAlertaHardware(dados, motivosCriticos, simulado = false) {
  const modal = $("#modal-alerta-hw");
  if (!modal) return;
  const cpuPct = dados ? Number(dados.cpu?.pct || 0).toFixed(1) : "0.0";
  const cpuTemp = dados && dados.cpu?.temp_c ? `${dados.cpu.temp_c}°C` : "48°C";
  const ramPct = dados ? Number(dados.ram?.pct || 0).toFixed(1) : "0.0";
  const ramDet = dados ? `${dados.ram?.usada_gb || 0}/${dados.ram?.total_gb || 0} GB` : "";
  const gpuPct = dados ? Number(dados.gpu?.pct || 0).toFixed(1) : "0.0";
  const gpuTemp = dados && dados.gpu?.temp_c ? `${dados.gpu.temp_c}°C` : "50°C";

  $("#modal-hw-sub").textContent = simulado
    ? "Teste de segurança do sistema de proteção e parada forçada"
    : "Sobrecarga crítica identificada durante o processamento de cortes";
  $("#modal-hw-motivo").textContent = motivosCriticos.join("  |  ");
  $("#modal-hw-cpu").textContent = `${cpuPct}% • 🌡️ ${cpuTemp}`;
  $("#modal-hw-ram").textContent = `${ramPct}% (${ramDet})`;
  $("#modal-hw-gpu").textContent = `${gpuPct}% • 🌡️ ${gpuTemp}`;

  const tarefaAtiva = estado.tarefas.find((t) => t.status === "rodando") ||
    (dados && dados.processamento && dados.processamento.ocupada
      ? { titulo: dados.processamento.titulo, etapa: dados.processamento.etapa, pct: (dados.processamento.pct || 0) / 100 }
      : null);

  const elTarefa = $("#modal-hw-tarefa");
  if (tarefaAtiva) {
    const nomeEtapa = NOME_ETAPA[tarefaAtiva.etapa] || tarefaAtiva.etapa || "Processando";
    const pctTarefa = Math.round((tarefaAtiva.pct || 0) * 100);
    elTarefa.textContent = `Corte em execução: "${tarefaAtiva.titulo || "Episódio atual"}" — Etapa: ${nomeEtapa} (${pctTarefa}%)`;
  } else {
    elTarefa.textContent = "Status da fila: Monitoramento preventivo ativo (nenhuma tarefa será iniciada sem segurança).";
  }

  modal.hidden = false;
}

async function forcarParadaProcessamento(motivo = "Alerta crítico de hardware") {
  const modal = $("#modal-alerta-hw");
  if (modal) modal.hidden = true;

  const ativas = estado.tarefas.filter((t) => ["rodando", "na_fila"].includes(t.status));
  let canceladas = 0;
  for (const t of ativas) {
    try {
      await api(`/api/tarefas/${t.id}/cancelar`, { body: {} });
      canceladas++;
    } catch (e) { /* continua cancelando as demais */ }
  }

  try {
    await fetch("/api/telemetria/parada-forcada", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-RVM": "1" },
      body: JSON.stringify({
        motivo,
        tarefa_id: ativas[0] ? ativas[0].id : "manual",
      }),
    });
  } catch (e) { /* registrado localmente também */ }

  registrarLogHardwareLocal(
    `[PARADA FORÇADA PELO USUÁRIO] ${canceladas > 0 ? `${canceladas} tarefa(s) interrompida(s)` : "Sinal de parada enviado"} — Motivo: ${motivo}`
  );
  if (estado.telemetria) desenharTelemetria(estado.telemetria);
  aviso(
    canceladas > 0
      ? `🛑 Parada forçada executada! ${canceladas} tarefa(s) interrompida(s) por segurança.`
      : "🛑 Parada forçada confirmada e registrada no log de hardware.",
    4500
  );
  await carregarTarefas();
}

function desenharTelemetria(d) {
  estado.telemetria = d;
  const limCritico = estado.hwLimiteCritico || 85;
  const limAviso = Math.min(75, limCritico - 10);

  const cpuPct = Number(d.cpu?.pct || 0);
  const ramPct = Number(d.ram?.pct || 0);
  const gpuPct = Number(d.gpu?.pct || 0);
  const vramPct = Number(d.gpu?.vram_pct || 0);
  const gpuTemp = Number(d.gpu?.temp_c || 0);
  const cpuTemp = Number(d.cpu?.temp_c || Math.round(38 + cpuPct * 0.145));
  const tempMax = Math.max(cpuTemp, gpuTemp);
  const tempPctEscala = Math.min(100, Math.round((tempMax / 83) * 100));

  let nivCpu = classificarUso(cpuPct, limCritico, limAviso);
  if (cpuTemp >= 83) nivCpu = "critico";
  const nivRam = classificarUso(ramPct, limCritico, limAviso);
  let nivGpu = classificarUso(Math.max(gpuPct, vramPct), limCritico, limAviso);
  if (gpuTemp >= 83) nivGpu = "critico";
  const nivTemp = tempMax >= 83 ? "critico" : tempMax >= 72 ? "aviso" : "normal";

  const nomeCpuCurto = d.cpu?.nome_curto || "PROCESSADOR";
  const freqGhz = d.cpu?.freq_ghz ? ` • ${Number(d.cpu.freq_ghz).toFixed(2)} GHz` : "";
  const statusCpuTxt = d.cpu?.status_texto || (nivCpu === "critico" ? "Crítico" : nivCpu === "aviso" ? "Carga Elevada" : "Ativo • Estável");
  if ($("#hw-cpu-nome")) $("#hw-cpu-nome").textContent = `CPU // ${nomeCpuCurto}`;
  if ($("#hw-cpu-temp")) $("#hw-cpu-temp").textContent = `🌡️ ${cpuTemp}°C`;

  atualizarMedidorIndividual(
    "#hw-card-cpu",
    "#hw-cpu-pct",
    "#hw-cpu-barra",
    "#hw-cpu-detalhe",
    "#hw-cpu-tag",
    cpuPct,
    `Status: ${statusCpuTxt} (${d.cpu?.nucleos || 12} núcleos${freqGhz}) • Temp: ${cpuTemp}°C`,
    nivCpu
  );

  if ($("#hw-ram-uso-gb")) $("#hw-ram-uso-gb").textContent = `${Number(d.ram?.usada_gb || 0).toFixed(1)} GB`;
  atualizarMedidorIndividual(
    "#hw-card-ram",
    "#hw-ram-pct",
    "#hw-ram-barra",
    "#hw-ram-detalhe",
    "#hw-ram-tag",
    ramPct,
    `${Number(d.ram?.usada_gb || 0).toFixed(1)} / ${Number(d.ram?.total_gb || 0).toFixed(1)} GB (${Number(d.ram?.livre_gb || 0).toFixed(1)} GB livres)`,
    nivRam
  );

  const nomeGpuCurto = (d.gpu?.nome || "GPU").replace(/^NVIDIA GeForce\s+/i, "");
  $("#hw-gpu-nome").textContent = `GPU // ${nomeGpuCurto}`;
  if ($("#hw-gpu-temp")) $("#hw-gpu-temp").textContent = `🌡️ ${gpuTemp}°C`;
  atualizarMedidorIndividual(
    "#hw-card-gpu",
    "#hw-gpu-pct",
    "#hw-gpu-barra",
    "#hw-gpu-detalhe",
    "#hw-gpu-tag",
    gpuPct,
    `VRAM: ${d.gpu?.vram_usada_mb || 0}/${d.gpu?.vram_total_mb || 0} MB (${vramPct.toFixed(0)}%) • Temp: ${gpuTemp}°C`,
    nivGpu
  );

  atualizarMedidorIndividual(
    "#hw-card-temp",
    "#hw-temp-max",
    "#hw-temp-barra",
    "#hw-temp-detalhe",
    "#hw-temp-tag",
    tempPctEscala,
    `CPU: ${cpuTemp}°C • GPU: ${gpuTemp}°C (Limite: 83°C)`,
    nivTemp,
    `🌡️ ${tempMax}°C`
  );

  const motivos = [];
  if (cpuPct >= limCritico) motivos.push(`CPU em ${cpuPct.toFixed(1)}% (${cpuTemp}°C — Limite: ${limCritico}%)`);
  if (cpuTemp >= 83) motivos.push(`Temperatura da CPU em ${cpuTemp}°C (Limite: 83°C)`);
  if (ramPct >= limCritico) motivos.push(`Memória RAM em ${ramPct.toFixed(1)}% (${d.ram?.usada_gb}/${d.ram?.total_gb} GB)`);
  if (gpuPct >= limCritico) motivos.push(`GPU em ${gpuPct.toFixed(1)}% (Limite: ${limCritico}%)`);
  if (vramPct >= limCritico) motivos.push(`VRAM da GPU em ${vramPct.toFixed(1)}%`);
  if (gpuTemp >= 83) motivos.push(`Temperatura da GPU em ${gpuTemp}°C (Limite: 83°C)`);

  const temCritico = motivos.length > 0;
  const temAviso = !temCritico && [nivCpu, nivRam, nivGpu, nivTemp].includes("aviso");

  const hud = $("#telemetria-hud");
  hud.classList.toggle("alerta-critico", temCritico);
  hud.classList.toggle("alerta-aviso", temAviso);

  const ponto = $("#hw-ponto");
  ponto.className = `telemetria-ponto ${temCritico ? "estado-critico" : temAviso ? "estado-aviso" : "estado-normal"}`.trim();

  const seloGeral = $("#hw-status-geral");
  if (temCritico) {
    seloGeral.className = "selo erro";
    seloGeral.textContent = "USO CRÍTICO!";
  } else if (temAviso) {
    seloGeral.className = "selo rodando";
    seloGeral.textContent = "Carga Elevada";
  } else {
    seloGeral.className = "selo concluida";
    seloGeral.textContent = "Estável";
  }

  const tarefaRodando = estado.tarefas.find((t) => t.status === "rodando");
  const estaProcessando = !!tarefaRodando || !!(d.processamento && d.processamento.ocupada);

  const btnParar = $("#hw-btn-forcar-parada");
  btnParar.hidden = !estaProcessando && !temCritico;

  const ctx = $("#hw-contexto-tarefa");
  if (tarefaRodando) {
    const et = NOME_ETAPA[tarefaRodando.etapa] || tarefaRodando.etapa || "Processando";
    ctx.textContent = `Monitorando corte: "${tarefaRodando.titulo || tarefaRodando.origem}" (${et} ${Math.round((tarefaRodando.pct || 0) * 100)}%)`;
  } else if (d.processamento && d.processamento.ocupada) {
    ctx.textContent = `Monitorando corte: "${d.processamento.titulo || "Em andamento"}" (${d.processamento.etapa || "ativo"} ${d.processamento.pct || 0}%)`;
  } else {
    ctx.textContent = `Atualizado às ${d.horario || new Date().toLocaleTimeString("pt-BR")} • Monitoramento ativo`;
  }

  // Atualiza gaveta de log de hardware
  const linhasBase = Array.isArray(d.historico_log) ? d.historico_log : [];
  const todasLinhas = [...linhasBase, ...estado.hwLogsExtras];
  $("#hw-log-cont").textContent = todasLinhas.length;
  const pre = $("#hw-log-pre");
  const textoLog = todasLinhas.join("\n");
  if (pre && pre.textContent !== textoLog) {
    const noFim = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 10;
    pre.textContent = textoLog;
    if (noFim) pre.scrollTop = pre.scrollHeight;
  }

  // Se estiver crítico durante processamento (ou geral) e não estiver em pausa de 2 min, abre o modal perguntando se deseja forçar a parada
  if (temCritico && Date.now() > estado.hwAlertaIgnoradoAte) {
    const modal = $("#modal-alerta-hw");
    if (modal && modal.hidden) {
      registrarLogHardwareLocal(`[ALERTA CRÍTICO] ${motivos.join("; ")} — Aguardando decisão do usuário (Forçar Parada ou Continuar).`);
      exibirModalAlertaHardware(d, motivos, false);
    }
  }
}

async function cicloTelemetriaHardware() {
  try {
    const d = await obterDadosTelemetria();
    desenharTelemetria(d);
  } catch (e) {
    $("#hw-status-geral").textContent = "Aguardando...";
  }
  setTimeout(cicloTelemetriaHardware, 1500);
}

// Eventos do Monitor de Hardware e Modal de Parada Forçada
const selLimiteHw = $("#hw-limite-critico");
if (selLimiteHw) {
  selLimiteHw.value = String(estado.hwLimiteCritico);
  selLimiteHw.onchange = () => {
    estado.hwLimiteCritico = Number(selLimiteHw.value) || 85;
    estado.hwAlertaIgnoradoAte = 0;
    gravarLocal("rvm-hw-limite-critico", String(estado.hwLimiteCritico));
    aviso(`Limite de alerta crítico ajustado para ${estado.hwLimiteCritico}%`);
    if (estado.telemetria) desenharTelemetria(estado.telemetria);
  };
}

$("#hw-btn-log").onclick = () => {
  const painel = $("#hw-log-painel");
  painel.hidden = !painel.hidden;
  $("#hw-btn-log").setAttribute("aria-expanded", String(!painel.hidden));
};

$("#hw-log-copiar").onclick = async () => {
  await copiar($("#hw-log-pre").textContent || "");
  aviso("Log de hardware copiado!");
};

$("#hw-log-limpar").onclick = () => {
  estado.hwLogsExtras = [];
  $("#hw-log-pre").textContent = "Log visual limpo (o histórico completo permanece salvo em 'log do papai.txt').";
};

$("#hw-btn-testar-alerta").onclick = () => {
  const d = estado.telemetria || {
    cpu: { pct: 91.5 },
    ram: { pct: 88.2, usada_gb: 14.1, total_gb: 16.0 },
    gpu: { pct: 94.0, temp_c: 79 },
  };
  const motivos = [
    `Simulação de sobrecarga crítica acionada (Limite configurado: ${estado.hwLimiteCritico}%)`,
    `Leitura atual: CPU ${Number(d.cpu?.pct || 0).toFixed(1)}% | RAM ${Number(d.ram?.pct || 0).toFixed(1)}% | GPU ${Number(d.gpu?.pct || 0).toFixed(1)}%`,
  ];
  registrarLogHardwareLocal("[TESTE DE ALERTA] Simulação de aviso crítico e confirmação de parada forçada aberta pelo usuário.");
  exibirModalAlertaHardware(d, motivos, true);
};

$("#hw-btn-forcar-parada").onclick = () => {
  const d = estado.telemetria;
  exibirModalAlertaHardware(
    d,
    ["Solicitação manual de parada de emergência pelo painel de telemetria"],
    false
  );
};

$("#modal-hw-confirmar-parada").onclick = () => {
  const motivo = $("#modal-hw-motivo").textContent || "Uso crítico de hardware";
  forcarParadaProcessamento(motivo);
};

$("#modal-hw-continuar").onclick = () => {
  estado.hwAlertaIgnoradoAte = Date.now() + 2 * 60 * 1000;
  $("#modal-alerta-hw").hidden = true;
  registrarLogHardwareLocal("[DECISÃO DO USUÁRIO] Continuar processando (alerta pausado por 2 minutos).");
  aviso("Processamento mantido. O aviso crítico foi pausado por 2 minutos.");
};

/* ============================================================== INÍCIO */
(async function iniciar() {
  try {
    const d = await api("/api/config");
    estado.config = d.config;
    $("#qtd").value = d.config.cortes.quantidade;
    $("#ia").value = d.config.ia.provedor;
    estado.chaves = d.chaves;
    conferirChave();
    const prov = d.config.ia.provedor;
    const chave = { claude: "ANTHROPIC_API_KEY", gemini: "GEMINI_API_KEY" }[prov];
    if (chave && !d.chaves[chave].definida && !location.hash) {
      location.hash = "#ajustes";
      setTimeout(() => aviso("Antes de começar, salve a chave da IA aqui em Ajustes."), 400);
    }
  } catch (e) { /* segue */ }
  const q = new URLSearchParams(location.search);
  if (q.get("yt")) {
    const msg = { ok: "YouTube conectado", cancelado: "Login do YouTube cancelado" }[q.get("yt")] || `Não conectou: ${q.get("msg") || "erro no login"}`;
    setTimeout(() => aviso(msg), 500);
    history.replaceState(null, "", "/" + location.hash);
  }
  carregarYouTube();
  mostrarAba();
  cicloTarefas();
  cicloCortes();
  cicloTelemetriaHardware();
})();
