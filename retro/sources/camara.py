"""Coletor da Câmara dos Deputados (dadosabertos.camara.leg.br).

Duas etapas separadas:
  download(store, cfg)  -> baixa arquivos oficiais para data/raw/camara/ (precisa de rede)
  load(conn, store, cfg)-> normaliza os arquivos já baixados no SQLite (offline)

Arquivos em massa usados (um por ano):
  votacoes, votacoesVotos, votacoesOrientacoes, votacoesProposicoes  (CSV)
  proposicoes, proposicoesAutores                                     (CSV)
  eventos, eventosOrgaos, eventosPresencaDeputados                    (JSON)
API v2:
  /deputados?idLegislatura=N   todos que exerceram na legislatura
  /deputados                   os que estão em exercício hoje
  /deputados/{id}/historico    mudanças de situação (exercício, licença...)
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date

from ..db import register_source
from .base import (
    LayoutError,
    ProgressFn,
    RawStore,
    pick,
    read_csv,
    read_json_records,
    require_any,
)

ARQ = "https://dadosabertos.camara.leg.br/arquivos/{nome}/{fmt}/{nome}-{ano}.{fmt}"
API = "https://dadosabertos.camara.leg.br/api/v2"
PLEN_ID = "180"

CSV_FILES = {
    "votacoes": ["id", "data", "dataHoraRegistro", "siglaOrgao", "aprovacao",
                 "votosSim", "votosNao", "votosOutros", "descricao"],
    "votacoesVotos": ["idVotacao", "dataHoraVoto", "voto", "deputado_id",
                      "deputado_siglaPartido", "deputado_siglaUf"],
    "votacoesOrientacoes": ["idVotacao", "siglaBancada", "orientacao"],
    "votacoesProposicoes": ["idVotacao", "proposicao_id", "proposicao_titulo", "proposicao_ementa"],
    "proposicoes": ["id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao",
                    "ultimoStatus_descricaoSituacao"],
    "proposicoesAutores": ["idProposicao", "idDeputadoAutor", "ordemAssinatura", "proponente"],
}
JSON_FILES = ["eventos", "eventosOrgaos", "eventosPresencaDeputados"]
VOTACAO_FILES = ["votacoes", "votacoesVotos", "votacoesOrientacoes", "votacoesProposicoes"]
PROPOSICAO_FILES = ["proposicoes", "proposicoesAutores"]


def bulk_name(nome: str, ano: int, fmt: str) -> str:
    return f"{nome}-{ano}.{fmt}"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


# ---------------------------------------------------------------- download

def _paginate(store: RawStore, url: str) -> list[dict]:
    out: list[dict] = []
    while url:
        page = store.get_json(url)
        out.extend(page.get("dados", []))
        url = next((l["href"] for l in page.get("links", []) if l.get("rel") == "next"), None)
    return out


def download(store: RawStore, cfg: dict, log: ProgressFn = print) -> None:
    current_year = date.today().year
    leg = cfg["legislatura"]

    def bulk(nome: str, ano: int, fmt: str, refresh: bool) -> None:
        url = ARQ.format(nome=nome, fmt=fmt, ano=ano)
        store.fetch(url, bulk_name(nome, ano, fmt), refresh=refresh)
        log(f"  ok {nome}-{ano}.{fmt}")

    # Votações e sessões de anos fechados não mudam: reaproveita o que já foi baixado.
    for ano in cfg["anos"]:
        for nome in VOTACAO_FILES:
            bulk(nome, ano, "csv", refresh=ano >= current_year)
        for nome in JSON_FILES:
            bulk(nome, ano, "json", refresh=ano >= current_year)
    # Proposições antigas mudam de situação (ex.: viram lei), então sempre atualiza.
    for ano in cfg["anos_proposicoes"]:
        for nome in PROPOSICAO_FILES:
            bulk(nome, ano, "csv", refresh=True)

    url_leg = f"{API}/deputados?idLegislatura={leg}&itens=100&ordem=ASC&ordenarPor=nome"
    deputados = _paginate(store, url_leg)
    store.save_json("deputados-legislatura.json", url_leg, deputados)
    url_atual = f"{API}/deputados?itens=100&ordem=ASC&ordenarPor=nome"
    store.save_json("deputados-em-exercicio.json", url_atual, _paginate(store, url_atual))
    log(f"  ok {len(deputados)} deputados na legislatura {leg}")

    historicos = {}
    for i, d in enumerate(deputados, 1):
        historicos[str(d["id"])] = store.get_json(f"{API}/deputados/{d['id']}/historico", pause=0.1).get("dados", [])
        if i % 100 == 0:
            log(f"  histórico {i}/{len(deputados)}")
    store.save_json("deputados-historico.json", f"{API}/deputados/{{id}}/historico", historicos)
    store.save_manifest()


# ---------------------------------------------------------------- load

def load(conn: sqlite3.Connection, store: RawStore, cfg: dict, log: ProgressFn = print) -> None:
    src = lambda nome: register_source(conn, "camara", store.entry(nome))  # noqa: E731
    inicio = cfg["inicio_mandato"]
    leg = int(cfg["legislatura"])

    _load_deputados(conn, store, src, leg)
    log(f"  deputados: {conn.execute('SELECT COUNT(*) FROM parlamentar').fetchone()[0]}")

    for ano in cfg["anos"]:
        _load_votacoes(conn, store, src, ano, inicio)
    n = conn.execute("SELECT COUNT(*) FROM votacao").fetchone()[0]
    log(f"  votações nominais do Plenário: {n}")

    for ano in cfg["anos"]:
        _load_presenca(conn, store, src, ano, inicio)
    log(f"  sessões deliberativas: {conn.execute('SELECT COUNT(*) FROM sessao').fetchone()[0]}")

    for ano in cfg["anos_proposicoes"]:
        _load_proposicoes(conn, store, src, ano, set(cfg["tipos_legislativos"]))
    log(f"  proposições de autoria: {conn.execute('SELECT COUNT(*) FROM proposicao').fetchone()[0]}")
    conn.commit()


def _load_deputados(conn, store, src, leg: int) -> None:
    nome = "deputados-legislatura.json"
    deputados = read_json_records(store.path(nome))
    require_any(deputados, nome, {"id": ("id",), "nome": ("nome",), "partido": ("siglaPartido",),
                                  "uf": ("siglaUf",)})
    fid = src(nome)
    em_exercicio = {str(d["id"]) for d in read_json_records(store.path("deputados-em-exercicio.json"))}
    src("deputados-em-exercicio.json")
    for d in deputados:
        conn.execute(
            """INSERT INTO parlamentar (id, nome, partido, uf, url_foto, legislatura, em_exercicio, fonte_id)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, partido=excluded.partido,
                 uf=excluded.uf, url_foto=excluded.url_foto, em_exercicio=excluded.em_exercicio""",
            (int(d["id"]), d["nome"], d.get("siglaPartido"), d.get("siglaUf"), d.get("urlFoto"),
             leg, int(str(d["id"]) in em_exercicio), fid),
        )
    # A listagem por legislatura traz o partido/UF do último registro; a de exercício, o atual.
    for d in read_json_records(store.path("deputados-em-exercicio.json")):
        conn.execute("UPDATE parlamentar SET partido=?, uf=?, url_foto=? WHERE id=?",
                     (d.get("siglaPartido"), d.get("siglaUf"), d.get("urlFoto"), int(d["id"])))

    hnome = "deputados-historico.json"
    historicos = json.loads(store.path(hnome).read_text(encoding="utf-8"))
    hid = src(hnome)
    for dep_id, eventos in historicos.items():
        for h in eventos:
            if str(h.get("idLegislatura")) != str(leg):
                continue
            conn.execute(
                "INSERT OR IGNORE INTO situacao_historico VALUES (?,?,?,?,?)",
                (int(dep_id), h["dataHora"], h.get("situacao"), h.get("descricaoStatus"), hid),
            )


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def _load_votacoes(conn, store, src, ano: int, inicio: str) -> None:
    files = {n: bulk_name(n, ano, "csv") for n in VOTACAO_FILES}
    fids = {n: src(f) for n, f in files.items()}

    plen: set[str] = set()
    for r in read_csv(store.path(files["votacoes"]), CSV_FILES["votacoes"]):
        if r["siglaOrgao"] != "PLEN" or (r["data"] or "")[:10] < inicio:
            continue
        plen.add(r["id"])
        conn.execute(
            """INSERT OR REPLACE INTO votacao
               (id, data, data_hora, sigla_orgao, aprovacao, votos_sim, votos_nao, votos_outros, descricao, fonte_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r["id"], r["data"][:10], r["dataHoraRegistro"] or None, r["siglaOrgao"], _int(r["aprovacao"]),
             _int(r["votosSim"]), _int(r["votosNao"]), _int(r["votosOutros"]), r["descricao"], fids["votacoes"]),
        )

    votos_por_votacao: dict[str, list[str]] = {}
    for r in read_csv(store.path(files["votacoesVotos"]), CSV_FILES["votacoesVotos"]):
        if r["idVotacao"] not in plen or not r["deputado_id"]:
            continue
        votos_por_votacao.setdefault(r["idVotacao"], []).append(r["voto"])
        conn.execute(
            "INSERT OR REPLACE INTO voto VALUES (?,?,?,?,?,?,?)",
            (r["idVotacao"], int(r["deputado_id"]), r["voto"].strip(), r["deputado_siglaPartido"],
             r["deputado_siglaUf"], r["dataHoraVoto"] or None, fids["votacoesVotos"]),
        )
    # Votação secreta: a Câmara registra quem votou, mas nenhum voto individual.
    for vid, votos in votos_por_votacao.items():
        if votos and all(not v.strip() for v in votos):
            conn.execute("UPDATE votacao SET secreta=1 WHERE id=?", (vid,))

    for r in read_csv(store.path(files["votacoesOrientacoes"]), CSV_FILES["votacoesOrientacoes"]):
        if r["idVotacao"] in plen:
            conn.execute("INSERT OR REPLACE INTO orientacao VALUES (?,?,?,?)",
                         (r["idVotacao"], r["siglaBancada"], r["orientacao"], fids["votacoesOrientacoes"]))

    for r in read_csv(store.path(files["votacoesProposicoes"]), CSV_FILES["votacoesProposicoes"]):
        if r["idVotacao"] in plen and r["proposicao_id"]:
            conn.execute("INSERT OR REPLACE INTO votacao_proposicao VALUES (?,?,?,?,?)",
                         (r["idVotacao"], int(r["proposicao_id"]), r["proposicao_titulo"],
                          r["proposicao_ementa"], fids["votacoesProposicoes"]))


