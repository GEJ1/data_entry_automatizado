"""
Render a PDF del lote falso. Los DATOS viven en `datos_fake.py`.

Produce un PDF con la MISMA estructura que los reportes reales:
  * una ficha por cliente (encabezado Cliente + CUIT + fecha de emision)
  * Seccion "1. Solicitudes de Referencia": 12 columnas, subagrupada por
    "Solicitud hecha el X por Y" (o "No hay...")
  * Seccion "2. Alertas / Denuncias": 6 columnas (o "No hay...")
  * cada cliente arranca en pagina nueva; los clientes "gordos" se derraman
    a la pagina siguiente, que repite los encabezados de columna pero NO el
    encabezado del cliente (igual que el real).

Ademas de PDF escribe el GROUND TRUTH (`<salida>.verdad.json`): lo que el
extractor tendria que devolver. Con eso el parser se verifica solo, con
`python -m tests.verificar_extractor`, en vez de mirar columnas a ojo.

Uso:
    python demo/generar_pdf_fake.py                # 15 clientes
    python demo/generar_pdf_fake.py --clientes 300 # escala a 300
    python demo/generar_pdf_fake.py --salida data/entrada/lote.pdf

Los datos son 100% inventados. Semilla fija => salida reproducible.
"""
import argparse
import json
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak
)
from reportlab.pdfgen import canvas as canvas_mod

from datos_fake import COLS_ALE, COLS_REF, armar_lote, manifiesto, verdad

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
st_cliente = ParagraphStyle("cliente", fontName="Helvetica-Bold", fontSize=12,
                            textColor=colors.HexColor("#1F4E79"), spaceAfter=2)
st_emision = ParagraphStyle("emision", fontName="Helvetica", fontSize=8,
                            textColor=colors.HexColor("#666666"), spaceAfter=8)
st_seccion = ParagraphStyle("seccion", fontName="Helvetica-Bold", fontSize=9.5,
                            textColor=colors.HexColor("#333333"),
                            spaceBefore=8, spaceAfter=4)
st_vacio = ParagraphStyle("vacio", fontName="Helvetica-Oblique", fontSize=8,
                          textColor=colors.HexColor("#888888"), spaceAfter=6)
st_cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=7, leading=8)
st_head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7, leading=8,
                         textColor=colors.white)
st_sub = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=7.5, leading=9,
                        textColor=colors.HexColor("#1F4E79"))

W_REF = [52, 96, 42, 52, 52, 52, 52, 78, 34, 78, 56, 52]
W_ALE = [55, 110, 90, 70, 70, 250]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def celda(texto, style=st_cell):
    return Paragraph(str(texto), style)

def tabla_ref(subgrupos):
    data = [[celda(h, st_head) for h in COLS_REF]]
    estilos = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B0B0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    r = 1
    for sg in subgrupos:
        data.append([celda(sg["titulo"], st_sub)] + [""] * (len(COLS_REF) - 1))
        estilos += [("SPAN", (0, r), (-1, r)),
                    ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#EAF0F7"))]
        r += 1
        for f in sg["filas"]:
            data.append([celda(f[c]) for c in COLS_REF])
            r += 1
    t = Table(data, colWidths=W_REF, repeatRows=1)  # repite SOLO encabezado
    t.setStyle(TableStyle(estilos))
    return t

def tabla_ale(filas):
    data = [[celda(h, st_head) for h in COLS_ALE]]
    for f in filas:
        data.append([celda(f[c]) for c in COLS_ALE])
    t = Table(data, colWidths=W_ALE, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7A2E2E")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B0B0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t

def ficha(cli):
    els = [Paragraph(f"Cliente: {cli['nombre']} (CUIT: {cli['cuit']})", st_cliente),
           Paragraph(f"Fecha de Emisión: {cli['emision'].strftime('%d/%m/%Y')} 19:00", st_emision),
           Paragraph("1. Solicitudes de Referencia", st_seccion)]
    if cli["referencias"]:
        els.append(tabla_ref(cli["referencias"]))
    else:
        els.append(Paragraph("No hay solicitudes de referencia para este cliente.", st_vacio))
    els.append(Paragraph("2. Alertas / Denuncias", st_seccion))
    if cli["alertas"]:
        els.append(tabla_ale(cli["alertas"]))
    else:
        els.append(Paragraph("No hay alertas ni denuncias para este cliente.", st_vacio))
    return els


class NumberedCanvas(canvas_mod.Canvas):
    """Pie de pagina con 'N / total' y una URL falsa, estilo export de Chrome."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self._pie(total)
            super().showPage()
        super().save()

    def _pie(self, total):
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#999999"))
        w, _ = landscape(A4)
        self.drawString(15 * mm, 8 * mm,
                        "localhost/cadmi/reportes/bulk?lote=17")
        self.drawRightString(w - 15 * mm, 8 * mm,
                             f"{self._pageNumber} / {total}")


def generar(salida, n_clientes):
    clientes = armar_lote(n_clientes)

    doc = SimpleDocTemplate(salida, pagesize=landscape(A4),
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="Resumen Bulk de Clientes - Lote 17 (DEMO)")
    story = []
    for i, (_, cli) in enumerate(clientes):
        story += ficha(cli)
        if i < len(clientes) - 1:
            story.append(PageBreak())
    doc.build(story, canvasmaker=NumberedCanvas)

    ruta_verdad = Path(salida).with_suffix(".verdad.json")
    ruta_verdad.write_text(
        json.dumps(verdad(clientes), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nPDF generado:   {salida}  ({len(clientes)} clientes)")
    print(f"Ground truth:   {ruta_verdad}\n")
    print(manifiesto(clientes))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clientes", type=int, default=15)
    ap.add_argument("--salida", default="data/entrada/lote17.pdf")
    args = ap.parse_args()
    generar(args.salida, args.clientes)
