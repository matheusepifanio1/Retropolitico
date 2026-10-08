"""Linha de comando.

  python -m retro baixar     # baixa arquivos oficiais (precisa de rede)
  python -m retro carregar   # normaliza data/raw -> data/retrospectiva.sqlite
  python -m retro site       # gera o site em _site/
  python -m retro tudo       # as três etapas
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import db
from .site.build import CuradoriaError, build
from .sources import camara
from .sources.base import DownloadError, LayoutError, RawStore

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="retro", description="Retrospectiva Política")
    p.add_argument("etapa", choices=["baixar", "carregar", "site", "tudo"])
    p.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    p.add_argument("--db", type=Path, default=ROOT / "data" / "retrospectiva.sqlite")
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--config", type=Path, default=ROOT / "config")
    args = p.parse_args(argv)

    settings = yaml.safe_load((args.config / "settings.yaml").read_text(encoding="utf-8"))
    store = RawStore(args.raw, "camara")
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
