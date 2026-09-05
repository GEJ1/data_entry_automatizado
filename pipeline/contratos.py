"""
Los CONTRATOS del pipeline: las piezas que se enchufan y se reemplazan.

Este archivo es el corazon de la modularidad. No hace nada: solo define
la forma que tienen que tener las piezas para encajar. Si queres procesar
otro formato de archivo, o cargar en otra web, no toques el resto del
pipeline: escribi una pieza nueva que cumpla el contrato de aca.

Hay dos puntos de enchufe, uno en cada punta:

    archivo --[Extractor]--> FichaCruda --> (dominio) --> ItemDeCarga --[Cargador]--> web

Regla de oro: el Extractor NO sabe de negocio. No sabe que es un CUIT ni
que es la antiguedad. Solo sabe abrir un archivo y devolver texto puesto
en cabeceras y tablas. Toda la interpretacion vive en `dominio/`.
Gracias a eso, un extractor de DOCX es intercambiable con uno de PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

# Una fila de tabla tal como sale del archivo: encabezado -> texto crudo.
# TODO string, sin convertir. Convertir es tarea del dominio.
Fila = dict[str, str]


@dataclass
class FichaCruda:
    """
    Una unidad del documento (aca: un cliente) ya separada del resto, pero
    SIN interpretar. Es lo unico que un Extractor tiene que saber producir.

    cabecera: los datos sueltos de arriba de la ficha.
              ej: {"Cliente": "AIR COMPUTER SA", "CUIT": "30709204595",
                   "Fecha de Emision": "03/07/2026"}
    tablas:   las tablas de la ficha, por nombre de seccion.
              ej: {"referencias": [ {...}, {...} ], "alertas": []}
              Las claves de cada Fila son los encabezados de columna
              tal cual aparecen en el documento.
    origen:   de donde salio, para poder rastrear un dato hasta su fuente
              cuando algo no cierra. ej: "lote17.pdf p.9-10"
    """
    cabecera: dict[str, str] = field(default_factory=dict)
    tablas: dict[str, list[Fila]] = field(default_factory=dict)
    origen: str = ""

    def tabla(self, nombre: str) -> list[Fila]:
        """Las filas de una seccion. Seccion ausente y seccion vacia son lo mismo."""
        return self.tablas.get(nombre, [])

    def a_dict(self) -> dict:
        """Para serializar a JSONL (la costura entre etapa 1 y etapa 2)."""
        return {"cabecera": self.cabecera, "tablas": self.tablas, "origen": self.origen}

    @classmethod
    def de_dict(cls, d: dict) -> "FichaCruda":
        return cls(cabecera=d.get("cabecera", {}),
                   tablas=d.get("tablas", {}),
                   origen=d.get("origen", ""))


@runtime_checkable
class Extractor(Protocol):
    """
    ENCHUFE 1: leer un archivo y escupir fichas crudas.

    Para soportar un formato nuevo alcanza con una clase que tenga estos
    dos atributos. Ver `extractores/pdf_plumber.py` y `extractores/docx_.py`:
    hacen cosas muy distintas por dentro y son intercambiables por fuera.
    """
    formatos: tuple[str, ...]   # extensiones que maneja, ej: (".pdf",)

    def extraer(self, ruta: Path) -> Iterator[FichaCruda]:
        """
        Devuelve las fichas de a una (generador). Es a proposito: un lote
        de 3000 clientes no tiene por que entrar entero en memoria.
        """
        ...


@dataclass
class ItemDeCarga:
    """
    ENCHUFE 2 (entrada): una fila lista para escribir en la web.

    Deliberadamente NO contiene objetos del dominio: solo strings ya
    formateados como el formulario los espera. El Cargador es tonto y
    no decide nada; si tuviera que decidir, el error aparece recien
    frente al navegador, que es el peor lugar para descubrirlo.

    formulario: a que formulario de la web va esta fila. Una web real tiene
              varios, y cada uno se llega por un camino distinto. El nombre
              indexa el bloque correspondiente de config/mapeo_web.yaml.
    clave:    identifica la fila de forma unica y estable. Es la base de la
              idempotencia: si esta clave ya figura OK en el estado, se saltea.
              Arranca con el nombre del formulario, para que dos formularios
              distintos no puedan pisarse la clave entre si.
    busqueda: como encontrar la fila en la web (ej: {"cuit": "...",
              "fecha": "09/01/2025", "informante": "AIR COMPUTER"}).
    campos:   que escribir, nombre logico -> valor ya como string.
              Los nombres logicos se traducen a selectores via config/mapeo_web.yaml.
    """
    formulario: str
    clave: str
    busqueda: dict[str, str]
    campos: dict[str, str]


@dataclass
class Resultado:
    """Que paso con un ItemDeCarga. `ok=False` no corta el lote: se anota y sigue."""
    clave: str
    ok: bool
    detalle: str = ""


@runtime_checkable
class Cargador(Protocol):
    """
    ENCHUFE 2 (salida): escribir un item donde sea.

    Implementaciones previstas:
      * CargadorPlaywright -> la web de verdad (o la web_demo)
      * CargadorDryRun     -> llena el formulario y NO guarda (ensayo)
      * CargadorNulo       -> no abre nada, solo loguea (para testear el resto)
    """
    def __enter__(self) -> "Cargador": ...
    def __exit__(self, *exc) -> None: ...

    def cargar(self, item: ItemDeCarga) -> Resultado:
        """Escribe UN item. Nunca lanza por un dato malo: devuelve Resultado(ok=False)."""
        ...
