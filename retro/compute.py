"""Indicadores calculados a partir do banco. Cada regra está descrita em docs/METODOLOGIA.md.

Princípios:
  - Nada é inferido além do que o dado oficial diz.
  - Quando não há dado suficiente, o resultado é None (o site mostra "indisponível"),
    nunca zero.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

LEI = re.compile(r"transformad[oa] (em|na) (norma juridica|lei)")
# Ementas típicas de leis honoríficas ou comemorativas. Lista pública na metodologia.
HOMENAGEM = [
    r"\bdenomina\b", r"\bconfere (a|o)\b.*\b(denominacao|titulo)\b", r"\binstitui o dia\b",
    r"\binstitui a semana\b", r"\binstitui o mes\b", r"\binstitui o ano\b", r"\binscreve o nome\b",
    r"livro dos herois", r"\bcapital nacional d", r"\bdeclara patron[oa]\b", r"\bdata comemorativa\b",
]
_HOMENAGEM_RE = re.compile("|".join(HOMENAGEM))
HOMENAGEM_LEGIVEL = [
    "denomina", "confere a/o … denominação/título", "institui o dia", "institui a semana",
    "institui o mês", "institui o ano", "inscreve o nome", "livro dos heróis",
    "capital nacional d…", "declara patrono/patrona", "data comemorativa",
]
VOTOS_VALIDOS = ("Sim", "Não", "Abstenção", "Obstrução")


def norm(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def is_lei(situacao: str | None) -> bool:
    return bool(LEI.search(norm(situacao)))


def is_homenagem(ementa: str | None) -> bool:
    return bool(_HOMENAGEM_RE.search(norm(ementa)))


@dataclass
class Periodo:
    inicio: str
    fim: str  # exclusivo

    def contem(self, momento: str) -> bool:
        return self.inicio <= momento < self.fim


def periodos_exercicio(historico: list[sqlite3.Row | dict], ate: str) -> list[Periodo]:
    """Intervalos [início, fim) em que a situação era 'Exercício'."""
    periodos: list[Periodo] = []
    aberto: str | None = None
    for h in sorted(historico, key=lambda h: h["data_hora"]):
        # Registros de troca de nome/partido vêm com situação vazia: não mudam o exercício.
        if not (h["situacao"] or "").strip():
            continue
        em_exercicio = norm(h["situacao"]) == "exercicio"
        if em_exercicio and aberto is None:
            aberto = h["data_hora"]
        elif not em_exercicio and aberto is not None:
            periodos.append(Periodo(aberto, h["data_hora"]))
            aberto = None
    if aberto is not None:
        periodos.append(Periodo(aberto, ate))
    return periodos


def _no_periodo(momento: str | None, periodos: list[Periodo]) -> bool:
    return bool(momento) and any(p.contem(momento) for p in periodos)


PRESENTE_SITE = "presenca"
AUSENTE_SITE = "ausencia"


def classificar_sessoes(conn: sqlite3.Connection, dep_id: int, periodos: list[Periodo]) -> list[dict]:
    """Cada sessão deliberativa em exercício, classificada como:
    P presente (registro de presença, voto, ou 'Presença' no site da Câmara)
    J ausência justificada (motivo publicado no site da Câmara)
    N ausência sem justificativa ('Ausência' no site da Câmara)
    U sem registro de presença e sem informação de justificativa
    """
    registrados = {r[0] for r in conn.execute("SELECT sessao_id FROM presenca WHERE parlamentar_id=?", (dep_id,))}
    votou = {r[0] for r in conn.execute(
        """SELECT DISTINCT v.id_evento FROM voto x JOIN votacao v ON v.id = x.votacao_id
           WHERE x.parlamentar_id=? AND v.id_evento IS NOT NULL""", (dep_id,))}
    site = {r["data"]: r["status"] for r in conn.execute(
        "SELECT data, status FROM frequencia_dia WHERE parlamentar_id=?", (dep_id,))}
    out = []
    for s in conn.execute("SELECT id, data_hora FROM sessao ORDER BY data_hora"):
        if not _no_periodo(s["data_hora"], periodos):
            continue
        dia = s["data_hora"][:10]
        status = site.get(dia)
        if s["id"] in registrados or s["id"] in votou or norm(status) == PRESENTE_SITE:
            cod, motivo = "P", None
        elif status is None:
            cod, motivo = "U", None
        elif norm(status) == AUSENTE_SITE:
            cod, motivo = "N", None
        else:
            cod, motivo = "J", status
        out.append({"id": s["id"], "data": dia, "cod": cod, "motivo": motivo,
                    "so_voto": s["id"] in votou and s["id"] not in registrados,
                    "conflito": cod == "P" and norm(status) == AUSENTE_SITE})
    return out


@dataclass
class Presenca:
    sessoes: int
    presentes: int
    justificadas: int = 0
    nao_justificadas: int = 0
    sem_informacao: int = 0
    motivos: list = field(default_factory=list)
    por_ano: list[dict] = field(default_factory=list)
    so_por_voto: int = 0
    conflitos: int = 0  # presença/voto registrado em dia marcado como "Ausência" no site

    @property
    def sem_registro(self) -> int:
        return self.sessoes - self.presentes

    @property
    def pct(self) -> int | None:
        return round(100 * self.presentes / self.sessoes) if self.sessoes else None


def _pct(n: int, t: int) -> int:
    return round(100 * n / t) if t else 0


def presenca(conn: sqlite3.Connection, dep_id: int, periodos: list[Periodo]) -> Presenca | None:
    if not periodos:
        return None
    sessoes = classificar_sessoes(conn, dep_id, periodos)
    if not sessoes:
        return None
    from collections import Counter
    c = Counter(s["cod"] for s in sessoes)
    motivos = Counter(s["motivo"] for s in sessoes if s["motivo"])
    anos: dict[str, Counter] = {}
    for s in sessoes:
        anos.setdefault(s["data"][:4], Counter())[s["cod"]] += 1
    por_ano = []
    for ano, k in sorted(anos.items()):
        t = sum(k.values())
        por_ano.append({"ano": ano, "sessoes": t, "presentes": k["P"], "justificadas": k["J"],
                        "nao_justificadas": k["N"], "sem_informacao": k["U"], "sem_registro": t - k["P"],
                        "pct": _pct(k["P"], t), "pct_j": _pct(k["J"], t), "pct_n": _pct(k["N"], t),
                        "pct_u": _pct(k["U"], t)})
    return Presenca(len(sessoes), c["P"], c["J"], c["N"], c["U"], motivos.most_common(), por_ano,
                    sum(s["so_voto"] for s in sessoes), sum(s["conflito"] for s in sessoes))


@dataclass
class ResumoVotos:
    votacoes_no_periodo: int
    com_registro: int
    por_tipo: dict[str, int]


def resumo_votos(conn: sqlite3.Connection, dep_id: int, periodos: list[Periodo]) -> ResumoVotos | None:
    if not periodos:
        return None
    votos = {r["votacao_id"]: r["voto"] for r in conn.execute(
        "SELECT votacao_id, voto FROM voto WHERE parlamentar_id=?", (dep_id,))}
    total = registrados = 0
    tipos: dict[str, int] = {}
    for v in conn.execute("SELECT id, data_hora, data, secreta FROM votacao"):
        if not _no_periodo(v["data_hora"] or v["data"], periodos):
            continue
        total += 1
        if v["id"] in votos:
            registrados += 1
            chave = "Secreta" if v["secreta"] else (votos[v["id"]] or "Sem voto")
            tipos[chave] = tipos.get(chave, 0) + 1
    return ResumoVotos(total, registrados, tipos)


def leis(conn: sqlite3.Connection, dep_id: int) -> dict:
    rows = conn.execute(
        """SELECT p.*, a.ordem_assinatura FROM autoria a JOIN proposicao p ON p.id = a.proposicao_id
           WHERE a.parlamentar_id=? ORDER BY p.data_apresentacao DESC""", (dep_id,)).fetchall()
    principal, coautor, homenagem, tramitando = [], [], [], 0
    for r in rows:
        if not is_lei(r["situacao"]):
            if r["ordem_assinatura"] == 1:
                tramitando += 1
            continue
        item = dict(r)
        if is_homenagem(r["ementa"]):
            homenagem.append(item)
        elif r["ordem_assinatura"] == 1:
            principal.append(item)
        else:
            coautor.append(item)
    return {"principal": principal, "coautor": coautor, "homenagem": homenagem,
            "apresentadas_principal_nao_lei": tramitando}


def trajetoria(historico: list) -> list[dict]:
    """Linha do tempo do mandato, com o texto oficial de cada registro."""
    itens = []
    for h in sorted(historico, key=lambda h: h["data_hora"]):
        itens.append({
            "data": h["data_hora"][:10],
            "situacao": h["situacao"] or "Registro de nome/partido",
            "descricao": h["descricao_status"] or "",
            "partido": h["partido"] or "",
            "exercicio": norm(h["situacao"]) == "exercicio",
        })
    return itens


MEMBRO = {"titular", "suplente"}


def cargos(conn: sqlite3.Connection, dep_id: int) -> dict:
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM cargo WHERE parlamentar_id=? ORDER BY data_inicio DESC", (dep_id,))]
    direcao = [r for r in rows if norm(r["titulo"]) not in MEMBRO]
    membro = [r for r in rows if norm(r["titulo"]) in MEMBRO]
    return {"direcao": direcao, "membro": membro}


ROTULO_SITUACAO = {"exercicio": "Em exercício", "licenca": "Licença", "suplencia": "Suplência",
                   "convocado": "Convocado", "vacancia": "Vacância", "suspenso": "Suspenso",
                   "fim de mandato": "Fim de mandato", "fim do mandato": "Fim de mandato"}


def _dia(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def linha_do_tempo(historico: list, direcao: list[dict], inicio: str, ate: str) -> dict:
    """Faixas da linha do tempo do perfil, com posições em % entre o início do mandato e hoje."""
    t0, t1 = _dia(inicio), _dia(ate)
    span = max((t1 - t0).days, 1)

    def pos(a: str, b: str) -> tuple[float, float]:
        da, db = max(_dia(a), t0), min(_dia(b), t1)
        left = 100 * (da - t0).days / span
        return round(left, 2), round(max(100 * (db - da).days / span, 0.6), 2)

    # Situação: cada registro vale até o próximo registro de situação.
    regs = [h for h in sorted(historico, key=lambda h: h["data_hora"]) if (h["situacao"] or "").strip()]
    situacao = []
    for i, h in enumerate(regs):
        fim = regs[i + 1]["data_hora"] if i + 1 < len(regs) else ate
        if _dia(fim) <= t0 or _dia(h["data_hora"]) >= t1:
            continue
        chave = norm(h["situacao"])
        if situacao and situacao[-1]["chave"] == chave:
            situacao[-1]["fim"] = fim[:10]
            continue
        situacao.append({"chave": chave, "rotulo": ROTULO_SITUACAO.get(chave, h["situacao"]),
                         "detalhe": h["descricao_status"] or "", "inicio": max(h["data_hora"][:10], inicio),
                         "fim": fim[:10], "exercicio": chave == "exercicio"})
    for s in situacao:
        s["left"], s["width"] = pos(s["inicio"], s["fim"])

    # Cargos de direção, empilhados em linhas quando se sobrepõem.
    cargos, linhas_fim = [], []
    for c in sorted(direcao, key=lambda c: c["data_inicio"] or ""):
        ini = c["data_inicio"] or inicio
        fim = c["data_fim"] or ate[:10]
        if _dia(fim) <= t0:
            continue
        linha = next((i for i, f in enumerate(linhas_fim) if f <= ini), None)
        if linha is None:
            linhas_fim.append(fim)
            linha = len(linhas_fim) - 1
        else:
            linhas_fim[linha] = fim
        left, width = pos(ini, fim)
        cargos.append({"rotulo": f"{c['titulo']} · {c['sigla_orgao'] or c['nome_orgao']}",
                       "detalhe": c["nome_orgao"] or "", "inicio": max(ini, inicio), "fim": fim,
                       "linha": linha, "left": left, "width": width, "atual": not c["data_fim"]})

    anos = [{"ano": a, "left": pos(f"{a}-01-01", f"{a}-01-02")[0]}
            for a in range(t0.year + 1, t1.year + 1)]
    return {"inicio": inicio, "fim": ate[:10], "situacao": situacao, "cargos": cargos,
            "linhas_cargos": max(len(linhas_fim), 1), "anos": anos}


CODIGO_VOTO = {"Sim": "S", "Não": "N", "Abstenção": "A", "Obstrução": "O", "Artigo 17": "P"}


def serie_periodo(conn: sqlite3.Connection, dep_id: int, periodos: list[Periodo], leis_dep: dict) -> dict:
    """Dados compactos para o filtro por período no navegador (só datas e códigos)."""
    sessoes = [[s["data"], s["cod"]] for s in classificar_sessoes(conn, dep_id, periodos)]
    votos = {r["votacao_id"]: r["voto"] for r in conn.execute(
        "SELECT votacao_id, voto FROM voto WHERE parlamentar_id=?", (dep_id,))}
    vs = []
    for v in conn.execute("SELECT id, data, data_hora, secreta FROM votacao ORDER BY data"):
        if not _no_periodo(v["data_hora"] or v["data"], periodos):
            continue
        if v["id"] not in votos:
            cod = ""
        elif v["secreta"]:
            cod = "X"
        else:
            cod = CODIGO_VOTO.get(votos[v["id"]], "X")
        vs.append([v["data"], cod])
    leis = [[p["data_apresentacao"] or "", k] for k, lista in
            (("p", leis_dep["principal"]), ("c", leis_dep["coautor"]), ("h", leis_dep["homenagem"]))
            for p in lista]
    return {"s": sessoes, "v": vs, "l": leis}


def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
