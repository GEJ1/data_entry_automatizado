"""
Esquema de validacion y normalizacion para el pipeline de fichas de clientes.

Decisiones de diseno clave (todas apuntan a determinismo / repetibilidad):

  * Los valores relativos de Antiguedad ("2 meses", "1 año") se anclan a la
    FECHA DE EMISION de cada ficha, NO a date.today(). Asi el mismo PDF da
    siempre el mismo resultado, corras cuando corras. El PDF es una funcion pura.

  * Antiguedad se resuelve con un matcher de prioridad: se prueban los patrones
    en orden y gana el primero que matchea (ver parse_antiguedad).

  * Umbral año vs cantidad: 4 digitos = año (2011). 1-3 digitos = cantidad de
    años (18 -> 18 años atras, NO 2018).

  * Expansion de año de 2 digitos con pivote en la emision (2026):
    00-26 -> 20xx, 27-99 -> 19xx.

  * Fechas del PDF son d/m/aaaa (formato AR), nunca m/d/aaaa.

  * Referencias con Inactivo = "Si" se DESCARTAN (from_raw devuelve None). No son
    error: es una exclusion legitima. Se cuentan aparte para reconciliar.

  * Plazo fuera de 0-90 o no numerico -> None + marca de problema. La fila igual
    se emite; el problema se loguea para revision humana.

Requiere: pydantic>=2, python-dateutil
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Normalizadores puros (sin estado, testeables uno por uno)
# ---------------------------------------------------------------------------

_VACIOS = {"", "-", "n/c", "nc", "reciente", "año", "años", "anio", "anios",
           "mes", "meses"}


def parse_monto(raw: str | None) -> Decimal | None:
    """
    '$0' -> 0 ; '23,000' -> 23000 ; '10044.71' -> 10044.71 ; '1' -> 1

    Convencion observada: la coma es separador de miles, el punto es decimal.
    Si no parsea, devuelve None (el llamador lo rutea a problemas).
    """
    if raw is None:
        return None
    s = raw.strip().replace("$", "").replace("U$D", "").replace(" ", "")
    if s in ("", "-"):
        return None
    s = s.replace(",", "")  # miles fuera; el punto queda como decimal
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_fecha(raw: str | None) -> date | None:
    """Fecha d/m/aaaa (formato AR). Devuelve None si no matchea el patron."""
    if raw is None:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw.strip())
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _expandir_anio_2d(yy: int, pivote: int = 26) -> int:
    """00..pivote -> 20xx ; (pivote+1)..99 -> 19xx. Pivote atado a la emision."""
    return 2000 + yy if yy <= pivote else 1900 + yy


def parse_antiguedad(raw: str | None, emision: date) -> date | None:
    """
    Matcher de prioridad. Primer patron que matchea, gana.
    'emision' es la fecha de emision de la ficha (ancla de los relativos).
    """
    if raw is None:
        return None
    s = raw.strip().lower()

    # 1. vacios / palabra sola sin numero -> sin fecha
    if s in _VACIOS:
        return None

    # 2. d/m/aaaa
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    # 3. m/aaaa  -> dia = 01
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        mo, y = map(int, m.groups())
        try:
            return date(y, mo, 1)
        except ValueError:
            return None

    # 4. m/aa    -> dia = 01, año de 2 digitos expandido
    m = re.fullmatch(r"(\d{1,2})/(\d{2})", s)
    if m:
        mo, yy = map(int, m.groups())
        try:
            return date(_expandir_anio_2d(yy), mo, 1)
        except ValueError:
            return None

    # 5. aaaa solo -> 01/07/aaaa (mitad de año, sin sesgo)
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return date(int(m.group(1)), 7, 1)

    # 6. 'N meses' / 'N años' -> emision - N
    m = re.match(r"(\d+)\s*(mes|año|anio)", s)
    if m:
        n = int(m.group(1))
        if s[m.start(2):].startswith("mes"):
            return emision - relativedelta(months=n)
        return emision - relativedelta(years=n)

    # 7. numero solo (1-3 digitos) -> cantidad de años -> emision - N
    m = re.fullmatch(r"(\d{1,3})", s)
    if m:
        return emision - relativedelta(years=int(m.group(1)))

    # no matcheo ningun patron conocido -> sin fecha (rutear a problemas afuera)
    return None


def parse_plazo(raw: str | None) -> tuple[int | None, bool]:
    """
    Devuelve (valor, es_problema).
    Valido: entero 0-90. Fuera de rango o no numerico -> (None, True).
    """
    if raw is None:
        return (None, False)
    s = raw.strip()
    if s in ("", "-"):
        return (None, False)
    if not s.isdigit():
        return (None, True)         # basura tipo '3060' (con letras) etc.
    v = int(s)
    if 0 <= v <= 90:
        return (v, False)
    return (None, True)             # '3060', '150', etc. -> null + problema


def cuit_valido(cuit: str) -> bool:
    """Verifica los 11 digitos y el digito verificador del CUIT (mod 11)."""
    d = re.sub(r"\D", "", cuit or "")
    if len(d) != 11:
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(x) * w for x, w in zip(d[:10], pesos))
    resto = total % 11
    verif = 0 if resto == 0 else (9 if resto == 1 else 11 - resto)
    return verif == int(d[10])


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Referencia(BaseModel):
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
    # inactivo NO se guarda: si venia "Si", la fila ni se construye

    @classmethod
    def from_raw(cls, row: dict, emision: date) -> "Referencia | None":
        """
        Construye una Referencia desde una fila cruda del parser.
        Devuelve None si la fila esta inactiva (se descarta).
        'row' trae las 12 columnas crudas como strings.
        """
        inactivo = (row.get("inactivo") or "").strip().lower()
        if inactivo.startswith("si") or inactivo.startswith("sí"):
            return None  # exclusion legitima; el parser la cuenta aparte

        plazo, _ = parse_plazo(row.get("plazo"))
        return cls(
            fecha=parse_fecha(row.get("fecha")),
            informante=(row.get("informante") or "").strip(),
            es_cliente=(row.get("es_cliente") or "").strip().lower()
            in ("si", "sí"),
            co_ars=parse_monto(row.get("co_ars")),
            ct_ars=parse_monto(row.get("ct_ars")),
            co_usd=parse_monto(row.get("co_usd")),
            ct_usd=parse_monto(row.get("ct_usd")),
            condicion_venta=(row.get("condicion_venta") or "").strip(),
            plazo=plazo,
            concepto=(row.get("concepto") or "").strip(),
            antiguedad=parse_antiguedad(row.get("antiguedad"), emision),
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


# ---------------------------------------------------------------------------
# Smoke test rapido de los normalizadores (corre con: python esquema.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emision = date(2026, 7, 3)

    casos_antiguedad = [
        ("12/5/2006", date(2006, 5, 12)),
        ("05/2019", date(2019, 5, 1)),
        ("05/18", date(2018, 5, 1)),
        ("2011", date(2011, 7, 1)),
        ("2 meses", emision - relativedelta(months=2)),
        ("1 año", emision - relativedelta(years=1)),
        ("3", emision - relativedelta(years=3)),
        ("18", emision - relativedelta(years=18)),
        ("reciente", None),
        ("-", None),
        ("n/c", None),
    ]
    for raw, esperado in casos_antiguedad:
        got = parse_antiguedad(raw, emision)
        ok = "OK " if got == esperado else "MAL"
        print(f"[{ok}] antiguedad({raw!r}) = {got}  (esperado {esperado})")

    print()
    for raw, esperado in [("30", (30, False)), ("7", (7, False)),
                          ("90", (90, False)), ("3060", (None, True)),
                          ("150", (None, True)), ("", (None, False))]:
        got = parse_plazo(raw)
        ok = "OK " if got == esperado else "MAL"
        print(f"[{ok}] plazo({raw!r}) = {got}  (esperado {esperado})")

    print()
    for cuit_in, esperado_ok in [("30-70920459-5", True),   # valido
                                 ("30709204595", True),      # valido, sin guiones
                                 ("30-70920459-4", False),   # verificador malo
                                 ("123", False)]:            # ni 11 digitos
        c = Cliente(cuit=cuit_in, nombre="X", emision=emision)
        ok = "OK " if c.cuit_ok == esperado_ok else "MAL"
        destino = "carga" if c.cuit_ok else "-> problemas"
        print(f"[{ok}] cuit({cuit_in!r}) cuit_ok={c.cuit_ok} ({destino})")
