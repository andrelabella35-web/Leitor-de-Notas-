#!/usr/bin/env python3
"""Mede a acurácia por campo rodando o pipeline real (PDF -> IA) nas notas de samples/.

Uso: python3 scripts/avaliar.py [N]   (N = quantas notas avaliar; padrão: todas)
Não grava no banco. Cada nota leva ~1-3 min em CPU.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import motores  # noqa: E402
from dados import normalizar  # noqa: E402

CAMPOS = ["empresa", "cnpj", "valor_total", "data_emissao", "data_vencimento"]


def igual(campo, lido, esperado):
    if lido is None:
        return False
    if campo == "empresa":
        return lido.strip().lower() == esperado.strip().lower()
    return lido == esperado


def main():
    pasta = Path(__file__).resolve().parent.parent / "samples"
    gab = json.loads((pasta / "gabarito.json").read_text())
    nomes = sorted(gab)[: int(sys.argv[1])] if len(sys.argv) > 1 else sorted(gab)
    acertos = {c: 0 for c in CAMPOS}
    nulos = {c: 0 for c in CAMPOS}
    detalhes = {}
    for nome in nomes:
        t = time.time()
        pdf = (pasta / nome).read_bytes()
        for tentativa in range(3):  # o Ollama pode ser reiniciado pelo sistema (OOM)
            try:
                bruto = motores.extrair(pdf)
                break
            except (motores.ErroMotor, OSError) as e:
                print(f"{nome}: falha ({e}); tentando de novo em 20s", flush=True)
                time.sleep(20)
        else:
            bruto = "{}"
        lido = normalizar(bruto)
        detalhes[nome] = {"lido": lido, "esperado": gab[nome]}
        for c in CAMPOS:
            acertos[c] += igual(c, lido[c], gab[nome][c])
            nulos[c] += lido[c] is None
        print(f"{nome}: {time.time() - t:.0f}s  " + " ".join(
            f"{c}={'ok' if igual(c, lido[c], gab[nome][c]) else 'ERRO'}" for c in CAMPOS), flush=True)
    n = len(nomes)
    print(f"\nAcurácia em {n} notas ({motores.nome_modelo()}):")
    for c in CAMPOS:
        print(f"  {c:16s} {acertos[c]}/{n} = {100 * acertos[c] / n:.0f}%   (não lidos: {nulos[c]})")
    (pasta / "resultado_avaliacao.json").write_text(
        json.dumps({"modelo": motores.nome_modelo(), "notas": n, "acertos": acertos, "nao_lidos": nulos, "detalhes": detalhes},
                   ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
