"""
Verifica un extractor contra el GROUND TRUTH que dejo el generador.

El generador de datos falsos sabe exactamente que escribio en el archivo, asi
que puede dejar al lado un JSON con lo que un extractor correcto tendria que
devolver. Comparar contra eso es la diferencia entre "parece que anda" y "anda":
un parser puede leer 14 clientes perfecto y comerse una fila del quinceavo, y a
ojo no lo ves nunca.

Uso:
    python -m tests.verificar_extractor data/entrada/lote17.pdf
    python -m tests.verificar_extractor data/entrada/lote17.docx

La verdad se busca sola en `<archivo>.verdad.json`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.extractores import para


def _diferencias(esperado: dict, obtenido: dict, ruta: str = "") -> list[str]:
    """Diferencias legibles entre dos fichas. Devuelve [] si son iguales."""
    difs: list[str] = []

    for k in sorted(set(esperado) | set(obtenido)):
        aca = f"{ruta}.{k}" if ruta else k
        e, o = esperado.get(k, "<falta>"), obtenido.get(k, "<falta>")

        if isinstance(e, dict) and isinstance(o, dict):
            difs += _diferencias(e, o, aca)
        elif isinstance(e, list) and isinstance(o, list):
            if len(e) != len(o):
                difs.append(f"{aca}: {len(e)} filas esperadas, {len(o)} obtenidas")
            for i, (fe, fo) in enumerate(zip(e, o)):
                difs += _diferencias(fe, fo, f"{aca}[{i}]")
        elif e != o:
            difs.append(f"{aca}: esperado {e!r}, obtenido {o!r}")

    return difs


def verificar(archivo: Path) -> int:
    """Devuelve la cantidad de fichas con diferencias (0 = todo bien)."""
    ruta_verdad = archivo.with_suffix(".verdad.json")
    if not ruta_verdad.exists():
        print(f"No encuentro el ground truth: {ruta_verdad}\n"
              f"Generalo con: python demo/generar_pdf_fake.py --salida {archivo}")
        return 1

    esperadas = json.loads(ruta_verdad.read_text(encoding="utf-8"))
    extractor = para(archivo)
    obtenidas = [f.a_dict() for f in extractor.extraer(archivo)]

    print(f"archivo:  {archivo}")
    print(f"extractor: {type(extractor).__name__}")
    print(f"fichas:   {len(esperadas)} esperadas, {len(obtenidas)} obtenidas\n")

    con_fallas = 0
    if len(esperadas) != len(obtenidas):
        print(f"!! CANTIDAD DE FICHAS DISTINTA "
              f"({len(esperadas)} vs {len(obtenidas)})\n")
        con_fallas += 1

    for i, (esp, obt) in enumerate(zip(esperadas, obtenidas), start=1):
        # `origen` (archivo y pagina) no esta en la verdad: depende del render,
        # no del contenido. Se muestra igual, porque sirve para ubicar la falla.
        difs = _diferencias(esp, {k: v for k, v in obt.items() if k != "origen"})
        nombre = esp["cabecera"].get("Cliente", "?")
        if difs:
            con_fallas += 1
            print(f"[MAL] ficha {i:>2} {nombre}   ({obt.get('origen', '')})")
            for d in difs[:8]:
                print(f"         {d}")
            if len(difs) > 8:
                print(f"         ... y {len(difs) - 8} diferencias mas")
        else:
            print(f"[OK ] ficha {i:>2} {nombre}   ({obt.get('origen', '')})")

    total = len(esperadas)
    print(f"\n{total - con_fallas}/{total} fichas identicas al ground truth")
    return con_fallas


if __name__ == "__main__":
    archivo = Path(sys.argv[1] if len(sys.argv) > 1 else "data/entrada/lote17.pdf")
    sys.exit(0 if verificar(archivo) == 0 else 1)
