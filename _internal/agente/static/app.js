"use strict";
/* RVM - interface no navegador. Fala com o servidor local (agente/web.py). */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const estado = {
  aba: "cortar",
  ocupada: false,
  tarefas: [],
  statusAnterior: {},
  episodios: [],
  filtro: lerLocal("rvm-filtro", "pendente"),
  config: null,
  chaves: {},
  arquivo: null,
  diagFeito: false,
};

const NOME_ETAPA = { baixar: "Baixando", transcrever: "Transcrevendo", escolher: "Escolhendo trechos", editar: "Montando vídeos", postar: "Enviando ao YouTube" };
const ORDEM_ETAPAS = ["baixar", "transcrever", "escolher", "editar", "postar"];
const SO_ETAPA = { refazer: "editar", postar_youtube: "postar" };
const NOME_STATUS_TAREFA = { na_fila: "Na fila", rodando: "Trabalhando", concluida: "Pronto", erro: "Deu erro", cancelada: "Cancelada" };
const NOME_STATUS_CORTE = { pendente: "Pendente", aprovado: "Aprovado", rejeitado: "Rejeitado", renderizando: "Refazendo", postado: "Postado" };

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
function aviso(msg) {
  const el = $("#aviso");
  el.textContent = msg;
  el.classList.add("mostrar");
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => el.classList.remove("mostrar"), 2600);
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
  for (const t of d.tarefas) {
    const antes = estado.statusAnterior[t.id];
    if (antes && antes !== t.status) {
      if (t.status === "concluida" && t.tipo === "processar") aviso(`Pronto: ${t.resultado.cortes || 0} cortes de "${t.titulo}"`);
      if (t.status === "concluida" && t.tipo === "refazer") aviso("Corte refeito");
      if (t.status === "concluida" && t.tipo === "postar_youtube") aviso("Postado no YouTube");
      if (t.status === "erro") aviso("Uma tarefa deu erro. Veja na fila.");
      if (["concluida", "erro", "cancelada"].includes(t.status)) carregarCortes();
    }
    estado.statusAnterior[t.id] = t.status;
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
      const up = await enviarArquivo(estado.arquivo);
      corpo.origem = up.caminho;
      corpo.canal = $("#canal").value.trim();
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

function criarCard(epId, n) {
  const card = $("#tpl-corte").content.firstElementChild.cloneNode(true);
  card.dataset.ep = epId;
  card.dataset.n = n;
  card.id = `corte-${epId}-${n}`;
  const marcarSujo = () => { card.dataset.sujo = "1"; };
  $$("input, textarea", card).forEach((i) => i.addEventListener("input", marcarSujo));
  const titulo = $(".f-titulo", card);
  titulo.addEventListener("input", () => { $(".contador", card).textContent = `${titulo.value.length}/100`; });
  $$("[data-acao]", card).forEach((b) => (b.onclick = () => acaoCorte(card, b.dataset.acao)));
  return card;
}

function definirValor(el, valor) {
  if (document.activeElement === el) return;
  if (el.value !== String(valor)) el.value = valor;
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
  if (!card.dataset.sujo) {
    definirValor($(".f-titulo", card), c.titulo || "");
    definirValor($(".f-descricao", card), c.descricao || "");
    definirValor($(".f-hashtags", card), (c.hashtags || []).join(" "));
    definirValor($(".f-gancho", card), c.gancho || "");
    definirValor($(".f-inicio", card), Number(c.inicio).toFixed(1));
    definirValor($(".f-fim", card), Number(c.fim).toFixed(1));
    $(".f-legenda", card).checked = c.legenda !== false;
    $(".contador", card).textContent = `${(c.titulo || "").length}/100`;
  }
  $(".corte-num", card).textContent = `Corte ${c.numero}`;
  $(".corte-meta", card).textContent =
    `${Math.round(c.duracao)} s, nota ${c.nota != null ? Number(c.nota).toLocaleString("pt-BR") : "?"}, a partir de ${mmss(c.inicio)}`;
  $(".corte-motivo", card).textContent = c.motivo || "";
  $(".corte-motivo", card).hidden = !c.motivo;
  $(".credito", card).textContent = c.credito || "";
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
  $$("[data-acao]", card).forEach((b) => { if (b.dataset.acao !== "copiar") b.disabled = renderizando; });
  const erro = $(".corte-erro", card);
  erro.hidden = !c.erro;
  erro.textContent = c.erro ? `Não deu para refazer: ${c.erro}` : "";
  card.dataset.post = [c.titulo, c.descricao, c.credito, (c.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
}

function textosDoCard(card) {
  return {
    titulo: $(".f-titulo", card).value,
    descricao: $(".f-descricao", card).value,
    hashtags: $(".f-hashtags", card).value,
  };
}

async function acaoCorte(card, acao) {
  const base = `/api/cortes/${encodeURIComponent(card.dataset.ep)}/${card.dataset.n}`;
  try {
    if (acao === "copiar") {
      const t = textosDoCard(card);
      const credito = $(".credito", card).textContent;
      const texto = [t.titulo, t.descricao, credito, t.hashtags].filter((x) => x && x.trim()).join("\n\n");
      await copiar(texto);
      aviso("Texto do post copiado");
      return;
    }
    if (acao === "youtube") {
      if (!estado.youtube || !estado.youtube.conectado) { aviso("Conecte o YouTube em Ajustes primeiro."); return; }
      const painel = $(".postar", card);
      painel.hidden = !painel.hidden;
      if (!painel.hidden) {
        $(".p-privacidade", card).value = (estado.config && estado.config.youtube && estado.config.youtube.privacidade) || "public";
        painel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      return;
    }
    if (acao === "fechar-yt") { $(".postar", card).hidden = true; return; }
    if (acao === "enviar-yt") {
      await api(base, { body: textosDoCard(card) });
      const quando = $(".p-agendar", card).value;
      let agendar;
      if (quando) {
        const d = new Date(quando);
        if (d.getTime() < Date.now() + 15 * 60 * 1000) { aviso("Agende para pelo menos 15 minutos à frente."); return; }
        agendar = d.toISOString();
      }
      await api(`${base}/postar`, { body: { privacidade: $(".p-privacidade", card).value, agendar } });
      delete card.dataset.sujo;
      $(".postar", card).hidden = true;
      aviso("Enviando ao YouTube. Acompanhe na fila.");
      carregarTarefas();
      return;
    }
    if (acao === "refazer") {
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
      aviso("Refazendo o corte. Ele entrou na fila.");
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
    if (el.type === "checkbox") el.checked = !!v;
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
})();
