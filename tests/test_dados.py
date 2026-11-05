import json
import unittest

import base  # noqa: F401
from dados import cnpj_valido, norm_data, normalizar


class CnpjTest(unittest.TestCase):
    def test_valido(self):
        self.assertTrue(cnpj_valido("11222333000181"))

    def test_invalidos(self):
        for c in ("11222333000182", "123", "11111111111111", ""):
            self.assertFalse(cnpj_valido(c), c)


class DataTest(unittest.TestCase):
    def test_formatos(self):
        for e in ("2026-11-03", "03/11/2026", "03-11-2026"):
            self.assertEqual(norm_data(e), "2026-11-03")

    def test_invalidas(self):
        for e in ("31/02/2026", "ontem", "", None, 20261103):
            self.assertIsNone(norm_data(e))


class NormalizarTest(unittest.TestCase):
    def test_resposta_completa(self):
        bruto = json.dumps({"empresa": "  Padaria Sol LTDA ", "cnpj": "11.222.333/0001-81", "valor_total": "1.287,40",
                            "data_emissao": "03/11/2026", "data_vencimento": "2026-12-03"})
        self.assertEqual(normalizar(bruto), {
            "empresa": "Padaria Sol LTDA", "cnpj": "11.222.333/0001-81", "valor_total": 1287.40,
            "data_emissao": "2026-11-03", "data_vencimento": "2026-12-03"})

    def test_cnpj(self):
        self.assertEqual(normalizar('{"cnpj": "11222333000181"}')["cnpj"], "11.222.333/0001-81")
        self.assertIsNone(normalizar('{"cnpj": "11.222.333/0001-82"}')["cnpj"])

    def test_valor_invalido_vira_none(self):
        for v in (0, "0,00", -5, "abc", None):
            self.assertIsNone(normalizar(json.dumps({"valor_total": v}))["valor_total"], v)

    def test_json_com_texto_em_volta(self):
        self.assertEqual(normalizar('Aqui: {"empresa": "ACME"} fim')["empresa"], "ACME")

    def test_lixo_nao_quebra(self):
        for bruto in ("{}", "", "não é json", "[1,2]", '{"a": ', "null"):
            self.assertEqual(set(normalizar(bruto).values()), {None}, bruto)


if __name__ == "__main__":
    unittest.main()
