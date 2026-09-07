"""
La forma del documento, que es la misma en PDF y en DOCX.

Lo unico que cambia entre un extractor y otro es la libreria con la que se lee.
Si esto estuviera duplicado, al primer cambio de encabezado se despegarian.
"""
from __future__ import annotations

import re

from pipeline.dominio.normalizadores import clave_columna

# "Cliente: SERVICIOS CCI SRL (CUIT: 33645428418)"
RE_CLIENTE = re.compile(r"^Cliente:\s*(?P<nombre>.+?)\s*\(CUIT:\s*(?P<cuit>[\d\-]+)\s*\)\s*$")
# "Fecha de Emisión: 03/07/2026 19:00"
RE_EMISION = re.compile(r"^Fecha de Emisi[oó]n:\s*(?P<valor>.+)$")
# Fila combinada que abre un subgrupo de referencias.
PREFIJO_SUBGRUPO = "Solicitud hecha el"


def limpiar(texto: str | None) -> str:
    """
    Colapsa espacios y saltos de linea: una celda angosta parte el texto en
    varias lineas, y eso es ruido del render. Sin esto, el mismo informante no
    matchea consigo mismo.
    """
    return " ".join((texto or "").split())


def seccion_de(encabezados: list[str]) -> str | None:
    """
    Que tabla es esta, mirando SUS ENCABEZADOS y no el titulo de seccion: la
    pagina de continuacion no repite el titulo, pero si los encabezados.
    """
    claves = {clave_columna(e) for e in encabezados}
    if "informante" in claves:
        return "referencias"
    if "alertante" in claves:
        return "alertas"
    return None
