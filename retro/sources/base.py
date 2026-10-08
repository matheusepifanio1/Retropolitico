"""Download de arquivos oficiais com registro de proveniência.

Cada arquivo baixado vai para `data/raw/<orgao>/` e entra em `manifest.json`
com URL, SHA-256, tamanho e data. O manifesto é publicado junto com o site para
que qualquer pessoa possa baixar o mesmo arquivo da fonte e conferir o hash.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import requests

USER_AGENT = "retrospectiva-politica/0.1 (+dados abertos; contato no repositório)"
csv.field_size_limit(sys.maxsize)


class DownloadError(RuntimeError):
    pass


class LayoutError(RuntimeError):
    """O arquivo oficial não tem o formato esperado. A coleta para em vez de adivinhar."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class RawStore:
    """Pasta de arquivos brutos + manifesto."""

    def __init__(self, root: Path, orgao: str, session: requests.Session | None = None):
        self.dir = root / orgao
        self.dir.mkdir(parents=True, exist_ok=True)
        self.orgao = orgao
        self.manifest_path = root / "manifest.json"
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        if self.manifest_path.exists():
            return {e["nome"]: e for e in json.loads(self.manifest_path.read_text(encoding="utf-8"))}
        return {}

    def save_manifest(self) -> None:
        entries = sorted(self._manifest.values(), key=lambda e: e["nome"])
        self.manifest_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def entry(self, nome: str) -> dict:
        return self._manifest[nome]

    def path(self, nome: str) -> Path:
        return self.dir / nome

    def _record(self, nome: str, url: str) -> dict:
        digest, size = sha256_of(self.path(nome))
        entry = {"nome": nome, "url": url, "sha256": digest, "bytes": size, "baixado_em": now_iso()}
        self._manifest[nome] = entry
        return entry

    def fetch(self, url: str, nome: str, *, refresh: bool = True, retries: int = 4) -> dict:
        """Baixa `url` para `nome`. Com refresh=False, reaproveita o arquivo já baixado."""
        dest = self.path(nome)
        if dest.exists() and not refresh and nome in self._manifest:
            return self._manifest[nome]
        part = dest.with_name(dest.name + ".part")
        last: Exception | None = None
        for attempt in range(retries):
            try:
                with self.session.get(url, stream=True, timeout=(15, 300)) as r:
                    if r.status_code == 404:
                        raise DownloadError(f"{url}: 404 (arquivo ainda não publicado?)")
                    r.raise_for_status()
                    with open(part, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                part.replace(dest)
                return self._record(nome, url)
            except DownloadError:
                part.unlink(missing_ok=True)
                raise
            except Exception as exc:  # rede instável: tenta de novo com espera crescente
                last = exc
                part.unlink(missing_ok=True)
                time.sleep(2 ** attempt)
        raise DownloadError(f"{url}: falhou após {retries} tentativas: {last}")

    def save_json(self, nome: str, url: str, payload) -> dict:
        """Grava uma resposta de API já agregada (ex.: várias páginas) como arquivo bruto."""
        self.path(nome).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self._record(nome, url)

    def get_json(self, url: str, *, retries: int = 4, pause: float = 0.0):
        last: Exception | None = None
        for attempt in range(retries):
            try:
                r = self.session.get(url, timeout=(15, 120), headers={"Accept": "application/json"})
                r.raise_for_status()
                if pause:
                    time.sleep(pause)
                return r.json()
            except Exception as exc:
                last = exc
                time.sleep(2 ** attempt)
        raise DownloadError(f"{url}: falhou após {retries} tentativas: {last}")


# ---------- leitura com checagem de layout ----------

def read_csv(path: Path, columns: list[str], *, encoding: str = "utf-8-sig", delimiter: str = ";") -> Iterator[dict]:
    """Lê só as colunas listadas. Coluna esperada ausente => LayoutError (nunca adivinha)."""
    with open(path, encoding=encoding, newline="") as f:
        rows = csv.reader(f, delimiter=delimiter)
        header = next(rows, [])
        missing = [c for c in columns if c not in header]
        if missing:
            raise LayoutError(
                f"{path.name}: colunas ausentes {missing}. Colunas encontradas: {header}"
            )
        index = [(c, header.index(c)) for c in columns]
        for row in rows:
            if row:
                yield {c: (row[i] if i < len(row) else "") for c, i in index}


def read_json_records(path: Path) -> list[dict]:
    """Arquivos JSON da Câmara vêm como {"dados": [...]}; aceita também lista pura."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("dados", [])
    if not isinstance(data, list):
        raise LayoutError(f"{path.name}: esperado lista de registros")
    return data


def id_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rstrip("/").rsplit("/", 1)[-1] or None


def pick(record: dict, *keys: str, uri_keys: tuple[str, ...] = ()) -> str | None:
    """Primeiro valor não vazio entre `keys`; senão, extrai o id de uma das `uri_keys`."""
    for k in keys:
        v = record.get(k)
        if v not in (None, ""):
            return str(v)
    for k in uri_keys:
        v = id_from_uri(record.get(k))
        if v:
            return v
    return None


def require_any(records: list[dict], name: str, groups: dict[str, tuple[str, ...]]) -> None:
    """Confere, no primeiro registro, que cada campo lógico tem ao menos uma chave conhecida."""
    if not records:
        return
    sample = records[0]
    flat = set(sample.keys())
    for k, v in sample.items():
        if isinstance(v, dict):
            flat |= {f"{k}.{kk}" for kk in v}
    missing = [logical for logical, keys in groups.items() if not any(k in flat for k in keys)]
    if missing:
        raise LayoutError(f"{name}: campos {missing} não encontrados. Chaves do 1º registro: {sorted(flat)}")


ProgressFn = Callable[[str], None]
