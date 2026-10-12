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
  // Uma linha que diz quem é a pessoa, a partir dos dados oficiais.
  const cargoTxt = (c) => `${titulo(c[1]).toLowerCase()}${c[3] ? ` em ${titulo(c[3])}` : ""} (${c[2]})`;
  const quemE = (p) => {
    const atual = (p.m || []).find((m) => !m[3]);
    const ultima = p.c[0];
    const anoAtual = new Date().getFullYear();
    const linhas = [];
    if (atual) linhas.push(`${atual[4]}${atual[0] === "pres" ? "" : ` (${atual[5]})`} · em exercício`);
    if (ultima && ultima[0] >= anoAtual - 1 && ultima !== undefined) {
      const r = ultima[6];
      if (r === "Disputa o 2º turno") linhas.push(`Disputa o 2º turno para ${cargoTxt(ultima)}`);
      else if (!atual) linhas.push(`${r === "Eleito(a)" ? "Eleito(a)" : "Candidato(a) a"} ${cargoTxt(ultima)}, ${ultima[0]}${r !== "Eleito(a)" ? ` · ${r}` : ""}`);
    }
    if (!linhas.length && ultima) {
      const eleito = p.c.find((c) => c[6] === "Eleito(a)");
      linhas.push(eleito ? `Eleito(a) ${cargoTxt(eleito)} em ${eleito[0]}` : `Candidato(a) a ${cargoTxt(ultima)} em ${ultima[0]} · ${ultima[6]}`);
    }
    return linhas;
  };
  return { base, norm, esc, titulo, json, pessoa, quemE, cargoTxt };
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
  const cargoSel = document.getElementById("cargo");
  const contagem = document.getElementById("busca-contagem");
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
    if (!palavras.length) { lista.innerHTML = ""; vazio.hidden = true; if (contagem) contagem.textContent = ""; return; }
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
        const cargo = cargoSel ? cargoSel.value : "";
        const okCargo = !cargo || p.c.some((c) => norm(c[1]) === norm(cargo));
        const okUf = !uf || p.c.some((c) => c[2] === uf);
        if (okCargo && okUf) achados.push([id, p]);
      }
    }
    lista.innerHTML = achados.slice(0, 25).map(([id, p]) => {
      const nome = titulo(p.u || p.n);
      const ini = nome.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
      const foto = p.f ? `<img class="ini" src="${esc(p.f)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ini',textContent:'${esc(ini)}'}))">` : `<span class="ini" aria-hidden="true">${esc(ini)}</span>`;
      const linhas = RETRO.quemE(p);
      const extra = (p.d || p.s) ? '<span class="selo-res completo">Votos e presença</span>' : p.e ? '<span class="selo-res completo">Vetos e MPs</span>' : "";
      const civil = norm(p.n) !== norm(p.u) ? `<span class="civil">${esc(titulo(p.n))}</span>` : "";
      return `<a class="resultado" href="${base}/pessoa/?id=${id}">
        ${foto}
        <span class="txt"><span class="nome">${esc(nome)}</span>
        <span class="sub">${esc(linhas[0] || "")}</span>${linhas[1] ? `<span class="sub2">${esc(linhas[1])}</span>` : ""}${civil}${extra}</span>
        <svg class="seta" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></a>`;
    }).join("");
    if (contagem) contagem.textContent = achados.length ? `${achados.length >= 25 ? "Mais de 25" : achados.length} ${achados.length === 1 ? "pessoa encontrada" : "pessoas encontradas"}` : "";
    vazio.hidden = achados.length > 0;
  }

  let espera;
  const agendar = () => { clearTimeout(espera); espera = setTimeout(render, 180); };
  const inicial = new URLSearchParams(location.search).get("q");
  if (inicial) campo.value = inicial;
  campo.addEventListener("input", agendar);
  ufSel.addEventListener("change", render);
  if (cargoSel) cargoSel.addEventListener("change", render);
  render();
})();

