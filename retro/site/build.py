"""Gera o site estático a partir do banco."""

from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .. import compute
from . import pessoas

HERE = Path(__file__).parent
VOTO_LABEL = {"Sim": "SIM", "Não": "NÃO", "Abstenção": "ABSTENÇÃO", "Obstrução": "OBSTRUÇÃO",
              "Artigo 17": "ART. 17 (PRESIDENTE)"}


class CuradoriaError(RuntimeError):
    """Problema no arquivo de votações-chave (ex.: id inexistente, campo faltando)."""


def data_br(iso: str | None) -> str:
    if not iso:
        return "—"
    a, m, d = iso[:10].split("-")
    return f"{d}/{m}/{a}"


def voto_label(voto: str | None, secreta: bool = False) -> str:
    if secreta:
        return "SECRETA"
    if voto is None:
        return "SEM REGISTRO"
    return VOTO_LABEL.get(voto, voto.upper() or "SEM VOTO")


def load_chave(path: Path, conn: sqlite3.Connection) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    itens = raw.get("votacoes") or []
    obrig = ["id", "tema", "etapa", "resumo", "revisado_por", "revisado_em"]
    out = []
    for item in itens:
        faltando = [c for c in obrig if not item.get(c)]
        if faltando:
            raise CuradoriaError(f"votação-chave {item.get('id')}: campos faltando {faltando}")
        if "destaque" in item["etapa"].lower() and not item.get("sentido_sim"):
            raise CuradoriaError(f"votação-chave {item['id']}: destaque exige 'sentido_sim'")
        row = conn.execute("SELECT * FROM votacao WHERE id=?", (str(item["id"]),)).fetchone()
        if row is None:
            raise CuradoriaError(f"votação-chave {item['id']}: não existe entre as votações nominais do Plenário coletadas")
        prop = conn.execute("SELECT * FROM votacao_proposicao WHERE votacao_id=? LIMIT 1", (row["id"],)).fetchone()
        out.append({**dict(row), **{k: item.get(k) for k in obrig + ["sentido_sim"]},
                    "id": row["id"], "data_br": data_br(row["data"]),
                    "proposicao": dict(prop) if prop else None})
    out.sort(key=lambda v: v["data"] or "", reverse=True)
    return out


CAMPOS_CARD = {"titulo": None, "ementa": None, "proposicao": None, "resumo": None, "etapa": None,
               "sentido_sim": None, "revisado_por": None, "revisado_em": None, "orientacao": None}


def para_card(v: dict) -> dict:
    """Garante todos os campos usados pelo card de votação (chave ou recente)."""
    card = {**CAMPOS_CARD, **v}
    if card["proposicao"]:
        card["titulo"] = card["titulo"] or card["proposicao"].get("titulo")
        card["ementa"] = card["ementa"] or card["proposicao"].get("ementa")
    return card


def cobertura(presenca, resumo) -> tuple[list[dict], dict]:
    blocos = [
        {"nome": "Presença em sessões", "ok": presenca is not None, "motivo": "sem sessões no período"},
        {"nome": "Votações nominais", "ok": resumo is not None, "motivo": "sem histórico de exercício"},
        {"nome": "Leis e proposições", "ok": True, "motivo": ""},
        {"nome": "Emendas orçamentárias", "ok": False, "motivo": "próxima etapa"},
        {"nome": "Promessas de campanha", "ok": False, "motivo": "etapa futura"},
    ]
    n = sum(b["ok"] for b in blocos)
    if n == len(blocos):
        nivel = {"nome": "Cobertura completa", "barras": 3}
    elif n >= 2:
        nivel = {"nome": f"Cobertura parcial · {n} de {len(blocos)} blocos", "barras": 2}
    else:
        nivel = {"nome": "Só dados básicos", "barras": 1}
    return blocos, nivel


UF_NOME = {"AC": "do Acre", "AL": "de Alagoas", "AP": "do Amapá", "AM": "do Amazonas", "BA": "da Bahia",
           "CE": "do Ceará", "DF": "do Distrito Federal", "ES": "do Espírito Santo", "GO": "de Goiás",
           "MA": "do Maranhão", "MT": "de Mato Grosso", "MS": "de Mato Grosso do Sul", "MG": "de Minas Gerais",
           "PA": "do Pará", "PB": "da Paraíba", "PR": "do Paraná", "PE": "de Pernambuco", "PI": "do Piauí",
           "RJ": "do Rio de Janeiro", "RN": "do Rio Grande do Norte", "RS": "do Rio Grande do Sul",
           "RO": "de Rondônia", "RR": "de Roraima", "SC": "de Santa Catarina", "SP": "de São Paulo",
           "SE": "de Sergipe", "TO": "do Tocantins"}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def mes_ano(iso: str) -> str:
    return f"{MESES[int(iso[5:7]) - 1]} de {iso[:4]}"


