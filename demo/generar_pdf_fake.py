"""
Generador de PDFs FALSOS para el video/demo del pipeline de data entry.

Produce un PDF con la MISMA estructura que los reportes reales:
  * una ficha por cliente (encabezado Cliente + CUIT + fecha de emision)
  * Seccion "1. Solicitudes de Referencia": 12 columnas, subagrupada por
    "Solicitud hecha el X por Y" (o "No hay...")
  * Seccion "2. Alertas / Denuncias": 6 columnas (o "No hay...")
  * cada cliente arranca en pagina nueva; los clientes "gordos" se derraman
    a la pagina siguiente, que repite los encabezados de columna pero NO el
    encabezado del cliente (igual que el real).

Ademas SIEMBRA a proposito cada caso dificil que motiva el diseno, para que
en el video haya un momento por cada uno. Al final imprime un MANIFIESTO que
dice que cliente muestra que trampa.

Uso:
    pip install reportlab
    python generar_pdf_fake.py                # 15 clientes
    python generar_pdf_fake.py --clientes 300 # escala a 300
    python generar_pdf_fake.py --salida mi.pdf

Los datos son 100% inventados. Semilla fija => salida reproducible.
"""
import argparse
import random
from datetime import date, timedelta

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.pdfgen import canvas as canvas_mod

random.seed(17)  # Lote17, y determinismo

EMISION = date(2026, 7, 3)  # fecha de emision del lote (ancla de "N meses/años")

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

COLS_REF = ["Fecha", "Informante", "¿Es cliente?", "CO ($)", "CT ($)",
            "CO (USD)", "CT (U$D)", "Condición de venta", "Plazo",
            "Concepto", "Antigüedad", "Inactivo"]
W_REF = [52, 96, 42, 52, 52, 52, 52, 78, 34, 78, 56, 52]

COLS_ALE = ["Fecha", "Alertante", "Tipo", "Estado", "Monto", "Comentarios"]
W_ALE = [55, 110, 90, 70, 70, 250]

# ---------------------------------------------------------------------------
# Utilidades de datos falsos
# ---------------------------------------------------------------------------
def cuit_valido(tipo=None):
    """Genera un CUIT de 11 digitos con digito verificador correcto."""
    tipo = tipo or random.choice(["20", "23", "27", "30", "33"])
    medio = "".join(str(random.randint(0, 9)) for _ in range(8))
    base = tipo + medio
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
    verif = 0 if resto == 0 else (9 if resto == 1 else 11 - resto)
    return base + str(verif)

def cuit_invalido():
    """CUIT de 11 digitos con verificador MAL (para la trampa de checksum)."""
    c = cuit_valido()
    mal = (int(c[-1]) + 1) % 10
    return c[:-1] + str(mal)

NOMBRES = ["SERVICIOS CCI SRL", "AIR COMPUTER SA", "SOLUTIONBOX SA",
           "ELIT SA", "STENFAR SA", "MICROGLOBAL SA", "MASNET SA",
           "LICENCIAS ON LINE SA", "DISTRECOM SRL", "NEXSYS DE ARGENTINA",
           "PC ARTS ARGENTINA SA", "AFECTIVA SA", "NB TECH SRL",
           "DINSER SERVICIOS SRL", "GRUPO NUCLEO SA", "MEGATONE SA"]
INFORMANTES = ["FREE (Perez, G.)", "AIR COMPUTER", "SOLUTIONBOX", "STENFAR",
               "MICROGLOBAL", "MASNET S.A.", "ELIT S.A.", "NEXSYS",
               "DISTECNA", "PC ARTS"]
CONDIC = ["Cuenta corriente", "Cheque diferido", "Contado", "Sin especificar"]
CONCEPTO = ["Insumos", "Hardware", "Licencias", "Servicios", "Equipamiento"]
TIPO_ALE = ["Mora", "Cheque rechazado", "Concurso preventivo", "Denuncia"]
ESTADO_ALE = ["Abierta", "Cerrada", "En análisis"]

def fecha_rand(desde=date(2023, 1, 1), hasta=date(2026, 6, 30)):
    d = (hasta - desde).days
    return (desde + timedelta(days=random.randint(0, d))).strftime("%d/%m/%Y")

