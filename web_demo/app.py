"""
La WEB FALSA: el formulario donde termina el pipeline.

No es un mock ni un stub: es una web de verdad, con su base SQLite, su buscador
y su formulario de edicion. Existe para que la etapa de carga se pueda escribir,
correr y romper sin depender de ningun sistema real, sin credenciales y sin
riesgo de escribir donde no va.

Esta hecha para reproducir la parte incomoda del problema, no para ser linda.
En particular, el ID de la fila a editar NO se puede calcular: hay que buscar
por CUIT, entrar a la solicitud y cosechar el href del lapiz. Igual que en una
web real, donde los ids son internos y no estan en el documento de origen.

    /                                                  buscador por CUIT
    /admin/buscar?cuit=...                             solicitudes y alertas del cliente
    /admin/solicitudes/<sid>                           tabla de filas financieras
    /admin/solicitudes/<sid>/financieras/<fid>/edit    formulario de referencias
    /admin/clientes/<cuit>/alertas                     tabla de alertas
    /admin/clientes/<cuit>/alertas/<aid>/edit          formulario de alertas

Hay DOS formularios a proposito, y se llega a ellos por caminos distintos: las
filas financieras cuelgan de una solicitud, las alertas cuelgan del cliente. Es
lo que obliga a que el cargador trate la navegacion como configuracion en vez de
tenerla hardcodeada.

Cada formulario incluye A PROPOSITO campos que NO hay que tocar (Monto Asegurado,
Seguro y Doc en referencias; el numero de expediente en alertas). Estan ahi para
que la lista blanca del cargador sea una defensa real y no un comentario: si el
cargador se equivoca, se ve.

Uso:
    python web_demo/sembrar.py data/salida/lote17.jsonl
    python web_demo/app.py            # http://127.0.0.1:5000
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for

BASE = Path(__file__).resolve().parent
DB = BASE / "datos.db"

# Las columnas que cada formulario deja editar. La lista blanca del cargador
# tiene que ser un subconjunto de esta: si no coinciden, algo se desincronizo.
CAMPOS_EDITABLES = ["condicion", "credito_otorgado", "credito_tomado",
                    "otorgado_usd", "tomado_usd", "antiguedad"]
CAMPOS_EDITABLES_ALERTA = ["tipo", "estado", "monto", "comentarios"]

# Campos que se muestran y se guardan, pero que el pipeline NUNCA debe tocar.
CAMPOS_PROHIBIDOS = ["monto_asegurado", "seguro", "doc"]
CAMPOS_PROHIBIDOS_ALERTA = ["expediente"]

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = conectar()
    return g.db


@app.teardown_appcontext
def cerrar_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


ESQUEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    cuit    TEXT PRIMARY KEY,
    nombre  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS solicitudes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    cuit    TEXT NOT NULL REFERENCES clientes(cuit),
    titulo  TEXT NOT NULL           -- "Solicitud hecha el 09/01/2025 por FREE"
);
CREATE TABLE IF NOT EXISTS financieras (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    solicitud_id      INTEGER NOT NULL REFERENCES solicitudes(id),
    fecha             TEXT NOT NULL,     -- identifica la fila, no se edita
    informante        TEXT NOT NULL,     -- identifica la fila, no se edita
    concepto          TEXT DEFAULT '',
    -- editables por el pipeline
    condicion         TEXT DEFAULT '',
    credito_otorgado  TEXT DEFAULT '',
    credito_tomado    TEXT DEFAULT '',
    otorgado_usd      TEXT DEFAULT '',
    tomado_usd        TEXT DEFAULT '',
    antiguedad        TEXT DEFAULT '',
    -- NUNCA los toca el pipeline
    monto_asegurado   TEXT DEFAULT '',
    seguro            TEXT DEFAULT '',
    doc               TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS alertas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cuit         TEXT NOT NULL REFERENCES clientes(cuit),
    fecha        TEXT NOT NULL,      -- identifica la fila, no se edita
    alertante    TEXT NOT NULL,      -- identifica la fila, no se edita
    -- editables por el pipeline
    tipo         TEXT DEFAULT '',
    estado       TEXT DEFAULT '',
    monto        TEXT DEFAULT '',
    comentarios  TEXT DEFAULT '',
    -- NUNCA lo toca el pipeline: es del sistema legal
    expediente   TEXT DEFAULT ''
);
"""


def crear_esquema() -> None:
    con = conectar()
    con.executescript(ESQUEMA)
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    return render_template("buscar.html", cuit="", cliente=None, solicitudes=None)


