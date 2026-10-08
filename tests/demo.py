"""Gera um site de demonstração com os dados de teste (fictícios), sem rede.

    python -m tests.demo && python -m http.server -d _demo 8000
"""

from pathlib import Path
import tempfile

from retro import db
from retro.site.build import build
from retro.sources import camara
from tests import fixtures

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        store = fixtures.write_raw(tmp / "raw")
        conn = db.connect(tmp / "demo.sqlite")
        camara.load(conn, store, fixtures.settings()["camara"])
        from retro.sources import tse
        from retro.sources.base import RawStore
        st = RawStore(tmp / "raw", "tse")
        cpfs = tse.load(conn, st, fixtures.settings()["tse"], lambda n: db.register_source(conn, "tse", st.entry(n)))
        tse.ligar_deputados(conn, store, cpfs, lambda n: db.register_source(conn, "camara", store.entry(n)))
        chave = tmp / "chave.yaml"
        chave.write_text(fixtures.CHAVE_OK, encoding="utf-8")
        build(conn, ROOT / "_demo", fixtures.settings(), chave, db_path=tmp / "demo.sqlite")
    print("Demo em _demo/ (dados fictícios)")
