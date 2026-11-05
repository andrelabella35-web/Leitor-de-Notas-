"""Exporta as notas para uma planilha .xlsx, só com a biblioteca padrão (zipfile + XML).

Textos são gravados como texto literal (inlineStr), então um nome de empresa como "=CMD(...)"
nunca vira fórmula no Excel. Datas e valores saem como células reais (dá para somar e filtrar).
"""
import io
import re
import zipfile
from datetime import date
from xml.sax.saxutils import escape

COLUNAS = [  # (título, chave, tipo, largura)
    ("#", "id", "n", 6),
    ("Empresa", "empresa", "s", 36),
    ("CNPJ", "cnpj", "s", 20),
    ("Emissão", "data_emissao", "d", 12),
    ("Vencimento", "data_vencimento", "d", 12),
    ("Valor total (R$)", "valor_total", "m", 16),
    ("Arquivo", "arquivo", "s", 30),
]
_PROIBIDOS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")  # inválidos em XML 1.0

# estilos: 0 normal, 1 cabeçalho, 2 data, 3 moeda
_ESTILOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;R$&quot; #,##0.00"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs></styleSheet>"""

_RAIZ = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_TIPOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_LIVRO = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Notas" sheetId="1" r:id="rId1"/></sheets></workbook>"""

_LIVRO_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _col(i: int) -> str:
    return chr(ord("A") + i)  # até 26 colunas, de sobra


def _texto(ref: str, valor, estilo: int = 0) -> str:
    s = escape(_PROIBIDOS.sub("", str(valor)))
    return f'<c r="{ref}" t="inlineStr" s="{estilo}"><is><t xml:space="preserve">{s}</t></is></c>'


def _celula(ref: str, valor, tipo: str) -> str:
    if valor is None or valor == "":
        return ""
    if tipo == "s":
        return _texto(ref, valor)
    if tipo == "d":
        try:  # serial do Excel: dias desde 1899-12-30
            serial = (date.fromisoformat(str(valor)[:10]) - date(1899, 12, 30)).days
        except ValueError:
            return _texto(ref, valor)
        return f'<c r="{ref}" s="2"><v>{serial}</v></c>'
    if tipo == "m":
        return f'<c r="{ref}" s="3"><v>{float(valor)!r}</v></c>'
    return f'<c r="{ref}"><v>{int(valor)}</v></c>'


def gerar_xlsx(notas: list[dict]) -> bytes:
    """Recebe a lista de `banco.listar()` e devolve os bytes do .xlsx (mais antigas primeiro)."""
    linhas = ['<row r="1">' + "".join(_texto(f"{_col(i)}1", t, 1) for i, (t, *_r) in enumerate(COLUNAS)) + "</row>"]
    for n, nota in enumerate(reversed(notas), start=2):
        cels = "".join(_celula(f"{_col(i)}{n}", nota.get(chave), tipo) for i, (_t, chave, tipo, _w) in enumerate(COLUNAS))
        linhas.append(f'<row r="{n}">{cels}</row>')
    ultima = _col(len(COLUNAS) - 1)
    larguras = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{c[3]}" customWidth="1"/>' for i, c in enumerate(COLUNAS))
    folha = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f"<cols>{larguras}</cols><sheetData>{''.join(linhas)}</sheetData>"
        f'<autoFilter ref="A1:{ultima}{max(len(notas) + 1, 1)}"/></worksheet>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TIPOS)
        z.writestr("_rels/.rels", _RAIZ)
        z.writestr("xl/workbook.xml", _LIVRO)
        z.writestr("xl/_rels/workbook.xml.rels", _LIVRO_RELS)
        z.writestr("xl/styles.xml", _ESTILOS)
        z.writestr("xl/worksheets/sheet1.xml", folha)
    return buf.getvalue()
