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
        self.assertEqual(len(linhas), 3)  # cabeçalho + 2 notas
        ids = [l.find("m:c[@r='A%s']/m:v" % l.get("r"), NS) for l in linhas[1:]]
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
        self.assertEqual(len(abrir(exportar.gerar_xlsx([])).findall(".//m:row", NS)), 1)


if __name__ == "__main__":
    unittest.main()
