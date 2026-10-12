"""Resumos em linguagem simples das propostas votadas.

Arquivo: config/linguagem_simples.yaml
  resumos:
    "camara:2487436": {titulo: "...", resumo: "...", tema: "impostos"}
    "senado:160000":  {...}

Os resumos são gerados automaticamente com IA a partir da ementa oficial e aparecem no
site com esse aviso, sempre ao lado do texto oficial. Votações-chave continuam com o
resumo escrito e revisado por pessoas.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .. import compute

TEMAS = {
    "impostos": "Impostos e economia",
    "orcamento": "Orçamento e gastos públicos",
    "trabalho": "Trabalho e previdência",
    "saude": "Saúde",
    "educacao": "Educação",
    "seguranca": "Segurança e justiça",
    "meio-ambiente": "Meio ambiente e terras",
    "agro": "Agropecuária",
    "social": "Assistência social e direitos",
    "infraestrutura": "Infraestrutura, energia e transporte",
    "instituicoes": "Política e instituições",
    "costumes": "Família e costumes",
    "consumidor": "Consumidor e empresas",
    "tecnologia": "Tecnologia e comunicação",
    "cultura": "Cultura e esporte",
    "internacional": "Relações internacionais e defesa",
    "homenagem": "Homenagens e datas",
    "outros": "Outros temas",
}


def carregar(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for chave, item in (raw.get("resumos") or {}).items():
        if not item or not item.get("resumo"):
            continue
        tema = item.get("tema") or "outros"
        out[str(chave)] = {"titulo": item.get("titulo") or "", "resumo": item["resumo"],
                           "tema": tema if tema in TEMAS else "outros",
                           "tema_rotulo": TEMAS.get(tema, TEMAS["outros"])}
    return out


def sentido(descricao: str | None) -> str | None:
    """O que significava votar SIM, quando dá para dizer sem interpretação.

    Destaques e requerimentos ficam sem frase: neles o SIM pode significar manter ou tirar um trecho.
    """
    d = compute.norm(descricao)
    if not d or "destaque" in d or "requerimento" in d or "emenda" in d and "subemenda substitutiva global" not in d:
        return None
    if d.startswith(("aprovad", "rejeitad")):
        return "SIM era a favor do texto em votação. NÃO era contra."
    return None
