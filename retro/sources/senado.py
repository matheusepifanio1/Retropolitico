"""Senado Federal e Congresso Nacional (legis.senado.leg.br/dadosabertos).

Coleta:
  - senadores das legislaturas configuradas (titulares e suplentes que exerceram);
  - mandatos com períodos de exercício e filiações partidárias;
  - cargos em comissões;
  - processos de autoria (projetos e normas geradas);
  - votações nominais do Plenário, mês a mês, com o registro de cada senador
    (inclui as siglas oficiais de ausência: licença, missão, "não compareceu"...);
  - vetos presidenciais por ano (base do perfil de presidente);
  - tabela oficial de tipos de comparecimento.

As respostas JSON do Senado são conversões de XML: um item único às vezes vem
como objeto em vez de lista. `_lista` trata os dois casos.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

from .base import DownloadError, LayoutError, RawStore, require_any

API = "https://legis.senado.leg.br/dadosabertos"

# Tipos de documento que podem virar norma e entram no perfil (PLV fica de fora, como na Câmara).
TIPOS_DOC = {
    "Projeto de Lei Ordinária": "PL",
    "Projeto de Lei": "PL",
    "Projeto de Lei Complementar": "PLP",
    "Proposta de Emenda à Constituição": "PEC",
    "Projeto de Decreto Legislativo": "PDL",
    "Projeto de Resolução": "PRS",
    "Projeto de Resolução do Senado": "PRS",
}


def _lista(x) -> list:
    if x is None or x == "":
        return []
    return x if isinstance(x, list) else [x]


def _get(d, *caminho):
    for k in caminho:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _meses(inicio: str, hoje: date):
    a, m = int(inicio[:4]), int(inicio[5:7])
    while (a, m) <= (hoje.year, hoje.month):
        yield a, m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def _fim_mes(a: int, m: int) -> date:
    return (date(a + (m == 12), 1 if m == 12 else m + 1, 1) - timedelta(days=1))


def _get_ou_none(store: RawStore, url: str, log, rotulo: str):
    try:
        return store.get_json(url, pause=0.05)
    except DownloadError as exc:
        log(f"  AVISO {rotulo}: {exc}")
        return None


def download(store: RawStore, cfg: dict, log=print) -> None:
    hoje = date.today()
    codigos: set[str] = set()
    for leg in cfg["legislaturas"]:
        url = f"{API}/senador/lista/legislatura/{leg}"
        d = store.get_json(url)
        store.save_json(f"senadores-leg{leg}.json", url, d)
        for p in _lista(_get(d, "ListaParlamentarLegislatura", "Parlamentares", "Parlamentar")):
            codigos.add(str(_get(p, "IdentificacaoParlamentar", "CodigoParlamentar")))
    codigos.discard("None")
    log(f"  ok {len(codigos)} senadores nas legislaturas {cfg['legislaturas']}")

    detalhes, mandatos, cargos, processos = {}, {}, {}, {}
    for i, cod in enumerate(sorted(codigos, key=int), 1):
        detalhes[cod] = _get_ou_none(store, f"{API}/senador/{cod}", log, f"detalhe {cod}")
        mandatos[cod] = store.get_json(f"{API}/senador/{cod}/mandatos", pause=0.05)  # essencial
        cargos[cod] = _get_ou_none(store, f"{API}/senador/{cod}/cargos", log, f"cargos {cod}")
        processos[cod] = _get_ou_none(store, f"{API}/processo?codigoParlamentarAutor={cod}", log, f"processos {cod}")
        if processos[cod] is not None:
            # Guarda só os campos usados (as respostas trazem milhares de requerimentos).
            processos[cod] = [{k: p.get(k) for k in ("id", "identificacao", "tipoDocumento", "ementa", "dataApresentacao",
                                                      "situacaoAtual", "normaGerada", "autoria", "codigoMateria")}
                              for p in processos[cod] if p.get("tipoDocumento") in TIPOS_DOC]
        if i % 50 == 0:
            log(f"  senadores {i}/{len(codigos)}")
    store.save_json("senadores-detalhe.json", f"{API}/senador/{{codigo}}", detalhes)
    store.save_json("senadores-mandatos.json", f"{API}/senador/{{codigo}}/mandatos", mandatos)
    store.save_json("senadores-cargos.json", f"{API}/senador/{{codigo}}/cargos", cargos)
    store.save_json("senadores-processos.json", f"{API}/processo?codigoParlamentarAutor={{codigo}}", processos)
    log("  ok mandatos, cargos e processos")

    # Votações: meses fechados há mais de 60 dias não mudam.
    n = 0
    for a, m in _meses(cfg["inicio"], hoje):
        nome = f"senado-votacoes-{a}-{m:02d}.json"
        fim = _fim_mes(a, m)
        if store.path(nome).exists() and (hoje - fim).days > 60:
            try:
                store.entry(nome)
                continue
            except KeyError:
                pass
        url = f"{API}/votacao?dataInicio={a}-{m:02d}-01&dataFim={fim.isoformat()}"
        store.save_json(nome, url, store.get_json(url, pause=0.1))
        n += 1
    log(f"  ok votações ({n} meses atualizados)")

    for ano in range(int(cfg["inicio"][:4]), hoje.year + 1):
        nome = f"cn-vetos-{ano}.json"
        if store.path(nome).exists() and ano < hoje.year - 1:
            continue
        url = f"{API}/materia/vetos/{ano}"
        store.save_json(nome, url, store.get_json(url))
    log("  ok vetos")
    url = f"{API}/plenario/lista/tiposComparecimento"
    store.save_json("senado-tipos-comparecimento.json", url, store.get_json(url))


# ---------------------------------------------------------------- carga

# Classificação das siglas oficiais do Senado (tabela "tipos de comparecimento").
PRESENTE = {"Sim", "Não", "Abstenção", "Votou", "VO", "P-NRV", "P-OD", "PR", "PS", "OB", "Obstrução",
            "SF", "PSF", "Presidente (art. 51 RISF)"}
SEM_JUSTIFICATIVA = {"NCom"}
# Não estava em exercício ou não houve votação individual: não entra na conta.
FORA_DA_CONTA = {"AFO", "CAS", "DJ", "FAL", "IMP", "PER", "REN", "TER", "RET", "DIS", "NH", "SI", "VS",
                 "RR", "IL", "LCS"}
# Sem informação suficiente para classificar.
SEM_INFORMACAO = {"NA", "NR", "L7", "LL", ""}
# Siglas usadas nas votações com grafia diferente da tabela oficial.
ALIAS = {"MERC": "MER"}


def classificar_voto(sigla: str | None, tipos: dict[str, str]) -> tuple[str, str | None]:
    """P presente, J ausência com motivo oficial, N não compareceu, U sem informação, X fora da conta."""
    s = (sigla or "").strip()
    s = ALIAS.get(s, s) if ALIAS.get(s) in tipos else s
    if s in PRESENTE or s.startswith("Presidente"):
        return "P", None
    if s in SEM_JUSTIFICATIVA:
        return "N", None
    if s in FORA_DA_CONTA:
        return "X", None
    if s in SEM_INFORMACAO or s not in tipos:
        return "U", None
    return "J", tipos[s]


def _dia_seguinte(iso: str) -> str:
    return (date.fromisoformat(iso[:10]) + timedelta(days=1)).isoformat()


def _primeiro_autor(autoria: str | None) -> str:
    a = (autoria or "").split("(")[0]
    return re.sub(r"^\s*senador[a]?\s+", "", a, flags=re.I).strip()


def load(conn, store: RawStore, cfg: dict, log=print) -> None:
    from ..compute import norm

    def src(nome: str) -> int:
        from .. import db
        return db.register_source(conn, "senado", store.entry(nome))

    # Senadores: reúne as listas das legislaturas.
    lista: dict[str, dict] = {}
    for leg in cfg["legislaturas"]:
        nome = f"senadores-leg{leg}.json"
        fid = src(nome)
        d = json.loads(store.path(nome).read_text(encoding="utf-8"))
        ps = _lista(_get(d, "ListaParlamentarLegislatura", "Parlamentares", "Parlamentar"))
        if not ps:
            raise LayoutError(f"{nome}: lista de senadores vazia ou em formato inesperado")
        for p in ps:
            ident = p.get("IdentificacaoParlamentar") or {}
            ms = _lista(_get(p, "Mandatos", "Mandato"))
            lista[str(ident.get("CodigoParlamentar"))] = {**ident, "_fid": fid,
                                                          "_uf": ms[0].get("UfParlamentar") if ms else None}
    det = json.loads(store.path("senadores-detalhe.json").read_text(encoding="utf-8"))
    mand = json.loads(store.path("senadores-mandatos.json").read_text(encoding="utf-8"))
    carg = json.loads(store.path("senadores-cargos.json").read_text(encoding="utf-8"))
    proc = json.loads(store.path("senadores-processos.json").read_text(encoding="utf-8"))
    fid_det, fid_mand = src("senadores-detalhe.json"), src("senadores-mandatos.json")
    fid_carg, fid_proc = src("senadores-cargos.json"), src("senadores-processos.json")

    janela = cfg["inicio"]
    hoje = date.today().isoformat()
    for cod, ident in lista.items():
        d = _get(det.get(cod) or {}, "DetalheParlamentar", "Parlamentar", "IdentificacaoParlamentar") or {}
        mandatos = _lista(_get(mand.get(cod) or {}, "MandatoParlamentar", "Parlamentar", "Mandatos", "Mandato"))
        em_exercicio = 0
        partidos = []
        for m in mandatos:
            leg1 = _get(m, "PrimeiraLegislaturaDoMandato") or {}
            leg2 = _get(m, "SegundaLegislaturaDoMandato") or {}
            m_ini = leg1.get("DataInicio") or ""
            m_fim = leg2.get("DataFim") or leg1.get("DataFim") or ""
            if m_fim and m_fim < janela:
                continue  # mandato encerrado antes da janela
            conn.execute("INSERT OR REPLACE INTO sen_mandato VALUES (?,?,?,?,?,?,?)",
                         (int(cod), str(m.get("CodigoMandato")), m.get("UfParlamentar"),
                          m.get("DescricaoParticipacao"), m_ini, m_fim, fid_mand))
            for e in _lista(_get(m, "Exercicios", "Exercicio")):
                ini, fim = e.get("DataInicio"), e.get("DataFim")
                if not ini or (fim and fim < janela):
                    continue
                if not fim and m_fim and m_fim >= hoje:
                    em_exercicio = 1
                conn.execute("INSERT OR REPLACE INTO sen_exercicio VALUES (?,?,?,?,?,?)",
                             (int(cod), ini, fim or (m_fim if m_fim and m_fim < hoje else None),
                              e.get("SiglaCausaAfastamento"), e.get("DescricaoCausaAfastamento"), fid_mand))
            for pt in _lista(_get(m, "Partidos", "Partido")):
                partidos.append((pt.get("DataFiliacao") or "", pt.get("Sigla")))
                conn.execute("INSERT OR IGNORE INTO sen_partido VALUES (?,?,?,?,?,?)",
                             (int(cod), pt.get("Sigla"), pt.get("Nome"), pt.get("DataFiliacao"),
                              pt.get("DataDesfiliacao"), fid_mand))
        if not conn.execute("SELECT 1 FROM sen_exercicio WHERE codigo=?", (int(cod),)).fetchone():
            continue  # suplente que não exerceu na janela: não vira perfil
        partido = d.get("SiglaPartidoParlamentar") or (max(partidos)[1] if partidos else None)
        sexo = {"Masculino": "M", "Feminino": "F"}.get(ident.get("SexoParlamentar") or d.get("SexoParlamentar") or "")
        conn.execute("INSERT OR REPLACE INTO senador VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (int(cod), ident.get("NomeParlamentar") or d.get("NomeParlamentar"),
                      ident.get("NomeCompletoParlamentar") or d.get("NomeCompletoParlamentar"), sexo, partido,
                      d.get("UfParlamentar") or ident["_uf"], d.get("UrlFotoParlamentar"),
                      d.get("UrlPaginaParlamentar"), em_exercicio, None, fid_det if d else ident["_fid"]))

        for c in _lista(_get(carg.get(cod) or {}, "CargoParlamentar", "Parlamentar", "Cargos", "Cargo")):
            fim = c.get("DataFim")
            if fim and fim < janela:
                continue
            com = c.get("IdentificacaoComissao") or {}
            conn.execute("INSERT OR IGNORE INTO sen_cargo VALUES (?,?,?,?,?,?,?,?)",
                         (int(cod), com.get("SiglaComissao"), com.get("NomeComissao"), com.get("SiglaCasaComissao"),
                          c.get("DescricaoCargo"), c.get("DataInicio"), fim, fid_carg))

    nomes = {r[0]: norm(r[1]) for r in conn.execute("SELECT codigo, nome FROM senador")}
    n_proc = 0
    for cod, ps in proc.items():
        if ps is None or int(cod) not in nomes:
            continue
        for p in ps:
            data = (p.get("dataApresentacao") or "")[:10]
            if not data or data < cfg["proposicoes_desde"]:
                continue
            conn.execute("INSERT OR IGNORE INTO sen_processo VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (int(p["id"]), p.get("identificacao"), TIPOS_DOC.get(p.get("tipoDocumento")),
                          p.get("ementa"), data, p.get("situacaoAtual"), p.get("normaGerada"), p.get("autoria"),
                          p.get("codigoMateria"), fid_proc))
            principal = norm(_primeiro_autor(p.get("autoria"))) == nomes[int(cod)]
            conn.execute("INSERT OR REPLACE INTO sen_autoria VALUES (?,?,?,?)", (int(p["id"]), int(cod), int(principal), fid_proc))
            n_proc += 1

    # Votações nominais do Plenário do Senado.
    n_vot = n_votos = 0
    for f in sorted(store.dir.glob("senado-votacoes-*.json")):
        fid = src(f.name)
        vs = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(vs, dict):
            vs = _lista(vs.get("votacoes") or vs.get("dados"))
        require_any(vs, f.name, {"id": ("codigoSessaoVotacao",), "data": ("dataSessao",), "votos": ("votos",)})
        for v in vs:
            if v.get("casaSessao") not in (None, "SF"):
                continue
            vid = int(v["codigoSessaoVotacao"])
            votos = _lista(v.get("votos"))
            conn.execute("INSERT OR REPLACE INTO sen_votacao VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (vid, (v.get("dataSessao") or "")[:10], v.get("identificacao"), v.get("ementa"),
                          v.get("descricaoVotacao"), v.get("resultadoVotacao"),
                          1 if v.get("votacaoSecreta") == "S" else 0, v.get("codigoMateria"), v.get("idProcesso"),
                          _get(v, "informeLegislativo", "texto"), fid))
            n_vot += 1
            for x in votos:
                conn.execute("INSERT OR REPLACE INTO sen_voto VALUES (?,?,?,?,?,?)",
                             (vid, int(x["codigoParlamentar"]), x.get("siglaVotoParlamentar"),
                              x.get("siglaPartidoParlamentar"), x.get("siglaUFParlamentar"), fid))
                n_votos += 1

    tipos = json.loads(store.path("senado-tipos-comparecimento.json").read_text(encoding="utf-8"))
    fid = src("senado-tipos-comparecimento.json")
    for t in _lista(_get(tipos, "ListaTiposComparecimento", "TiposComparecimento", "TipoComparecimento")):
        conn.execute("INSERT OR REPLACE INTO sen_tipo_comparecimento VALUES (?,?,?)", (t["Sigla"], t["Descricao"], fid))

    # Vetos presidenciais (Congresso Nacional).
    n_vetos = 0
    for f in sorted(store.dir.glob("cn-vetos-*.json")):
        fid = src(f.name)
        d = json.loads(f.read_text(encoding="utf-8"))
        for v in _lista(_get(d, "ListaVetosAnoCN", "Vetos", "Veto")):
            mat, vet = v.get("Materia") or {}, v.get("MateriaVetada") or {}
            norma = vet.get("NormaGerada") or {}
            conn.execute("INSERT OR REPLACE INTO veto VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (int(v["Codigo"]), f"VET {mat.get('Numero')}/{mat.get('Ano')}", 1 if v.get("Total") == "Sim" else 0,
                          v.get("DataPublicacao") or v.get("DataRecebimentoCongresso"), v.get("Assunto"), mat.get("Ementa"),
                          f"{vet.get('Sigla')} {vet.get('Numero')}/{vet.get('Ano')}", norma.get("NomeNorma"),
                          _get(v, "Mensagem", "UrlPlanalto"), int(v.get("QuantidadeDispositivos") or 0),
                          f"https://www.congressonacional.leg.br/materias/vetos/-/veto/detalhe/{v['Codigo']}", fid))
            n_vetos += 1
    log(f"  Senado: {conn.execute('SELECT COUNT(*) FROM senador').fetchone()[0]} senadores com exercício desde {janela}, "
        f"{n_vot} votações nominais, {n_votos} registros de voto, {n_proc} autorias, {n_vetos} vetos")


def ligar_tse(conn, log=print) -> None:
    """Liga o senador às candidaturas do TSE pelo nome completo, na mesma UF, em candidatura ao Senado.
    Só liga com uma única pessoa compatível."""
    from ..compute import norm

    def chave(s):
        return " ".join(re.sub(r"[^a-z ]", " ", norm(s)).split())

    idx: dict = {}
    for uf, nome, urna, pid, cargo in conn.execute(
            "SELECT uf, nome, nome_urna, pessoa_id, cargo FROM candidatura WHERE cargo IN ('SENADOR','1º SUPLENTE','2º SUPLENTE')"):
        idx.setdefault(("c", uf, chave(nome)), set()).add(pid)
        idx.setdefault(("u", uf, chave(urna)), set()).add(pid)
    ligados = 0
    for cod, nome, completo, uf in conn.execute("SELECT codigo, nome, nome_completo, uf FROM senador").fetchall():
        pid = None
        for k in (("c", uf, chave(completo)), ("u", uf, chave(nome))):
            achados = idx.get(k)
            if achados:
                pid = next(iter(achados)) if len(achados) == 1 else None
                break
        if pid:
            conn.execute("UPDATE senador SET pessoa_id=? WHERE codigo=?", (pid, cod))
            ligados += 1
    total = conn.execute("SELECT COUNT(*) FROM senador").fetchone()[0]
    log(f"  senadores ligados ao TSE: {ligados} de {total}")
