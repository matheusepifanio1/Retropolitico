"""Candidaturas do TSE (dadosabertos.tse.jus.br / cdn.tse.jus.br).

Arquivo por eleição: consulta_cand_{ano}.zip, com um CSV por UF (e às vezes um _BRASIL),
separador ';', codificação latin-1.

Privacidade: os arquivos brutos trazem CPF, título de eleitor, e-mail e outros dados
pessoais. Eles ficam só no cache privado da coleta. Nada disso é publicado, e a inspeção
abaixo só conta quantos valores existem em cada campo sensível, sem mostrar nenhum.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from datetime import date

from .base import RawStore

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
SENSIVEIS = ["NR_CPF_CANDIDATO", "NR_TITULO_ELEITORAL_CANDIDATO", "DT_NASCIMENTO", "NM_EMAIL", "SQ_CANDIDATO"]
# Colunas que podem aparecer no relatório com valor de exemplo (dados públicos da candidatura).
EXIBIVEIS = ["ANO_ELEICAO", "NM_TIPO_ELEICAO", "NR_TURNO", "DS_ELEICAO", "SG_UF", "SG_UE", "NM_UE", "DS_CARGO",
             "NR_CANDIDATO", "NM_URNA_CANDIDATO", "DS_SITUACAO_CANDIDATURA", "SG_PARTIDO", "DS_SIT_TOT_TURNO"]


def nome_zip(ano: int) -> str:
    return f"consulta_cand_{ano}.zip"


def download(store: RawStore, cfg: dict, log=print) -> None:
    atual = date.today().year
    for ano in cfg["anos"]:
        store.fetch(URL.format(ano=ano), nome_zip(ano), refresh=ano >= atual)
        log(f"  ok {nome_zip(ano)}")
    store.save_manifest()


def _classe(valor: str) -> str:
    v = (valor or "").strip()
    if not v:
        return "vazio"
    if v in ("-1", "-3", "-4", "#NULO#", "#NULO", "#NE#", "NÃO DIVULGÁVEL", "NAO DIVULGAVEL"):
        return f"marcador {v}"
    if re.fullmatch(r"\d+", v):
        return f"{len(v)} dígitos"
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v):
        return "data dd/mm/aaaa"
    if "@" in v:
        return "e-mail"
    if "*" in v or "X" in v.upper().replace("XX", "X"):
        return "mascarado"
    return "outro"


def membros_csv(zf: zipfile.ZipFile) -> list[str]:
    return [n for n in zf.namelist() if n.lower().endswith(".csv")]


def ler(zf: zipfile.ZipFile, membro: str):
    with zf.open(membro) as raw:
        texto = io.TextIOWrapper(raw, encoding="latin-1", newline="")
        yield from csv.DictReader(texto, delimiter=";")


def inspecionar(store: RawStore, cfg: dict) -> None:
    for ano in cfg["anos"]:
        caminho = store.path(nome_zip(ano))
        if not caminho.exists():
            print(f"{nome_zip(ano)}: não baixado")
            continue
        with zipfile.ZipFile(caminho) as zf:
            membros = membros_csv(zf)
            brasil = [m for m in membros if "BRASIL" in m.upper()]
            print(f"{nome_zip(ano)} [{caminho.stat().st_size // 1048576} MB] {len(membros)} CSVs; BRASIL: {brasil[:1]}")
            alvo = brasil or membros
            linhas, classes, cargos, situacoes = 0, {c: Counter() for c in SENSIVEIS}, Counter(), Counter()
            exemplo, header = None, None
            for membro in alvo:
                for r in ler(zf, membro):
                    if header is None:
                        header = list(r.keys())
                        exemplo = {k: r.get(k) for k in EXIBIVEIS if k in r}
                    linhas += 1
                    for c in SENSIVEIS:
                        if c in r:
                            classes[c][_classe(r[c])] += 1
                    cargos[r.get("DS_CARGO", "?")] += 1
                    situacoes[r.get("DS_SIT_TOT_TURNO", "?")] += 1
            print(f"    linhas: {linhas}")
            print(f"    colunas: {header}")
            print(f"    exemplo (só campos públicos): {exemplo}")
            for c in SENSIVEIS:
                print(f"    {c}: {dict(classes[c].most_common(6)) if classes[c] else 'coluna ausente'}")
            print(f"    cargos: {dict(cargos.most_common(15))}")
            print(f"    resultado (DS_SIT_TOT_TURNO): {dict(situacoes.most_common(12))}")


# ---------------------------------------------------------------- carga

PUBLICAS = ["ANO_ELEICAO", "NM_TIPO_ELEICAO", "DS_ELEICAO", "NR_TURNO", "SG_UF", "SG_UE", "NM_UE", "DS_CARGO",
            "SQ_CANDIDATO", "NR_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO", "NM_SOCIAL_CANDIDATO",
            "SG_PARTIDO", "DS_SITUACAO_CANDIDATURA", "DS_SIT_TOT_TURNO"]
# Lidas só em memória para agrupar candidaturas da mesma pessoa. Nunca gravadas.
IDENTIDADE = ["NR_TITULO_ELEITORAL_CANDIDATO", "NR_CPF_CANDIDATO"]


class _Grupos:
    """Union-find simples para juntar candidaturas que compartilham título ou CPF."""

    def __init__(self):
        self.pai: dict = {}

    def achar(self, x):
        self.pai.setdefault(x, x)
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def unir(self, a, b):
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self.pai[rb] = ra


def _membros_brasil(zf: zipfile.ZipFile) -> list[str]:
    membros = membros_csv(zf)
    brasil = [m for m in membros if "BRASIL" in m.upper()]
    return brasil or membros


def load(conn, store: RawStore, cfg: dict, src, log=print) -> dict[str, str]:
    """Carrega candidaturas e devolve {cpf: pessoa_id} só para ligar deputados (fica em memória).

    Cada linha vai direto para o banco (sem título nem CPF). Em memória fica só o agrupamento:
    {sq: chave de identidade} e o union-find de chaves.
    """
    from .base import LayoutError
    turno_de: dict[str, int] = {}
    chave_de: dict[str, tuple] = {}
    ano_de: dict[str, int] = {}
    grupos = _Grupos()
    cpf_de: dict[str, str] = {}
    sql = """INSERT OR REPLACE INTO candidatura VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""  # pessoa_id provisório = sq
    for ano in cfg["anos"]:
        nome = nome_zip(ano)
        if not store.path(nome).exists():
            raise LayoutError(f"{nome}: arquivo não baixado")
        fid = src(nome)
        lote = []
        with zipfile.ZipFile(store.path(nome)) as zf:
            for membro in _membros_brasil(zf):
                for i, r in enumerate(ler(zf, membro)):
                    if i == 0:
                        faltam = [c for c in PUBLICAS + IDENTIDADE if c not in r and c != "NM_SOCIAL_CANDIDATO"]
                        if faltam:
                            raise LayoutError(f"{nome}/{membro}: colunas ausentes {faltam}")
                    sq = (r["SQ_CANDIDATO"] or "").strip()
                    if not sq:
                        continue
                    turno = int(r["NR_TURNO"] or 1)
                    if turno_de.get(sq, 0) >= turno:
                        continue
                    turno_de[sq] = turno
                    titulo = (r["NR_TITULO_ELEITORAL_CANDIDATO"] or "").strip()
                    cpf = (r["NR_CPF_CANDIDATO"] or "").strip()
                    chave = ("sq", sq)
                    if len(titulo) == 12 and titulo.isdigit():
                        chave = ("t", titulo)
                    if len(cpf) == 11 and cpf.isdigit():
                        if chave[0] == "sq":
                            chave = ("c", cpf)
                        else:
                            grupos.unir(chave, ("c", cpf))
                        cpf_de[cpf] = sq
                    grupos.achar(chave)
                    chave_de[sq] = chave
                    ano_de[sq] = int(r["ANO_ELEICAO"])
                    social = (r.get("NM_SOCIAL_CANDIDATO") or "").strip()
                    nome_exib = social if social and social not in ("#NULO#", "#NULO", "#NE") else r["NM_CANDIDATO"]
                    lote.append((sq, sq, int(r["ANO_ELEICAO"]), r["NM_TIPO_ELEICAO"], r["DS_ELEICAO"], r["SG_UF"],
                                 r["SG_UE"], r["NM_UE"], r["DS_CARGO"], r["NR_CANDIDATO"], nome_exib,
                                 r["NM_URNA_CANDIDATO"], r["SG_PARTIDO"], r["DS_SITUACAO_CANDIDATURA"],
                                 r["DS_SIT_TOT_TURNO"], turno, fid))
                    if len(lote) >= 50000:
                        conn.executemany(sql, lote)
                        lote = []
        if lote:
            conn.executemany(sql, lote)
        log(f"  TSE {ano}: {len(chave_de)} candidaturas acumuladas")

    # pessoa_id = SQ da candidatura mais antiga do grupo (número público e estável).
    primeiro: dict = {}
    for sq, chave in chave_de.items():
        raiz = grupos.achar(chave)
        k = (ano_de[sq], sq)
        if raiz not in primeiro or k < primeiro[raiz]:
            primeiro[raiz] = k
    conn.executemany("UPDATE candidatura SET pessoa_id=? WHERE sq_candidato=?",
                     ((primeiro[grupos.achar(chave)][1], sq) for sq, chave in chave_de.items()))
    log(f"  TSE: {len(chave_de)} candidaturas de {len(primeiro)} pessoas")
    return {cpf: primeiro[grupos.achar(chave_de[sq])][1] for cpf, sq in cpf_de.items()}