_SESSAO_DELIB = re.compile(r"sessao deliberativa")
_ENCERRADA = re.compile(r"encerrad")


def _load_presenca(conn, store, src, ano: int, inicio: str) -> None:
    n_ev, n_org, n_pres = (bulk_name(n, ano, "json") for n in JSON_FILES)
    eventos = read_json_records(store.path(n_ev))
    require_any(eventos, n_ev, {
        "id": ("id", "uri"),
        "inicio": ("dataHoraInicio",),
        "tipo": ("descricaoTipo",),
        "situacao": ("situacao",),
    })
    orgaos_evento = read_json_records(store.path(n_org))
    require_any(orgaos_evento, n_org, {
        "evento": ("idEvento", "uriEvento"),
        "orgao": ("idOrgao", "uriOrgao", "siglaOrgao"),
    })
    presencas = read_json_records(store.path(n_pres))
    require_any(presencas, n_pres, {
        "evento": ("idEvento", "uriEvento"),
        "deputado": ("idDeputado", "uriDeputado"),
    })

    plen_eventos: set[str] = set()
    for o in orgaos_evento:
        org_id = pick(o, "idOrgao", uri_keys=("uriOrgao",))
        if org_id == PLEN_ID or (o.get("siglaOrgao") or "").upper() == "PLEN":
            plen_eventos.add(pick(o, "idEvento", uri_keys=("uriEvento",)))

    fid_ev, fid_pres = src(n_ev), src(n_pres)
    src(n_org)
    sessoes: set[str] = set()
    for e in eventos:
        eid = pick(e, "id", uri_keys=("uri",))
        inicio_ev = (e.get("dataHoraInicio") or "")
        orgaos = e.get("orgaos") or []
        no_plen = eid in plen_eventos or any(
            str(o.get("id")) == PLEN_ID or (o.get("sigla") or "").upper() == "PLEN" for o in orgaos
            if isinstance(o, dict))
        if (no_plen and _SESSAO_DELIB.search(_norm(e.get("descricaoTipo", "")))
                and _ENCERRADA.search(_norm(e.get("situacao", ""))) and inicio_ev[:10] >= inicio):
            sessoes.add(eid)
            conn.execute("INSERT OR REPLACE INTO sessao VALUES (?,?,?,?)",
                         (int(eid), inicio_ev, e.get("descricaoTipo"), fid_ev))

    for p in presencas:
        eid = pick(p, "idEvento", uri_keys=("uriEvento",))
        did = pick(p, "idDeputado", uri_keys=("uriDeputado",))
        if eid in sessoes and did:
            conn.execute("INSERT OR IGNORE INTO presenca VALUES (?,?,?)", (int(eid), int(did), fid_pres))


