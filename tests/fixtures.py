"""Gera arquivos brutos pequenos no mesmo formato dos arquivos oficiais da Câmara.

Os nomes de coluna dos CSVs seguem os arquivos reais (separador ';', UTF-8 com BOM),
incluindo colunas extras que o leitor deve ignorar.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from retro.sources.base import RawStore

ANO = 2024
INICIO = "2023-02-01"


def _csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, "") for h in header])


def _json(path: Path, rows) -> None:
    path.write_text(json.dumps(rows if not isinstance(rows, list) else {"dados": rows}, ensure_ascii=False), encoding="utf-8")


def settings() -> dict:
    return {
        "camara": {"legislatura": 57, "inicio_mandato": INICIO, "anos": [ANO], "anos_proposicoes": [ANO],
                   "tipos_legislativos": ["PL", "PLP", "PEC"]},
        "site": {"titulo": "Retrospectiva", "url_base": "", "repositorio": "https://github.com/exemplo/retro"},
    }


def write_raw(root: Path, *, drop_column: str | None = None) -> RawStore:
    store = RawStore(root, "camara")
    d = store.dir

    deps = [
        {"id": 101, "uri": "https://x/deputados/101", "nome": "Ana Ribeiro", "siglaPartido": "PAA", "siglaUf": "SP",
         "idLegislatura": 57, "urlFoto": "https://x/101.jpg", "email": "a@x"},
        {"id": 102, "uri": "https://x/deputados/102", "nome": "Bruno Sales", "siglaPartido": "PBB", "siglaUf": "AC",
         "idLegislatura": 57, "urlFoto": "", "email": ""},
        {"id": 103, "uri": "https://x/deputados/103", "nome": "Carla Dias", "siglaPartido": "PBB", "siglaUf": "AC",
         "idLegislatura": 57, "urlFoto": "", "email": ""},
    ]
    _json(d / "deputados-legislatura.json", deps)
    _json(d / "deputados-em-exercicio.json", deps[:2])
    historico = {
        # Formato real: registros de troca de nome/partido vêm com situacao null.
        "101": [
            {"dataHora": "2023-02-01T00:00", "situacao": None, "siglaPartido": "PXX", "siglaUf": "SP",
             "descricaoStatus": "Nome no início da legislatura / Partido no início da legislatura", "idLegislatura": 57},
            {"dataHora": "2023-02-01T00:00", "situacao": "Exercício", "descricaoStatus": "Posse", "idLegislatura": 57},
            {"dataHora": "2024-01-15T00:00", "situacao": None, "siglaPartido": "PAA", "siglaUf": "SP",
             "descricaoStatus": "Alteração de partido", "idLegislatura": 57},
        ],
        # Bruno se licencia entre jan e jun/2024; Carla (suplente) assume nesse intervalo.
        "102": [
            {"dataHora": "2023-02-01T00:00", "situacao": "Exercício", "descricaoStatus": "Posse", "idLegislatura": 57},
            {"dataHora": "2024-01-10T00:00", "situacao": "Licença", "descricaoStatus": "Licença", "idLegislatura": 57},
            {"dataHora": "2024-06-01T00:00", "situacao": "Exercício", "descricaoStatus": "Reassunção", "idLegislatura": 57},
            {"dataHora": "2019-02-01T00:00", "situacao": "Exercício", "descricaoStatus": "Legislatura anterior", "idLegislatura": 56},
        ],
        "103": [
            {"dataHora": "2024-01-10T00:00", "situacao": "Exercício", "descricaoStatus": "Suplente", "idLegislatura": 57},
            {"dataHora": "2024-06-01T00:00", "situacao": "Fim do Mandato", "descricaoStatus": "Saída", "idLegislatura": 57},
        ],
    }
    (d / "deputados-historico.json").write_text(json.dumps(historico, ensure_ascii=False), encoding="utf-8")

    # ---- votações
    vh = ["id", "uri", "data", "dataHoraRegistro", "idOrgao", "siglaOrgao", "aprovacao", "votosSim",
          "votosNao", "votosOutros", "descricao", "ultimaAberturaVotacao_descricao"]
    if drop_column:
        vh = [c for c in vh if c != drop_column]
    _csv(d / f"votacoes-{ANO}.csv", vh, [
        {"id": "900-1", "data": "2024-03-05", "dataHoraRegistro": "2024-03-05T20:10:00", "siglaOrgao": "PLEN",
         "aprovacao": "1", "votosSim": "2", "votosNao": "0", "votosOutros": "0",
         "descricao": "Aprovado o Substitutivo ao Projeto de Lei nº 1, de 2024."},
        {"id": "900-2", "data": "2024-08-01", "dataHoraRegistro": "2024-08-01T19:00:00", "siglaOrgao": "PLEN",
         "aprovacao": "0", "votosSim": "", "votosNao": "", "votosOutros": "", "descricao": "Votação secreta de autoridade."},
        # Votação simbólica / encaminhamento: está no arquivo, mas sem votos individuais.
        {"id": "900-3", "data": "2024-05-01", "dataHoraRegistro": "2024-05-01T18:00:00", "siglaOrgao": "PLEN",
         "aprovacao": "1", "votosSim": "0", "votosNao": "0", "votosOutros": "0",
         "descricao": "Aprovado o requerimento (votação simbólica)."},
        {"id": "800-1", "data": "2024-04-01", "dataHoraRegistro": "2024-04-01T10:00:00", "siglaOrgao": "CCJC",
         "aprovacao": "1", "votosSim": "10", "votosNao": "2", "votosOutros": "0", "descricao": "Votação em comissão."},
    ])
    _csv(d / f"votacoesVotos-{ANO}.csv",
         ["idVotacao", "uriVotacao", "dataHoraVoto", "voto", "deputado_id", "deputado_uri", "deputado_nome",
          "deputado_siglaPartido", "deputado_siglaUf", "deputado_idLegislatura", "deputado_urlFoto"], [
        {"idVotacao": "900-1", "dataHoraVoto": "2024-03-05T20:05:00", "voto": "Sim", "deputado_id": "101",
         "deputado_siglaPartido": "PAA", "deputado_siglaUf": "SP"},
        {"idVotacao": "900-1", "dataHoraVoto": "2024-03-05T20:06:00", "voto": "Sim", "deputado_id": "103",
         "deputado_siglaPartido": "PBB", "deputado_siglaUf": "AC"},
        {"idVotacao": "900-2", "dataHoraVoto": "2024-08-01T18:50:00", "voto": "", "deputado_id": "101",
         "deputado_siglaPartido": "PAA", "deputado_siglaUf": "SP"},
        {"idVotacao": "900-2", "dataHoraVoto": "2024-08-01T18:51:00", "voto": "", "deputado_id": "102",
         "deputado_siglaPartido": "PBB", "deputado_siglaUf": "AC"},
        {"idVotacao": "800-1", "dataHoraVoto": "2024-04-01T10:00:00", "voto": "Não", "deputado_id": "102",
         "deputado_siglaPartido": "PBB", "deputado_siglaUf": "AC"},
    ])
    _csv(d / f"votacoesOrientacoes-{ANO}.csv", ["idVotacao", "uriVotacao", "siglaOrgao", "siglaBancada", "orientacao"], [
        {"idVotacao": "900-1", "siglaBancada": "PAA", "orientacao": "Sim"},
        {"idVotacao": "900-1", "siglaBancada": "Governo", "orientacao": "Sim"},
    ])
    _csv(d / f"votacoesProposicoes-{ANO}.csv",
         ["idVotacao", "uriVotacao", "data", "descricao", "proposicao_id", "proposicao_uri", "proposicao_titulo",
          "proposicao_ementa", "proposicao_codTipo", "proposicao_siglaTipo", "proposicao_numero", "proposicao_ano"], [
        {"idVotacao": "900-1", "proposicao_id": "5001", "proposicao_titulo": "PL 1/2024",
         "proposicao_ementa": "Dispõe sobre a transparência da fila de cirurgias."},
    ])

    # ---- eventos (JSON)
    _json(d / f"eventos-{ANO}.json", [
        {"id": 1, "uri": "https://x/eventos/1", "dataHoraInicio": "2024-02-06T14:00", "situacao": "Encerrada",
         "descricaoTipo": "Sessão Deliberativa", "descricao": "Sessão"},
        {"id": 2, "uri": "https://x/eventos/2", "dataHoraInicio": "2024-03-05T14:00", "situacao": "Encerrada",
         "descricaoTipo": "Sessão Deliberativa Extraordinária", "descricao": "Sessão"},
        {"id": 3, "uri": "https://x/eventos/3", "dataHoraInicio": "2024-07-02T14:00", "situacao": "Encerrada",
         "descricaoTipo": "Sessão Deliberativa", "descricao": "Sessão"},
        {"id": 4, "uri": "https://x/eventos/4", "dataHoraInicio": "2024-07-03T14:00", "situacao": "Cancelada",
         "descricaoTipo": "Sessão Deliberativa", "descricao": "Cancelada"},
        {"id": 5, "uri": "https://x/eventos/5", "dataHoraInicio": "2024-07-04T14:00", "situacao": "Encerrada",
         "descricaoTipo": "Sessão Não Deliberativa de Debates", "descricao": "Debates"},
        {"id": 6, "uri": "https://x/eventos/6", "dataHoraInicio": "2024-07-05T10:00", "situacao": "Encerrada",
         "descricaoTipo": "Reunião Deliberativa", "descricao": "Comissão"},
    ])
    _json(d / f"eventosOrgaos-{ANO}.json", [
        {"idEvento": 1, "uriEvento": "https://x/eventos/1", "idOrgao": 180, "siglaOrgao": "PLEN"},
        {"idEvento": 2, "uriEvento": "https://x/eventos/2", "idOrgao": 180, "siglaOrgao": "PLEN"},
        {"idEvento": 3, "uriEvento": "https://x/eventos/3", "idOrgao": 180, "siglaOrgao": "PLEN"},
        {"idEvento": 4, "uriEvento": "https://x/eventos/4", "idOrgao": 180, "siglaOrgao": "PLEN"},
        {"idEvento": 5, "uriEvento": "https://x/eventos/5", "idOrgao": 180, "siglaOrgao": "PLEN"},
        {"idEvento": 6, "uriEvento": "https://x/eventos/6", "idOrgao": 2003, "siglaOrgao": "CCJC"},
    ])
    _json(d / f"eventosPresencaDeputados-{ANO}.json", [
        {"idEvento": 1, "idDeputado": 101}, {"idEvento": 2, "idDeputado": 101}, {"idEvento": 3, "idDeputado": 101},
        {"idEvento": 1, "idDeputado": 102}, {"idEvento": 3, "idDeputado": 102},
        {"uriEvento": "https://x/eventos/2", "uriDeputado": "https://x/deputados/103"},
        {"idEvento": 6, "idDeputado": 102},
    ])

    # ---- proposições
    _csv(d / f"proposicoes-{ANO}.csv",
         ["id", "uri", "siglaTipo", "numero", "ano", "codTipo", "descricaoTipo", "ementa", "ementaDetalhada",
          "keywords", "dataApresentacao", "ultimoStatus_dataHora", "ultimoStatus_descricaoSituacao"], [
        {"id": "5001", "siglaTipo": "PL", "numero": "1", "ano": "2024", "ementa": "Dispõe sobre a transparência da fila de cirurgias.",
         "dataApresentacao": "2024-01-20T10:00", "ultimoStatus_descricaoSituacao": "Transformado em Norma Jurídica"},
        {"id": "5002", "siglaTipo": "PL", "numero": "2", "ano": "2024", "ementa": "Denomina Rodovia Fulano de Tal o trecho da BR-000.",
         "dataApresentacao": "2024-02-01T10:00", "ultimoStatus_descricaoSituacao": "Transformado em Norma Jurídica"},
        {"id": "5003", "siglaTipo": "PL", "numero": "3", "ano": "2024", "ementa": "Altera a lei de licitações.",
         "dataApresentacao": "2024-02-02T10:00", "ultimoStatus_descricaoSituacao": "Transformado em Norma Jurídica"},
        {"id": "5004", "siglaTipo": "PL", "numero": "4", "ano": "2024", "ementa": "Cria programa de crédito.",
         "dataApresentacao": "2024-02-03T10:00", "ultimoStatus_descricaoSituacao": "Aguardando Parecer"},
        {"id": "5005", "siglaTipo": "REQ", "numero": "5", "ano": "2024", "ementa": "Requer audiência.",
         "dataApresentacao": "2024-02-04T10:00", "ultimoStatus_descricaoSituacao": "Transformado em Norma Jurídica"},
    ])
    _csv(d / f"proposicoesAutores-{ANO}.csv",
         ["idProposicao", "uriProposicao", "idDeputadoAutor", "uriAutor", "codTipoAutor", "tipoAutor", "nomeAutor",
          "siglaPartidoAutor", "siglaUFAutor", "ordemAssinatura", "proponente"], [
        {"idProposicao": "5001", "idDeputadoAutor": "101", "ordemAssinatura": "1", "proponente": "1"},
        {"idProposicao": "5002", "idDeputadoAutor": "101", "ordemAssinatura": "1", "proponente": "1"},
        {"idProposicao": "5003", "idDeputadoAutor": "102", "ordemAssinatura": "1", "proponente": "1"},
        {"idProposicao": "5003", "idDeputadoAutor": "101", "ordemAssinatura": "2", "proponente": "1"},
        {"idProposicao": "5004", "idDeputadoAutor": "101", "ordemAssinatura": "1", "proponente": "1"},
        {"idProposicao": "5005", "idDeputadoAutor": "101", "ordemAssinatura": "1", "proponente": "1"},
        {"idProposicao": "5003", "idDeputadoAutor": "", "nomeAutor": "Senado Federal", "ordemAssinatura": "3", "proponente": "0"},
    ])

    for f in sorted(d.iterdir()):
        store._record(f.name, f"https://dadosabertos.camara.leg.br/teste/{f.name}")
    store.save_manifest()
    return store


CHAVE_OK = """
votacoes:
  - id: "900-1"
    tema: social
    etapa: "Texto-base"
    resumo: "A proposta torna pública a fila de cirurgias."
    sentido_sim: "Aprovar o texto-base."
    revisado_por: "Pessoa Revisora"
    revisado_em: "2026-10-08"
"""
