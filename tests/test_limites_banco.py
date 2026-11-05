import tempfile
import unittest
from pathlib import Path
from unittest import mock

import base  # noqa: F401
import banco
import config
from limites import Limitador

DADOS = {"empresa": "ACME", "cnpj": "11.222.333/0001-81", "valor_total": 10.5,
         "data_emissao": "2026-11-03", "data_vencimento": "2026-12-03"}


class LimitadorTest(unittest.TestCase):
    def test_limite_por_ip(self):
        t = [0.0]
        lim = Limitador(por_ip_hora=2, relogio=lambda: t[0])
        self.assertTrue(lim.permitir("a")[0])
        self.assertTrue(lim.permitir("a")[0])
        self.assertFalse(lim.permitir("a")[0])
        self.assertTrue(lim.permitir("b")[0])  # outro IP não é afetado
        t[0] = 3601  # a janela de 1 h passou
        self.assertTrue(lim.permitir("a")[0])

    def test_teto_diario_global(self):
        lim = Limitador(por_dia=2)
        self.assertTrue(lim.permitir("a")[0])
        self.assertTrue(lim.permitir("b")[0])
        ok, msg = lim.permitir("c")
        self.assertFalse(ok)
        self.assertIn("diário", msg)

    def test_zero_significa_sem_limite(self):
        lim = Limitador(0, 0)
        self.assertTrue(all(lim.permitir("a")[0] for _ in range(100)))


class BancoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = mock.patch.object(config, "SQLITE_PATH", Path(self.tmp.name) / "t.db")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        banco.iniciar()

    def test_inserir_e_listar(self):
        i = banco.inserir(DADOS, "a.pdf", "{}", "s1")
        n = banco.listar()[0]
        self.assertEqual((n["id"], n["empresa"], n["cnpj"], n["valor_total"]), (i, "ACME", "11.222.333/0001-81", 10.5))
        self.assertNotIn("resposta_ia", n)
        self.assertNotIn("sessao", n)

    def test_isolamento_por_sessao(self):
        banco.inserir(DADOS, "a.pdf", None, "s1")
        banco.inserir(DADOS, "b.pdf", None, "s2")
        self.assertEqual([n["arquivo"] for n in banco.listar("s1")], ["a.pdf"])
        self.assertEqual(len(banco.listar()), 2)
        self.assertEqual(banco.listar("outra"), [])

    def test_apagar_antigas(self):
        banco.inserir(DADOS, "velha.pdf", None, "s1")
        with banco.conexao() as con:
            con.execute("UPDATE notas SET criado_em = datetime('now','localtime','-30 hours')")
        banco.inserir(DADOS, "nova.pdf", None, "s1")
        self.assertEqual(banco.apagar_antigas(24), 1)
        self.assertEqual([n["arquivo"] for n in banco.listar()], ["nova.pdf"])
        self.assertEqual(banco.apagar_antigas(0), 0)

    def test_migracao_de_banco_antigo(self):
        with banco.conexao() as con:
            con.execute("DROP TABLE notas")
            con.execute("CREATE TABLE notas (id INTEGER PRIMARY KEY AUTOINCREMENT, empresa TEXT, valor_total NUMERIC,"
                        " data_emissao TEXT, arquivo TEXT NOT NULL, resposta_ia TEXT, criado_em TEXT DEFAULT CURRENT_TIMESTAMP)")
        banco.iniciar()
        banco.inserir(DADOS, "a.pdf", None, "s1")  # só funciona se as colunas novas foram criadas
        self.assertEqual(len(banco.listar()), 1)

    def test_postgres_converte_placeholders(self):
        with mock.patch.object(config, "DATABASE_URL", "postgresql://x"):
            con = mock.Mock()
            banco._exec(con, "SELECT * FROM notas WHERE sessao = ? AND id = ?", ("s", 1))
            con.execute.assert_called_once_with("SELECT * FROM notas WHERE sessao = %s AND id = %s", ("s", 1))


if __name__ == "__main__":
    unittest.main()
