"""Páginas de presença em Plenário do site da Câmara (camara.leg.br).

As justificativas de ausência não estão nos dados abertos, mas aparecem na página oficial
de cada deputado: https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}

Para cada página guardamos URL, data, SHA-256 do HTML e só as linhas de texto relevantes
(datas, presença, ausência, justificativa). O HTML completo não é guardado para não
inflar o repositório; qualquer pessoa pode abrir a mesma URL na fonte.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from html.parser import HTMLParser

from .base import RawStore, now_iso

URL = "https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}"
ARQUIVO = "presenca-plenario-site.json"
RELEVANTE = re.compile(r"\d{2}/\d{2}/\d{4}|presen|ausen|ausên|justific|sess[aã]o|deliberativ", re.I)


class _Texto(HTMLParser):
    """Converte HTML em linhas de texto, com células de tabela separadas por ' | '."""

    def __init__(self):
        super().__init__()
        self.linhas, self.atual, self.ignorar = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.ignorar += 1
        elif tag in ("tr", "li", "p", "div", "br", "h1", "h2", "h3", "h4", "dt", "dd"):
            self._quebra()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.ignorar = max(0, self.ignorar - 1)
        elif tag in ("td", "th"):
            self.atual.append(" | ")
        elif tag in ("tr", "li", "p", "div", "dd"):
            self._quebra()

    def handle_data(self, data):
        if not self.ignorar:
            self.atual.append(data)

    def _quebra(self):
        linha = re.sub(r"\s+", " ", "".join(self.atual)).strip(" |")
        if linha:
            self.linhas.append(linha)
        self.atual = []


def html_para_linhas(html: str) -> list[str]:
    p = _Texto()
    p.feed(html)
    p._quebra()
    return [l for l in p.linhas if RELEVANTE.search(l)]


def download(store: RawStore, cfg: dict, log=print) -> None:
    historicos = json.loads(store.path("deputados-historico.json").read_text(encoding="utf-8"))
    anterior = {}
    if store.path(ARQUIVO).exists():
        anterior = json.loads(store.path(ARQUIVO).read_text(encoding="utf-8"))
    ano_atual = date.today().year
    inicio = cfg["inicio_mandato"]
    saida, n, erros = {}, 0, 0
    for dep_id, hist in historicos.items():
        datas = [h["dataHora"][:10] for h in hist
                 if (h.get("situacao") or "") == "Exercício" and h.get("dataHora", "")[:10] >= inicio]
        if not datas:
            continue
        for ano in cfg["anos"]:
            if ano < int(min(datas)[:4]):
                continue
            chave = f"{dep_id}-{ano}"
            velho = anterior.get(chave)
            if velho and velho.get("ok") and ano < ano_atual:
                saida[chave] = velho  # ano fechado: reaproveita
                continue
            url = URL.format(id=dep_id, ano=ano)
            try:
                r = store.session.get(url, timeout=(15, 60))
                html = r.text if r.status_code == 200 else ""
                saida[chave] = {
                    "url": url, "status": r.status_code, "ok": r.status_code == 200,
                    "sha256": hashlib.sha256(r.content).hexdigest(), "baixado_em": now_iso(),
                    "linhas": html_para_linhas(html) if html else [],
                }
            except Exception as exc:  # página indisponível não derruba a coleta
                erros += 1
                saida[chave] = {"url": url, "ok": False, "erro": str(exc)[:200], "baixado_em": now_iso(), "linhas": []}
            n += 1
            time.sleep(0.15)
            if n % 200 == 0:
                log(f"  páginas de presença: {n}")
    store.save_json(ARQUIVO, URL.format(id="{id}", ano="{ano}"), saida)
    store.save_manifest()
    ok = sum(1 for v in saida.values() if v.get("ok"))
    log(f"  ok páginas de presença do site: {ok}/{len(saida)} (novas: {n}, erros de rede: {erros})")