@app.route("/admin/buscar")
def buscar():
    """
    Buscador por CUIT. La URL SI es templateable, pero lo que devuelve son
    solicitudes con ids internos: de aca en mas hay que navegar, no calcular.
    """
    cuit = (request.args.get("cuit") or "").strip()
    db = get_db()
    cliente = db.execute("SELECT * FROM clientes WHERE cuit = ?", (cuit,)).fetchone()
    solicitudes, n_alertas = [], 0
    if cliente:
        solicitudes = db.execute(
            "SELECT * FROM solicitudes WHERE cuit = ? ORDER BY id", (cuit,)).fetchall()
        n_alertas = db.execute(
            "SELECT COUNT(*) FROM alertas WHERE cuit = ?", (cuit,)).fetchone()[0]
    return render_template("buscar.html", cuit=cuit, cliente=cliente,
                           solicitudes=solicitudes, n_alertas=n_alertas)


@app.route("/admin/solicitudes/<int:sid>")
def solicitud(sid: int):
    db = get_db()
    sol = db.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    if sol is None:
        return "Solicitud inexistente", 404
    cliente = db.execute("SELECT * FROM clientes WHERE cuit = ?", (sol["cuit"],)).fetchone()
    filas = db.execute(
        "SELECT * FROM financieras WHERE solicitud_id = ? ORDER BY id", (sid,)).fetchall()
    return render_template("solicitud.html", sol=sol, cliente=cliente, filas=filas)


@app.route("/admin/solicitudes/<int:sid>/financieras/<int:fid>/edit",
           methods=["GET", "POST"])
def editar(sid: int, fid: int):
    db = get_db()
    fila = db.execute(
        "SELECT * FROM financieras WHERE id = ? AND solicitud_id = ?",
        (fid, sid)).fetchone()
    if fila is None:
        return "Fila inexistente", 404

    if request.method == "POST":
        campos = CAMPOS_EDITABLES + CAMPOS_PROHIBIDOS
        valores = [request.form.get(c, "") for c in campos]
        db.execute(f"UPDATE financieras SET {', '.join(c + ' = ?' for c in campos)} "
                   f"WHERE id = ?", (*valores, fid))
        db.commit()
        return redirect(url_for("solicitud", sid=sid) + f"?guardada={fid}")

    sol = db.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    cliente = db.execute("SELECT * FROM clientes WHERE cuit = ?", (sol["cuit"],)).fetchone()
    return render_template("editar.html", fila=fila, sol=sol, cliente=cliente,
                           editables=CAMPOS_EDITABLES, prohibidos=CAMPOS_PROHIBIDOS)


@app.route("/admin/clientes/<cuit>/alertas")
def alertas(cuit: str):
    db = get_db()
    cliente = db.execute("SELECT * FROM clientes WHERE cuit = ?", (cuit,)).fetchone()
    if cliente is None:
        return "Cliente inexistente", 404
    filas = db.execute(
        "SELECT * FROM alertas WHERE cuit = ? ORDER BY id", (cuit,)).fetchall()
    return render_template("alertas.html", cliente=cliente, filas=filas)


@app.route("/admin/clientes/<cuit>/alertas/<int:aid>/edit", methods=["GET", "POST"])
def editar_alerta(cuit: str, aid: int):
    db = get_db()
    fila = db.execute("SELECT * FROM alertas WHERE id = ? AND cuit = ?",
                      (aid, cuit)).fetchone()
    if fila is None:
        return "Alerta inexistente", 404

    if request.method == "POST":
        campos = CAMPOS_EDITABLES_ALERTA + CAMPOS_PROHIBIDOS_ALERTA
        valores = [request.form.get(c, "") for c in campos]
        db.execute(f"UPDATE alertas SET {', '.join(c + ' = ?' for c in campos)} "
                   f"WHERE id = ?", (*valores, aid))
        db.commit()
        return redirect(url_for("alertas", cuit=cuit) + f"?guardada={aid}")

    cliente = db.execute("SELECT * FROM clientes WHERE cuit = ?", (cuit,)).fetchone()
    return render_template("editar_alerta.html", fila=fila, cliente=cliente,
                           editables=CAMPOS_EDITABLES_ALERTA,
                           prohibidos=CAMPOS_PROHIBIDOS_ALERTA)


if __name__ == "__main__":
    crear_esquema()
    app.run(debug=True, port=5000)
