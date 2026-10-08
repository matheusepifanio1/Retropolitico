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
        "tse": {"anos": [2022, 2024]},
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
            {"dataHora": "2022-03-31T00:00", "situacao": "Exercício", "descricaoStatus": "Anterior à posse", "idLegislatura": 57},
            {"dataHora": "2024-01-10T00:00", "situacao": "Exercício", "descricaoStatus": "Suplente", "idLegislatura": 57},
            {"dataHora": "2024-06-01T00:00", "situacao": "Fim do Mandato", "descricaoStatus": "Saída", "idLegislatura": 57},
        ],
    }
    (d / "deputados-historico.json").write_text(json.dumps(historico, ensure_ascii=False), encoding="utf-8")
    orgaos = {
        "101": [
            {"idOrgao": 2003, "uriOrgao": "https://x/orgaos/2003", "siglaOrgao": "CCJC",
             "nomeOrgao": "Comissão de Constituição e Justiça e de Cidadania", "nomePublicacao": "Comissão de Constituição e Justiça e de Cidadania",
             "titulo": "Presidente", "codTitulo": "1", "dataInicio": "2024-03-06T00:00", "dataFim": "2025-03-01T00:00"},
            {"idOrgao": 2004, "uriOrgao": "https://x/orgaos/2004", "siglaOrgao": "CSAUDE",
             "nomeOrgao": "Comissão de Saúde", "nomePublicacao": "Comissão de Saúde",
             "titulo": "Titular", "codTitulo": "101", "dataInicio": "2023-03-01T00:00", "dataFim": None},
        ],
        "102": [], "103": [],
    }
    (d / "deputados-orgaos.json").write_text(json.dumps(orgaos, ensure_ascii=False), encoding="utf-8")

    # ---- votações
    vh = ["id", "uri", "data", "dataHoraRegistro", "idOrgao", "siglaOrgao", "idEvento", "aprovacao", "votosSim",
          "votosNao", "votosOutros", "descricao", "ultimaAberturaVotacao_descricao"]
    if drop_column:
        vh = [c for c in vh if c != drop_column]
    _csv(d / f"votacoes-{ANO}.csv", vh, [
        {"id": "900-1", "data": "2024-03-05", "dataHoraRegistro": "2024-03-05T20:10:00", "siglaOrgao": "PLEN", "idEvento": "2",
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
        {"idEvento": 1, "idDeputado": 101},
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

    # Páginas de presença do site da Câmara, no formato real extraído (linhas de dia e de sessão).
    site = {
        "101-2024": {"url": "https://www.camara.leg.br/deputados/101/presenca-plenario/2024", "status": 200, "ok": True,
                     "sha256": "0" * 64, "baixado_em": "2026-10-08T00:00:00Z", "linhas": [
            "Presença em Plenário - 2024", "Data | Frequência por Sessão | Frequência por Dia/Justificativa",
            "06/02/2024 Presença | | Presença", "EXTRAORDINÁRIA Nº 001 - 06/02/2024 | Presença",
            "05/03/2024 Presença | | Presença", "EXTRAORDINÁRIA Nº 017 - 05/03/2024 | Presença",
            "02/07/2024 Missão Autorizada | | Missão Autorizada", "EXTRAORDINÁRIA Nº 120 - 02/07/2024 | Missão Autorizada"]},
        "103-2024": {"url": "https://www.camara.leg.br/deputados/103/presenca-plenario/2024", "status": 200, "ok": True,
                     "sha256": "1" * 64, "baixado_em": "2026-10-08T00:00:00Z", "linhas": [
            "06/02/2024 Ausência | | Ausência", "EXTRAORDINÁRIA Nº 001 - 06/02/2024 | Ausência",
            "05/03/2024 Presença | | Presença"]},
    }
    (d / "presenca-plenario-site.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")

    # Cadastro da Câmara com CPF (fictício), lido só para ligar ao TSE.
    _csv(d / "deputados.csv", ["uri", "nome", "nomeCivil", "cpf", "siglaSexo", "dataNascimento"], [
        {"uri": "https://x/deputados/101", "nome": "Ana Ribeiro", "cpf": "11111111111", "siglaSexo": "F"},
        {"uri": "https://x/deputados/102", "nome": "Bruno Sales", "nomeCivil": "Bruno Sáles Lima", "cpf": "", "siglaSexo": "M"},
        {"uri": "https://x/deputados/103", "nome": "Carla Dias", "cpf": "33333333333", "siglaSexo": "F"},
    ])

    for f in sorted(d.iterdir()):
        store._record(f.name, f"https://dadosabertos.camara.leg.br/teste/{f.name}")
    store.save_manifest()
    write_tse(root)
    return store


TSE_COLS = ["ANO_ELEICAO", "NM_TIPO_ELEICAO", "DS_ELEICAO", "NR_TURNO", "SG_UF", "SG_UE", "NM_UE", "DS_CARGO",
            "SQ_CANDIDATO", "NR_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO", "NM_SOCIAL_CANDIDATO",
            "NR_CPF_CANDIDATO", "NR_TITULO_ELEITORAL_CANDIDATO", "DT_NASCIMENTO", "DS_GENERO", "DS_COR_RACA",
            "SG_PARTIDO", "DS_SITUACAO_CANDIDATURA", "DS_SIT_TOT_TURNO"]


def _cand(ano, turno, uf, ue, nm_ue, cargo, sq, num, nome, urna, cpf, titulo, partido, res, sit="APTO"):
    return {"ANO_ELEICAO": str(ano), "NM_TIPO_ELEICAO": "ELEIÇÃO ORDINÁRIA", "DS_ELEICAO": f"Eleições {ano}",
            "NR_TURNO": str(turno), "SG_UF": uf, "SG_UE": ue, "NM_UE": nm_ue, "DS_CARGO": cargo, "SQ_CANDIDATO": sq,
            "NR_CANDIDATO": num, "NM_CANDIDATO": nome, "NM_URNA_CANDIDATO": urna, "NM_SOCIAL_CANDIDATO": "#NULO#",
            "NR_CPF_CANDIDATO": cpf, "NR_TITULO_ELEITORAL_CANDIDATO": titulo, "DT_NASCIMENTO": "01/01/1980",
            "DS_GENERO": "FEMININO", "DS_COR_RACA": "PARDA", "SG_PARTIDO": partido,
            "DS_SITUACAO_CANDIDATURA": sit, "DS_SIT_TOT_TURNO": res}


def write_tse(root: Path) -> RawStore:
    import io
    import zipfile
    store = RawStore(root, "tse")
    linhas = {
        2022: [
            _cand(2022, 1, "SP", "SP", "SÃO PAULO", "DEPUTADO FEDERAL", "250000000001", "1234", "ANA RIBEIRO SILVA",
                  "ANA RIBEIRO", "11111111111", "000000000001", "PAA", "ELEITO POR QP"),
            # Câmara sem CPF: liga pelo nome civil + UF + cargo
            _cand(2022, 1, "AC", "AC", "ACRE", "DEPUTADO FEDERAL", "10000000005", "2222", "BRUNO SALES LIMA",
                  "BRUNO SALES", "55555555555", "000000000005", "PBB", "ELEITO POR MÉDIA"),
            _cand(2022, 1, "AC", "AC", "ACRE", "GOVERNADOR", "10000000002", "40", "DOUGLAS RUAS PEREIRA",
                  "DOUGLAS RUAS", "44444444444", "000000000004", "PXX", "2º TURNO"),
            _cand(2022, 2, "AC", "AC", "ACRE", "GOVERNADOR", "10000000002", "40", "DOUGLAS RUAS PEREIRA",
                  "DOUGLAS RUAS", "44444444444", "000000000004", "PXX", "NÃO ELEITO"),
        ],
        2024: [
            # 2024 sem CPF: liga pelo título de eleitor
            _cand(2024, 1, "AC", "01392", "RIO BRANCO", "PREFEITO", "10000000010", "40", "DOUGLAS RUAS PEREIRA",
                  "DOUGLAS RUAS", "-4", "000000000004", "PXX", "ELEITO"),
            # homônimo: mesmo nome, outro título
            _cand(2024, 1, "MG", "41238", "BELO HORIZONTE", "VEREADOR", "130000000020", "40123", "DOUGLAS RUAS PEREIRA",
                  "DOUGLAS DO BAIRRO", "-4", "000000000099", "PYY", "SUPLENTE"),
        ],
    }
    for ano, rows in linhas.items():
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writerow(TSE_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in TSE_COLS])
        with zipfile.ZipFile(store.path(f"consulta_cand_{ano}.zip"), "w") as z:
            z.writestr(f"consulta_cand_{ano}_BRASIL.csv", buf.getvalue().encode("latin-1"))
            z.writestr(f"consulta_cand_{ano}_AC.csv", buf.getvalue().encode("latin-1"))
        store._record(f"consulta_cand_{ano}.zip", f"https://cdn.tse.jus.br/teste/consulta_cand_{ano}.zip")
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
