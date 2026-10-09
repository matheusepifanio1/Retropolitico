"""Senado e Presidência: carga, classificação de presença e páginas."""

import json
import tempfile
import unittest
from pathlib import Path

from retro import compute_senado
from retro.site.build import build
from retro.sources import senado
from retro.sources.base import RawStore

from tests import fixtures
from tests.test_pipeline import carregar

CFG = {"legislaturas": [57], "inicio": "2023-02-01", "proposicoes_desde": "2023-02-01"}


def _parl(cod, nome, completo, sexo, uf, participacao="Titular"):
    return {"IdentificacaoParlamentar": {"CodigoParlamentar": str(cod), "NomeParlamentar": nome,
                                        "NomeCompletoParlamentar": completo, "SexoParlamentar": sexo},
            # Formato real: item único vem como objeto, não lista.
            "Mandatos": {"Mandato": {"CodigoMandato": "9", "UfParlamentar": uf, "DescricaoParticipacao": participacao}}}


def write_senado(root: Path) -> RawStore:
    st = RawStore(root, "senado")
    leg = {"ListaParlamentarLegislatura": {"Parlamentares": {"Parlamentar": [
        _parl(1, "Fulano Silva", "Fulano de Tal Silva", "Masculino", "AC"),
        _parl(2, "Beltrana", "Beltrana Souza", "Feminino", "AC", "1º Suplente"),
        _parl(3, "Nunca Exerceu", "Nunca Exerceu Costa", "Masculino", "AC", "2º Suplente"),
    ]}}}
    st.save_json("senadores-leg57.json", "https://x/senador/lista/legislatura/57", leg)
    detalhe = {"1": {"DetalheParlamentar": {"Parlamentar": {"IdentificacaoParlamentar": {
        "NomeParlamentar": "Fulano Silva", "SiglaPartidoParlamentar": "PSS", "UfParlamentar": "AC",
        "UrlFotoParlamentar": "http://x/1.jpg"}}}}, "2": None, "3": None}
    st.save_json("senadores-detalhe.json", "https://x/senador/{codigo}", detalhe)

    def mand(exercicios, partidos):
        return {"MandatoParlamentar": {"Parlamentar": {"Mandatos": {"Mandato": [{
            "CodigoMandato": "9", "UfParlamentar": "AC", "DescricaoParticipacao": "Titular",
            "PrimeiraLegislaturaDoMandato": {"NumeroLegislatura": "57", "DataInicio": "2023-02-01", "DataFim": "2027-01-31"},
            "Exercicios": {"Exercicio": exercicios}, "Partidos": {"Partido": partidos}}]}}}}
    mandatos = {
        # Fulano se afastou (virou ministro) entre março e maio de 2024: a suplente assumiu.
        "1": mand([{"DataInicio": "2023-02-01", "DataFim": "2024-02-29", "SiglaCausaAfastamento": "AFO",
                    "DescricaoCausaAfastamento": "Afastamento para exercer cargo de ministro"},
                   {"DataInicio": "2024-06-01"}], [{"Sigla": "PSS", "DataFiliacao": "2020-01-01"}]),
        "2": mand({"DataInicio": "2024-03-01", "DataFim": "2024-05-31"}, {"Sigla": "PTT", "DataFiliacao": "2019-01-01"}),
        "3": {"MandatoParlamentar": {"Parlamentar": {"Mandatos": {"Mandato": {"CodigoMandato": "9", "UfParlamentar": "AC"}}}}},
    }
    st.save_json("senadores-mandatos.json", "https://x/senador/{codigo}/mandatos", mandatos)
    cargos = {"1": {"CargoParlamentar": {"Parlamentar": {"Cargos": {"Cargo": [
        {"IdentificacaoComissao": {"SiglaComissao": "CAE", "NomeComissao": "Comissão de Assuntos Econômicos", "SiglaCasaComissao": "SF"},
         "DescricaoCargo": "PRESIDENTE", "DataInicio": "2025-03-01"},
        {"IdentificacaoComissao": {"SiglaComissao": "CCJ", "NomeComissao": "Comissão de Constituição", "SiglaCasaComissao": "SF"},
         "DescricaoCargo": "TITULAR", "DataInicio": "2023-03-01"}]}}}}, "2": None, "3": None}
    st.save_json("senadores-cargos.json", "https://x/senador/{codigo}/cargos", cargos)
    processos = {"1": [
        {"id": "11", "identificacao": "PL 10/2023", "tipoDocumento": "Projeto de Lei Ordinária",
         "ementa": "Cria cadastro nacional de vagas em creches.", "dataApresentacao": "2023-04-01",
         "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA", "normaGerada": "Lei nº 15.000 de 01/02/2025",
         "autoria": "Senador Fulano Silva (PSS/AC)", "codigoMateria": "150001"},
        {"id": "12", "identificacao": "PL 11/2023", "tipoDocumento": "Projeto de Lei Ordinária",
         "ementa": "Institui o Dia Nacional do Agricultor Familiar.", "dataApresentacao": "2023-05-01",
         "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA", "normaGerada": "Lei nº 15.001 de 01/02/2025",
         "autoria": "Senador Fulano Silva (PSS/AC)", "codigoMateria": "150002"},
        {"id": "13", "identificacao": "PEC 2/2023", "tipoDocumento": "Proposta de Emenda à Constituição",
         "ementa": "Altera o art. 1º.", "dataApresentacao": "2023-06-01",
         "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA", "normaGerada": "Emenda Constitucional nº 140",
         "autoria": "Senadora Outra Pessoa (PXX/SP), Senador Fulano Silva (PSS/AC)", "codigoMateria": "150003"},
        {"id": "14", "identificacao": "PL 99/2015", "tipoDocumento": "Projeto de Lei Ordinária",
         "ementa": "Antigo.", "dataApresentacao": "2015-01-01", "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA",
         "normaGerada": "Lei nº 13.000", "autoria": "Senador Fulano Silva (PSS/AC)", "codigoMateria": "1"},
    ], "2": [], "3": None}
    st.save_json("senadores-processos.json", "https://x/processo?codigoParlamentarAutor={codigo}", processos)

    def votacao(cod, data, votos, secreta="N", materia="PL 50/2023"):
        return {"codigoSessaoVotacao": str(cod), "dataSessao": data, "casaSessao": "SF", "identificacao": materia,
                "ementa": f"Ementa da votação {cod}.", "descricaoVotacao": f"Votação nominal {cod}",
                "resultadoVotacao": "A", "votacaoSecreta": secreta, "codigoMateria": "160000",
                "votos": [{"codigoParlamentar": str(c), "siglaVotoParlamentar": s, "siglaPartidoParlamentar": "PSS",
                           "siglaUFParlamentar": "AC"} for c, s in votos]}
    st.save_json("senado-votacoes-2024-01.json", "https://x/votacao?2024-01", [
        votacao(1, "2024-01-10", [(1, "Sim")]),
        votacao(2, "2024-01-11", [(1, "NCom")]),
        votacao(3, "2024-01-12", [(1, "LS")]),
        votacao(4, "2024-01-13", [(1, "Votou")], secreta="S", materia="MSF 1/2024"),
    ])
    st.save_json("senado-votacoes-2024-04.json", "https://x/votacao?2024-04", [
        # Fulano afastado: a votação conta para a suplente, não para ele.
        votacao(5, "2024-04-10", [(1, "AFO"), (2, "Não")]),
    ])
    st.save_json("senado-votacoes-2024-07.json", "https://x/votacao?2024-07", [
        votacao(6, "2024-07-10", [(1, "P-NRV")]),
        votacao(7, "2024-07-11", [(1, "Presidente (art. 51 RISF)")]),
        votacao(8, "2024-07-12", []),  # sem registro do senador
    ])
    st.save_json("senado-tipos-comparecimento.json", "https://x/tipos", {"ListaTiposComparecimento": {
        "TiposComparecimento": {"TipoComparecimento": [
            {"Sigla": s, "Descricao": d} for s, d in [("LS", "Licença saúde"), ("NCom", "Não Compareceu"),
                                                       ("AFO", "Afastamento do exercício"), ("P-NRV", "Presente – Não registrou voto"),
                                                       ("MIS", "Missão da Casa no País/exterior")]]}}})
    st.save_json("cn-vetos-2024.json", "https://x/vetos/2024", {"ListaVetosAnoCN": {"Vetos": {"Veto": [
        {"Codigo": "100", "Materia": {"Numero": "5", "Ano": "2024", "Ementa": "Veto total ao PL 1/2024"},
         "MateriaVetada": {"Sigla": "PL", "Numero": "1", "Ano": "2024"}, "Total": "Sim", "DataPublicacao": "2024-05-10",
         "Assunto": "Assunto A", "QuantidadeDispositivos": "0", "Mensagem": {"UrlPlanalto": "https://planalto/vet1"}},
        {"Codigo": "101", "Materia": {"Numero": "6", "Ano": "2024", "Ementa": "Veto parcial"},
         "MateriaVetada": {"Sigla": "PL", "Numero": "2", "Ano": "2024", "NormaGerada": {"NomeNorma": "Lei nº 14.900"}},
         "Total": "Não", "DataPublicacao": "2024-06-10", "Assunto": "Assunto B", "QuantidadeDispositivos": "3"},
    ]}}})
    st.save_manifest()
    return st


