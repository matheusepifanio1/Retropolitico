"""Indicadores do Senado e da Presidência. Mesmas regras gerais de compute.py:
nada inferido além do dado oficial; sem dado suficiente, o resultado é None.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta

from .compute import Periodo, is_homenagem, is_lei, norm
from .sources.senado import classificar_voto

MEMBRO = {"titular", "suplente", "membro"}


def periodos(conn: sqlite3.Connection, cod: int, janela: str, ate: str) -> list[Periodo]:
    """Períodos de exercício [início, fim) dentro da janela. O fim oficial é inclusivo."""
    out = []
    for r in conn.execute("SELECT inicio, fim FROM sen_exercicio WHERE codigo=? ORDER BY inicio", (cod,)):
        ini = max(r["inicio"][:10], janela)
        fim = (date.fromisoformat(r["fim"][:10]) + timedelta(days=1)).isoformat() if r["fim"] else ate[:10]
        fim = min(fim, ate[:10]) if fim > ate[:10] else fim
        if fim > ini:
            out.append(Periodo(ini, fim))
    return out


def _dentro(dia: str, ps: list[Periodo]) -> bool:
    return any(p.contem(dia) for p in ps)


def tipos_comparecimento(conn) -> dict[str, str]:
    return {r["sigla"]: r["descricao"] for r in conn.execute("SELECT sigla, descricao FROM sen_tipo_comparecimento")}


def registros(conn, cod: int, ps: list[Periodo], tipos: dict[str, str]) -> list[dict]:
    """Cada votação nominal no período de exercício, com o registro do senador classificado."""
    meus = {r["votacao_id"]: r["sigla"] for r in conn.execute("SELECT votacao_id, sigla FROM sen_voto WHERE codigo=?", (cod,))}
    out = []
    for v in conn.execute("SELECT * FROM sen_votacao ORDER BY data, id"):
        if not v["data"] or not _dentro(v["data"], ps):
            continue
        sigla = meus.get(v["id"])
        if sigla is None:
            cod_c, motivo = "U", None
        else:
            cod_c, motivo = classificar_voto(sigla, tipos)
        if cod_c == "X":
            continue
        out.append({**dict(v), "sigla": sigla, "cod": cod_c, "motivo": motivo})
    return out


def presenca(regs: list[dict]) -> dict | None:
    if not regs:
        return None
    c = Counter(r["cod"] for r in regs)
    t = len(regs)
    pct = lambda n, tot: round(100 * n / tot) if tot else 0  # noqa: E731
    anos: dict[str, Counter] = {}
    for r in regs:
        anos.setdefault(r["data"][:4], Counter())[r["cod"]] += 1
    por_ano = [{"ano": a, "total": sum(k.values()), "presentes": k["P"], "justificadas": k["J"],
                "nao_justificadas": k["N"], "sem_informacao": k["U"], "pct": pct(k["P"], sum(k.values())),
                "pct_j": pct(k["J"], sum(k.values())), "pct_n": pct(k["N"] + k["U"], sum(k.values()))}
               for a, k in sorted(anos.items())]
    motivos = Counter(r["motivo"] for r in regs if r["motivo"]).most_common()
    return {"total": t, "presentes": c["P"], "justificadas": c["J"], "nao_justificadas": c["N"],
            "sem_informacao": c["U"], "pct": pct(c["P"], t), "pct_j": pct(c["J"], t),
            "pct_n": pct(c["N"] + c["U"], t), "motivos": motivos, "por_ano": por_ano}


ROTULO_VOTO = {"Sim": "SIM", "Não": "NÃO", "Abstenção": "ABSTENÇÃO", "Votou": "VOTOU (SECRETA)", "VO": "VOTOU (SECRETA)",
               "NCom": "NÃO COMPARECEU", "P-NRV": "PRESENTE, SEM VOTO", "P-OD": "OBSTRUÇÃO"}


def rotulo(r: dict, tipos: dict[str, str]) -> str:
    s = r["sigla"]
    if s is None:
        return "SEM REGISTRO"
    if s.startswith("Presidente"):
        return "PRESIDIU"
    return ROTULO_VOTO.get(s) or (tipos.get(s) or s).upper()


def resumo_votos(regs: list[dict]) -> dict:
    c = Counter()
    for r in regs:
        s = r["sigla"] or ""
        if s in ("Sim", "Não", "Abstenção"):
            c[s] += 1
        elif s in ("Votou", "VO"):
            c["Secreta"] += 1
    return {"total": len(regs), "sim": c["Sim"], "nao": c["Não"], "abstencao": c["Abstenção"], "secreta": c["Secreta"],
            "com_voto": c["Sim"] + c["Não"] + c["Abstenção"] + c["Secreta"]}


def leis(conn, cod: int) -> dict:
    rows = conn.execute(
        """SELECT p.*, a.principal FROM sen_autoria a JOIN sen_processo p ON p.id = a.processo_id
           WHERE a.codigo=? ORDER BY p.data_apresentacao DESC""", (cod,)).fetchall()
    principal, coautor, homenagem, resolucoes, outros = [], [], [], [], 0
    for r in rows:
        virou = bool(r["norma"]) or is_lei(r["situacao"])
        if not virou:
            outros += bool(r["principal"])
            continue
        item = dict(r)
        if r["sigla_tipo"] == "PRS":
            # Resoluções tratam do funcionamento interno do Senado (ex.: grupos parlamentares): não são leis.
            resolucoes.append(item)
        elif is_homenagem(r["ementa"]):
            homenagem.append(item)
        elif r["principal"]:
            principal.append(item)
        else:
            coautor.append(item)
    return {"principal": principal, "coautor": coautor, "homenagem": homenagem, "resolucoes": resolucoes,
            "apresentadas_principal_nao_lei": outros}


def cargos(conn, cod: int) -> dict:
    rows = [dict(r) for r in conn.execute("SELECT * FROM sen_cargo WHERE codigo=? ORDER BY inicio DESC", (cod,))]
    return {"direcao": [r for r in rows if norm(r["cargo"]) not in MEMBRO],
            "membro": [r for r in rows if norm(r["cargo"]) in MEMBRO]}


# ---------------------------------------------------------------- Presidência

def presidentes(conn, desde_ano: int) -> list[dict]:
    """Presidentes eleitos segundo o TSE, com o mandato constitucional de 4 anos a partir de 1º de janeiro.
    Só eleições a partir de `desde_ano` (antes disso houve impeachment e o TSE não registra substituições)."""
    out = []
    for r in conn.execute(
            """SELECT * FROM candidatura WHERE cargo='PRESIDENTE' AND upper(resultado)='ELEITO' AND ano>=?
               ORDER BY ano""", (desde_ano,)):
        inicio = f"{r['ano'] + 1}-01-01"
        fim = f"{r['ano'] + 4}-12-31"
        out.append({**dict(r), "inicio": inicio, "fim": fim})
    return out


def atos_presidente(conn, p: dict, hoje: str) -> dict | None:
    if p["inicio"] > hoje:
        return None  # mandato ainda não começou
    fim = min(p["fim"], hoje)
    vetos = []
    for v in conn.execute("SELECT * FROM veto WHERE data_publicacao BETWEEN ? AND ? ORDER BY data_publicacao DESC",
                          (p["inicio"], fim)):
        v = dict(v)
        u = v["url_planalto"] or ""
        if "null" in u or "2147483647" in u:
            v["url_planalto"] = None  # link malformado na fonte: usa a página do veto no Congresso
        vetos.append(v)
    # Uma MP pode aparecer com mais de um registro na Câmara: conta cada número/ano uma vez (o registro mais recente).
    unicas: dict = {}
    for m in conn.execute(
            "SELECT * FROM medida_provisoria WHERE data_apresentacao BETWEEN ? AND ? ORDER BY id",
            (p["inicio"], fim)):
        unicas[(m["numero"], m["ano"])] = dict(m)
    mpvs = sorted(unicas.values(), key=lambda m: (m["data_apresentacao"], m["numero"] or 0), reverse=True)
    situacoes = Counter((m["situacao"] or "Sem situação publicada") for m in mpvs).most_common()
    viraram = sum(1 for m in mpvs if is_lei(m["situacao"]))
    por_ano: dict[str, Counter] = {}
    for v in vetos:
        por_ano.setdefault(v["data_publicacao"][:4], Counter())["total" if v["total"] else "parcial"] += 1
    for m in mpvs:
        por_ano.setdefault(m["data_apresentacao"][:4], Counter())["mpv"] += 1
    return {"vetos": vetos, "vetos_totais": sum(v["total"] for v in vetos),
            "vetos_parciais": sum(1 - v["total"] for v in vetos), "mpvs": mpvs, "mpv_viraram_lei": viraram,
            "mpv_situacoes": situacoes, "ate": fim,
            "por_ano": [{"ano": a, **{k: c[k] for k in ("total", "parcial", "mpv")}} for a, c in sorted(por_ano.items())]}
