"""
Extractor de PDF nativo (texto seleccionable) con pdfplumber.

Cumple el contrato `Extractor` de `pipeline/contratos.py`: recibe una ruta y
devuelve FichaCruda. No interpreta NADA: no sabe que es un CUIT ni como se lee
una antiguedad. Solo separa el documento en fichas y pone texto en celdas.

Las tres trampas que resuelve (y que motivan casi todo el codigo de abajo):

1. LAS FICHAS SE DERRAMAN. Un cliente con muchas referencias sigue en la pagina
   siguiente, y esa pagina NO repite el encabezado del cliente (si repite los
   encabezados de columna). Por eso se streamea el documento entero y se corta
   por el encabezado `Cliente: ... (CUIT: ...)`, nunca pagina por pagina.

2. LAS FILAS DE SUBGRUPO NO SON DATOS. "Solicitud hecha el X por Y" es una celda
   combinada que abarca las 12 columnas; pdfplumber la devuelve como el titulo
   completo en la primera celda y None en las otras once. Hay que detectarla
   (una sola celda con texto) y bajar ese titulo a las filas que le siguen,
   porque la solicitud forma parte de la clave de idempotencia: sin ella, dos
   solicitudes distintas del mismo cliente colisionan.
   Comparar con docx_.py, que recibe la MISMA celda combinada repetida doce
   veces: distinta maña de la libreria, misma deteccion de fondo.

3. QUE TABLA ES CUAL. En vez de adivinar por posicion o por el titulo de seccion
   (que la pagina de continuacion no repite), se mira el ENCABEZADO de la tabla:
   si tiene "Informante" es referencias, si tiene "Alertante" es alertas. Funciona
   igual en la primera pagina y en las de continuacion.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pdfplumber

from pipeline.contratos import FichaCruda, Fila
from pipeline.extractores.comun import (
    PREFIJO_SUBGRUPO, RE_CLIENTE, RE_EMISION, limpiar as _limpiar, seccion_de,
)


class ExtractorPDF:
    """Extractor para los reportes en PDF nativo. Ver contratos.Extractor."""

    formatos = (".pdf",)
    nombre = "pdf"

    def extraer(self, ruta: Path) -> Iterator[FichaCruda]:
        ruta = Path(ruta)
        ficha: FichaCruda | None = None
        paginas: list[int] = []      # paginas que abarca la ficha en curso
        solicitud = ""               # subgrupo vigente (cruza el corte de pagina)

        with pdfplumber.open(ruta) as pdf:
            for n_pag, pagina in enumerate(pdf.pages, start=1):
                lineas = pagina.extract_text_lines()

                # Se juntan encabezados y tablas en UNA lista ordenada por
                # posicion vertical. Asi da igual si el encabezado de un cliente
                # cae a mitad de pagina: el orden de lectura se respeta solo.
                elementos: list[tuple[float, str, object]] = []
                for ln in lineas:
                    texto = _limpiar(ln["text"])
                    if RE_CLIENTE.match(texto):
                        elementos.append((ln["top"], "cliente", texto))
                    elif RE_EMISION.match(texto):
                        elementos.append((ln["top"], "emision", texto))
                for tabla in pagina.find_tables():
                    elementos.append((tabla.bbox[1], "tabla", tabla))
                elementos.sort(key=lambda e: e[0])

                for _, tipo, dato in elementos:
                    if tipo == "cliente":
                        if ficha is not None:
                            ficha.origen = self._origen(ruta, paginas)
                            yield ficha
                        m = RE_CLIENTE.match(dato)
                        ficha = FichaCruda(
                            cabecera={"Cliente": m.group("nombre"),
                                      "CUIT": m.group("cuit")},
                            # Ambas secciones siempre presentes: "no hay tabla" y
                            # "tabla vacia" son lo mismo para quien consume esto.
                            tablas={"referencias": [], "alertas": []})
                        paginas = [n_pag]
                        solicitud = ""

                    elif tipo == "emision" and ficha is not None:
                        ficha.cabecera["Fecha de Emisión"] = \
                            RE_EMISION.match(dato).group("valor")

                    elif tipo == "tabla" and ficha is not None:
                        if n_pag not in paginas:
                            paginas.append(n_pag)
                        solicitud = self._volcar_tabla(
                            dato, ficha, solicitud, ruta, n_pag)

        if ficha is not None:
            ficha.origen = self._origen(ruta, paginas)
            yield ficha

    # -- internos -----------------------------------------------------------

    @staticmethod
    def _origen(ruta: Path, paginas: list[int]) -> str:
        """'lote17.pdf p.9-10'. Sirve para rastrear un dato hasta su fuente."""
        if not paginas:
            return ruta.name
        rango = str(paginas[0]) if len(paginas) == 1 else f"{paginas[0]}-{paginas[-1]}"
        return f"{ruta.name} p.{rango}"

    def _volcar_tabla(self, tabla, ficha: FichaCruda, solicitud: str,
                      ruta: Path, n_pag: int) -> str:
        """Vuelca una tabla en la ficha. Devuelve el subgrupo vigente al terminar."""
        filas = tabla.extract()
        if not filas:
            return solicitud

        encabezados = [_limpiar(c) for c in filas[0]]
        seccion = seccion_de(encabezados)
        if seccion is None:
            # Tabla que no reconocemos: se avisa fuerte en vez de tragarsela.
            print(f"AVISO: tabla desconocida en {ruta.name} p.{n_pag}, "
                  f"encabezados={encabezados}", file=sys.stderr)
            return solicitud

        for cruda in filas[1:]:
            celdas = [_limpiar(c) for c in cruda]
            con_texto = [c for c in celdas if c]

            if not con_texto:
                continue  # fila totalmente vacia: ruido del render

            # Fila de subgrupo: una sola celda con texto, y es el titulo.
            if (seccion == "referencias" and len(con_texto) == 1
                    and celdas[0].startswith(PREFIJO_SUBGRUPO)):
                solicitud = celdas[0]
                continue

            fila: Fila = dict(zip(encabezados, celdas))
            if seccion == "referencias":
                # La solicitud es un titulo que abarca varias filas en el
                # documento; aca se baja a cada fila porque despues forma
                # parte de la clave que identifica el registro.
                fila = {"Solicitud": solicitud, **fila}
            ficha.tablas[seccion].append(fila)

        return solicitud
