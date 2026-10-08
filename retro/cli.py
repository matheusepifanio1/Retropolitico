"""Linha de comando.

  python -m retro baixar     # baixa arquivos oficiais (precisa de rede)
  python -m retro carregar   # normaliza data/raw -> data/retrospectiva.sqlite
  python -m retro site       # gera o site em _site/
  python -m retro tudo       # as três etapas
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from . import db
from .site.build import CuradoriaError, build
from .sources import camara, camara_site, tse
from .sources.base import DownloadError, LayoutError, RawStore

ROOT = Path(__file__).resolve().parent.parent


def inspecionar(pasta: Path) -> None:
    """Mostra o cabeçalho (CSV) ou as chaves do 1º registro (JSON) de cada arquivo bruto."""
    import csv
    import json

    site = pasta / "presenca-plenario-site.json"
    if site.exists():
        paginas = json.loads(site.read_text(encoding="utf-8"))
        ok = [k for k, v in paginas.items() if v.get("ok")]
        print(f"{site.name}: {len(ok)}/{len(paginas)} páginas ok; status: "
              f"{sorted({str(v.get('status', v.get('erro', '?')))[:40] for v in paginas.values()})}")
        for chave in ["204450-2024", "204379-2024"] + ok[:1]:
            v = paginas.get(chave)
            if v:
                print(f"--- {chave} {v.get('url')} ({len(v.get('linhas', []))} linhas)")
                for linha in v.get("linhas", [])[:80]:
                    print(f"    {linha[:300]}")
    for f in sorted(pasta.glob("*")):
        if f.name == site.name:
            continue
        if f.suffix == ".csv":
            with open(f, encoding="utf-8-sig", newline="") as fh:
                rows = csv.reader(fh, delimiter=";")
                header = next(rows, [])
                first = next(rows, [])
            print(f"{f.name} [{f.stat().st_size // 1024} KB] colunas={header}")
            print(f"    exemplo={dict(zip(header, first))}")
        elif f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                print(f"{f.name}: JSON inválido ({exc})")
                continue
            if isinstance(data, dict) and "dados" in data:
                data = data["dados"]
            if isinstance(data, dict):  # ex.: históricos por deputado
                data = next(iter(data.values()), [])
            first = data[0] if isinstance(data, list) and data else {}
            print(f"{f.name} [{f.stat().st_size // 1024} KB] registros={len(data) if isinstance(data, list) else '?'}")
            print(f"    exemplo={json.dumps(first, ensure_ascii=False)[:600]}")


def sanidade(conn) -> None:
    """Estatísticas para conferir se os números fazem sentido (vão para o relatório da execução)."""
    from statistics import median
    from . import compute

    print("Checagem de sanidade:")
    for r in conn.execute("SELECT substr(data,1,4) ano, COUNT(*) n, SUM(secreta) s FROM votacao GROUP BY ano"):
        print(f"  votações nominais {r['ano']}: {r['n']} (secretas: {r['s']})")
    for r in conn.execute("SELECT substr(data_hora,1,4) ano, COUNT(*) n FROM sessao GROUP BY ano"):
        print(f"  sessões deliberativas {r['ano']}: {r['n']}")
    ate = compute.agora_iso()
    pres, part, sem_periodo, so_voto_total = [], [], 0, 0
    just_total = nj_total = u_total = conflitos_total = 0
    for d in conn.execute("SELECT id, nome FROM parlamentar WHERE em_exercicio=1"):
        hist = conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=?", (d["id"],)).fetchall()
        periodos = compute.periodos_exercicio(hist, ate)
        if not periodos:
            sem_periodo += 1
            continue
        p = compute.presenca(conn, d["id"], periodos)
        v = compute.resumo_votos(conn, d["id"], periodos)
        if p:
            pres.append(p.pct)
            so_voto_total += p.so_por_voto
            just_total += p.justificadas
            nj_total += p.nao_justificadas
            u_total += p.sem_informacao
            conflitos_total += p.conflitos
            if p.pct < 50:
                hs = "; ".join(f"{h['data_hora'][:10]} {h['situacao']}" for h in hist if h["situacao"])
                print(f"  ATENÇÃO presença {p.pct}%: id={d['id']} {d['nome']} "
                      f"({p.presentes}/{p.sessoes}, justificadas {p.justificadas}, sem justificativa {p.nao_justificadas}, sem info {p.sem_informacao}) histórico: {hs}")
        if v and v.votacoes_no_periodo:
            part.append(round(100 * v.com_registro / v.votacoes_no_periodo))
    print(f"  deputados em exercício sem período de exercício no histórico: {sem_periodo}")
    print(f"  sessões contadas como presença só pelo voto (sem registro de presença): {so_voto_total}")
    print(f"  ausências: justificadas={just_total} sem justificativa={nj_total} sem informação={u_total} "
          f"conflitos (presença/voto em dia 'Ausência')={conflitos_total}")
    n_ev = conn.execute("SELECT COUNT(*) FROM votacao WHERE id_evento IN (SELECT id FROM sessao)").fetchone()[0]
    print(f"  votações nominais ligadas a uma sessão deliberativa: {n_ev}")
    for nome, xs in (("presença %", pres), ("participação em votações %", part)):
        if xs:
            xs.sort()
            faixas = {f: sum(1 for x in xs if lo <= x < hi) for f, (lo, hi) in
                      {"<50": (0, 50), "50-79": (50, 80), "80-94": (80, 95), "95+": (95, 101)}.items()}
            print(f"  {nome}: n={len(xs)} min={xs[0]} mediana={median(xs)} max={xs[-1]} faixas={faixas}")
    n_c = conn.execute("SELECT COUNT(*) FROM candidatura").fetchone()[0]
    n_p = conn.execute("SELECT COUNT(DISTINCT pessoa_id) FROM candidatura").fetchone()[0]
    multi = conn.execute("SELECT COUNT(*) FROM (SELECT pessoa_id FROM candidatura GROUP BY pessoa_id HAVING COUNT(*) > 1)").fetchone()[0]
    lig = conn.execute("SELECT COUNT(*) FROM parlamentar WHERE pessoa_id IS NOT NULL").fetchone()[0]
    print(f"  TSE: {n_c} candidaturas, {n_p} pessoas, {multi} com mais de uma candidatura; deputados ligados: {lig}")
    for r in conn.execute("SELECT ano, COUNT(*) n FROM candidatura GROUP BY ano"):
        print(f"    TSE {r['ano']}: {r['n']} candidaturas")
    # Conferência com uma figura pública conhecida (candidato em 2026).
    for r in conn.execute("""SELECT pessoa_id, ano, cargo, uf, nm_ue, partido, resultado FROM candidatura
                             WHERE pessoa_id IN (SELECT pessoa_id FROM candidatura WHERE nome_urna LIKE 'DOUGLAS RUAS%')
                             ORDER BY pessoa_id, ano"""):
        print(f"    exemplo DOUGLAS RUAS: {tuple(r)}")
    for r in conn.execute("SELECT status, COUNT(*) n FROM frequencia_dia GROUP BY status ORDER BY n DESC LIMIT 20"):
        print(f"    frequência no site '{r['status']}': {r['n']}")
    leis = sum(1 for r in conn.execute("SELECT situacao FROM proposicao") if compute.is_lei(r[0]))
    print(f"  proposições de deputados que viraram lei: {leis}")
    for r in conn.execute("SELECT situacao, COUNT(*) n FROM proposicao GROUP BY situacao ORDER BY n DESC LIMIT 12"):
        print(f"    situação '{r['situacao']}': {r['n']}")
    for r in conn.execute("SELECT situacao, COUNT(*) n FROM situacao_historico GROUP BY situacao ORDER BY n DESC"):
        print(f"    histórico situação '{r['situacao']}': {r['n']}")
    for r in conn.execute("""SELECT situacao, descricao_status, COUNT(*) n FROM situacao_historico
                             GROUP BY situacao, descricao_status ORDER BY n DESC LIMIT 25"""):
        print(f"    histórico descrição [{r['situacao']}] '{r['descricao_status']}': {r['n']}")
    for r in conn.execute("SELECT titulo, COUNT(*) n FROM cargo GROUP BY titulo ORDER BY n DESC LIMIT 15"):
        print(f"    cargo '{r['titulo']}': {r['n']}")


def candidatas(conn) -> None:
    """Votações de mérito de PEC/PLP/PL/MPV/PDL com mais votos, para a curadoria das votações-chave."""
    from . import compute
    rows = conn.execute(
        """SELECT v.id, v.data, v.descricao, v.votos_sim, v.votos_nao, v.votos_outros, v.aprovacao,
                  MIN(vp.titulo) titulo, MIN(vp.ementa) ementa
           FROM votacao v LEFT JOIN votacao_proposicao vp ON vp.votacao_id = v.id
           GROUP BY v.id ORDER BY v.data DESC""").fetchall()
    n = 0
    for r in rows:
        tit = r["titulo"] or ""
        if not compute.is_merito(r["descricao"]) or not tit.startswith(("PEC", "PLP", "PL ", "MPV", "PDL", "PLV")):
            continue
        n += 1
        print(f"{r['id']} | {r['data']} | {tit} | {r['votos_sim']}x{r['votos_nao']} | "
              f"{(r['descricao'] or '')[:160]} || {(r['ementa'] or '')[:220]}")
    print(f"total: {n}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="retro", description="Retrospectiva Política")
    p.add_argument("etapa", choices=["baixar", "carregar", "site", "tudo", "inspecionar", "candidatas"])
    p.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    p.add_argument("--db", type=Path, default=ROOT / "data" / "retrospectiva.sqlite")
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--config", type=Path, default=ROOT / "config")
    args = p.parse_args(argv)

    settings = yaml.safe_load((args.config / "settings.yaml").read_text(encoding="utf-8"))
    if "RETRO_URL_BASE" in os.environ:
        settings["site"]["url_base"] = os.environ["RETRO_URL_BASE"]
    store = RawStore(args.raw, "camara")
    if args.etapa == "candidatas":
        candidatas(db.connect(args.db))
        return 0
    if args.etapa == "inspecionar":
        inspecionar(store.dir)
        print("=== TSE")
        tse.inspecionar(RawStore(args.raw, "tse"), settings["tse"])
        return 0
    try:
        if args.etapa in ("baixar", "tudo"):
            print("Baixando arquivos da Câmara…")
            camara.download(store, settings["camara"])
            print("Baixando páginas de presença do site da Câmara…")
            camara_site.download(store, settings["camara"])
            print("Baixando candidaturas do TSE…")
            tse.download(RawStore(args.raw, "tse"), settings["tse"])
        if args.etapa in ("carregar", "tudo"):
            print("Carregando no banco…")
            args.db.parent.mkdir(parents=True, exist_ok=True)
            args.db.unlink(missing_ok=True)  # o banco é sempre reconstruído dos arquivos brutos
            conn = db.connect(args.db)
            camara.load(conn, store, settings["camara"])
            store_tse = RawStore(args.raw, "tse")
            cpf_pessoa = tse.load(conn, store_tse, settings["tse"],
                                  lambda nome: db.register_source(conn, "tse", store_tse.entry(nome)))
            tse.ligar_deputados(conn, store, cpf_pessoa,
                                lambda nome: db.register_source(conn, "camara", store.entry(nome)))
            del cpf_pessoa
            conn.commit()
            sanidade(conn)
            conn.execute("VACUUM")
            conn.close()
        if args.etapa in ("site", "tudo"):
            print("Gerando o site…")
            conn = db.connect(args.db)
            info = build(conn, args.out, settings, args.config / "votacoes_chave.yaml", db_path=args.db)
            print(f"  {info['deputados']} perfis de deputados, {info['pessoas']} pessoas na busca, "
                  f"{info['votacoes_chave']} votações-chave → {args.out}")
    except (LayoutError, CuradoriaError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        print("Nada foi publicado. Corrija o leitor ou a curadoria antes de seguir.", file=sys.stderr)
        return 2
    except DownloadError as exc:
        print(f"ERRO de download: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
