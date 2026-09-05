"""
Lo que comparten todos los extractores, sea cual sea el formato.

Vive aparte por una razon concreta: la forma del documento (que un cliente
abre con "Cliente: X (CUIT: Y)", que una tabla con columna "Informante" es la
de referencias) es la MISMA en PDF y en DOCX. Lo unico que cambia es la
libreria con la que se lee. Si esto estuviera duplicado en cada extractor,
al primer cambio de encabezado se despegarian.
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
    Colapsa espacios y saltos de linea. Una celda angosta parte el texto en
    varias lineas ("NETPOINT DE\\nARGENTINA...") y eso es ruido del render, no
    del dato: sin esto, el mismo informante no matchea consigo mismo.
    """
    return " ".join((texto or "").split())


def seccion_de(encabezados: list[str]) -> str | None:
    """
    Que tabla es esta, mirando SUS ENCABEZADOS.

    No se usa el titulo de seccion ("1. Solicitudes de Referencia") a proposito:
    la pagina de continuacion no lo repite, pero si repite los encabezados de
    columna. Mirando la tabla misma, el criterio funciona igual en la primera
    pagina y en las de continuacion.
    """
    claves = {clave_columna(e) for e in encabezados}
    if "informante" in claves:
        return "referencias"
    if "alertante" in claves:
        return "alertas"
    return None
