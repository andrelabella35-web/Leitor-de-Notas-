"""Leitura da nota via API do Google Gemini: PDF -> texto JSON bruto."""
import base64
import json
import time
import urllib.error
import urllib.request

import config

PROMPT = (
    "Este documento é uma nota fiscal brasileira. Extraia: "
    "empresa (razão social ou nome fantasia do EMITENTE), "
    "cnpj (CNPJ do EMITENTE, 14 dígitos), "
    "valor_total (valor total da nota, número com ponto decimal), "
    "data_emissao (formato AAAA-MM-DD) e "
    "data_vencimento (formato AAAA-MM-DD). "
    'Responda SOMENTE com JSON: {"empresa": "...", "cnpj": "00.000.000/0000-00", "valor_total": 0.00, '
    '"data_emissao": "AAAA-MM-DD", "data_vencimento": "AAAA-MM-DD"}. '
    "Use null para o que não conseguir ler."
)


class ErroMotor(Exception):
    """Falha da API de IA; `status` é o código HTTP a devolver ao cliente."""

    def __init__(self, msg: str, status: int = 502):
        super().__init__(msg)
        self.status = status


def extrair(pdf: bytes) -> str:
    if not config.GEMINI_API_KEY:
        raise ErroMotor("GEMINI_API_KEY não configurada no servidor", 500)
    corpo = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    url = f"{config.GEMINI_URL}/models/{config.GEMINI_MODELO}:generateContent"
    req = urllib.request.Request(
        url, json.dumps(corpo).encode(),
        {"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY},  # chave no header, nunca na URL
    )
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 503 and tentativa < 2:  # modelo sobrecarregado: transitório, tenta de novo
                time.sleep(2 * (tentativa + 1))
                continue
            erro_http = e
            j = None
            break
        except OSError as e:
            raise ErroMotor(f"API de IA indisponível: {type(e).__name__}", 502)
    if j is None:  # nunca repassar o corpo/URL: pode conter detalhes da conta
        e = erro_http
        if e.code == 429:
            raise ErroMotor("Limite gratuito da API de IA atingido. Tente novamente em alguns minutos.", 429)
        raise ErroMotor(f"A API de IA recusou a requisição (HTTP {e.code})", 502)
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise ErroMotor("A IA não devolveu resposta para este documento", 502)


def nome_modelo() -> str:
    return config.GEMINI_MODELO
