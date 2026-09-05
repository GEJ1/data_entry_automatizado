"""
Normalizadores: funciones puras que convierten texto sucio en datos limpios.

Son GENERICOS: no saben nada de clientes, referencias ni alertas. Si adaptas
este pipeline a otro rubro, este archivo probablemente sobreviva casi intacto;
el que vas a reescribir es `esquema.py`.

Decisiones de diseno clave (todas apuntan a determinismo / repetibilidad):

  * Los valores relativos de Antiguedad ("2 meses", "1 año") se anclan a la
    FECHA DE EMISION de cada ficha, NO a date.today(). Asi el mismo archivo da
    siempre el mismo resultado, corras cuando corras. La entrada es una funcion pura.

  * Antiguedad se resuelve con un matcher de prioridad: se prueban los patrones
    en orden y gana el primero que matchea (ver parse_antiguedad).

  * Umbral año vs cantidad: 4 digitos = año (2011). 1-3 digitos = cantidad de
    años (18 -> 18 años atras, NO 2018).

  * Expansion de año de 2 digitos con pivote en la emision (2026):
    00-26 -> 20xx, 27-99 -> 19xx.

  * Fechas son d/m/aaaa (formato AR), nunca m/d/aaaa.

  * Plazo fuera de 0-90 o no numerico -> None + marca de problema. La fila igual
    se emite; el problema se loguea para revision humana.

Ninguna de estas funciones lanza excepciones por un dato feo: devuelven None y
dejan que el llamador decida. Un dato malo no puede voltear un lote de 3000.

Requiere: python-dateutil
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta

_VACIOS = {"", "-", "n/c", "nc", "reciente", "año", "años", "anio", "anios",
           "mes", "meses"}


def clave_columna(encabezado: str) -> str:
    """
    Normaliza un encabezado de columna para poder mapearlo sin depender de
    tildes, mayusculas, signos ni espacios de mas.

    '¿Es cliente?' -> 'es cliente' ; 'Condición de venta' -> 'condicion de venta'

    Existe porque los encabezados son lo mas fragil del pipeline: cambian de
    un documento a otro (o de PDF a DOCX) por detalles cosmeticos.
    """
    s = unicodedata.normalize("NFKD", encabezado or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("¿", "").replace("?", "").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_monto(raw: str | None) -> Decimal | None:
    """
    '$0' -> 0 ; '23,000' -> 23000 ; '10044.71' -> 10044.71 ; '1' -> 1

    Convencion observada: la coma es separador de miles, el punto es decimal.
    Si no parsea, devuelve None (el llamador lo rutea a problemas).
    """
    if raw is None:
        return None
    s = raw.strip().replace("$", "").replace("U$D", "").replace("USD", "")
    s = s.replace(" ", "")
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
# Smoke test rapido (corre con: python src/dominio/normalizadores.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emision = date(2026, 7, 3)
    fallas = 0

    def chequear(etiqueta, got, esperado):
        global fallas
        ok = got == esperado
        fallas += 0 if ok else 1
        print(f"[{'OK ' if ok else 'MAL'}] {etiqueta} = {got}  (esperado {esperado})")

    for raw, esp in [("12/5/2006", date(2006, 5, 12)), ("05/2019", date(2019, 5, 1)),
                     ("05/18", date(2018, 5, 1)), ("2011", date(2011, 7, 1)),
                     ("2 meses", emision - relativedelta(months=2)),
                     ("1 año", emision - relativedelta(years=1)),
                     ("3", emision - relativedelta(years=3)),
                     ("18", emision - relativedelta(years=18)),
                     ("reciente", None), ("-", None), ("n/c", None)]:
        chequear(f"antiguedad({raw!r})", parse_antiguedad(raw, emision), esp)

    print()
    for raw, esp in [("30", (30, False)), ("7", (7, False)), ("90", (90, False)),
                     ("3060", (None, True)), ("150", (None, True)), ("", (None, False))]:
        chequear(f"plazo({raw!r})", parse_plazo(raw), esp)

    print()
    for raw, esp in [("$0", Decimal(0)), ("23,000", Decimal(23000)),
                     ("$ 10044.71", Decimal("10044.71")), ("USD 10044.71", Decimal("10044.71")),
                     ("1", Decimal(1)), ("-", None)]:
        chequear(f"monto({raw!r})", parse_monto(raw), esp)

    print()
    for raw, esp in [("30-70920459-5", True), ("30709204595", True),
                     ("30-70920459-4", False), ("123", False)]:
        chequear(f"cuit_valido({raw!r})", cuit_valido(raw), esp)

    print()
    for raw, esp in [("¿Es cliente?", "es cliente"), ("Condición de venta", "condicion de venta"),
                     ("CT (U$D)", "ct (u$d)"), ("  Antigüedad\n", "antiguedad")]:
        chequear(f"clave_columna({raw!r})", clave_columna(raw), esp)

    print(f"\n{'TODO OK' if fallas == 0 else str(fallas) + ' FALLAS'}")
