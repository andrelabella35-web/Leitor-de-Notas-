#!/usr/bin/env python3
"""Gera notas fiscais FICTÍCIAS em PDF + gabarito.json, para demonstração e medição de acurácia.

Todos os dados são inventados; os CNPJs são gerados com dígitos verificadores válidos
e não pertencem (intencionalmente) a nenhuma empresa conhecida.
"""
import json
import random
from pathlib import Path

SAIDA = Path(__file__).resolve().parent.parent / "samples"
random.seed(42)  # reprodutível

EMPRESAS = [
    "Padaria Sol Nascente LTDA", "Mecânica Três Irmãos ME", "Clínica Vida Plena S/S",
    "Papelaria Folha Branca EIRELI", "Auto Peças Horizonte LTDA", "Studio Luz e Forma ME",
    "Restaurante Sabor da Serra LTDA", "Tech Suporte Informática LTDA", "Floricultura Primavera ME",
    "Transportadora Rota Norte LTDA", "Escola de Idiomas Novo Mundo S/S", "Lavanderia Brisa Limpa ME",
]
LAYOUTS = [
    ("NOTA FISCAL ELETRONICA - NFS-e", "Emitente", "Emissao", "Vencimento", "VALOR TOTAL"),
    ("DANFSE - Documento Auxiliar", "Prestador", "Data de emissao", "Data de vencimento", "Valor Total da Nota"),
    ("FATURA / NOTA DE SERVICO", "Razao Social", "Emitida em", "Vence em", "Total a pagar"),
]


def cnpj_valido(base12: str) -> str:
    d = base12
    for n in (12, 13):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        r = sum(int(a) * b for a, b in zip(d, pesos)) % 11
        d += str(0 if r < 2 else 11 - r)
    return d


def fmt_cnpj(d):
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def brl(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(linhas):
    # Helvetica (WinAnsi) cobre acentos latinos; codifica em cp1252.
    c = "BT /F1 16 Tf 50 780 Td 26 TL\n" + "".join(f"({esc(l)}) Tj T*\n" for l in linhas) + "ET"
    cb = c.encode("cp1252")
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>\nstream\n" % len(cb) + cb + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
    ]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % p for p in offs)
    out += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)
    return out


def main():
    SAIDA.mkdir(exist_ok=True)
    gabarito = {}
    for i, empresa in enumerate(EMPRESAS, 1):
        titulo, l_emp, l_em, l_venc, l_tot = LAYOUTS[i % len(LAYOUTS)]
        cnpj = fmt_cnpj(cnpj_valido("".join(random.choice("0123456789") for _ in range(8)) + "0001"))
        em = (2026, random.randint(1, 10), random.randint(1, 28))
        venc = (em[0], em[1] + 1, random.randint(1, 28))
        itens = [(random.choice(["Servico", "Produto", "Mensalidade", "Taxa"]) + f" {k}", round(random.uniform(20, 900), 2))
                 for k in range(1, random.randint(2, 4) + 1)]
        total = round(sum(v for _, v in itens), 2)
        linhas = [titulo, "", f"{l_emp}: {empresa}", f"CNPJ: {cnpj}", f"{l_em}: {em[2]:02d}/{em[1]:02d}/{em[0]}",
                  f"{l_venc}: {venc[2]:02d}/{venc[1]:02d}/{venc[0]}", ""]
        linhas += [f"{n} ........ R$ {brl(v)}" for n, v in itens]
        linhas += ["", f"{l_tot}: R$ {brl(total)}"]
        nome = f"nota_{i:02d}.pdf"
        (SAIDA / nome).write_bytes(pdf(linhas))
        gabarito[nome] = {
            "empresa": empresa, "cnpj": cnpj, "valor_total": total,
            "data_emissao": f"{em[0]}-{em[1]:02d}-{em[2]:02d}",
            "data_vencimento": f"{venc[0]}-{venc[1]:02d}-{venc[2]:02d}",
        }
    (SAIDA / "gabarito.json").write_text(json.dumps(gabarito, ensure_ascii=False, indent=2))
    print(f"{len(gabarito)} notas geradas em {SAIDA}")


if __name__ == "__main__":
    main()