def frase_perfil(dep, linha: dict) -> str:
    """Frase de abertura do perfil, montada só com dados oficiais."""
    partido = f"pelo {dep['partido']} " if dep["partido"] else ""
    cargo = {"F": "Deputada", "M": "Deputado"}.get(dep["sexo"] or "", "Deputado(a)")
    frase = f"{cargo} federal {partido}{UF_NOME.get(dep['uf'], '')}".strip() + "."
    exerc = [s for s in linha["situacao"] if s["exercicio"]]
    licencas = [s for s in linha["situacao"] if s["chave"] == "licenca"]
    if dep["em_exercicio"] and exerc:
        frase += f" Em exercício desde {mes_ano(exerc[0]['inicio'])}"
        if licencas:
            frase += f", com {len(licencas)} {'período' if len(licencas) == 1 else 'períodos'} de licença"
        frase += "."
    elif exerc:
        frase += f" Exerceu o mandato de {mes_ano(exerc[0]['inicio'])} a {mes_ano(exerc[-1]['fim'])}."
    return frase


RANK_CARGO = ["presidente", "1º vice-presidente", "2º vice-presidente", "3º vice-presidente", "vice-presidente",
              "relator", "coordenador-geral", "coordenador", "coordenadora"]


def cargo_destaque(direcao: list[dict]) -> dict | None:
    if not direcao:
        return None
    def ordem(c):
        t = compute.norm(c["titulo"])
        ranks = [compute.norm(x) for x in RANK_CARGO]
        rank = ranks.index(t) if t in ranks else len(ranks)
        return (rank, "".join(chr(255 - ord(ch)) for ch in (c["data_inicio"] or "")))  # mais recente primeiro
    c = sorted(direcao, key=ordem)[0]
    return {**c, "periodo": (f"De {mes_ano(c['data_inicio'])} " if c["data_inicio"] else "")
            + (f"a {mes_ano(c['data_fim'])}." if c["data_fim"] else "até hoje.")}


