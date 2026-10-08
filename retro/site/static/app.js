// Botões "i": abrem e fecham a explicação ligada por aria-controls.
document.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".info-btn");
  if (!btn) return;
  const alvo = document.getElementById(btn.getAttribute("aria-controls"));
  if (!alvo) return;
  const abrir = btn.getAttribute("aria-expanded") !== "true";
  btn.setAttribute("aria-expanded", String(abrir));
  alvo.hidden = !abrir;
});

// Utilidades compartilhadas
const RETRO = (() => {
  const base = document.body.dataset.base || "";
  const norm = (s) => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const titulo = (s) => (s && s === s.toUpperCase()
    ? s.toLowerCase().replace(/(^|[\s'-])(\p{L})/gu, (m, a, b) => a + b.toUpperCase()).replace(/ (De|Da|Do|Das|Dos|E) /g, (w) => w.toLowerCase())
    : s || "");
  const cache = new Map();
  const json = (url) => {
    if (!cache.has(url)) cache.set(url, fetch(url).then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
    return cache.get(url);
  };
  const BALDES = 4096;
  const pessoa = async (id) => (await json(`${base}/pessoas/${Number(BigInt(id) % BigInt(BALDES))}.json`))[id];
  return { base, norm, esc, titulo, json, pessoa };
})();

// Busca da página inicial: índice dividido pelas 3 primeiras letras de cada palavra do nome.
(function busca() {
  const campo = document.getElementById("busca");
  if (!campo) return;
  const { base, norm, esc, titulo, json, pessoa } = RETRO;
  const lista = document.getElementById("resultados");
  const ufSel = document.getElementById("uf");
  const vazio = document.getElementById("sem-resultados");
  const dica = document.getElementById("busca-dica");
  let cargo = "Todos";
  let versao = 0;

  async function idsPara(token) {
    const shard = await json(`${base}/busca/${token.slice(0, 3)}.json`);
    const exatos = shard[token] || [];
    const outros = Object.keys(shard).filter((t) => t !== token && t.startsWith(token)).flatMap((t) => shard[t]);
    return [...exatos, ...outros];
  }

  function rotuloCand(c) {
    const [ano, cg, uf, local] = c;
    return `${titulo(cg)} em ${ano}${local ? `, ${titulo(local)}` : ""} (${uf})`;
  }

  async function render() {
    const minha = ++versao;
    const palavras = norm(campo.value).split(/[^a-z0-9]+/).filter((p) => p.length >= 3 && !["das", "dos"].includes(p));
    dica.hidden = palavras.length > 0;
    if (!palavras.length) { lista.innerHTML = ""; vazio.hidden = true; return; }
    const listas = await Promise.all(palavras.map(idsPara));
    if (minha !== versao) return;
    listas.sort((a, b) => a.length - b.length);
    const resto = listas.slice(1).map((l) => new Set(l));
    const vistos = new Set();
    const candidatos = [];
    for (const id of listas[0]) {
      if (vistos.has(id) || !resto.every((s) => s.has(id))) continue;
      vistos.add(id);
      candidatos.push(id);
      if (candidatos.length >= 120) break;
    }
    const uf = ufSel.value;
    const achados = [];
    for (let i = 0; i < candidatos.length && achados.length < 25; i += 25) {
      const recs = await Promise.all(candidatos.slice(i, i + 25).map(async (id) => [id, await pessoa(id)]));
      if (minha !== versao) return;
      for (const [id, p] of recs) {
        if (!p) continue;
        const okCargo = cargo === "Todos" || p.c.some((c) => norm(c[1]) === norm(cargo));
        const okUf = !uf || p.c.some((c) => c[2] === uf);
        if (okCargo && okUf) achados.push([id, p]);
      }
    }
    lista.innerHTML = achados.slice(0, 25).map(([id, p]) => {
      const href = p.d ? `${base}/deputado/${p.d}/` : `${base}/pessoa/?id=${id}`;
      const selo = p.d ? '<span class="selo-res completo">Votos e presença</span>' : '<span class="selo-res eleitoral">Candidaturas</span>';
      const eleito = p.c.find((c) => c[6] === "Eleito(a)");
      const linha = eleito ? `Eleito(a) ${titulo(eleito[1]).toLowerCase()} em ${eleito[0]}${eleito[3] ? `, ${titulo(eleito[3])}` : ""} (${eleito[2]})` : `Candidato(a) a ${rotuloCand(p.c[0]).replace(/^(.)/, (m) => m.toLowerCase())}`;
      return `<a class="resultado" href="${href}">
        <span class="ini" aria-hidden="true"></span>
        <span class="txt"><span class="nome">${esc(titulo(p.u || p.n))}</span>
        <span class="sub">${esc(titulo(p.n))}. ${esc(linha)}. ${p.c.length} ${p.c.length === 1 ? "candidatura" : "candidaturas"}.</span></span>
        ${selo}</a>`;
    }).join("");
    vazio.hidden = achados.length > 0;
  }

  let espera;
  const agendar = () => { clearTimeout(espera); espera = setTimeout(render, 180); };
  const inicial = new URLSearchParams(location.search).get("q");
  if (inicial) campo.value = inicial;
  campo.addEventListener("input", agendar);
  ufSel.addEventListener("change", render);
  document.querySelectorAll("[data-cargo]").forEach((b) => b.addEventListener("click", () => {
    cargo = b.dataset.cargo;
    document.querySelectorAll("[data-cargo]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    render();
  }));
  render();
})();

// Página de pessoa (candidaturas do TSE), montada no navegador.
(async function paginaPessoa() {
  const cfgEl = document.getElementById("config-pessoa");
  if (!cfgEl) return;
  const { base, esc, titulo, pessoa } = RETRO;
  const id = new URLSearchParams(location.search).get("id");
  const p = id && /^\d+$/.test(id) ? await pessoa(id) : null;
  if (!p) {
    document.getElementById("p-nome").textContent = "Pessoa não encontrada";
    document.getElementById("p-erro").hidden = false;
    return;
  }
  const nome = titulo(p.u || p.n);
  document.title = `${nome} · Retrospectiva`;
  document.getElementById("p-nome").textContent = nome;
  const eleicoes = p.c.length;
  const eleito = p.c.filter((c) => c[6] === "Eleito(a)").length;
  const anos = p.c.map((c) => c[0]);
  document.getElementById("p-frase").textContent =
    `${titulo(p.n)}. ${eleicoes} ${eleicoes === 1 ? "candidatura" : "candidaturas"} registradas no TSE entre ${Math.min(...anos)} e ${Math.max(...anos)}` +
    (eleito ? `. Eleito(a) ${eleito} ${eleito === 1 ? "vez" : "vezes"}.` : ".");
  document.getElementById("p-chips").innerHTML = p.d
    ? `<a class="chip forte" href="${base}/deputado/${p.d}/">Ver votos, presença e leis na Câmara</a>`
    : "";
  const segs = p.d ? 3 : 1;
  document.getElementById("p-cobertura").innerHTML =
    `<div class="segs" aria-hidden="true">${[0, 1, 2, 3, 4].map((i) => `<i class="${i < segs ? "on" : ""}"></i>`).join("")}</div>
     <span><strong>${p.d ? "Dados em 3 de 5 áreas." : "Só dados eleitorais."}</strong> ${p.d ? "Candidaturas e mandato de deputado federal." : "Para este cargo ainda não há votos ou presença em formato aberto."}</span>`;
  const classe = (r) => r === "Eleito(a)" ? "sim" : r === "Não eleito(a)" ? "nao" : r.includes("turno") ? "outro" : "ausente";
  document.getElementById("p-lista").innerHTML = p.c.map((c) => {
    const [ano, cargo, uf, local, partido, numero, resultado, , suplementar] = c;
    return `<article class="voto-card">
      <div class="voto-lado"><span class="voto ${classe(resultado)}">${esc(resultado)}</span><span class="xsmall muted">${ano}</span></div>
      <div class="voto-corpo">
        <div class="etiquetas"><span class="etiqueta">${esc(partido)}</span><span class="etiqueta">Número ${esc(numero)}</span>${suplementar ? '<span class="etiqueta">Eleição suplementar</span>' : ""}</div>
        <h3>${esc(titulo(cargo))}${local ? ` em ${esc(titulo(local))}` : ""} (${esc(uf)})</h3>
        <p class="oficial"><a href="https://dadosabertos.tse.jus.br/dataset/candidatos-${ano}">Arquivo de candidatos ${ano} no TSE</a></p>
      </div></article>`;
  }).join("");
  document.getElementById("p-candidaturas").hidden = false;
})();

// Linha do tempo: filtra o perfil pelo período clicado.
(function linhaDoTempo() {
  const serieEl = document.getElementById("serie-periodo");
  const barras = document.querySelectorAll(".lt-barra");
  if (!serieEl || !barras.length) return;
  const serie = JSON.parse(serieEl.textContent);
  const banner = document.getElementById("filtro-periodo");
  const br = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4);
  const set = (alvo, txt) => { const el = document.querySelector(`[data-alvo="${alvo}"]`); if (el) el.textContent = txt; };
  const original = {};
  document.querySelectorAll("[data-alvo]").forEach((el) => { original[el.dataset.alvo] = el.tagName === "A" ? el.getAttribute("href") : el.textContent; });
  const dentro = (d, a, b) => d && d >= a && d < b;

  const fmt = (n) => n.toLocaleString("pt-BR");
  const barra = (alvo, partes) => {
    const el = document.querySelector(`[data-alvo="${alvo}"]`);
    if (!el) return;
    el.querySelectorAll("span").forEach((s, i) => { s.style.width = `${partes[i] || 0}%`; });
  };
  const originalBarras = {};
  document.querySelectorAll('[data-alvo$="-barra"]').forEach((el) => {
    originalBarras[el.dataset.alvo] = [...el.querySelectorAll("span")].map((s) => s.style.width);
  });

  function aplicar(a, b, rotulo, fimExibido) {
    const ses = serie.s.filter(([d]) => dentro(d, a, b));
    const conta = (c) => ses.filter(([, x]) => x === c).length;
    const pres = conta("P"), j = conta("J"), n = conta("N"), u = conta("U");
    const pct = (k) => (ses.length ? Math.round((100 * k) / ses.length) : 0);
    if (ses.length) {
      set("pres-pct", `${pct(pres)}%`);
      set("pres-detalhe", `${fmt(pres)} presenças em ${fmt(ses.length)} sessões, ${fmt(j)} ausências justificadas, ${fmt(n)} sem justificativa${u ? `, ${fmt(u)} sem informação` : ""}.`);
    } else {
      set("pres-pct", "—");
      set("pres-detalhe", "Nenhuma sessão deliberativa em exercício neste período.");
    }
    barra("pres-barra", [pct(pres), pct(j), pct(n + u)]);
    const vs = serie.v.filter(([d]) => dentro(d, a, b));
    const votou = vs.filter(([, c]) => c).length;
    set("vot-valor", fmt(votou));
    set("vot-detalhe", `votos registrados em ${fmt(vs.length)} votações neste período`);
    barra("vot-barra", [vs.length ? Math.round((100 * votou) / vs.length) : 0]);
    const link = document.querySelector('[data-alvo="vot-link"]');
    if (link) { link.setAttribute("href", `${original["vot-link"]}?de=${a}&ate=${b}`); link.textContent = "Ver as votações deste período"; }
    const ls = serie.l.filter(([d]) => dentro(d, a, b));
    const nl = (k) => ls.filter(([, x]) => x === k).length;
    set("leis-valor", String(nl("p")));
    set("leis-detalhe", `Projetos apresentados neste período. Também foi coautor(a) de ${nl("c")} e autor(a) de ${nl("h")} de homenagem.`);
    document.querySelectorAll("[data-data]").forEach((el) => el.classList.toggle("fora-do-periodo", !dentro(el.dataset.data, a, b)));
    document.getElementById("filtro-rotulo").textContent = rotulo;
    document.getElementById("filtro-datas").textContent = `${br(a)} a ${br(fimExibido)}`;
    banner.hidden = false;
  }

  function limpar() {
    Object.entries(original).forEach(([alvo, v]) => {
      const el = document.querySelector(`[data-alvo="${alvo}"]`);
      if (!el) return;
      if (el.tagName === "A") { el.setAttribute("href", v); el.textContent = "Ver todas as votações"; } else if (!el.dataset.alvo.endsWith("-barra")) el.textContent = v;
    });
    Object.entries(originalBarras).forEach(([alvo, ws]) => {
      const el = document.querySelector(`[data-alvo="${alvo}"]`);
      el.querySelectorAll("span").forEach((s, i) => { s.style.width = ws[i]; });
    });
    document.querySelectorAll(".fora-do-periodo").forEach((el) => el.classList.remove("fora-do-periodo"));
    barras.forEach((x) => x.setAttribute("aria-pressed", "false"));
    banner.hidden = true;
  }

  barras.forEach((btn) => btn.addEventListener("click", () => {
    const ativo = btn.getAttribute("aria-pressed") === "true";
    limpar();
    if (ativo) return;
    btn.setAttribute("aria-pressed", "true");
    // fim exclusivo: inclui o último dia do período
    const fim = new Date(btn.dataset.fim + "T00:00:00Z");
    fim.setUTCDate(fim.getUTCDate() + 1);
    aplicar(btn.dataset.inicio, fim.toISOString().slice(0, 10), btn.dataset.rotulo, btn.dataset.fim);
  }));
  document.getElementById("filtro-limpar").addEventListener("click", limpar);
})();

// Página de votos: ?de=AAAA-MM-DD&ate=AAAA-MM-DD filtra as linhas.
(function votosPorPeriodo() {
  const q = new URLSearchParams(location.search);
  const de = q.get("de"), ate = q.get("ate");
  const banner = document.getElementById("filtro-periodo");
  if (!de || !ate || !banner || document.getElementById("serie-periodo")) return;
  const br = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4);
  document.querySelectorAll("tr[data-data]").forEach((tr) => tr.classList.toggle("fora-do-periodo", !(tr.dataset.data >= de && tr.dataset.data < ate)));
  const ultimo = new Date(ate + "T00:00:00Z");
  ultimo.setUTCDate(ultimo.getUTCDate() - 1);  // "ate" é exclusivo
  document.getElementById("filtro-datas").textContent = `${br(de)} a ${br(ultimo.toISOString().slice(0, 10))}`;
  banner.hidden = false;
})();

// Perfil: alterna entre votações-chave e recentes.
document.querySelectorAll("[data-lista]").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll("[data-lista]").forEach((b) => {
    const on = b === btn;
    b.setAttribute("aria-pressed", String(on));
    document.getElementById(b.dataset.lista).hidden = !on;
  });
}));

// Perfil: marca a aba da seção visível.
(function abas() {
  const links = [...document.querySelectorAll(".abas a")];
  if (!links.length || !("IntersectionObserver" in window)) return;
  const porId = Object.fromEntries(links.map((l) => [l.getAttribute("href").slice(1), l]));
  const obs = new IntersectionObserver((itens) => {
    itens.filter((i) => i.isIntersecting).forEach((i) => {
      links.forEach((l) => l.classList.toggle("ativa", l === porId[i.target.id]));
    });
  }, { rootMargin: "-40% 0px -55% 0px" });
  Object.keys(porId).forEach((id) => { const el = document.getElementById(id); if (el) obs.observe(el); });
})();
