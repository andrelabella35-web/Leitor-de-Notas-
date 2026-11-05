"""Motores de leitura: PDF -> texto JSON bruto. Dois disponíveis: Ollama (local) e Gemini (nuvem)."""
import base64
import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import config

CAMPOS = (
    "empresa (razão social ou nome fantasia do EMITENTE), "
    "cnpj (CNPJ do EMITENTE, 14 dígitos), "
    "valor_total (valor total da nota, número com ponto decimal), "
    "data_emissao (formato AAAA-MM-DD) e "
    "data_vencimento (formato AAAA-MM-DD). "
    'Responda SOMENTE com JSON: {"empresa": "...", "cnpj": "00.000.000/0000-00", "valor_total": 0.00, '
    '"data_emissao": "AAAA-MM-DD", "data_vencimento": "AAAA-MM-DD"}. '
    "Use null para o que não conseguir ler."
)


def prompt(objeto: str) -> str:
    return f"Este(a) {objeto} é uma nota fiscal brasileira. Extraia: " + CAMPOS


class ErroMotor(Exception):
    """Falha do motor de IA; `status` é o código HTTP a devolver ao cliente."""

    def __init__(self, msg: str, status: int = 502):
        super().__init__(msg)
        self.status = status


def pdf_para_png(pdf: bytes) -> bytes:
    """Renderiza a primeira página do PDF em PNG (usado só pelo motor local)."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "in.pdf")
        src.write_bytes(pdf)
        try:
            r = subprocess.run(
                ["pdftoppm", "-png", "-r", str(config.DPI), "-f", "1", "-l", "1", "-singlefile", str(src), str(Path(d, "p"))],
                capture_output=True, timeout=60,
            )
        except FileNotFoundError:
            raise ErroMotor("pdftoppm não está instalado (sudo apt install poppler-utils)", 500)
        out = Path(d, "p.png")
        if r.returncode != 0 or not out.exists():
            raise ValueError("PDF inválido ou ilegível")
        return out.read_bytes()


def _post_json(url: str, corpo: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, json.dumps(corpo).encode(), {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def extrair_ollama(pdf: bytes) -> str:
    png = pdf_para_png(pdf)
    corpo = {
        "model": config.OLLAMA_MODELO, "stream": False, "format": "json",
        "options": {"temperature": 0, "num_ctx": 4096},
        "messages": [{"role": "user", "content": prompt("imagem"), "images": [base64.b64encode(png).decode()]}],
    }
    try:
        return _post_json(config.OLLAMA_URL + "/api/chat", corpo, {}, 600)["message"]["content"]
    except OSError as e:
        raise ErroMotor(f"Ollama indisponível: {e}", 502)


def extrair_gemini(pdf: bytes) -> str:
    if not config.GEMINI_API_KEY:
        raise ErroMotor("GEMINI_API_KEY não configurada no servidor", 500)
    corpo = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}},
            {"text": prompt("documento PDF")},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    url = f"{config.GEMINI_URL}/models/{config.GEMINI_MODELO}:generateContent"
    try:
        j = _post_json(url, corpo, {"x-goog-api-key": config.GEMINI_API_KEY}, 120)
    except urllib.error.HTTPError as e:  # nunca repassar o corpo/URL: pode conter detalhes da conta
        if e.code == 429:
            raise ErroMotor("Limite gratuito da API de IA atingido. Tente novamente em alguns minutos.", 429)
        raise ErroMotor(f"A API de IA recusou a requisição (HTTP {e.code})", 502)
    except OSError as e:
        raise ErroMotor(f"API de IA indisponível: {type(e).__name__}", 502)
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise ErroMotor("A IA não devolveu resposta para este documento", 502)


def extrair(pdf: bytes) -> str:
    if config.MOTOR == "gemini":
        return extrair_gemini(pdf)
    if config.MOTOR == "ollama":
        return extrair_ollama(pdf)
    raise ErroMotor(f"MOTOR inválido: {config.MOTOR!r} (use 'ollama' ou 'gemini')", 500)


def nome_modelo() -> str:
    return config.GEMINI_MODELO if config.MOTOR == "gemini" else config.OLLAMA_MODELO
