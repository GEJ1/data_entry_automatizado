"""
Registro de extractores: la tabla que decide quien lee que archivo.

Agregar soporte para un formato nuevo son dos pasos y ninguno toca el resto
del pipeline:

  1. escribi una clase que cumpla el contrato `Extractor` (ver contratos.py)
  2. sumala a EXTRACTORES

El resto del pipeline llama a `para(ruta)` y no se entera de que formato es.
"""
from __future__ import annotations

from pathlib import Path

from pipeline.contratos import Extractor
from pipeline.extractores.docx_ import ExtractorDOCX
from pipeline.extractores.pdf_plumber import ExtractorPDF

EXTRACTORES: list[Extractor] = [ExtractorPDF(), ExtractorDOCX()]


def para(ruta: str | Path) -> Extractor:
    """El extractor que corresponde a la extension del archivo."""
    ext = Path(ruta).suffix.lower()
    for e in EXTRACTORES:
        if ext in e.formatos:
            return e
    soportados = sorted({f for e in EXTRACTORES for f in e.formatos})
    raise ValueError(f"No hay extractor para {ext!r}. Soportados: {soportados}")
