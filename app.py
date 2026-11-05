#!/usr/bin/env python3
"""Leitor de notas fiscais: PDF -> IA de visão (Ollama local ou Gemini) -> SQL (SQLite ou Postgres).

Uso local:  python3 app.py            (http://localhost:8000)
Produção:   veja README.md (variáveis de ambiente em config.py)
"""
import json
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import banco
import config
import motores
from dados import normalizar
from limites import Limitador

limitador = Limitador(config.LIMITE_IP_HORA, config.LIMITE_DIA)
AMOSTRA = re.compile(r"^/amostras/(nota_\d{2}\.pdf)$")


class Handler(BaseHTTPRequestHandler):
    server_version = "LeitorNotas"

    # ---- utilidades ----
    def _enviar(self, codigo, corpo: bytes, tipo: str, extra=()):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, obj, codigo=200):
        self._enviar(codigo, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", self._cookie_novo())

    def _ip(self) -> str:
        if config.CONFIAR_PROXY:  # o proxy acrescenta o IP real à direita; o que vem antes pode ser forjado
            xff = self.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[-1].strip()
        return self.client_address[0]

    def _sessao(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        v = c["sid"].value if "sid" in c else ""
        if re.fullmatch(r"[A-Za-z0-9_\-]{20,64}", v):
            return v, False
        return secrets.token_urlsafe(24), True

    def _cookie_novo(self):
        sid, novo = self._sessao_cache
        if not novo:
            return ()
        flags = "; Secure" if config.CONFIAR_PROXY else ""
        return (("Set-Cookie", f"sid={sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000{flags}"),)

    def handle_one_request(self):
        self._sessao_cache = None
        super().handle_one_request()

    def _carregar_sessao(self):
        self._sessao_cache = self._sessao()
        return self._sessao_cache[0]

    # ---- rotas ----
    def do_GET(self):
        sid = self._carregar_sessao()
        if self.path == "/":
            self._enviar(200, (config.BASE / "static/index.html").read_bytes(), "text/html; charset=utf-8", self._cookie_novo())
        elif self.path == "/api/config":
            self._json({"demo": config.MODO_DEMO, "motor": config.MOTOR, "modelo": motores.nome_modelo(),
                        "max_mb": config.MAX_PDF_MB})
        elif self.path == "/api/amostras":
            self._json(sorted(p.name for p in (config.BASE / "samples").glob("nota_[0-9][0-9].pdf")))
        elif (m := AMOSTRA.match(self.path)) and (config.BASE / "samples" / m.group(1)).is_file():
            self._enviar(200, (config.BASE / "samples" / m.group(1)).read_bytes(), "application/pdf")
        elif self.path == "/api/notas":
            self._json(banco.listar(sid if config.MODO_DEMO else None))
        else:
            self._json({"erro": "não encontrado"}, 404)

    def do_POST(self):
        sid = self._carregar_sessao()
        if self.path != "/api/upload":
            return self._json({"erro": "não encontrado"}, 404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= config.MAX_PDF_MB * 1024 * 1024:
                return self._json({"erro": f"arquivo vazio ou maior que {config.MAX_PDF_MB} MB"}, 413)
            pdf = self.rfile.read(n)
            if not pdf.startswith(b"%PDF"):
                return self._json({"erro": "o arquivo não é um PDF"}, 400)
            ok, msg = limitador.permitir(self._ip())
            if not ok:
                return self._json({"erro": msg}, 429)
            nome = unquote(self.headers.get("X-Filename", "nota.pdf"))[:200]
            bruto = motores.extrair(pdf)
            dados = normalizar(bruto)
            guardar_bruto = None if config.MODO_DEMO else bruto  # no demo não guardamos a resposta completa
            dados["id"] = banco.inserir(dados, nome, guardar_bruto, sid)
            self._json(dados)
        except ValueError as e:
            self._json({"erro": str(e)}, 400)
        except motores.ErroMotor as e:
            self._json({"erro": str(e)}, e.status)
        except Exception as e:  # nunca vazar detalhes internos ao cliente
            print(f"erro inesperado: {type(e).__name__}: {e}", flush=True)
            self._json({"erro": "falha interna ao processar a nota"}, 500)

    def log_message(self, fmt, *args):  # sem IPs/URLs completos nos logs
        print(f"{self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}", flush=True)


def _faxina():
    while True:
        try:
            n = banco.apagar_antigas(config.RETENCAO_HORAS)
            if n:
                print(f"{n} nota(s) antigas apagadas", flush=True)
        except Exception as e:
            print(f"faxina falhou: {type(e).__name__}", flush=True)
        time.sleep(3600)


def main():
    banco.iniciar()
    if config.RETENCAO_HORAS:
        threading.Thread(target=_faxina, daemon=True).start()
    print(f"Leitor de notas em http://{config.HOST}:{config.PORT}  "
          f"(motor={config.MOTOR}/{motores.nome_modelo()}, banco={'postgres' if config.DATABASE_URL else 'sqlite'}, "
          f"demo={config.MODO_DEMO})", flush=True)
    ThreadingHTTPServer((config.HOST, config.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
