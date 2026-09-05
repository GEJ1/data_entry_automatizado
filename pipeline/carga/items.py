"""
Cliente validado -> ItemDeCarga: que se escribe, donde, y con que clave.

Aca se decide DOS cosas delicadas:

1. QUE CAMPOS SE ESCRIBEN. Un campo que quedo en None NO se manda: se deja como
   estaba. Escribir "" seria pisar con vacio un dato que capaz ya estaba bien,
   y es exactamente el tipo de error que no se nota hasta que es tarde. Ante la
   duda, no tocar.

2. QUE FILAS NO SE CARGAN. La clave es (cliente, solicitud, fecha, informante).
   Si dos referencias del documento comparten clave, no hay forma de saber cual
   fila de la web le toca a cual: en la pantalla las dos matchean igual. Esas
   filas se apartan como CONFLICTO y no se cargan. Cargarlas "a ver si pega"
   escribiria un dato en la fila equivocada sin que nadie se entere.
"""
from __future__ import annotations

from collections import defaultdict

from pipeline.contratos import ItemDeCarga
from pipeline.dominio.esquema import Cliente, Referencia


def clave_de(cuit: str, r: Referencia) -> str:
    fecha = r.fecha.strftime("%d/%m/%Y") if r.fecha else ""
    return f"{cuit}|{r.solicitud}|{fecha}|{r.informante}"


def _campos(r: Referencia) -> dict[str, str]:
    """Nombre logico -> texto a escribir. Los None se omiten a proposito."""
    crudos = {
        "condicion": r.condicion_venta or None,
        "credito_otorgado": r.co_ars,
        "credito_tomado": r.ct_ars,
        "otorgado_usd": r.co_usd,
        "tomado_usd": r.ct_usd,
        "antiguedad": r.antiguedad.strftime("%d/%m/%Y") if r.antiguedad else None,
    }
    return {k: str(v) for k, v in crudos.items() if v is not None}


def armar(clientes: list[Cliente]) -> tuple[list[ItemDeCarga], list[str]]:
    """
    Devuelve (items cargables, conflictos).

    Los conflictos son claves repetidas: se informan y NO se cargan.
    """
    por_clave: dict[str, list[ItemDeCarga]] = defaultdict(list)

    for c in clientes:
        for r in c.referencias:
            clave = clave_de(c.cuit, r)
            por_clave[clave].append(ItemDeCarga(
                clave=clave,
                busqueda={
                    "cuit": c.cuit,
                    "cliente": c.nombre,
                    "solicitud": r.solicitud,
                    "fecha": r.fecha.strftime("%d/%m/%Y") if r.fecha else "",
                    "informante": r.informante,
                },
                campos=_campos(r)))

    items, conflictos = [], []
    for clave, grupo in por_clave.items():
        if len(grupo) > 1:
            conflictos.append(f"{clave}  ({len(grupo)} filas con la misma clave)")
        else:
            items.append(grupo[0])
    return items, conflictos
