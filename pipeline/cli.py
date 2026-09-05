"""
La linea de comandos: una etapa, un comando, un archivo de salida.

    python -m pipeline.cli extraer  data/entrada/lote17.pdf
    python -m pipeline.cli revisar  data/salida/lote17.jsonl
    python -m pipeline.cli cargar   data/salida/lote17.jsonl --dry-run

Cada comando lee un archivo y escribe otro. No hay estado escondido entre
etapas: lo que pasa de una a la otra esta en disco y se puede abrir. Eso es lo
que permite cortar en la mitad de un lote de 3000 y retomar sin repetir trabajo,
y tambien lo que permite reemplazar UNA etapa sin tocar las demas.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline import jsonl
from pipeline.dominio.esquema import Cliente
from pipeline.extractores import para


def _reconciliar(clientes: list[Cliente]) -> None:
    """
    El resumen que hay que leer antes de cargar nada.

    No alcanza con "no hubo excepciones": un parser puede terminar contento y
    haberse comido 40 filas. Estos numeros tienen que cerrar contra el documento.
    """
    refs = sum(len(c.referencias) for c in clientes)
    descartadas = sum(c.descartadas for c in clientes)
    alertas = sum(len(c.alertas) for c in clientes)
    con_problemas = [c for c in clientes if c.problemas]
    cuits_malos = [c for c in clientes if not c.cuit_ok]

    print("\nRECONCILIACION")
    print("-" * 52)
    print(f"  clientes                      {len(clientes)}")
    print(f"  referencias a cargar          {refs}")
    print(f"  filas inactivas descartadas   {descartadas}   (exclusion legitima)")
    print(f"  filas de referencia en total  {refs + descartadas}")
    print(f"  alertas leidas                {alertas}")
    print(f"  CUIT invalidos                {len(cuits_malos)}")
    print(f"  clientes con algo dudoso      {len(con_problemas)}")
    print("-" * 52)
    if con_problemas:
        print("  Revisalos en la hoja 'Problemas' antes de cargar:")
        for c in con_problemas[:10]:
            print(f"    {c.cuit}  {c.nombre:<28} {c.problemas[0]}")
        if len(con_problemas) > 10:
            print(f"    ... y {len(con_problemas) - 10} clientes mas")


def cmd_extraer(args) -> int:
    entrada = Path(args.entrada)
    salida = Path(args.salida or f"data/salida/{entrada.stem}.jsonl")

    extractor = para(entrada)
    print(f"extractor: {type(extractor).__name__}  ({entrada})")

    clientes = [Cliente.from_ficha(f) for f in extractor.extraer(entrada)]
    if args.limite:
        clientes = clientes[:args.limite]

    jsonl.escribir(clientes, salida)
    print(f"escrito:   {salida}")
    _reconciliar(clientes)
    return 0


def cmd_revisar(args) -> int:
    from pipeline.vistas import excel

    entrada = Path(args.entrada)
    salida = Path(args.salida or entrada.with_suffix(".xlsx"))
    clientes = list(jsonl.leer(entrada))
    excel.generar(clientes, salida)
    print(f"planilla:  {salida}   ({len(clientes)} clientes)")
    _reconciliar(clientes)
    return 0


def cmd_cargar(args) -> int:
    from pipeline.carga import items as armador
    from pipeline.carga.estado import Estado
    from pipeline.carga.mapeo import Mapeo
    from pipeline.carga.navegador import CargadorNulo, CargadorPlaywright

    clientes = list(jsonl.leer(args.entrada))
    mapeo = Mapeo.cargar(args.mapeo)
    real = not (args.dry_run or args.simular)   # ¿esta corrida escribe de verdad?
    items, conflictos = armador.armar(clientes)

    if args.limite:
        items = items[:args.limite]

    print(f"web:       {mapeo.base_url}")
    print(f"filas:     {len(items)} cargables")
    if conflictos:
        # No se cargan: en la web las dos filas matchean igual y no hay forma
        # de saber cual es cual. Se informan para resolverlos a mano.
        print(f"CONFLICTOS (no se cargan): {len(conflictos)}")
        for c in conflictos:
            print(f"  {c}")

    if args.dry_run:
        print("modo:      DRY-RUN (se llena el formulario y NO se guarda)")
    elif args.simular:
        print("modo:      SIMULADO (no se abre ningun navegador)")
    else:
        print("modo:      CARGA REAL")

    with Estado(args.estado) as estado:
        pendientes = [i for i in items if not estado.ya_cargada(i.clave)]
        salteadas = len(items) - len(pendientes)
        if salteadas:
            print(f"salteadas: {salteadas} ya cargadas en una corrida anterior")

        if args.simular:
            cargador = CargadorNulo(mapeo)
        else:
            cargador = CargadorPlaywright(mapeo, dry_run=args.dry_run,
                                          headless=not args.ver,
                                          lento_ms=args.lento)

        ok = fallidas = 0
        with cargador:
            for n, item in enumerate(pendientes, start=1):
                r = cargador.cargar(item)
                marca = "ok " if r.ok else "MAL"
                print(f"  [{marca}] {n:>4}/{len(pendientes)}  {item.clave}")
                if not r.ok:
                    print(f"          {r.detalle}")
                    fallidas += 1
                else:
                    ok += 1
                # Ni dry-run ni simulado anotan: no escribieron nada en la web.
                # Si anotaran, la corrida real saltearia esas filas creyendo
                # que ya estan cargadas, y quedarian vacias para siempre.
                if real:
                    estado.anotar(r.clave, "ok" if r.ok else "error", r.detalle)

        print(f"\nRESULTADO: {ok} ok, {fallidas} con error, "
              f"{salteadas} salteadas, {len(conflictos)} en conflicto")
        if real:
            print(f"estado:    {args.estado}  {estado.resumen()}")
    return 0 if fallidas == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="pipeline", description="Pipeline de data entry: archivo -> web.")
    sub = ap.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("extraer", help="archivo (PDF/DOCX) -> JSONL validado")
    p.add_argument("entrada")
    p.add_argument("-o", "--salida")
    p.add_argument("--limite", type=int,
                   help="procesar solo los primeros N clientes (para probar en chico)")
    p.set_defaults(func=cmd_extraer)

    p = sub.add_parser("revisar", help="JSONL -> planilla Excel de revision")
    p.add_argument("entrada")
    p.add_argument("-o", "--salida")
    p.set_defaults(func=cmd_revisar)

    p = sub.add_parser("cargar", help="JSONL -> formulario web")
    p.add_argument("entrada")
    p.add_argument("--dry-run", action="store_true",
                   help="llenar el formulario SIN guardar (no anota estado)")
    p.add_argument("--simular", action="store_true",
                   help="no abrir navegador: solo decir que haria")
    p.add_argument("--ver", action="store_true",
                   help="mostrar el navegador en vez de correr headless")
    p.add_argument("--lento", type=int, default=0, metavar="MS",
                   help="frenar cada accion N ms (para grabar o mirar)")
    p.add_argument("--limite", type=int, help="cargar solo las primeras N filas")
    p.add_argument("--mapeo", default="config/mapeo_web.yaml")
    p.add_argument("--estado", default="data/salida/estado_carga.db")
    p.set_defaults(func=cmd_cargar)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
