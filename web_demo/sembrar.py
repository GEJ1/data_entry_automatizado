"""
Siembra la web demo con los clientes del JSONL, PERO CON LOS CAMPOS VACIOS.

Esa es justamente la situacion real: las filas ya existen en el sistema (alguien
cargo la solicitud), y lo que falta es completarles los datos financieros a mano,
uno por uno. El pipeline viene a hacer exactamente ese trabajo.

Lo que se siembra: cliente, solicitud y una fila financiera por referencia, mas
una fila de alerta por alerta. En las dos, solo lo que IDENTIFICA la fila
(fecha + quien la informo) y el resto en blanco. Tambien se inventan valores
para los campos prohibidos —poliza en referencias, expediente en alertas— asi
se nota si el cargador los pisa.

Uso:
    python web_demo/sembrar.py data/salida/lote17.jsonl
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import jsonl                       # noqa: E402
from web_demo.app import DB, conectar, crear_esquema   # noqa: E402

random.seed(17)


def sembrar(ruta_jsonl: str | Path) -> None:
    if DB.exists():
        DB.unlink()          # sembrar es siempre desde cero: la demo se reinicia
    crear_esquema()

    con = conectar()
    clientes = solicitudes = filas = alertas = 0

    for c in jsonl.leer(ruta_jsonl):
        con.execute("INSERT OR REPLACE INTO clientes (cuit, nombre) VALUES (?, ?)",
                    (c.cuit, c.nombre))
        clientes += 1

        # Una solicitud por titulo distinto, en el orden en que aparecen.
        ids: dict[str, int] = {}
        for r in c.referencias:
            if r.solicitud not in ids:
                cur = con.execute(
                    "INSERT INTO solicitudes (cuit, titulo) VALUES (?, ?)",
                    (c.cuit, r.solicitud))
                ids[r.solicitud] = cur.lastrowid
                solicitudes += 1

            con.execute(
                "INSERT INTO financieras (solicitud_id, fecha, informante, concepto,"
                " monto_asegurado, seguro, doc) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ids[r.solicitud],
                 r.fecha.strftime("%d/%m/%Y") if r.fecha else "",
                 r.informante, r.concepto,
                 # valores de poliza preexistentes: si el cargador los pisa, se ve
                 f"{random.randint(50, 900)}.000", random.choice(["SI", "NO"]),
                 random.choice(["A-1", "B-2", "C-3"])))
            filas += 1

        for a in c.alertas:
            con.execute(
                "INSERT INTO alertas (cuit, fecha, alertante, expediente)"
                " VALUES (?, ?, ?, ?)",
                (c.cuit,
                 a.fecha.strftime("%d/%m/%Y") if a.fecha else "",
                 a.alertante,
                 # expediente preexistente: si el cargador lo pisa, se ve
                 f"EXP-{random.randint(1000, 9999)}/{random.randint(18, 26)}"))
            alertas += 1

    con.commit()
    con.close()
    print(f"sembrado en {DB}")
    print(f"  clientes     {clientes}")
    print(f"  solicitudes  {solicitudes}")
    print(f"  filas financieras a completar  {filas}")
    print(f"  alertas a completar            {alertas}")


if __name__ == "__main__":
    sembrar(sys.argv[1] if len(sys.argv) > 1 else "data/salida/lote17.jsonl")