SETTINGS = {**fixtures.settings(), "senado": CFG, "presidencia": {"eleicoes_desde": 2018}}


class TestSenado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.conn = carregar(self.tmp)
        st = write_senado(self.tmp / "raw")
        senado.load(self.conn, RawStore(self.tmp / "raw", "senado"), CFG, log=lambda *_: None)
        self.conn.executemany("INSERT INTO candidatura (sq_candidato, pessoa_id, ano, cargo, uf, nome, nome_urna, partido, resultado, turno_final) VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("10000000777", "10000000777", 2018, "SENADOR", "AC", "FULANO DE TAL SILVA", "FULANO", "PSS", "ELEITO", 1),
            ("10000000888", "10000000888", 2022, "PRESIDENTE", "BR", "PRESIDENTE TESTE", "PRESIDENTE TESTE", "PZZ", "ELEITO", 2),
        ])
        senado.ligar_tse(self.conn, log=lambda *_: None)
        self.tipos = compute_senado.tipos_comparecimento(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_so_quem_exerceu_vira_perfil(self):
        nomes = {r[0] for r in self.conn.execute("SELECT nome FROM senador")}
        self.assertEqual(nomes, {"Fulano Silva", "Beltrana"})

    def test_periodos_e_presenca(self):
        ps = compute_senado.periodos(self.conn, 1, CFG["inicio"], "2024-08-01T00:00:00")
        self.assertEqual([(p.inicio, p.fim) for p in ps], [("2023-02-01", "2024-03-01"), ("2024-06-01", "2024-08-01")])
        regs = compute_senado.registros(self.conn, 1, ps, self.tipos)
        self.assertEqual([r["id"] for r in regs], [1, 2, 3, 4, 6, 7, 8], "votação 5 é do período de afastamento")
        p = compute_senado.presenca(regs)
        self.assertEqual((p["total"], p["presentes"], p["justificadas"], p["nao_justificadas"], p["sem_informacao"]),
                         (7, 4, 1, 1, 1))
        self.assertEqual(p["motivos"], [("Licença saúde", 1)])
        v = compute_senado.resumo_votos(regs)
        self.assertEqual((v["sim"], v["secreta"], v["com_voto"]), (1, 1, 2))

    def test_suplente_conta_so_o_proprio_periodo(self):
        ps = compute_senado.periodos(self.conn, 2, CFG["inicio"], "2024-08-01T00:00:00")
        regs = compute_senado.registros(self.conn, 2, ps, self.tipos)
        self.assertEqual([(r["id"], r["sigla"]) for r in regs], [(5, "Não")])

    def test_leis(self):
        leis = compute_senado.leis(self.conn, 1)
        self.assertEqual([p["identificacao"] for p in leis["principal"]], ["PL 10/2023"])
        self.assertEqual([p["identificacao"] for p in leis["homenagem"]], ["PL 11/2023"])
        self.assertEqual([p["identificacao"] for p in leis["coautor"]], ["PEC 2/2023"], "segundo nome na autoria")

    def test_ligacao_tse(self):
        self.assertEqual(self.conn.execute("SELECT pessoa_id FROM senador WHERE codigo=1").fetchone()[0], "10000000777")

    def test_presidencia(self):
        ps = compute_senado.presidentes(self.conn, 2018)
        self.assertEqual([(p["inicio"], p["fim"]) for p in ps], [("2023-01-01", "2026-12-31")])
        atos = compute_senado.atos_presidente(self.conn, ps[0], "2024-12-31")
        self.assertEqual((atos["vetos_totais"], atos["vetos_parciais"], len(atos["mpvs"]), atos["mpv_viraram_lei"]), (1, 1, 2, 1))

    def test_site(self):
        chave = self.tmp / "chave.yaml"
        chave.write_text(fixtures.CHAVE_OK, encoding="utf-8")
        (self.tmp / "planos_governo.yaml").write_text(
            "planos:\n  - {ano: 2022, cargo: PRESIDENTE, uf: BR, partido: PZZ, url: 'https://tse/plano.pdf'}\n", encoding="utf-8")
        out = self.tmp / "site"
        info = build(self.conn, out, SETTINGS, chave)
        self.assertEqual((info["senadores"], info["presidentes"]), (2, 1))
        perfil = (out / "senador/1/index.html").read_text(encoding="utf-8")
        self.assertIn("Fulano Silva", perfil)
        self.assertIn("Senador pelo PSS do Acre", perfil)
        self.assertIn("licença saúde (1)", perfil)
        self.assertIn("Presidente · Comissão de Assuntos Econômicos", perfil)
        self.assertIn("https://x/1.jpg", perfil, "foto em https")
        self.assertTrue((out / "senador/1/votos/index.html").exists())
        pres = (out / "presidente/10000000888/index.html").read_text(encoding="utf-8")
        self.assertIn("medidas provisórias editadas", pres)
        pessoa = json.loads((out / f"pessoas/{10000000888 % 4096}.json").read_text(encoding="utf-8"))["10000000888"]
        self.assertEqual(pessoa["e"], 1)
        self.assertEqual(pessoa["c"][0][9], "https://tse/plano.pdf")
        sen = json.loads((out / f"pessoas/{10000000777 % 4096}.json").read_text(encoding="utf-8"))["10000000777"]
        self.assertEqual(sen["s"], 1)
        self.assertTrue((out / "senadores/index.html").exists())
        for page in out.rglob("*.html"):
            self.assertNotIn("{{", page.read_text(encoding="utf-8"), page)


if __name__ == "__main__":
    unittest.main()