def _load_proposicoes(conn, store, src, ano: int, tipos: set[str]) -> None:
    n_prop, n_aut = bulk_name("proposicoes", ano, "csv"), bulk_name("proposicoesAutores", ano, "csv")
    fid_aut, fid_prop = src(n_aut), src(n_prop)
    deputados = {r[0] for r in conn.execute("SELECT id FROM parlamentar")}

    autores: dict[int, list[tuple[int, int | None, int | None]]] = {}
    for r in read_csv(store.path(n_aut), CSV_FILES["proposicoesAutores"]):
        dep = _int(r["idDeputadoAutor"])
        if dep in deputados:
            autores.setdefault(int(r["idProposicao"]), []).append(
                (dep, _int(r["ordemAssinatura"]), _int(r["proponente"])))

    for r in read_csv(store.path(n_prop), CSV_FILES["proposicoes"]):
        pid = _int(r["id"])
        if pid not in autores or r["siglaTipo"] not in tipos:
            continue
        # Arquivos mais recentes trazem o status mais novo: sobrescreve.
        conn.execute(
            """INSERT INTO proposicao VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET situacao=excluded.situacao, fonte_id=excluded.fonte_id""",
            (pid, r["siglaTipo"], _int(r["numero"]), _int(r["ano"]), r["ementa"],
             (r["dataApresentacao"] or "")[:10] or None, r["ultimoStatus_descricaoSituacao"] or None, fid_prop),
        )
        for dep, ordem, proponente in autores[pid]:
            conn.execute("INSERT OR REPLACE INTO autoria VALUES (?,?,?,?,?)", (pid, dep, ordem, proponente, fid_aut))


__all__ = ["download", "load", "LayoutError"]
