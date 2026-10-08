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

// Busca da página inicial (dados em busca.json, gerado no build).
(async function busca() {
  const campo = document.getElementById("busca");
  if (!campo) return;
  const lista = document.getElementById("resultados");
  const ufSel = document.getElementById("uf");
  const vazio = document.getElementById("sem-resultados");
  const base = document.body.dataset.base || "";
  let dados = [];
  try {
    dados = await (await fetch(base + "/busca.json")).json();
  } catch (e) {
    lista.innerHTML = "";
    vazio.hidden = false;
    vazio.textContent = "Não foi possível carregar a lista. Use a lista completa abaixo.";
    return;
  }
  const norm = (s) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function render() {
    const q = norm(campo.value.trim());
    const uf = ufSel.value;
    if (!q && !uf) { lista.innerHTML = ""; vazio.hidden = true; return; }
    const achados = dados
      .filter((d) => (!uf || d.uf === uf) && (!q || d.n.includes(q)))
      .slice(0, 30);
    lista.innerHTML = achados.map((d) => `
      <a class="resultado" href="${base}/deputado/${d.id}/">
        <img src="${esc(d.foto || "")}" alt="" loading="lazy" width="52" height="52">
        <span class="txt"><span class="nome">${esc(d.nome)}</span>
        <span class="sub">${esc(d.cargo)} ${d.partido ? "pelo " + esc(d.partido) : "sem partido"}, ${esc(d.uf || "")}${d.exercicio ? "" : ". Fora de exercício hoje"}</span></span>
        <span class="selo-res completo">Votos e presença</span>
      </a>`).join("");
    vazio.hidden = achados.length > 0;
  }
  const inicial = new URLSearchParams(location.search).get("q");
  if (inicial) campo.value = inicial;
  campo.addEventListener("input", render);
  ufSel.addEventListener("change", render);
  render();
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
