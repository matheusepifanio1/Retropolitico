"""Candidaturas do TSE (dadosabertos.tse.jus.br / cdn.tse.jus.br).

Arquivo por eleição: consulta_cand_{ano}.zip, com um CSV por UF (e às vezes um _BRASIL),
separador ';', codificação latin-1.

Privacidade: os arquivos brutos trazem CPF, título de eleitor, e-mail e outros dados
pessoais. Eles ficam só no cache privado da coleta. Nada disso é publicado, e a inspeção
abaixo só conta quantos valores existem em cada campo sensível, sem mostrar nenhum.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from datetime import date

from .base import RawStore

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
SENSIVEIS = ["NR_CPF_CANDIDATO", "NR_TITULO_ELEITORAL_CANDIDATO", "DT_NASCIMENTO", "NM_EMAIL", "SQ_CANDIDATO"]
# Colunas que podem aparecer no relatório com valor de exemplo (dados públicos da candidatura).
EXIBIVEIS = ["ANO_ELEICAO", "NM_TIPO_ELEICAO", "NR_TURNO", "DS_ELEICAO", "SG_UF", "SG_UE", "NM_UE", "DS_CARGO",
             "NR_CANDIDATO", "NM_URNA_CANDIDATO", "DS_SITUACAO_CANDIDATURA", "SG_PARTIDO", "DS_SIT_TOT_TURNO"]


def nome_zip(ano: int) -> str:
    return f"consulta_cand_{ano}.zip"


def download(store: RawStore, cfg: dict, log=print) -> None:
    atual = date.today().year
    for ano in cfg["anos"]:
        store.fetch(URL.format(ano=ano), nome_zip(ano), refresh=ano >= atual)
        log(f"  ok {nome_zip(ano)}")
    store.save_manifest()


def _classe(valor: str) -> str:
    v = (valor or "").strip()
    if not v:
        return "vazio"
    if v in ("-1", "-3", "-4", "#NULO#", "#NULO", "#NE#", "NÃO DIVULGÁVEL", "NAO DIVULGAVEL"):
        return f"marcador {v}"
    if re.fullmatch(r"\d+", v):
        return f"{len(v)} dígitos"
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v):
        return "data dd/mm/aaaa"
    if "@" in v:
        return "e-mail"
    if "*" in v or "X" in v.upper().replace("XX", "X"):
        return "mascarado"
    return "outro"


def membros_csv(zf: zipfile.ZipFile) -> list[str]:
    return [n for n in zf.namelist() if n.lower().endswith(".csv")]


def ler(zf: zipfile.ZipFile, membro: str):
    with zf.open(membro) as raw:
        texto = io.TextIOWrapper(raw, encoding="latin-1", newline="")
        yield from csv.DictReader(texto, delimiter=";")


def inspecionar(store: RawStore, cfg: dict) -> None:
    for ano in cfg["anos"]:
        caminho = store.path(nome_zip(ano))
        if not caminho.exists():
            print(f"{nome_zip(ano)}: não baixado")
            continue
        with zipfile.ZipFile(caminho) as zf:
            membros = membros_csv(zf)
            brasil = [m for m in membros if "BRASIL" in m.upper()]
            print(f"{nome_zip(ano)} [{caminho.stat().st_size // 1048576} MB] {len(membros)} CSVs; BRASIL: {brasil[:1]}")
            alvo = brasil or membros
            linhas, classes, cargos, situacoes = 0, {c: Counter() for c in SENSIVEIS}, Counter(), Counter()
            exemplo, header = None, None
            for membro in alvo:
                for r in ler(zf, membro):
                    if header is None:
                        header = list(r.keys())
                        exemplo = {k: r.get(k) for k in EXIBIVEIS if k in r}
                    linhas += 1
                    for c in SENSIVEIS:
                        if c in r:
                            classes[c][_classe(r[c])] += 1
                    cargos[r.get("DS_CARGO", "?")] += 1
                    situacoes[r.get("DS_SIT_TOT_TURNO", "?")] += 1
            print(f"    linhas: {linhas}")
            print(f"    colunas: {header}")
            print(f"    exemplo (só campos públicos): {exemplo}")
            for c in SENSIVEIS:
                print(f"    {c}: {dict(classes[c].most_common(6)) if classes[c] else 'coluna ausente'}")
            print(f"    cargos: {dict(cargos.most_common(15))}")
            print(f"    resultado (DS_SIT_TOT_TURNO): {dict(situacoes.most_common(12))}")