// Perfil único: linha do tempo horizontal (eleições e mandatos) e painel de detalhes.
(async function paginaPessoa() {
  const cfgEl = document.getElementById("config-pessoa");
  if (!cfgEl) return;
  const { base, esc, titulo, pessoa, cargoTxt } = RETRO;
  const id = new URLSearchParams(location.search).get("id");
  const p = id && /^\d+$/.test(id) ? await pessoa(id) : null;
  if (!p) {
    document.getElementById("p-nome").textContent = "Pessoa não encontrada";
    document.getElementById("p-erro").hidden = false;
    return;
  }
  const hoje = new Date().toISOString().slice(0, 10);
  const anoHoje = Number(hoje.slice(0, 4));
  const br = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "");
  const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const mesAno = (iso) => `${MESES[Number(iso.slice(5, 7)) - 1]} de ${iso.slice(0, 4)}`;

  // ---------- dados
  const nome = titulo(p.u || p.n);
  const eleicoes = p.c.map((c) => ({
    id: `e-${c[7]}`, ano: c[0], cargo: c[1], uf: c[2], local: c[3], partido: c[4], numero: c[5], res: c[6],
    sq: c[7], suplementar: c[8], plano: c[9] || "", data: `${c[0]}-10-05`,
  })).sort((a, b) => a.data.localeCompare(b.data));

  const TIPO_CARGO = { "DEPUTADO FEDERAL": "dep", "SENADOR": "sen", "PRESIDENTE": "pres" };
  const mandatos = (p.m || []).map(([tipo, ref, ini, fim, rot, uf]) => ({
    id: `m-${tipo}-${ref}`, tipo, ref, ini, fim, rot, uf, dados: true,
  }));
  const sobrepoe = (a, b) => a.ini < (b.fim || hoje) && (a.fim || hoje) > b.ini;

  // Mandatos de quem foi eleito em cargos sem dados abertos: período previsto pela Constituição.
  const previsto = (e) => {
    const c = e.cargo, a = e.ano;
    if (/SUPLENTE/.test(c)) return null;
    if (/PREFEITO|VEREADOR/.test(c)) return [`${a + 1}-01-01`, `${a + 4}-12-31`];
    if (/DEPUTADO/.test(c)) return [`${a + 1}-02-01`, `${a + 5}-01-31`];
    if (c === "SENADOR") return [`${a + 1}-02-01`, `${a + 9}-01-31`];
    if (/GOVERNADOR|PRESIDENTE/.test(c)) return [`${a + 1}-01-01`, `${a + 4}-12-31`];
    return null;
  };
  eleicoes.filter((e) => e.res === "Eleito(a)" && !e.suplementar).forEach((e) => {
    const per = previsto(e);
    if (!per || per[0] > hoje) return;
    const m = { id: `m-tse-${e.sq}`, tipo: "tse", ref: e.sq, ini: per[0], fim: per[1], dados: false, eleicao: e,
      rot: `${titulo(e.cargo)}${e.local ? ` em ${titulo(e.local)}` : ` (${e.uf})`}` };
    const tipo = TIPO_CARGO[e.cargo];
    if (tipo && mandatos.some((x) => x.dados && x.tipo === tipo && sobrepoe(x, m))) return;
    mandatos.push(m);
  });
  mandatos.sort((a, b) => a.ini.localeCompare(b.ini));

  // ---------- topo
  document.title = `${nome} · Retrospectiva`;
  document.getElementById("p-nome").textContent = nome;
  const fotoEl = document.getElementById("p-foto");
  const iniciais = nome.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  fotoEl.textContent = iniciais;
  if (p.f) {
    const img = new Image();
    img.alt = `Foto oficial de ${nome}`;
    img.onload = () => { fotoEl.textContent = ""; fotoEl.appendChild(img); };
    img.src = p.f;
  }
  const linhas = RETRO.quemE(p);
  document.getElementById("p-frase").textContent = linhas.join(". ") + ".";
  const anos = eleicoes.map((e) => e.ano);
  const partido = p.c[0] ? p.c[0][4] : "";
  document.getElementById("p-chips").innerHTML = [
    partido && `<span class="chip">${esc(partido)}</span>`,
    `<span class="chip">${eleicoes.length} ${eleicoes.length === 1 ? "eleição" : "eleições"} desde ${Math.min(...anos)}</span>`,
    mandatos.length && `<span class="chip">${mandatos.length} ${mandatos.length === 1 ? "mandato" : "mandatos"}</span>`,
    p.n && p.u && p.n !== p.u && `<span class="chip">Nome completo: ${esc(titulo(p.n))}</span>`,
  ].filter(Boolean).join("");

  // ---------- linha do tempo
  const t0 = `${Math.min(...anos, ...mandatos.map((m) => Number(m.ini.slice(0, 4))))}-01-01`;
  const anoFim = Math.max(anoHoje, ...anos);
  const t1 = `${anoFim + 1}-01-01`;
  const ms = (iso) => Date.parse(iso + "T00:00:00Z");
  const span = ms(t1) - ms(t0);
  const pos = (iso) => Math.max(0, Math.min(100, (100 * (ms(iso) - ms(t0))) / span));
  const nAnos = anoFim + 1 - Number(t0.slice(0, 4));
  const tl = document.getElementById("tl");
  tl.style.minWidth = `${Math.max(nAnos * 72, 320)}px`;

  let marcas = "";
  for (let a = Number(t0.slice(0, 4)); a <= anoFim; a++) {
    const x = pos(`${a}-01-01`);
    marcas += `<span class="tl-ano" style="left:${x}%">${a}</span>`;
  }
  const grade = Array.from({ length: nAnos }, (_, i) => `<span class="tl-grade" style="left:${pos(`${Number(t0.slice(0, 4)) + i}-01-01`)}%"></span>`).join("");
  const hojeX = pos(hoje);

  const classeRes = (r) => (r === "Eleito(a)" ? "eleito" : r === "Disputa o 2º turno" || r === "Foi ao 2º turno" ? "turno" : r === "Suplente" ? "suplente" : "nao");
  const pontos = eleicoes.map((e) => `<button type="button" class="tl-ponto ${classeRes(e.res)}" data-sel="${e.id}" style="left:${pos(e.data)}%"
      aria-label="Eleição de ${e.ano}: ${esc(titulo(e.cargo))}${e.local ? ` em ${esc(titulo(e.local))}` : ""}, ${esc(e.res)}" aria-pressed="false">
      <span class="tl-bola"></span><span class="tl-rot">${e.ano}</span></button>`).join("");

  // mandatos que se sobrepõem vão para linhas diferentes
  const fimLinha = [];
  const barras = mandatos.map((m) => {
    let linha = fimLinha.findIndex((f) => f <= m.ini);
    if (linha < 0) { fimLinha.push(m.fim || "9999"); linha = fimLinha.length - 1; } else fimLinha[linha] = m.fim || "9999";
    const fimDesenho = m.fim && m.fim < hoje ? m.fim : (m.fim && m.fim > hoje && !m.dados ? m.fim : hoje);
    const left = pos(m.ini), width = Math.max(pos(fimDesenho) - left, 1.2);
    const per = m.fim ? `de ${br(m.ini)} a ${br(m.fim)}` : `desde ${br(m.ini)}`;
    return `<button type="button" class="tl-barra ${m.dados ? "com-dados" : "sem-dados"}" data-sel="${m.id}"
      style="left:${left}%;width:${width}%;top:${8 + linha * 48}px" aria-pressed="false"
      aria-label="Mandato: ${esc(m.rot)}, ${per}${m.dados ? "" : ", sem dados abertos"}"><span>${esc(m.rot)}</span></button>`;
  }).join("");
  const alturaM = 16 + Math.max(fimLinha.length, 1) * 48;

  tl.innerHTML = `
    <div class="tl-eixo">${marcas}</div>
    <div class="tl-faixa"><span class="tl-nome">Eleições</span><div class="tl-trilho tl-eleicoes">${grade}<span class="tl-hoje" style="left:${hojeX}%"></span>${pontos}</div></div>
    <div class="tl-faixa"><span class="tl-nome">Mandatos</span><div class="tl-trilho" style="height:${alturaM}px">${grade}<span class="tl-hoje" style="left:${hojeX}%"><span>hoje</span></span>${barras || '<span class="tl-vazio">Nenhum mandato registrado</span>'}</div></div>`;

  // ---------- painel de detalhes
  const painel = document.getElementById("p-detalhe");
  const botao = (href, txt, forte) => `<a class="${forte ? "botao" : "botao-sec"}" href="${href}">${txt}</a>`;

  function htmlEleicao(e) {
    const mand = mandatos.find((m) => (m.eleicao && m.eleicao.sq === e.sq) ||
      (m.dados && TIPO_CARGO[e.cargo] === m.tipo && e.res === "Eleito(a)" && m.ini.slice(0, 4) === String(e.ano + 1)));
    const notas = {
      "Eleito(a)": mand ? "O mandato que veio desta eleição aparece na faixa Mandatos." : "",
      "Suplente": "Não ficou com a vaga, mas pode assumir se alguém do mesmo partido ou coligação sair.",
      "Disputa o 2º turno": "O 2º turno acontece no último domingo de outubro.",
      "Candidatura não apta": "O registro foi indeferido, cancelado ou houve renúncia.",
    };
    return `<div class="mandato">
      <div class="m-topo"><div><span class="m-rotulo">Eleição selecionada</span>
        <h2>${esc(titulo(e.cargo))}${e.local ? ` em ${esc(titulo(e.local))}` : ""} <span class="m-uf">(${esc(e.uf)})</span></h2>
        <p class="m-sub">Eleições de ${e.ano}${e.suplementar ? " · eleição suplementar" : ""}</p></div>
        <span class="res ${classeRes(e.res)}">${esc(e.res)}</span></div>
      <div class="mini-fatos">
        <div><span>Partido</span><strong>${esc(e.partido)}</strong></div>
        <div><span>Número na urna</span><strong>${esc(e.numero)}</strong></div>
      </div>
      ${notas[e.res] ? `<p>${notas[e.res]}</p>` : ""}
      <div class="acoes">
        ${e.plano ? botao(esc(e.plano), "Plano de governo entregue ao TSE (PDF)", true) : ""}
        ${mand ? `<button type="button" class="botao-sec" data-sel="${mand.id}">Ver o mandato</button>` : ""}
        ${botao(`https://dadosabertos.tse.jus.br/dataset/candidatos-${e.ano}`, "Arquivo oficial do TSE")}
      </div></div>`;
  }

  function htmlSemDados(m) {
    const e = m.eleicao;
    const c = e.cargo;
    const motivo = /PREFEITO|VEREADOR/.test(c) ? "As câmaras municipais e as prefeituras não publicam votos, presença e atos num formato padronizado."
      : /ESTADUAL|DISTRITAL|GOVERNADOR/.test(c) ? "As assembleias legislativas e os governos estaduais não publicam esses dados num formato padronizado."
      : c === "DEPUTADO FEDERAL" ? "Os dados da Câmara neste site começam em fevereiro de 2023."
      : c === "SENADOR" ? "Os dados do Senado neste site começam em fevereiro de 2019."
      : "Os atos deste mandato ainda não estão no site.";
    return `<div class="mandato">
      <div class="m-topo"><div><span class="m-rotulo">Mandato selecionado</span>
        <h2>${esc(m.rot)}</h2>
        <p class="m-sub">Período previsto: ${m.ini.slice(0, 4)} a ${m.fim.slice(0, 4)} · eleito(a) em ${e.ano} pelo ${esc(e.partido)}</p></div></div>
      <div class="aviso-claro"><strong>Ainda não temos votos e presença deste mandato.</strong> ${motivo}</div>
      <p class="nota">O período é o previsto em lei a partir do resultado da eleição no TSE. Ele não mostra renúncia, cassação ou licença.</p>
      <div class="acoes"><button type="button" class="botao-sec" data-sel="${e.id}">Ver a eleição de ${e.ano}</button></div></div>`;
  }

  const fragmentos = new Map();
  async function htmlMandato(m) {
    const url = `${base}/frag/${m.tipo}/${m.ref}.html`;
    if (!fragmentos.has(url)) fragmentos.set(url, fetch(url).then((r) => (r.ok ? r.text() : "")).catch(() => ""));
    const html = await fragmentos.get(url);
    return html || `<div class="vazio">Não foi possível carregar os detalhes deste mandato. Tente de novo.</div>`;
  }

  function prepararPainel() {
    painel.querySelectorAll(".filtro-tema").forEach((sel) => sel.addEventListener("change", () => {
      const lista = sel.closest(".m-sec").querySelector(".lista-votos");
      let n = 0;
      lista.querySelectorAll(".voto-card").forEach((card) => {
        const ok = !sel.value || card.dataset.tema === sel.value;
        card.hidden = !ok;
        n += ok;
      });
      const aviso = lista.querySelector(".sem-tema");
      if (aviso) aviso.hidden = n > 0;
    }));
  }

  let versao = 0;
  async function selecionar(sel, { rolar = false, focar = false } = {}) {
    const minha = ++versao;
    document.querySelectorAll(".tl [data-sel]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sel === sel)));
    const m = mandatos.find((x) => x.id === sel);
    const e = eleicoes.find((x) => x.id === sel);
    if (!m && !e) return;
    history.replaceState(null, "", `#${sel}`);
    painel.hidden = false;
    let html;
    if (e) html = htmlEleicao(e);
    else if (!m.dados) html = htmlSemDados(m);
    else { painel.innerHTML = '<div class="carregando">Carregando o mandato…</div>'; html = await htmlMandato(m); }
    if (minha !== versao) return;
    painel.innerHTML = html;
    prepararPainel();
    const btn = document.querySelector(`.tl [data-sel="${sel}"]`);
    if (btn && rolar) {
      const caixa = document.getElementById("tl-rolagem");
      caixa.scrollLeft = Math.max(0, btn.offsetLeft - caixa.clientWidth / 2);
    }
    if (focar) painel.focus({ preventScroll: false });
  }

  document.addEventListener("click", (ev) => {
    const alvo = ev.target.closest("[data-sel]");
    if (!alvo) return;
    const deFora = !alvo.closest(".tl");
    selecionar(alvo.dataset.sel, { rolar: deFora, focar: !deFora ? false : true });
    if (!deFora) painel.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  const inicial = location.hash.slice(1);
  const padrao = (mandatos.find((m) => m.dados && !m.fim) || [...mandatos].reverse().find((m) => m.dados) ||
    eleicoes[eleicoes.length - 1]).id;
  document.getElementById("p-trajetoria").hidden = false;
  const caixa = document.getElementById("tl-rolagem");
  caixa.scrollLeft = caixa.scrollWidth;
  selecionar([...mandatos, ...eleicoes].some((x) => x.id === inicial) ? inicial : padrao, { rolar: true });
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
