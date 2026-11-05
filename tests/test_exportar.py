import io
import unittest
import zipfile
from xml.etree import ElementTree as ET

import base  # noqa: F401
import exportar

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NOTAS = [  # como vem de banco.listar(): mais nova primeiro
    {"id": 2, "empresa": "=CMD()|'x'", "cnpj": None, "valor_total": None, "data_emissao": "2026-11-03",
     "data_vencimento": "data inválida", "arquivo": "b & <c>.pdf"},
    {"id": 1, "empresa": "ACME\x00 Ltda", "cnpj": "11.222.333/0001-81", "valor_total": 1287.4,
     "data_emissao": "2026-01-01", "data_vencimento": "2026-02-01", "arquivo": "a.pdf"},
]


def abrir(dados):
    z = zipfile.ZipFile(io.BytesIO(dados))
    assert z.testzip() is None
    for nome in z.namelist():
        ET.fromstring(z.read(nome))  # todo XML precisa ser bem formado
    return ET.fromstring(z.read("xl/worksheets/sheet1.xml"))


class ExportarTest(unittest.TestCase):
    def test_estrutura_e_ordem(self):
        linhas = abrir(exportar.gerar_xlsx(NOTAS)).findall(".//m:row", NS)
        self.assertEqual(len(linhas), 4)  # cabeçalho + 2 notas + total
        ids = [l.find("m:c[@r='A%s']/m:v" % l.get("r"), NS) for l in linhas[1:3]]
        self.assertEqual([i.text for i in ids], ["1", "2"])  # mais antigas primeiro

    def test_valores_numericos_e_datas(self):
        l2 = abrir(exportar.gerar_xlsx(NOTAS)).findall(".//m:row", NS)[1]
        self.assertEqual(l2.find("m:c[@r='F2']/m:v", NS).text, "1287.4")
        self.assertEqual(l2.find("m:c[@r='D2']/m:v", NS).text, "46023")  # 2026-01-01

    def test_texto_nao_vira_formula_e_caracteres_invalidos_saem(self):
        folha = abrir(exportar.gerar_xlsx(NOTAS))
        c = folha.find(".//m:c[@r='B3']", NS)
        self.assertEqual(c.get("t"), "inlineStr")
        self.assertEqual(c.find(".//m:t", NS).text, "=CMD()|'x'")
        self.assertIsNone(c.find("m:f", NS))
        self.assertEqual(folha.find(".//m:c[@r='B2']//m:t", NS).text, "ACME Ltda")
        self.assertEqual(folha.find(".//m:c[@r='G3']//m:t", NS).text, "b & <c>.pdf")

    def test_data_invalida_vira_texto_e_vazio_vira_celula_vazia(self):
        l3 = abrir(exportar.gerar_xlsx(NOTAS)).findall(".//m:row", NS)[2]
        self.assertEqual(l3.find("m:c[@r='E3']//m:t", NS).text, "data inválida")
        self.assertIsNone(l3.find("m:c[@r='F3']", NS))

    def test_sem_notas(self):
        linhas = abrir(exportar.gerar_xlsx([])).findall(".//m:row", NS)
        self.assertEqual(len(linhas), 2)  # cabeçalho + total
        self.assertEqual(linhas[1].find("m:c[@r='F2']/m:v", NS).text, "0")

    def test_linha_de_total(self):
        folha = abrir(exportar.gerar_xlsx(NOTAS))
        self.assertEqual(len(folha.findall(".//m:row", NS)), 4)  # cabeçalho + 2 notas + total
        self.assertEqual(folha.find(".//m:c[@r='E4']//m:t", NS).text, "Total")
        f = folha.find(".//m:c[@r='F4']", NS)
        self.assertEqual(f.find("m:f", NS).text, "SUM(F2:F3)")
        self.assertEqual(f.find("m:v", NS).text, "1287.4")  # valor nulo não entra na soma
        self.assertEqual(folha.find("m:autoFilter", NS).get("ref"), "A1:G3")  # filtro não inclui o total

    def test_filtrar_periodo(self):
        f = exportar.filtrar_periodo
        self.assertEqual(f(NOTAS, None, None), NOTAS)
        self.assertEqual([n["id"] for n in f(NOTAS, "2026-01-01", "2026-01-31")], [1])  # inclusivo
        self.assertEqual([n["id"] for n in f(NOTAS, "2026-02-01", None)], [2])
        self.assertEqual([n["id"] for n in f(NOTAS, None, "2026-12-31")], [2, 1])
        self.assertEqual(f(NOTAS, "2027-01-01", None), [])
        self.assertEqual(f([{"id": 9, "data_emissao": None}], "2026-01-01", None), [])


if __name__ == "__main__":
    unittest.main()
