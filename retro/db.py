"""Conexão com o SQLite e registro de proveniência."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def register_source(conn: sqlite3.Connection, orgao: str, entry: dict) -> int:
    """Grava (ou atualiza) um arquivo bruto no registro de fontes e devolve seu id."""
    conn.execute(
        """
        INSERT INTO fonte_arquivo (orgao, nome, url, sha256, bytes, baixado_em)
        VALUES (:orgao, :nome, :url, :sha256, :bytes, :baixado_em)
        ON CONFLICT(nome) DO UPDATE SET
            url = excluded.url, sha256 = excluded.sha256,
            bytes = excluded.bytes, baixado_em = excluded.baixado_em
        """,
        {"orgao": orgao, **entry},
    )
    row = conn.execute("SELECT id FROM fonte_arquivo WHERE nome = ?", (entry["nome"],)).fetchone()
    return row["id"]
