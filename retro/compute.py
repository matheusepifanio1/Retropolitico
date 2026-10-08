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
from datetime import datetime, timezone

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


@dataclass
class Presenca:
    sessoes: int
    presentes: int
    por_ano: list[dict] = field(default_factory=list)
    so_por_voto: int = 0  # sessões sem registro de presença, mas com voto registrado do deputado

    @property
    def sem_registro(self) -> int:
        return self.sessoes - self.presentes

    @property
    def pct(self) -> int | None:
        return round(100 * self.presentes / self.sessoes) if self.sessoes else None


def presenca(conn: sqlite3.Connection, dep_id: int, periodos: list[Periodo]) -> Presenca | None:
    if not periodos:
        return None
    registrados = {r[0] for r in conn.execute("SELECT sessao_id FROM presenca WHERE parlamentar_id=?", (dep_id,))}
    # Quem votou numa sessão estava presente nela, mesmo que o registro de presença falte.
    votou = {r[0] for r in conn.execute(
        """SELECT DISTINCT v.id_evento FROM voto x JOIN votacao v ON v.id = x.votacao_id
           WHERE x.parlamentar_id=? AND v.id_evento IS NOT NULL""", (dep_id,))}
    presentes = registrados | votou
    anos: dict[str, list[int]] = {}
    total = pres = so_voto = 0
    for s in conn.execute("SELECT id, data_hora FROM sessao ORDER BY data_hora"):
        if not _no_periodo(s["data_hora"], periodos):
            continue
        total += 1
        foi = s["id"] in presentes
        so_voto += s["id"] in votou and s["id"] not in registrados
        pres += foi
        a = anos.setdefault(s["data_hora"][:4], [0, 0])
        a[0] += 1
        a[1] += foi
    if total == 0:
        return None
    por_ano = [{"ano": ano, "sessoes": t, "presentes": p, "sem_registro": t - p,
                "pct": round(100 * p / t)} for ano, (t, p) in sorted(anos.items())]
    return Presenca(total, pres, por_ano, so_voto)


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


def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
