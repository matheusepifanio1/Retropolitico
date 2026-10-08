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
    store = fixtures.write_raw(tmp / "raw", **kw)
    conn = db.connect(tmp / "t.sqlite")
    camara.load(conn, store, fixtures.settings()["camara"], log=lambda *_: None)
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
        self.assertEqual((p.sessoes, p.presentes, p.so_por_voto), (3, 3, 1),
                         "votou na sessão 2 sem registro de presença: conta como presente")

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
        self.assertEqual(info, {"deputados": 3, "votacoes_chave": 1})
        perfil = (out / "deputado/101/index.html").read_text(encoding="utf-8")
        self.assertIn("Ana Ribeiro", perfil)
        self.assertIn("3 de 3", perfil)
        self.assertIn("Revisado por Pessoa Revisora", perfil)
        self.assertIn("Orientação do partido: Sim", perfil)
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
        self.assertIn("Nenhuma votação-chave publicada",
                      (self.tmp / "site/deputado/101/index.html").read_text(encoding="utf-8"))

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

    def test_lei(self):
        self.assertTrue(compute.is_lei("Transformado em Norma Jurídica"))
        self.assertTrue(compute.is_lei("Transformada em Norma Jurídica com Veto Parcial"))
        self.assertFalse(compute.is_lei("Aguardando Sanção"))


if __name__ == "__main__":
    unittest.main()
