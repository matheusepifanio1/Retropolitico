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
from .sources import camara
from .sources.base import DownloadError, LayoutError, RawStore

ROOT = Path(__file__).resolve().parent.parent


def inspecionar(pasta: Path) -> None:
    """Mostra o cabeçalho (CSV) ou as chaves do 1º registro (JSON) de cada arquivo bruto."""
    import csv
    import json

    for f in sorted(pasta.glob("*")):
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="retro", description="Retrospectiva Política")
    p.add_argument("etapa", choices=["baixar", "carregar", "site", "tudo", "inspecionar"])
    p.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    p.add_argument("--db", type=Path, default=ROOT / "data" / "retrospectiva.sqlite")
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--config", type=Path, default=ROOT / "config")
    args = p.parse_args(argv)

    settings = yaml.safe_load((args.config / "settings.yaml").read_text(encoding="utf-8"))
    if "RETRO_URL_BASE" in os.environ:
        settings["site"]["url_base"] = os.environ["RETRO_URL_BASE"]
    store = RawStore(args.raw, "camara")
    if args.etapa == "inspecionar":
        inspecionar(store.dir)
        return 0
    try:
        if args.etapa in ("baixar", "tudo"):
            print("Baixando arquivos da Câmara…")
            camara.download(store, settings["camara"])
        if args.etapa in ("carregar", "tudo"):
            print("Carregando no banco…")
            args.db.parent.mkdir(parents=True, exist_ok=True)
            args.db.unlink(missing_ok=True)  # o banco é sempre reconstruído dos arquivos brutos
            conn = db.connect(args.db)
            camara.load(conn, store, settings["camara"])
            conn.execute("VACUUM")
            conn.close()
        if args.etapa in ("site", "tudo"):
            print("Gerando o site…")
            conn = db.connect(args.db)
            info = build(conn, args.out, settings, args.config / "votacoes_chave.yaml", db_path=args.db)
            print(f"  {info['deputados']} perfis, {info['votacoes_chave']} votações-chave → {args.out}")
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