def build(conn: sqlite3.Connection, out: Path, settings: dict, chave_path: Path, db_path: Path | None = None) -> dict:
    cam, site = settings["camara"], settings["site"]
    base = (site.get("url_base") or "").rstrip("/")
    agora = datetime.now(timezone.utc)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["br"] = data_br
    ctx = {"site": site, "base": base, "legislatura": cam["legislatura"],
           "atualizado_em": agora.strftime("%d/%m/%Y %H:%M"), "tipos": cam["tipos_legislativos"],
           "anos_prop": cam["anos_proposicoes"], "inicio_mandato": data_br(cam["inicio_mandato"]),
           "homenagem_exprs": compute.HOMENAGEM_LEGIVEL}

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(HERE / "static", out / "static")

    def render(rel: str, template: str, **kw) -> None:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**ctx, **kw), encoding="utf-8")

    chave = load_chave(chave_path, conn)
    ate = agora.strftime("%Y-%m-%dT%H:%M:%S")
    deputados = conn.execute("SELECT * FROM parlamentar ORDER BY nome COLLATE NOCASE").fetchall()
    orient = {}
    for o in conn.execute("SELECT * FROM orientacao"):
        orient[(o["votacao_id"], o["sigla_bancada"].upper())] = o["orientacao"]
    nomes = {d["id"]: d["nome"] for d in deputados}
    todas_votacoes = conn.execute(
        """SELECT v.*, MIN(vp.titulo) AS titulo, MIN(vp.ementa) AS ementa, MIN(vp.proposicao_id) AS proposicao_id FROM votacao v
           LEFT JOIN votacao_proposicao vp ON vp.votacao_id = v.id
           GROUP BY v.id ORDER BY v.data_hora DESC, v.data DESC""").fetchall()

    busca = []
    for d in deputados:
        hist = conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=?", (d["id"],)).fetchall()
        periodos = compute.periodos_exercicio(hist, ate)
        pres = compute.presenca(conn, d["id"], periodos)
        resumo = compute.resumo_votos(conn, d["id"], periodos)
        leis = compute.leis(conn, d["id"])
        blocos, nivel = cobertura(pres, resumo)

        votos_dep = {r["votacao_id"]: r for r in conn.execute("SELECT * FROM voto WHERE parlamentar_id=?", (d["id"],))}
        chave_dep = []
        for v in chave:
            meu = votos_dep.get(v["id"])
            partido = (meu["partido"] if meu else d["partido"]) or ""
            chave_dep.append(para_card({**v, "voto": meu["voto"] if meu else None,
                              "voto_label": voto_label(meu["voto"] if meu else None, bool(v["secreta"]) and meu is not None),
                              "orientacao": orient.get((v["id"], partido.upper()))}))

        recentes = []
        for v in todas_votacoes:
            if len(recentes) >= 6:
                break
            if not compute.is_merito(v["descricao"]) or not any(p.contem(v["data_hora"] or v["data"]) for p in periodos):
                continue
            meu = votos_dep.get(v["id"])
            partido = (meu["partido"] if meu else d["partido"]) or ""
            recentes.append(para_card({**dict(v), "data_br": data_br(v["data"]), "voto": meu["voto"] if meu else None,
                             "voto_label": voto_label(meu["voto"] if meu else None, bool(v["secreta"]) and meu is not None),
                             "orientacao": orient.get((v["id"], partido.upper()))}))

        cargos = compute.cargos(conn, d["id"])
        linha = compute.linha_do_tempo(hist, cargos["direcao"], cam["inicio_mandato"], ate)
        serie = compute.serie_periodo(conn, d["id"], periodos, leis)
        render(f"deputado/{d['id']}/index.html", "deputado.html", pagina="perfil", dep=d, presenca=pres,
               resumo=resumo, leis=leis, chave=chave_dep, cobertura=blocos, nivel=nivel,
               trajetoria=compute.trajetoria(hist), cargos=cargos, linha=linha, recentes=recentes,
               frase=frase_perfil(d, linha), destaque=cargo_destaque(cargos["direcao"]),
               n_cobertura=sum(b["ok"] for b in blocos), n_comissoes=len({c["id_orgao"] for c in cargos["membro"]}),
               serie_json=json.dumps(serie, separators=(",", ":")))

        lista = []
        for v in todas_votacoes:
            if not any(p.contem(v["data_hora"] or v["data"]) for p in periodos):
                continue
            meu = votos_dep.get(v["id"])
            lista.append({**dict(v), "data_br": data_br(v["data"]), "voto": meu["voto"] if meu else None,
                          "voto_label": voto_label(meu["voto"] if meu else None, bool(v["secreta"]) and meu is not None)})
        if resumo:
            render(f"deputado/{d['id']}/votos/index.html", "votos.html", pagina="perfil", dep=d,
                   votos=lista, resumo=resumo)

        busca.append({"id": d["id"], "nome": d["nome"], "partido": d["partido"], "uf": d["uf"],
                      "foto": d["url_foto"], "cargo": "Deputado(a) federal", "exercicio": bool(d["em_exercicio"]),
                      "n": compute.norm(f"{d['nome']} {d['partido'] or ''} {d['uf'] or ''}")})

    (out / "busca.json").write_text(json.dumps(busca, ensure_ascii=False), encoding="utf-8")

    for v in chave:
        rows = []
        for r in conn.execute("SELECT * FROM voto WHERE votacao_id=?", (v["id"],)):
            rows.append({**dict(r), "nome": nomes.get(r["parlamentar_id"], f"Deputado {r['parlamentar_id']}"),
                         "voto_label": voto_label(r["voto"], bool(v["secreta"])),
                         "orientacao": orient.get((v["id"], (r["partido"] or "").upper()))})
        rows.sort(key=lambda r: compute.norm(r["nome"]))
        contagem = Counter(r["voto_label"] for r in rows).most_common()
        render(f"votacao/{v['id']}/index.html", "votacao.html", pagina="votacoes", v=v, votos=rows, contagem=contagem)

    tse_anos = settings.get("tse", {}).get("anos", [])
    info_pessoas = pessoas.gerar(conn, out, max(tse_anos) if tse_anos else agora.year)
    render("pessoa/index.html", "pessoa.html", pagina="pessoa", tse_anos=tse_anos or [agora.year])

    ufs = sorted({d["uf"] for d in deputados if d["uf"]})
    por_uf = [(uf, [d for d in deputados if d["uf"] == uf]) for uf in ufs]
    render("index.html", "index.html", pagina="inicio", ufs=ufs, segundo=info_pessoas["segundo_turno"],
           n_pessoas=info_pessoas["pessoas"], ano_tse=max(tse_anos) if tse_anos else agora.year)
    render("deputados/index.html", "lista.html", pagina="inicio", por_uf=por_uf)
    render("votacoes/index.html", "votacoes.html", pagina="votacoes", chave=chave)
    render("metodologia/index.html", "metodologia.html", pagina="metodologia")

    fontes = [dict(r) for r in conn.execute("SELECT orgao, nome, url, sha256, bytes, baixado_em FROM fonte_arquivo ORDER BY nome")]
    (out / "dados").mkdir(exist_ok=True)
    (out / "dados" / "manifesto.json").write_text(json.dumps(fontes, ensure_ascii=False, indent=2), encoding="utf-8")
    if db_path and db_path.exists():
        with open(db_path, "rb") as src, gzip.open(out / "dados" / "retrospectiva.sqlite.gz", "wb") as dst:
            shutil.copyfileobj(src, dst)
    render("dados/index.html", "dados.html", pagina="dados", fontes=fontes)
    (out / ".nojekyll").write_text("")
    return {"deputados": len(deputados), "votacoes_chave": len(chave), "pessoas": info_pessoas["pessoas"]}
