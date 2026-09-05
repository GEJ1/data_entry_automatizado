"""
La COSTURA entre etapas: un cliente por linea, en JSON.

Por que un archivo en el medio y no llamadas entre funciones: porque asi cada
etapa se corre, se corta y se retoma sola, y el resultado intermedio se puede
abrir y mirar. Cuando la carga web falla en el cliente 812, el JSONL ya esta y
no hay que volver a leer el PDF.

Por que JSONL y no un JSON grande: se escribe y se lee de a una linea, asi que
un lote de 5000 clientes no tiene que entrar entero en memoria, y un archivo
cortado a la mitad sigue siendo legible hasta donde llego.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from pipeline.dominio.esquema import Cliente


def escribir(clientes: Iterable[Cliente], salida: str | Path) -> Path:
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8") as f:
        for c in clientes:
            f.write(c.model_dump_json() + "\n")
    return salida


def leer(entrada: str | Path) -> Iterator[Cliente]:
    with Path(entrada).open(encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                yield Cliente.model_validate_json(linea)


def leer_crudo(entrada: str | Path) -> list[dict]:
    """Las lineas sin validar. Util para inspeccionar un JSONL sospechoso."""
    return [json.loads(l) for l in Path(entrada).read_text(encoding="utf-8").splitlines() if l.strip()]
