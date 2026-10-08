import json
import tempfile
import unittest
from pathlib import Path

from retro import compute, db
from retro.site.build import CuradoriaError, build
from retro.sources import camara
from retro.sources.base import LayoutError

from tests import fixtures


def carregar(tmp: Path, **kw):
    from retro.sources import tse
    from retro.sources.base import RawStore
    store = fixtures.write_raw(tmp / "raw", **kw)
    conn = db.connect(tmp / "t.sqlite")
    camara.load(conn, store, fixtures.settings()["camara"], log=lambda *_: None)
    st = RawStore(tmp / "raw", "tse")
    cpfs = tse.load(conn, st, fixtures.settings()["tse"], lambda n: db.register_source(conn, "tse", st.entry(n)),
                    log=lambda *_: None)
    tse.ligar_deputados(conn, store, cpfs, lambda n: db.register_source(conn, "camara", store.entry(n)),
                        log=lambda *_: None)
    return conn


class TestCarga(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.conn = carregar(self.tmp)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_so_votacoes_nominais_do_plenario(self):
        ids = {r[0] for r in self.conn.execute("SELECT id FROM votacao")}
        self.assertEqual(ids, {"900-1", "900-2"}, "exclui comissão e votação simbólica (900-3)")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM voto WHERE votacao_id='800-1'").fetchone()[0], 0)

    def test_votacao_secreta(self):
        sec = dict(self.conn.execute("SELECT id, secreta FROM votacao").fetchall())
        self.assertEqual(sec, {"900-1": 0, "900-2": 1})

    def test_sessoes_deliberativas(self):
        ids = {r[0] for r in self.conn.execute("SELECT id FROM sessao")}
        self.assertEqual(ids, {1, 2, 3}, "exclui cancelada, não deliberativa e comissão")

    def test_presenca_respeita_licenca(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=102").fetchall()
        self.assertEqual(len(hist), 3, "ignora histórico de outra legislatura")
        periodos = compute.periodos_exercicio(hist, "2026-12-31T00:00:00")
        p = compute.presenca(self.conn, 102, periodos)
        # Sessões 1 (fev/2024) e 2 (mar/2024) foram durante a licença: não contam.
        self.assertEqual((p.sessoes, p.presentes, p.sem_registro), (1, 1, 0))

    def test_troca_de_partido_nao_interrompe_exercicio(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=101").fetchall()
        periodos = compute.periodos_exercicio(hist, "2026-12-31T00:00:00")
        self.assertEqual(len(periodos), 1)
        self.assertEqual(periodos[0].inicio, "2023-02-01T00:00")

    def test_partido_de_quem_saiu_vem_do_historico(self):
        partido = self.conn.execute("SELECT partido FROM parlamentar WHERE id=103").fetchone()[0]
        self.assertEqual(partido, "PBB")

    def test_presenca_pelo_voto(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=101").fetchall()
        p = compute.presenca(self.conn, 101, compute.periodos_exercicio(hist, "2026-12-31T00:00:00"))
        self.assertEqual((p.sessoes, p.presentes, p.so_por_voto), (3, 2, 1),
                         "votou na sessão 2 sem registro de presença: conta como presente")
        self.assertEqual((p.justificadas, p.nao_justificadas, p.sem_informacao), (1, 0, 0))
        self.assertEqual(p.motivos, [("Missão Autorizada", 1)])

    def test_ausencia_sem_justificativa(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=103").fetchall()
        p = compute.presenca(self.conn, 103, compute.periodos_exercicio(hist, "2026-12-31T00:00:00"))
        self.assertEqual((p.presentes, p.justificadas, p.nao_justificadas), (1, 0, 1))

    def test_parse_pagina_presenca(self):
        from retro.sources.camara_site import parse_linhas
        self.assertEqual(parse_linhas(["06/02/2024 Missão Autorizada | | Missão Autorizada",
                                       "EXTRAORDINÁRIA Nº 001 - 06/02/2024 | Missão Autorizada",
                                       "Data | Frequência por Sessão | Frequência por Dia/Justificativa"]),
                         [("2024-02-06", "Missão Autorizada")])

    def test_cargos(self):
        c = compute.cargos(self.conn, 101)
        self.assertEqual([r["titulo"] for r in c["direcao"]], ["Presidente"])
        self.assertEqual(len(c["membro"]), 1)

    def test_linha_do_tempo(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=102").fetchall()
        lt = compute.linha_do_tempo(hist, [], "2023-02-01", "2026-10-08T00:00:00")
        self.assertEqual([s["rotulo"] for s in lt["situacao"]], ["Em exercício", "Licença", "Em exercício"])
        self.assertEqual(lt["situacao"][1]["inicio"], "2024-01-10")
        self.assertEqual(lt["situacao"][1]["fim"], "2024-06-01")
        self.assertAlmostEqual(sum(s["width"] for s in lt["situacao"]), 100, delta=1)
        c = compute.cargos(self.conn, 101)["direcao"]
        lt = compute.linha_do_tempo([], c, "2023-02-01", "2026-10-08T00:00:00")
        self.assertEqual(lt["cargos"][0]["rotulo"], "Presidente · CCJC")

    def test_serie_periodo(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=101").fetchall()
        per = compute.periodos_exercicio(hist, "2026-12-31T00:00:00")
        s = compute.serie_periodo(self.conn, 101, per, compute.leis(self.conn, 101))
        self.assertEqual(s["s"], [["2024-02-06", "P"], ["2024-03-05", "P"], ["2024-07-02", "J"]])
        self.assertEqual(s["v"], [["2024-03-05", "S"], ["2024-08-01", "X"]])
        self.assertEqual(sorted(k for _, k in s["l"]), ["c", "h", "p"])

    def test_suplente(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=103").fetchall()
        p = compute.presenca(self.conn, 103, compute.periodos_exercicio(hist, "2026-12-31T00:00:00"))
        # Em exercício só durante a licença do titular: sessões 1 e 2; presença na 2 (lida via uri).
        self.assertEqual((p.sessoes, p.presentes), (2, 1))

    def test_resumo_votos(self):
        hist = self.conn.execute("SELECT * FROM situacao_historico WHERE parlamentar_id=101").fetchall()
        r = compute.resumo_votos(self.conn, 101, compute.periodos_exercicio(hist, "2026-12-31T00:00:00"))
        self.assertEqual((r.votacoes_no_periodo, r.com_registro), (2, 2))
        self.assertEqual(r.por_tipo, {"Sim": 1, "Secreta": 1})

    def test_leis(self):
        leis = compute.leis(self.conn, 101)
        self.assertEqual([p["id"] for p in leis["principal"]], [5001])
        self.assertEqual([p["id"] for p in leis["homenagem"]], [5002])
        self.assertEqual([p["id"] for p in leis["coautor"]], [5003])
        self.assertEqual(leis["apresentadas_principal_nao_lei"], 1, "REQ fica de fora pelo tipo")

    def test_proveniencia(self):
        orfas = self.conn.execute("SELECT COUNT(*) FROM voto WHERE fonte_id IS NULL").fetchone()[0]
        self.assertEqual(orfas, 0)
        f = self.conn.execute("SELECT * FROM fonte_arquivo WHERE nome LIKE 'votacoesVotos%'").fetchone()
        self.assertEqual(len(f["sha256"]), 64)


class TestTSE(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.conn = carregar(self.tmp)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_agrupa_pessoa_entre_anos_pelo_titulo(self):
        rows = self.conn.execute("SELECT sq_candidato, pessoa_id, resultado FROM candidatura WHERE nome_urna='DOUGLAS RUAS' ORDER BY ano").fetchall()
        self.assertEqual({r["pessoa_id"] for r in rows}, {"10000000002"}, "2022 (com CPF) e 2024 (sem CPF) são a mesma pessoa")
        self.assertEqual(rows[0]["resultado"], "NÃO ELEITO", "fica o resultado do último turno")

    def test_homonimo_fica_separado(self):
        pid = self.conn.execute("SELECT pessoa_id FROM candidatura WHERE nome_urna='DOUGLAS DO BAIRRO'").fetchone()[0]
        self.assertEqual(pid, "130000000020")

    def test_sem_dados_pessoais(self):
        colunas = [r[1] for r in self.conn.execute("PRAGMA table_info(candidatura)")]
        for proibida in ("cpf", "titulo", "nascimento", "genero", "raca", "email"):
            self.assertFalse(any(proibida in c for c in colunas), proibida)
        texto = "\n".join(str(tuple(r)) for r in self.conn.execute("SELECT * FROM candidatura"))
        self.assertNotIn("44444444444", texto)
        self.assertNotIn("000000000004", texto)

    def test_deputado_ligado(self):
        r = self.conn.execute("SELECT pessoa_id, sexo FROM parlamentar WHERE id=101").fetchone()
        self.assertEqual((r["pessoa_id"], r["sexo"]), ("250000000001", "F"))
        r = self.conn.execute("SELECT pessoa_id FROM parlamentar WHERE id=102").fetchone()
        self.assertEqual(r["pessoa_id"], "10000000005", "sem CPF: liga pelo nome civil na mesma UF")
        r = self.conn.execute("SELECT pessoa_id FROM parlamentar WHERE id=103").fetchone()
        self.assertIsNone(r["pessoa_id"], "sem candidatura compatível: não liga")

    def test_site_pessoas(self):
        from retro.site import pessoas
        out = self.tmp / "site"
        info = pessoas.gerar(self.conn, out, 2024)
        self.assertEqual(info["pessoas"], 4)
        idx = json.loads((out / "busca" / "dou.json").read_text())
        self.assertEqual(set(idx["douglas"]), {"10000000002", "130000000020"})
        self.assertEqual(idx["douglas"][0], "10000000002", "quem já foi eleito vem primeiro")
        rec = json.loads((out / "pessoas" / f"{10000000002 % pessoas.BALDES}.json").read_text())["10000000002"]
        self.assertEqual([c[0] for c in rec["c"]], [2024, 2022])
        self.assertEqual(rec["c"][0][6], "Eleito(a)")
        ana = json.loads((out / "pessoas" / f"{250000000001 % pessoas.BALDES}.json").read_text())["250000000001"]
        self.assertEqual(ana["d"], 101)
        todos = "".join(p.read_text() for p in (out / "pessoas").glob("*.json"))
        self.assertNotIn("44444444444", todos)


class TestLayout(unittest.TestCase):
    def test_coluna_ausente_para_a_coleta(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(LayoutError) as ctx:
                carregar(Path(t), drop_column="siglaOrgao")
            self.assertIn("siglaOrgao", str(ctx.exception))


class TestSite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.conn = carregar(self.tmp)
        self.chave = self.tmp / "chave.yaml"

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_build_completo(self):
        self.chave.write_text(fixtures.CHAVE_OK, encoding="utf-8")
        out = self.tmp / "site"
        info = build(self.conn, out, fixtures.settings(), self.chave)
        self.assertEqual(info, {"deputados": 3, "votacoes_chave": 1, "pessoas": 4})
        perfil = (out / "deputado/101/index.html").read_text(encoding="utf-8")
        self.assertIn("Ana Ribeiro", perfil)
        self.assertIn("<strong>2</strong> presenças em 3 sessões", perfil)
        self.assertIn("Em exercício desde fevereiro de 2023", perfil)
        self.assertIn("missão autorizada (1)", perfil)
        self.assertIn("revisado por Pessoa Revisora", perfil)
        self.assertIn("Partido orientou <strong>Sim</strong>", perfil)
        self.assertIn("Presidente da Comissão de Constituição", perfil)
        self.assertIn("Linha do tempo", perfil)
        recentes = perfil.split('id="lista-recentes"')[1].split('id="presenca"')[0]
        self.assertIn("Aprovado o Substitutivo", recentes)
        self.assertNotIn("Votação secreta de autoridade", recentes, "não é votação de mérito")
        self.assertIn("Alteração de partido", perfil)
        self.assertIn("Comissão de Constituição e Justiça e de Cidadania", perfil)
        self.assertIn("Membro de 1 órgão como", perfil)
        perfil_c = (out / "deputado/102/index.html").read_text(encoding="utf-8")
        self.assertIn("SEM REGISTRO", perfil_c, "Bruno estava licenciado na votação-chave")
        votacao = (out / "votacao/900-1/index.html").read_text(encoding="utf-8")
        self.assertIn("Carla Dias", votacao)
        busca = json.loads((out / "busca.json").read_text(encoding="utf-8"))
        self.assertEqual([b["nome"] for b in busca], ["Ana Ribeiro", "Bruno Sales", "Carla Dias"])
        self.assertTrue((out / "dados/manifesto.json").exists())
        for page in out.rglob("*.html"):
            self.assertNotIn("{{", page.read_text(encoding="utf-8"), page)

    def test_sem_votacoes_chave(self):
        self.chave.write_text("votacoes: []\n", encoding="utf-8")
        build(self.conn, self.tmp / "site", fixtures.settings(), self.chave)
        perfil = (self.tmp / "site/deputado/101/index.html").read_text(encoding="utf-8")
        self.assertIn('aria-pressed="false" disabled>Votações-chave (0)', perfil)
        self.assertIn('id="lista-recentes" class="lista-votos" >', perfil, "recentes visíveis quando não há votações-chave")

    def test_curadoria_invalida(self):
        self.chave.write_text(fixtures.CHAVE_OK.replace("900-1", "999-9"), encoding="utf-8")
        with self.assertRaises(CuradoriaError):
            build(self.conn, self.tmp / "site", fixtures.settings(), self.chave)

    def test_destaque_exige_sentido_sim(self):
        txt = fixtures.CHAVE_OK.replace('"Texto-base"', '"Destaque supressivo"').replace(
            '    sentido_sim: "Aprovar o texto-base."\n', "")
        self.chave.write_text(txt, encoding="utf-8")
        with self.assertRaises(CuradoriaError):
            build(self.conn, self.tmp / "site", fixtures.settings(), self.chave)


class TestRegras(unittest.TestCase):
    def test_homenagem(self):
        self.assertTrue(compute.is_homenagem("Institui o Dia Nacional do Café."))
        self.assertTrue(compute.is_homenagem("Inscreve o nome de Fulana no Livro dos Heróis e Heroínas da Pátria."))
        self.assertFalse(compute.is_homenagem("Altera a Lei nº 8.666 para dispor sobre a denominação social de empresas."))

    def test_merito(self):
        self.assertTrue(compute.is_merito("Aprovada a Proposta de Emenda à Constituição nº 45, de 2019."))
        self.assertTrue(compute.is_merito("Rejeitado o Destaque nº 3."))
        self.assertFalse(compute.is_merito("Aprovado o Requerimento de urgência."))
        self.assertFalse(compute.is_merito("Mantido o texto."))

    def test_lei(self):
        self.assertTrue(compute.is_lei("Transformado em Norma Jurídica"))
        self.assertTrue(compute.is_lei("Transformada em Norma Jurídica com Veto Parcial"))
        self.assertFalse(compute.is_lei("Aguardando Sanção"))


if __name__ == "__main__":
    unittest.main()
