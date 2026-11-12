"""Valida o dashboard e os alertas versionados: `python3 -m unittest discover -s observabilidade`.

Não fala com o New Relic: confere o que dá para errar no JSON sem perceber (página faltando,
widget sobreposto ou fora da grade, query de um serviço que não existe).
"""
import json
import pathlib
import re
import unittest

AQUI = pathlib.Path(__file__).resolve().parent
SERVICOS = {"oficina-os-service", "oficina-billing-service", "oficina-execucao-service"}
COLUNAS = 12


def carrega(nome):
    return json.loads((AQUI / nome).read_text(encoding="utf-8"))


def queries(dashboard):
    for pagina in dashboard["pages"]:
        for widget in pagina["widgets"]:
            for q in widget["rawConfiguration"]["nrqlQueries"]:
                yield pagina["name"], widget["title"], q["query"]


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.dashboard = carrega("dashboard-saga.json")

    def test_e_um_dashboard_so_com_a_visao_geral_e_uma_pagina_por_servico(self):
        paginas = [p["name"] for p in self.dashboard["pages"]]

        self.assertTrue(paginas[0].startswith("Visão geral"))
        self.assertEqual(["OS Service", "Billing Service", "Execução Service"], paginas[1:])

    def test_toda_pagina_tem_widgets_com_titulo_e_query(self):
        for pagina in self.dashboard["pages"]:
            self.assertTrue(pagina["widgets"], pagina["name"])
        for pagina, titulo, query in queries(self.dashboard):
            self.assertTrue(titulo, pagina)
            self.assertTrue(query.strip().upper().startswith("SELECT"), f"{pagina}/{titulo}")

    def test_widgets_cabem_na_grade_e_nao_se_sobrepoem(self):
        for pagina in self.dashboard["pages"]:
            ocupadas = {}
            for widget in pagina["widgets"]:
                l = widget["layout"]
                self.assertGreaterEqual(l["column"], 1, widget["title"])
                self.assertLessEqual(l["column"] + l["width"] - 1, COLUNAS, f"{pagina['name']}/{widget['title']} passa da grade")
                for linha in range(l["row"], l["row"] + l["height"]):
                    for coluna in range(l["column"], l["column"] + l["width"]):
                        outro = ocupadas.setdefault((linha, coluna), widget["title"])
                        self.assertEqual(widget["title"], outro, f"{pagina['name']}: '{widget['title']}' sobrepõe '{outro}'")

    def test_queries_so_citam_os_servicos_da_saga(self):
        for pagina, titulo, query in queries(self.dashboard):
            for nome in re.findall(r"'(oficina-[a-z-]+)'", query):
                self.assertIn(nome, SERVICOS, f"{pagina}/{titulo}")

    def test_pagina_de_servico_so_olha_para_o_proprio_servico(self):
        donos = {"OS Service": "oficina-os-service", "Billing Service": "oficina-billing-service", "Execução Service": "oficina-execucao-service"}
        for pagina, titulo, query in queries(self.dashboard):
            if pagina in donos:
                self.assertEqual({donos[pagina]}, set(re.findall(r"'(oficina-[a-z-]+)'", query)), f"{pagina}/{titulo}")

    def test_a_visao_geral_junta_os_tres_servicos(self):
        geral = [q for p, t, q in queries(self.dashboard) if p.startswith("Visão geral") and "trace.id" in q]

        self.assertTrue(geral, "A visão geral precisa de um widget por trace.id.")
        self.assertTrue(any(SERVICOS == set(re.findall(r"'(oficina-[a-z-]+)'", q)) for q in geral))


class AlertasTest(unittest.TestCase):
    def test_toda_condicao_tem_nome_e_nrql(self):
        alertas = carrega("alertas-saga.json")

        self.assertTrue(alertas["condicoes"])
        for c in alertas["condicoes"]:
            self.assertTrue(c["nome"])
            self.assertTrue(c["nrql"].upper().startswith("SELECT COUNT(*)"), c["nome"])

    def test_cobre_a_falha_de_execucao_da_compensacao(self):
        nrqls = " ".join(c["nrql"] for c in carrega("alertas-saga.json")["condicoes"])

        self.assertIn("execucao.falhou", nrqls)
        self.assertIn("falha_ao_processar_mensagem", nrqls)


if __name__ == "__main__":
    unittest.main()