def monto_rand():
    return random.choice(["$0", f"{random.randint(1, 90)},000",
                          f"{random.randint(1, 500)*100:,}", "1", "$0"])

def fila_ref(informante=None, antiguedad="-", plazo="30", inactivo="-",
             co_ars=None, co_usd="USD 0", condicion=None, concepto=None,
             fecha=None):
    return {
        "Fecha": fecha or fecha_rand(),
        "Informante": informante or random.choice(INFORMANTES),
        "¿Es cliente?": random.choice(["Sí", "No"]),
        "CO ($)": co_ars if co_ars is not None else monto_rand(),
        "CT ($)": monto_rand(),
        "CO (USD)": co_usd,
        "CT (U$D)": "USD 0",
        "Condición de venta": condicion or random.choice(CONDIC),
        "Plazo": plazo,
        "Concepto": concepto or random.choice(CONCEPTO),
        "Antigüedad": antiguedad,
        "Inactivo": inactivo,
    }

def fila_ale():
    return {
        "Fecha": fecha_rand(), "Alertante": random.choice(INFORMANTES),
        "Tipo": random.choice(TIPO_ALE), "Estado": random.choice(ESTADO_ALE),
        "Monto": random.choice(["$ 10044.71", "$0", "23,000", "$ 5000"]),
        "Comentarios": random.choice(["Sin regularizar", "Regularizado",
                                      "En seguimiento", "-"]),
    }

def subgrupo(titulo, filas):
    return {"titulo": titulo, "filas": filas}

# ---------------------------------------------------------------------------
# Clientes con TRAMPAS sembradas (cada uno = un momento del video)
# ---------------------------------------------------------------------------
def clientes_trampa():
    L = []

    # 1) BASELINE: limpio, ambas secciones, una pagina
    L.append(("baseline: caso limpio", dict(
        nombre="SERVICIOS CCI SRL", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 09/01/2025 por FREE (Perez, G.)",
                              [fila_ref(informante="AIR COMPUTER", antiguedad="12/5/2006"),
                               fila_ref(informante="SOLUTIONBOX", antiguedad="05/2019")])],
        alertas=[fila_ale()])))

    # 2) ANTIGÜEDAD ZOO: las 7 formas + palabra sola
    zoo = [("12/5/2006", "fecha d/m/aaaa"), ("05/2019", "m/aaaa"),
           ("05/18", "m/aa"), ("2011", "año solo"), ("2 meses", "relativo meses"),
           ("1 año", "relativo años"), ("3", "numero solo = años"),
           ("reciente", "palabra sola = sin fecha"), ("-", "vacio"),
           ("n/c", "n/c")]
    L.append(("antigüedad: las 7 formas + palabra sola", dict(
        nombre="AIR COMPUTER SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 15/03/2025 por STENFAR",
                              [fila_ref(informante=f"REF {i+1}", antiguedad=a)
                               for i, (a, _) in enumerate(zoo)])],
        alertas=None)))

    # 3) PLAZO BASURA: validos + '3060' y '150'
    L.append(("plazo: basura 3060/150 mezclada con validos", dict(
        nombre="SOLUTIONBOX SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 20/02/2025 por MICROGLOBAL",
                              [fila_ref(plazo=p) for p in
                               ["30", "60", "7", "15", "21", "90", "0", "3060", "150"]])],
        alertas=None)))

    # 4) CUIT INVALIDO (verificador mal) -> debe ir a problemas, no bloquear
    L.append(("cuit: verificador invalido", dict(
        nombre="ELIT SA", cuit=cuit_invalido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 01/04/2025 por NEXSYS",
                              [fila_ref(antiguedad="2020")])],
        alertas=[fila_ale()])))

    # 5) DUPLICADO: mismo informante + misma fecha en la misma solicitud
    L.append(("matching: informante+fecha duplicados (colision)", dict(
        nombre="STENFAR SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 02/06/2026 por MASNET S.A.",
                              [fila_ref(informante="MICROGLOBAL", fecha="02/06/2026", plazo="30"),
                               fila_ref(informante="MICROGLOBAL", fecha="02/06/2026", plazo="60")])],
        alertas=None)))

    # 6) SIN REFERENCIAS (seccion 1 vacia), con alertas
    L.append(("seccion vacia: sin referencias", dict(
        nombre="MASNET SA", cuit=cuit_valido(), emision=EMISION,
        referencias=None, alertas=[fila_ale(), fila_ale()])))

    # 7) SIN ALERTAS (seccion 2 vacia), con referencias
    L.append(("seccion vacia: sin alertas", dict(
        nombre="LICENCIAS ON LINE SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 10/01/2025 por DISTECNA",
                              [fila_ref(antiguedad="7/2005")])],
        alertas=None)))

    # 8) VACIO TOTAL: ambas secciones vacias
    L.append(("ambas secciones vacias", dict(
        nombre="DISTRECOM SRL", cuit=cuit_valido(), emision=EMISION,
        referencias=None, alertas=None)))

    # 9) GORDO: se derrama a otra pagina (continuacion sin encabezado de cliente)
    L.append(("multipágina: se derrama, la 2da hoja repite solo columnas", dict(
        nombre="NEXSYS DE ARGENTINA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 05/05/2025 por PC ARTS",
                              [fila_ref(antiguedad=random.choice(["2010", "3 años", "05/2018", "-"]))
                               for _ in range(38)])],
        alertas=[fila_ale()])))

    # 10) MONTOS SUCIOS + celda que envuelve (nombre largo)
    L.append(("montos sucios + celda multilinea (wrap)", dict(
        nombre="PC ARTS ARGENTINA SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 12/03/2025 por GRUPO NUCLEO",
                              [fila_ref(informante="NETPOINT DE ARGENTINA COMUNICACIONES Y SERVICIOS INTEGRALES S.A.",
                                        co_ars="23,000", co_usd="USD 10044.71",
                                        condicion="Cheque diferido a 30/60/90 días",
                                        antiguedad="04/2010"),
                               fila_ref(co_ars="$0", antiguedad="1"),
                               fila_ref(co_ars="45,000", antiguedad="05/98")])],
        alertas=None)))

    # 11) INACTIVO: fila con Inactivo = "Sí (fecha)" -> se descarta
    L.append(("inactivo: fila 'Sí (fecha)' que debe descartarse", dict(
        nombre="AFECTIVA SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 22/04/2019 por CORCISA",
                              [fila_ref(informante="CORCISA", inactivo="Sí (30/10/2017)",
                                        antiguedad="-", plazo="0"),
                               fila_ref(informante="DINSER", antiguedad="2 años")])],
        alertas=None)))

    return L

