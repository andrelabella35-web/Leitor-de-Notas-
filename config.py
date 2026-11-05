"""Configuração por variáveis de ambiente (nada de segredos no código)."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _flag(nome: str) -> bool:
    return os.getenv(nome, "0").strip().lower() in ("1", "true", "sim", "yes")


# --- IA de leitura: API do Google Gemini (plano gratuito) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-3.1-flash-lite")  # confira os modelos gratuitos no AI Studio
GEMINI_URL = os.getenv("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")

# --- banco: SQLite por padrão; Postgres se DATABASE_URL estiver definida ---
DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", BASE / "notas.db"))

# --- modo demo público ---
MODO_DEMO = _flag("MODO_DEMO")  # cada visitante só vê as próprias notas; dados apagados após a retenção
CONFIAR_PROXY = _flag("CONFIAR_PROXY")  # atrás de proxy HTTPS (Render, Fly...): usa X-Forwarded-For e cookie Secure
MAX_PDF_MB = int(os.getenv("MAX_PDF_MB", "5" if MODO_DEMO else "20"))
LIMITE_IP_HORA = int(os.getenv("LIMITE_IP_HORA", "5" if MODO_DEMO else "0"))  # 0 = sem limite
LIMITE_DIA = int(os.getenv("LIMITE_DIA", "150" if MODO_DEMO else "0"))  # teto global, protege a cota da API
RETENCAO_HORAS = int(os.getenv("RETENCAO_HORAS", "24" if MODO_DEMO else "0"))  # 0 = guarda para sempre

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
