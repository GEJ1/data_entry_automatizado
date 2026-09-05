"""
Cliente validado -> ItemDeCarga: que se escribe, en que formulario, y con que clave.

Aca se decide DOS cosas delicadas:

1. QUE CAMPOS SE ESCRIBEN. Un campo que quedo en None NO se manda: se deja como
   estaba. Escribir "" seria pisar con vacio un dato que capaz ya estaba bien,
   y es exactamente el tipo de error que no se nota hasta que es tarde. Ante la
   duda, no tocar.

2. QUE FILAS NO SE CARGAN. Si dos filas del documento comparten clave, no hay
   forma de saber cual fila de la web le toca a cual: en la pantalla las dos
   matchean igual. Esas filas se apartan como CONFLICTO y no se cargan. Cargarlas
   "a ver si pega" escribiria un dato en la fila equivocada sin que nadie se
   entere.

Las claves arrancan con el nombre del formulario. No es cosmetico: el estado de
carga es una sola tabla para todo el lote, y sin ese prefijo una alerta y una
referencia podrian generar la misma clave y saltearse entre si.
"""
from __future__ import annotations

from collections import defaultdict

from pipeline.contratos import ItemDeCarga
from pipeline.dominio.esquema import Alerta, Cliente, Referencia


def _f(fecha) -> str:
    return fecha.strftime("%d/%m/%Y") if fecha else ""


def clave_referencia(cuit: str, r: Referencia) -> str:
    return f"referencias|{cuit}|{r.solicitud}|{_f(r.fecha)}|{r.informante}"


def clave_alerta(cuit: str, a: Alerta) -> str:
    return f"alertas|{cuit}|{_f(a.fecha)}|{a.alertante}"


def _campos_referencia(r: Referencia) -> dict[str, str]:
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


def _campos_alerta(a: Alerta) -> dict[str, str]:
    crudos = {
        "tipo": a.tipo or None,
        "estado": a.estado or None,
        "monto": a.monto,
        "comentarios": a.comentarios or None,
    }
    return {k: str(v) for k, v in crudos.items() if v is not None}


def armar(clientes: list[Cliente]) -> tuple[list[ItemDeCarga], list[str]]:
    """
    Devuelve (items cargables, conflictos).

    Los conflictos son claves repetidas: se informan y NO se cargan.
    """
    por_clave: dict[str, list[ItemDeCarga]] = defaultdict(list)

    for c in clientes:
        datos_cliente = {"cuit": c.cuit, "cliente": c.nombre}

        for r in c.referencias:
            clave = clave_referencia(c.cuit, r)
            por_clave[clave].append(ItemDeCarga(
                formulario="referencias",
                clave=clave,
                busqueda={**datos_cliente, "solicitud": r.solicitud,
                          "fecha": _f(r.fecha), "quien": r.informante},
                campos=_campos_referencia(r)))

        for a in c.alertas:
            clave = clave_alerta(c.cuit, a)
            por_clave[clave].append(ItemDeCarga(
                formulario="alertas",
                clave=clave,
                busqueda={**datos_cliente, "fecha": _f(a.fecha),
                          "quien": a.alertante},
                campos=_campos_alerta(a)))

    items, conflictos = [], []
    for clave, grupo in por_clave.items():
        if len(grupo) > 1:
            conflictos.append(f"{clave}  ({len(grupo)} filas con la misma clave)")
        else:
            items.append(grupo[0])
    return items, conflictos
