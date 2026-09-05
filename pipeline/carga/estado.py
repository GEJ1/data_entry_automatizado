"""
Estado de la carga en SQLite: que fila ya se cargo y que fila no.

Es lo que hace la carga IDEMPOTENTE. Un lote de 3000 filas tarda, y se va a
cortar: se cae la red, se vence la sesion, alguien cierra la notebook. Sin
esto, retomar significa empezar de cero y arriesgarse a cargar dos veces.

La clave es `(cliente, solicitud, fecha, informante)`: lo que identifica una
fila en el documento de origen. Deliberadamente NO se usa el id interno de la
web, porque ese recien se conoce despues de navegar hasta la fila; si la clave
dependiera de el, no se podria saber que saltear ANTES de ir a buscarlo.

Estados: 'ok' (cargada y verificada) | 'error' (fallo, con el detalle).
Lo que no figura, esta pendiente.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cargas (
    clave    TEXT PRIMARY KEY,
    estado   TEXT NOT NULL,
    detalle  TEXT DEFAULT '',
    momento  TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Estado:
    """Registro de lo ya cargado. Se abre con `with`."""

    def __init__(self, ruta: str | Path = "data/salida/estado_carga.db"):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.ruta)
        self.con.executescript(ESQUEMA)
        self.con.commit()

    def __enter__(self) -> "Estado":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    def ya_cargada(self, clave: str) -> bool:
        """Solo 'ok' cuenta. Una fila en error se reintenta en la corrida siguiente."""
        fila = self.con.execute(
            "SELECT estado FROM cargas WHERE clave = ?", (clave,)).fetchone()
        return fila is not None and fila[0] == "ok"

    def anotar(self, clave: str, estado: str, detalle: str = "") -> None:
        self.con.execute(
            "INSERT INTO cargas (clave, estado, detalle) VALUES (?, ?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET estado = excluded.estado, "
            "detalle = excluded.detalle, momento = CURRENT_TIMESTAMP",
            (clave, estado, detalle))
        self.con.commit()

    def resumen(self) -> dict[str, int]:
        return dict(self.con.execute(
            "SELECT estado, COUNT(*) FROM cargas GROUP BY estado").fetchall())

    def errores(self) -> list[tuple[str, str]]:
        return self.con.execute(
            "SELECT clave, detalle FROM cargas WHERE estado = 'error'").fetchall()

    def cerrar(self) -> None:
        self.con.close()
