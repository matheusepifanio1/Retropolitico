"""Sondagem de fontes novas: baixa amostras e mostra o formato real.

Não grava nada no banco nem no site. Serve para escrever a carga com base no
formato real das respostas, e não em documentação que pode estar desatualizada.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import requests

from .sources.base import USER_AGENT

SENADO = "https://legis.senado.leg.br/dadosabertos"
TSE_CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
DIVULGA = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"

S = requests.Session()
S.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def resumo(obj, prof=0, max_itens=2, max_prof=7):
    """Estrutura do JSON com exemplos curtos."""
    pad = "  " * prof
    if prof > max_prof:
        return pad + "…"
    if isinstance(obj, dict):
        linhas = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                linhas.append(f"{pad}{k}: {type(v).__name__}{'[' + str(len(v)) + ']' if isinstance(v, list) else ''}")
                linhas.append(resumo(v, prof + 1, max_itens, max_prof))
            else:
                linhas.append(f"{pad}{k} = {str(v)[:90]!r}")
        return "\n".join(linhas)
    if isinstance(obj, list):
        return "\n".join(resumo(x, prof, max_itens, max_prof) + f"\n{pad}--" for x in obj[:max_itens])
    return pad + repr(obj)[:90]


def get(url, **params):
    try:
        r = S.get(url, params=params, timeout=(15, 120))
        print(f"\n### GET {r.url} -> {r.status_code} {r.headers.get('content-type')} {len(r.content)} bytes")
        if r.status_code != 200:
            print(r.text[:400])
            return None
        try:
            return r.json()
        except ValueError:
            print(r.text[:1500])
            return None
    except Exception as exc:
        print(f"\n### GET {url} {params} -> ERRO {exc}")
        return None


def head(url):
    try:
        r = S.head(url, timeout=(15, 60), allow_redirects=True)
        print(f"HEAD {url} -> {r.status_code} {int(r.headers.get('content-length', 0)) / 1e6:.0f} MB")
    except Exception as exc:
        print(f"HEAD {url} -> ERRO {exc}")


def lista_senadores():
    d = get(f"{SENADO}/senador/lista/legislatura/57")
    if d:
        print(resumo(d, max_itens=1))
    return d


def achar(obj, chave):
    """Primeira ocorrência de `chave` em qualquer nível."""
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            r = achar(v, chave)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = achar(v, chave)
            if r is not None:
                return r
    return None


def senado():
    print("=" * 30, "SENADO", "=" * 30)
    d = lista_senadores()
    lista = achar(d, "Parlamentar") or []
    print(f"\nsenadores na legislatura 57: {len(lista)}")
    cod = None
    for p in lista:
        ident = p.get("IdentificacaoParlamentar", {})
        if ident.get("NomeParlamentar", "").upper().startswith(("FLÁVIO ARNS", "FLAVIO ARNS")):
            cod = ident.get("CodigoParlamentar")
    if not cod and lista:
        cod = lista[0].get("IdentificacaoParlamentar", {}).get("CodigoParlamentar")
    print("código de exemplo:", cod)
    if cod:
        for path in (f"/senador/{cod}", f"/senador/{cod}/mandatos", f"/senador/{cod}/licencas",
                     f"/senador/{cod}/cargos", f"/senador/{cod}/comissoes"):
            x = get(SENADO + path)
            if x:
                print(resumo(x, max_itens=2))
        x = get(f"{SENADO}/processo", codigoParlamentarAutor=cod)
        if x is not None:
            print(f"tipo={type(x).__name__} tamanho={len(x) if isinstance(x, list) else '-'}")
            print(resumo(x, max_itens=2))
            normas = [p for p in (x if isinstance(x, list) else []) if achar(p, "normaGerada") or achar(p, "norma")]
            print("processos com norma:", len(normas))
            if normas:
                print(resumo(normas[0]))
    v = get(f"{SENADO}/votacao", dataInicio="2025-05-01", dataFim="2025-05-31")
    if v is not None:
        print(f"tipo={type(v).__name__} tamanho={len(v) if isinstance(v, list) else '-'}")
        print(resumo(v, max_itens=1, max_prof=9))
        if isinstance(v, list):
            from collections import Counter
            siglas = Counter(achar(voto, "siglaVotoParlamentar") for vot in v for voto in (vot.get("votos") or []))
            print("siglas de voto:", siglas.most_common())
    for path in ("/plenario/lista/tiposComparecimento", "/materia/vetos/2025"):
        x = get(SENADO + path)
        if x:
            print(resumo(x, max_itens=2))
    x = get(f"{SENADO}/senador/lista/legislatura/56")
    print("legislatura 56:", len(achar(x, "Parlamentar") or []))


def tse(raw: Path):
    print("\n" + "=" * 30, "TSE", "=" * 30)
    for ano in (2018, 2022, 2026):
        head(f"{TSE_CDN}/votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip")
        head(f"{TSE_CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip")
        head(f"{TSE_CDN}/consulta_cand/consulta_cand_{ano}.zip")
    head(f"{TSE_CDN}/consulta_cand/bem_candidato_2026.zip")
    head(f"{TSE_CDN}/consulta_cand/rede_social_candidato_2026.zip")
    head(f"{TSE_CDN}/consulta_coligacao/consulta_coligacao_2026.zip")

    # Colunas de consulta_cand 2026 e exemplos de governador / presidente / senador.
    z = raw / "tse" / "consulta_cand_2026.zip"
    exemplos = {}
    if z.exists():
        with zipfile.ZipFile(z) as zf:
            nome = next((n for n in zf.namelist() if n.endswith("_BRASIL.csv")), None) or \
                next(n for n in zf.namelist() if n.endswith(".csv"))
            with zf.open(nome) as f:
                rd = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")
                print("colunas consulta_cand 2026:", rd.fieldnames)
                for r in rd:
                    c = r["DS_CARGO"]
                    if c in ("GOVERNADOR", "PRESIDENTE", "SENADOR") and c not in exemplos:
                        exemplos[c] = {k: r[k] for k in ("CD_ELEICAO", "SG_UE", "SQ_CANDIDATO", "NM_URNA_CANDIDATO",
                                                          "NR_TURNO", "DS_SIT_TOT_TURNO")}
                    if "DOUGLAS RUAS" in r["NM_URNA_CANDIDATO"]:
                        exemplos["DOUGLAS RUAS " + r["NR_TURNO"]] = {k: r[k] for k in ("CD_ELEICAO", "SG_UE", "SQ_CANDIDATO")}
        print(json.dumps(exemplos, ensure_ascii=False, indent=1))
    for rot, e in exemplos.items():
        d = get(f"{DIVULGA}/candidatura/buscar/2026/{e['SG_UE']}/{e['CD_ELEICAO']}/candidato/{e['SQ_CANDIDATO']}")
        if d:
            print(rot)
            print(resumo({k: d.get(k) for k in ("arquivos", "eleicao", "cargo", "descricaoSexo", "totalDeBens",
                                                "gastoCampanha1T", "gastoCampanha2T", "sites")}, max_itens=6))
            print("chaves:", sorted(d))
        if rot.startswith("DOUGLAS"):
            break
    get(f"{DIVULGA}/eleicao/ordinarias")


def main(raw: Path) -> None:
    for parte in (senado, lambda: tse(raw)):
        try:
            parte()
        except Exception as exc:  # sondagem nunca derruba a execução
            print("ERRO na sondagem:", type(exc).__name__, exc)