def cliente_relleno():
    """Cliente 'normal' aleatorio para inflar el volumen."""
    tiene_ref = random.random() > 0.15
    tiene_ale = random.random() > 0.5
    refs = None
    if tiene_ref:
        subs = []
        for _ in range(random.randint(1, 2)):
            subs.append(subgrupo(
                f"Solicitud hecha el {fecha_rand()} por {random.choice(INFORMANTES)}",
                [fila_ref(antiguedad=random.choice(
                    ["12/5/2006", "05/2019", "2011", "3 años", "-", "n/c", "2015"]))
                 for _ in range(random.randint(1, 4))]))
        refs = subs
    ales = [fila_ale() for _ in range(random.randint(1, 2))] if tiene_ale else None
    return ("relleno", dict(nombre=random.choice(NOMBRES), cuit=cuit_valido(),
                            emision=EMISION, referencias=refs, alertas=ales))

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
    trampas = clientes_trampa()
    clientes = list(trampas)
    while len(clientes) < n_clientes:
        clientes.append(cliente_relleno())

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

    # Manifiesto de trampas (para guionar el video)
    print(f"\nPDF generado: {salida}  ({len(clientes)} clientes)\n")
    print("MANIFIESTO DE TRAMPAS (cliente -> que muestra):")
    print("-" * 64)
    for i, (nota, cli) in enumerate(clientes):
        if nota == "relleno":
            continue
        print(f"  Cliente {i+1:>2}  {cli['nombre']:<26}  {nota}")
    print("-" * 64)
    print("El resto son clientes de relleno (datos limpios aleatorios).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clientes", type=int, default=15)
    ap.add_argument("--salida", default="Resumen_Bulk_FAKE_Lote17.pdf")
    args = ap.parse_args()
    generar(args.salida, args.clientes)
