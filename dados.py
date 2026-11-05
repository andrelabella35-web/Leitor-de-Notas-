"""Validação e normalização do que a IA devolve."""
import json
import re
from datetime import datetime


def cnpj_valido(d: str) -> bool:
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for n in (12, 13):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        r = sum(int(a) * b for a, b in zip(d, pesos)) % 11
        if int(d[n]) != (0 if r < 2 else 11 - r):
            return False
    return True


def norm_data(v):
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def normalizar(bruto: str) -> dict:
    try:
        d = json.loads(bruto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", bruto, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            d = {}
    if not isinstance(d, dict):
        d = {}
    empresa = str(d.get("empresa") or "").strip() or None

    digitos = re.sub(r"\D", "", str(d.get("cnpj") or ""))
    cnpj = f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}" if cnpj_valido(digitos) else None

    valor = d.get("valor_total")
    if isinstance(valor, str):
        s = re.sub(r"[^\d,.\-]", "", valor)
        if "," in s:  # formato brasileiro 1.234,56
            s = s.replace(".", "").replace(",", ".")
        valor = s
    try:
        valor = round(float(valor), 2)
    except (TypeError, ValueError):
        valor = None
    if not valor or valor <= 0:  # 0 = modelo não leu; grava NULL
        valor = None

    return {
        "empresa": empresa,
        "cnpj": cnpj,
        "valor_total": valor,
        "data_emissao": norm_data(d.get("data_emissao")),
        "data_vencimento": norm_data(d.get("data_vencimento")),
    }
