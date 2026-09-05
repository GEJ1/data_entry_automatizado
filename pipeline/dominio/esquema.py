"""
El DOMINIO: que significan los datos de este documento en particular.

Este es el archivo que reescribis si adaptas el pipeline a otro rubro. Los
normalizadores de al lado son genericos; esto de aca sabe que existe un
Cliente con un CUIT, que tiene Referencias y Alertas, y como se llaman las
columnas en el documento de origen.

Decisiones de diseno:

  * Referencias con Inactivo = "Si" se DESCARTAN (from_raw devuelve None). No son
    error: es una exclusion legitima. Se cuentan aparte (Cliente.descartadas)
    para poder reconciliar filas del documento contra filas cargadas.

  * Un CUIT invalido NO bloquea ni rompe: el cliente se construye igual y se
    marca (cuit_ok). Un cliente nunca desaparece en silencio.

  * Los problemas (plazo basura, CUIT invalido) viajan CON el dato, no en un log
    aparte. Asi la vista de problemas se arma leyendo el JSONL, sin correlacionar
    nada a mano.

  * El mapeo de columnas usa clave_columna(), asi que tolera tildes, mayusculas
    y signos. Es lo que permite que el mismo dominio lea un PDF y un DOCX cuyos
    encabezados difieren en detalles cosmeticos.

Requiere: pydantic>=2
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator

from pipeline.contratos import FichaCruda, Fila
from pipeline.dominio.normalizadores import (
    clave_columna, cuit_valido, parse_antiguedad, parse_fecha, parse_monto,
    parse_plazo,
)

# ---------------------------------------------------------------------------
# Mapeo columna del documento -> campo del modelo
#
# Las claves ya estan normalizadas con clave_columna(). Si el documento cambia
# los encabezados, se toca ACA y en ningun otro lado.
# ---------------------------------------------------------------------------

COLUMNAS_REFERENCIA = {
    "fecha": "fecha",
    "informante": "informante",
    "es cliente": "es_cliente",
    "co ($)": "co_ars",
    "ct ($)": "ct_ars",
    "co (usd)": "co_usd",
    "ct (u$d)": "ct_usd",
    "ct (usd)": "ct_usd",
    "condicion de venta": "condicion_venta",
    "plazo": "plazo",
    "concepto": "concepto",
    "antiguedad": "antiguedad",
    "inactivo": "inactivo",
    # columna sintetica: la agrega el extractor con el titulo del subgrupo
    # "Solicitud hecha el X por Y". No existe como columna en el documento.
    "solicitud": "solicitud",
}

COLUMNAS_ALERTA = {
    "fecha": "fecha",
    "alertante": "alertante",
    "tipo": "tipo",
    "estado": "estado",
    "monto": "monto",
    "comentarios": "comentarios",
}

# Cabecera de la ficha (fuera de las tablas).
COLUMNAS_CABECERA = {
    "cliente": "nombre",
    "cuit": "cuit",
    "fecha de emision": "emision",
}


def _mapear(fila: Fila, mapeo: dict[str, str]) -> dict[str, str]:
    """Traduce una fila cruda (encabezados del documento) a claves del modelo."""
    salida: dict[str, str] = {}
    for encabezado, valor in fila.items():
        campo = mapeo.get(clave_columna(encabezado))
        if campo:
            salida[campo] = valor
    return salida


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Referencia(BaseModel):
    solicitud: str = ""          # "Solicitud hecha el 09/01/2025 por FREE (Perez, G.)"
    fecha: date | None
    informante: str
    es_cliente: bool
    co_ars: Decimal | None
    ct_ars: Decimal | None
    co_usd: Decimal | None
    ct_usd: Decimal | None
    condicion_venta: str
    plazo: int | None
    concepto: str
    antiguedad: date | None
    problemas: list[str] = []
    # inactivo NO se guarda: si venia "Si", la fila ni se construye

    @classmethod
    def from_raw(cls, row: dict, emision: date) -> "Referencia | None":
        """
        Construye una Referencia desde una fila YA MAPEADA a claves del modelo.
        Devuelve None si la fila esta inactiva (se descarta).
        """
        inactivo = (row.get("inactivo") or "").strip().lower()
        if inactivo.startswith("si") or inactivo.startswith("sí"):
            return None  # exclusion legitima; el llamador la cuenta aparte

        problemas: list[str] = []
        plazo, plazo_malo = parse_plazo(row.get("plazo"))
        if plazo_malo:
            problemas.append(f"plazo fuera de rango o no numerico: {row.get('plazo')!r}")

        crudo_antig = (row.get("antiguedad") or "").strip()
        antiguedad = parse_antiguedad(crudo_antig, emision)
        if crudo_antig and antiguedad is None and crudo_antig.lower() not in (
                "-", "n/c", "nc", "reciente", ""):
            problemas.append(f"antiguedad no interpretable: {crudo_antig!r}")

        return cls(
            solicitud=(row.get("solicitud") or "").strip(),
            fecha=parse_fecha(row.get("fecha")),
            informante=(row.get("informante") or "").strip(),
            es_cliente=(row.get("es_cliente") or "").strip().lower() in ("si", "sí"),
            co_ars=parse_monto(row.get("co_ars")),
            ct_ars=parse_monto(row.get("ct_ars")),
            co_usd=parse_monto(row.get("co_usd")),
            ct_usd=parse_monto(row.get("ct_usd")),
            condicion_venta=(row.get("condicion_venta") or "").strip(),
            plazo=plazo,
            concepto=(row.get("concepto") or "").strip(),
            antiguedad=antiguedad,
            problemas=problemas,
        )


class Alerta(BaseModel):
    fecha: date | None
    alertante: str
    tipo: str
    estado: str
    monto: Decimal | None
    comentarios: str

    @classmethod
    def from_raw(cls, row: dict) -> "Alerta":
        return cls(
            fecha=parse_fecha(row.get("fecha")),
            alertante=(row.get("alertante") or "").strip(),
            tipo=(row.get("tipo") or "").strip(),
            estado=(row.get("estado") or "").strip(),
            monto=parse_monto(row.get("monto")),
            comentarios=(row.get("comentarios") or "").strip(),
        )


class Cliente(BaseModel):
    cuit: str
    nombre: str
    emision: date
    referencias: list[Referencia] = []
    alertas: list[Alerta] = []
    descartadas: int = 0    # filas inactivas salteadas (para reconciliar)
    origen: str = ""        # de que archivo/pagina salio

    @field_validator("cuit")
    @classmethod
    def _normalizar_cuit(cls, v: str) -> str:
        # No rompe la linea: deja solo los digitos y guarda lo que haya.
        # La validez (11 digitos + verificador) la reporta cuit_ok, que
        # rutea el cliente a problemas sin bloquear su carga.
        return re.sub(r"\D", "", v or "")

    @property
    def cuit_ok(self) -> bool:
        """11 digitos + digito verificador. Si es False -> va a problemas."""
        return cuit_valido(self.cuit)

    @property
    def problemas(self) -> list[str]:
        """Todo lo dudoso de este cliente, junto. Alimenta la vista de problemas."""
        p: list[str] = []
        if not self.cuit_ok:
            p.append(f"CUIT invalido: {self.cuit!r}")
        for i, r in enumerate(self.referencias, start=1):
            p += [f"referencia {i}: {x}" for x in r.problemas]
        return p

    # -- construccion desde una ficha cruda ---------------------------------

    @classmethod
    def from_ficha(cls, ficha: FichaCruda) -> "Cliente":
        """
        FichaCruda (lo que devuelve CUALQUIER extractor) -> Cliente validado.

        Este metodo es la bisagra del pipeline: de aca para arriba no importa
        si el archivo era un PDF, un DOCX o un CSV.
        """
        cab = _mapear(ficha.cabecera, COLUMNAS_CABECERA)
        # La emision suele venir con hora pegada ("03/07/2026 19:00"). Recortarla
        # es interpretacion, no extraccion: por eso se hace aca y no en el extractor.
        emision_raw = (cab.get("emision") or "").strip().split(" ")[0]
        emision = parse_fecha(emision_raw) or date.min

        referencias, descartadas = [], 0
        for fila in ficha.tabla("referencias"):
            ref = Referencia.from_raw(_mapear(fila, COLUMNAS_REFERENCIA), emision)
            if ref is None:
                descartadas += 1
            else:
                referencias.append(ref)

        alertas = [Alerta.from_raw(_mapear(f, COLUMNAS_ALERTA))
                   for f in ficha.tabla("alertas")]

        return cls(
            cuit=cab.get("cuit", ""),
            nombre=(cab.get("nombre") or "").strip(),
            emision=emision,
            referencias=referencias,
            alertas=alertas,
            descartadas=descartadas,
            origen=ficha.origen,
        )


# ---------------------------------------------------------------------------
# Smoke test (corre con: python -m pipeline.dominio.esquema)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ficha = FichaCruda(
        cabecera={"Cliente": "AIR COMPUTER SA", "CUIT": "30-70920459-5",
                  "Fecha de Emisión": "03/07/2026"},
        tablas={"referencias": [
            {"Solicitud": "Solicitud hecha el 09/01/2025 por FREE",
             "Fecha": "12/05/2025", "Informante": "SOLUTIONBOX",
             "¿Es cliente?": "Sí", "CO ($)": "23,000", "CT ($)": "$0",
             "CO (USD)": "USD 0", "CT (U$D)": "USD 0",
             "Condición de venta": "Cuenta corriente", "Plazo": "30",
             "Concepto": "Insumos", "Antigüedad": "2 meses", "Inactivo": "-"},
            {"Solicitud": "Solicitud hecha el 09/01/2025 por FREE",
             "Fecha": "13/05/2025", "Informante": "ELIT", "¿Es cliente?": "No",
             "CO ($)": "$0", "CT ($)": "$0", "CO (USD)": "USD 0",
             "CT (U$D)": "USD 0", "Condición de venta": "Contado",
             "Plazo": "3060", "Concepto": "Hardware", "Antigüedad": "2011",
             "Inactivo": "-"},
            {"Solicitud": "Solicitud hecha el 09/01/2025 por FREE",
             "Fecha": "14/05/2025", "Informante": "CORCISA", "¿Es cliente?": "Sí",
             "CO ($)": "$0", "CT ($)": "$0", "CO (USD)": "USD 0",
             "CT (U$D)": "USD 0", "Condición de venta": "Contado", "Plazo": "0",
             "Concepto": "Servicios", "Antigüedad": "-",
             "Inactivo": "Sí (30/10/2017)"},
        ], "alertas": [
            {"Fecha": "01/02/2026", "Alertante": "MASNET S.A.", "Tipo": "Mora",
             "Estado": "Abierta", "Monto": "$ 10044.71",
             "Comentarios": "Sin regularizar"},
        ]},
        origen="smoke-test")

    c = Cliente.from_ficha(ficha)
    fallas = 0

    def chequear(etiqueta, got, esperado):
        global fallas
        ok = got == esperado
        fallas += 0 if ok else 1
        print(f"[{'OK ' if ok else 'MAL'}] {etiqueta} = {got!r}  (esperado {esperado!r})")

    chequear("nombre", c.nombre, "AIR COMPUTER SA")
    chequear("cuit", c.cuit, "30709204595")
    chequear("cuit_ok", c.cuit_ok, True)
    chequear("emision", c.emision, date(2026, 7, 3))
    chequear("referencias (la inactiva se descarta)", len(c.referencias), 2)
    chequear("descartadas", c.descartadas, 1)
    chequear("alertas", len(c.alertas), 1)
    print()
    chequear("ref1 antiguedad (2 meses desde emision)",
             c.referencias[0].antiguedad, date(2026, 5, 3))
    chequear("ref1 co_ars", c.referencias[0].co_ars, Decimal(23000))
    chequear("ref1 es_cliente", c.referencias[0].es_cliente, True)
    chequear("ref1 solicitud", c.referencias[0].solicitud,
             "Solicitud hecha el 09/01/2025 por FREE")
    chequear("ref2 plazo basura -> None", c.referencias[1].plazo, None)
    chequear("ref2 marca el problema", len(c.referencias[1].problemas), 1)
    chequear("alerta monto", c.alertas[0].monto, Decimal("10044.71"))
    print()
    chequear("problemas del cliente", c.problemas,
             ["referencia 2: plazo fuera de rango o no numerico: '3060'"])

    print(f"\n{'TODO OK' if fallas == 0 else str(fallas) + ' FALLAS'}")
