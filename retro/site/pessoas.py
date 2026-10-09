"""Busca e perfis de todos os candidatos do TSE, em arquivos estáticos.

Estrutura publicada:
  busca/{abc}.json     {token: [pessoa_id, ...]}  tokens que começam com "abc", ids em ordem de relevância
  pessoas/{n}.json     {pessoa_id: registro}       n = pessoa_id % BALDES
  segundo-turno.json   disputas de 2º turno do ano mais recente

Nenhum dado pessoal além de nome, nome de urna e dados públicos da candidatura.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from .. import compute

BALDES = 4096
PALAVRAS_IGNORADAS = {"das", "dos", "del", "der", "van", "von", "the"}
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA"}
SEM_RESULTADO = {"#NULO#", "#NULO", "#NE", "#NE#", ""}


def tokens(*textos: str) -> set[str]:
    out = set()
    for t in textos:
        for p in re.split(r"[^a-z0-9]+", compute.norm(t)):
            if len(p) >= 3 and p not in PALAVRAS_IGNORADAS:
                out.add(p)
    return out


def rotulo_resultado(resultado: str | None, situacao: str | None, ano: int, ano_atual: int, turno: int) -> str:
    r = (resultado or "").strip().upper()
    if r in ELEITO:
        return "Eleito(a)"
    if r == "SUPLENTE":
        return "Suplente"
    if r == "NÃO ELEITO" or r == "NAO ELEITO":
        return "Não eleito(a)"
    if r == "2º TURNO":
        return "Disputa o 2º turno" if ano == ano_atual and turno == 1 else "Foi ao 2º turno"
    s = (situacao or "").strip().upper()
    if s and s not in ("APTO", "DEFERIDO", "#NE", "#NULO", "#NULO#"):
        return "Candidatura não apta"
    return "Sem resultado publicado"


def gerar(conn: sqlite3.Connection, out: Path, ano_atual: int, presidentes: set | None = None,
          planos: dict | None = None) -> dict:
    presidentes, planos = presidentes or set(), planos or {}
    deputado_de = {r["pessoa_id"]: r["id"] for r in conn.execute(
        "SELECT id, pessoa_id FROM parlamentar WHERE pessoa_id IS NOT NULL")}
    try:
        senador_de = {r["pessoa_id"]: r["codigo"] for r in conn.execute(
            "SELECT codigo, pessoa_id FROM senador WHERE pessoa_id IS NOT NULL")}
    except sqlite3.OperationalError:
        senador_de = {}
    baldes: dict[int, dict] = defaultdict(dict)
    indice: dict[str, list[int]] = defaultdict(list)
    n_pessoas = n_cand = 0
    atual, regs = None, []

    def fechar(pid: str, regs: list) -> None:
        nonlocal n_pessoas
        regs.sort(key=lambda r: (r["ano"], r["turno_final"]), reverse=True)
        ultimo = regs[0]
        cands = []
        eleito = 0
        for r in regs:
            rot = rotulo_resultado(r["resultado"], r["situacao"], r["ano"], ano_atual, r["turno_final"])
            eleito += rot == "Eleito(a)"
            # cargos estaduais e federais têm a UF como unidade eleitoral: não repetir o nome do estado
            local = r["nm_ue"] if r["nm_ue"] and (r["ue"] or "") not in (r["uf"], "BR") else ""
            plano = planos.get((r["ano"], (r["cargo"] or "").upper(), (r["uf"] or "").upper(), (r["partido"] or "").upper()), "")
            cands.append([r["ano"], r["cargo"], r["uf"], local, r["partido"], r["numero"], rot,
                          r["sq_candidato"], int("SUPLEMENTAR" in (r["tipo_eleicao"] or "").upper()), plano])
        rec = {"n": ultimo["nome"], "u": ultimo["nome_urna"], "c": cands}
        dep = deputado_de.get(pid)
        if dep:
            rec["d"] = dep
        sen = senador_de.get(pid)
        if sen:
            rec["s"] = sen
        if pid in presidentes:
            rec["e"] = 1
        baldes[int(pid) % BALDES][pid] = rec
        # relevância: tem perfil completo, já foi eleito, candidatura mais recente
        score = (5 if (dep or sen or pid in presidentes) else 0) * 100000 + min(eleito, 9) * 10000 + ultimo["ano"]
        chave = score * 10**13 + int(pid)
        for t in tokens(ultimo["nome"], ultimo["nome_urna"]):
            indice[t].append(chave)
        n_pessoas += 1

    for r in conn.execute("SELECT * FROM candidatura ORDER BY pessoa_id"):
        n_cand += 1
        if r["pessoa_id"] != atual:
            if atual is not None:
                fechar(atual, regs)
            atual, regs = r["pessoa_id"], []
        regs.append(dict(r))
    if atual is not None:
        fechar(atual, regs)

    (out / "pessoas").mkdir(parents=True, exist_ok=True)
    for b, conteudo in baldes.items():
        (out / "pessoas" / f"{b}.json").write_text(json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")),
                                                   encoding="utf-8")
    shards: dict[str, dict] = defaultdict(dict)
    for t, chaves in indice.items():
        chaves.sort(reverse=True)
        shards[t[:3]][t] = [str(c % 10**13) for c in chaves]
    (out / "busca").mkdir(parents=True, exist_ok=True)
    for p, conteudo in shards.items():
        (out / "busca" / f"{p}.json").write_text(json.dumps(conteudo, separators=(",", ":")), encoding="utf-8")

    # 2º turno do ano mais recente
    disputas = defaultdict(list)
    for r in conn.execute(
            """SELECT c.* FROM candidatura c WHERE c.ano = (SELECT MAX(ano) FROM candidatura)
               AND upper(c.resultado) = '2º TURNO' AND c.cargo IN ('GOVERNADOR', 'PRESIDENTE', 'PREFEITO')
               ORDER BY c.nome_urna"""):
        disputas[(r["cargo"], r["uf"], r["nm_ue"])].append({"id": r["pessoa_id"], "u": r["nome_urna"], "p": r["partido"]})
    segundo = [{"cargo": c, "uf": uf, "local": ue, "candidatos": sorted(v, key=lambda x: compute.norm(x["u"]))}
               for (c, uf, ue), v in sorted(disputas.items(), key=lambda kv: (kv[0][0] != "PRESIDENTE", kv[0][1], kv[0][2]))]
    return {"pessoas": n_pessoas, "candidaturas": n_cand, "shards": len(shards), "segundo_turno": segundo}
