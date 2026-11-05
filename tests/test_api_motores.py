import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import base  # noqa: F401
import app
import banco
import config
import motores
from limites import Limitador

RESPOSTA = json.dumps({"empresa": "ACME", "cnpj": "11.222.333/0001-81", "valor_total": 10.5,
                       "data_emissao": "2026-11-03", "data_vencimento": "2026-12-03"})


class Falso(BaseHTTPRequestHandler):
    """Imita a API do Gemini e registra o que recebeu."""
    recebido = {}
    status = 200

    def do_POST(self):
        Falso.recebido = {"path": self.path, "key": self.headers.get("x-goog-api-key"),
                          "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))}
        corpo = json.dumps({"candidates": [{"content": {"parts": [{"text": RESPOSTA}]}}]} if Falso.status == 200 else {"erro": "segredo"}).encode()
        self.send_response(Falso.status)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


def sobe(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


class GeminiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.url = sobe(Falso)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Falso.status = 200
        for k, v in (("MOTOR", "gemini"), ("GEMINI_URL", self.url), ("GEMINI_API_KEY", "chave-teste"), ("GEMINI_MODELO", "m-teste")):
            p = mock.patch.object(config, k, v)
            p.start()
            self.addCleanup(p.stop)

    def test_formato_da_requisicao(self):
        self.assertEqual(json.loads(motores.extrair(b"%PDF-x"))["empresa"], "ACME")
        r = Falso.recebido
        self.assertEqual(r["path"], "/models/m-teste:generateContent")
        self.assertEqual(r["key"], "chave-teste")  # a chave vai no header, não na URL
        partes = r["body"]["contents"][0]["parts"]
        self.assertEqual(partes[0]["inline_data"]["mime_type"], "application/pdf")
        self.assertEqual(r["body"]["generationConfig"]["responseMimeType"], "application/json")

    def test_sem_chave(self):
        with mock.patch.object(config, "GEMINI_API_KEY", ""), self.assertRaises(motores.ErroMotor) as c:
            motores.extrair(b"%PDF-x")
        self.assertEqual(c.exception.status, 500)

    def test_cota_estourada_vira_429_sem_vazar_corpo(self):
        Falso.status = 429
        with self.assertRaises(motores.ErroMotor) as c:
            motores.extrair(b"%PDF-x")
        self.assertEqual(c.exception.status, 429)
        self.assertNotIn("segredo", str(c.exception))

    def test_outro_erro_http(self):
        Falso.status = 500
        with self.assertRaises(motores.ErroMotor) as c:
            motores.extrair(b"%PDF-x")
        self.assertEqual(c.exception.status, 502)

    def test_motor_invalido(self):
        with mock.patch.object(config, "MOTOR", "xyz"), self.assertRaises(motores.ErroMotor):
            motores.extrair(b"%PDF-x")


class ApiTest(unittest.TestCase):
    """Servidor real com banco temporário e motor simulado."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.patches = [
            mock.patch.object(config, "SQLITE_PATH", Path(cls.tmp.name) / "t.db"),
            mock.patch.object(config, "MODO_DEMO", True),
            mock.patch.object(config, "MAX_PDF_MB", 1),
            mock.patch.object(motores, "extrair", lambda pdf: RESPOSTA),
            mock.patch.object(app, "limitador", Limitador(por_ip_hora=1000)),
        ]
        for p in cls.patches:
            p.start()
        banco.iniciar()
        cls.srv, cls.url = sobe(app.Handler)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        for p in cls.patches:
            p.stop()
        cls.tmp.cleanup()

    def req(self, caminho, corpo=None, cookie=None):
        h = {"X-Filename": "n.pdf"}
        if cookie:
            h["Cookie"] = cookie
        r = urllib.request.Request(self.url + caminho, corpo, h)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_upload_e_listagem(self):
        status, corpo, h = self.req("/api/upload", b"%PDF-1.4 x")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(corpo)["empresa"], "ACME")
        cookie = h["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", h["Set-Cookie"])
        _, lista, _ = self.req("/api/notas", cookie=cookie)
        self.assertEqual(len(json.loads(lista)), 1)

    def test_demo_isola_visitantes(self):
        _, _, h1 = self.req("/api/upload", b"%PDF-1.4 a")
        c1 = h1["Set-Cookie"].split(";")[0]
        _, lista, _ = self.req("/api/notas")  # visitante novo, sem cookie
        self.assertEqual(json.loads(lista), [])
        _, lista, _ = self.req("/api/notas", cookie=c1)
        self.assertTrue(json.loads(lista))

    def test_demo_nao_guarda_resposta_bruta(self):
        self.req("/api/upload", b"%PDF-1.4 a")
        with banco.conexao() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) c FROM notas WHERE resposta_ia IS NOT NULL").fetchone()["c"], 0)

    def test_cookie_forjado_e_ignorado(self):
        _, _, h = self.req("/api/notas", cookie="sid=../../etc/passwd")
        self.assertIn("Set-Cookie", h)  # recebe um sid novo e válido

    def test_rejeita_nao_pdf_vazio_e_grande(self):
        self.assertEqual(self.req("/api/upload", b"texto")[0], 400)
        self.assertEqual(self.req("/api/upload", b"")[0], 413)
        self.assertEqual(self.req("/api/upload", b"%PDF" + b"0" * (1024 * 1024))[0], 413)

    def test_rate_limit_devolve_429(self):
        with mock.patch.object(app, "limitador", Limitador(por_ip_hora=1)):
            self.assertEqual(self.req("/api/upload", b"%PDF-1")[0], 200)
            self.assertEqual(self.req("/api/upload", b"%PDF-1")[0], 429)

    def test_erro_do_motor_vira_status_certo(self):
        def falha(pdf):
            raise motores.ErroMotor("cota", 429)
        with mock.patch.object(motores, "extrair", falha):
            status, corpo, _ = self.req("/api/upload", b"%PDF-1")
        self.assertEqual((status, json.loads(corpo)["erro"]), (429, "cota"))

    def test_erro_inesperado_nao_vaza_detalhes(self):
        with mock.patch.object(motores, "extrair", side_effect=RuntimeError("senha do banco")), \
                mock.patch("builtins.print"):
            status, corpo, _ = self.req("/api/upload", b"%PDF-1")
        self.assertEqual(status, 500)
        self.assertNotIn("senha", corpo.decode())

    def test_amostras_sem_path_traversal(self):
        self.assertEqual(self.req("/amostras/nota_01.pdf")[0], 200)
        for p in ("/amostras/../app.py", "/amostras/..%2fapp.py", "/amostras/nota_1.pdf", "/amostras/gabarito.json"):
            self.assertEqual(self.req(p)[0], 404, p)

    def test_config_e_pagina(self):
        self.assertTrue(json.loads(self.req("/api/config")[1])["demo"])
        self.assertIn(b"Leitor de Notas", self.req("/")[1])


if __name__ == "__main__":
    unittest.main()