def _norm_nome(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z ]", " ", s).split())


def ligar_deputados(conn, store_camara: RawStore, cpf_pessoa: dict[str, str], src, log=print) -> None:
    """Liga cada deputado à pessoa do TSE.

    1) Pelo CPF do cadastro da Câmara, quando publicado (só em memória).
    2) Sem CPF: pela candidatura a deputado federal na mesma UF cujo nome completo
       coincide com o nome civil (ou o nome de urna com o nome parlamentar).
       Só liga quando há exatamente uma pessoa compatível; na dúvida, não liga.
    """
    from .base import read_csv
    nome = "deputados.csv"
    if not store_camara.path(nome).exists():
        log("  deputados.csv ausente: deputados sem ligação com o TSE")
        return
    src(nome)
    deps = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT id, uf, nome FROM parlamentar")}

    # Índice das candidaturas a deputado federal: (uf, nome) -> pessoas; priorizando 2022.
    por_civil: dict = {}
    por_urna: dict = {}
    for uf, n, urna, pid, ano in conn.execute(
            "SELECT uf, nome, nome_urna, pessoa_id, ano FROM candidatura WHERE cargo='DEPUTADO FEDERAL'"):
        prio = 0 if ano == 2022 else 1
        por_civil.setdefault((prio, uf, _norm_nome(n)), set()).add(pid)
        por_urna.setdefault((prio, uf, _norm_nome(urna)), set()).add(pid)

    def busca(idx, uf, chave):
        for prio in (0, 1):
            achados = idx.get((prio, uf, chave))
            if achados:
                return next(iter(achados)) if len(achados) == 1 else None
        return None

    por_cpf = por_nome = 0
    for r in read_csv(store_camara.path(nome), ["uri", "cpf", "siglaSexo", "nomeCivil"]):
        dep = int(r["uri"].rstrip("/").rsplit("/", 1)[-1])
        if dep not in deps:
            continue
        uf, nome_parl = deps[dep]
        pessoa = cpf_pessoa.get((r["cpf"] or "").strip().zfill(11)) if (r["cpf"] or "").strip() else None
        if pessoa:
            por_cpf += 1
        else:
            pessoa = busca(por_civil, uf, _norm_nome(r.get("nomeCivil"))) or busca(por_urna, uf, _norm_nome(nome_parl))
            por_nome += bool(pessoa)
        conn.execute("UPDATE parlamentar SET pessoa_id=?, sexo=? WHERE id=?", (pessoa, r["siglaSexo"] or None, dep))
    log(f"  deputados ligados ao TSE: {por_cpf + por_nome} de {len(deps)} (CPF {por_cpf}, nome {por_nome})")
