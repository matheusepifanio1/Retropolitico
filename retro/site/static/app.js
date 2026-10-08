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
    const achados = dados
      .filter((d) => (!uf || d.uf === uf) && (!q || d.n.includes(q)))
      .slice(0, 30);
    lista.innerHTML = achados.map((d) => `
      <a class="resultado" href="${base}/deputado/${d.id}/">
        <img src="${esc(d.foto || "")}" alt="" loading="lazy" width="44" height="44">
        <span><span class="nome">${esc(d.nome)}</span><br>
        <span class="small muted">${esc(d.cargo)} · ${esc(d.partido || "sem partido")} · ${esc(d.uf || "")}${d.exercicio ? "" : " · fora de exercício"}</span></span>
        <span class="ir">Ver perfil →</span>
      </a>`).join("");
    vazio.hidden = achados.length > 0;
  }
  campo.addEventListener("input", render);
  ufSel.addEventListener("change", render);
  render();
})();
