"""
Carga el mapeo de la web desde `config/mapeo_web.yaml`.

El punto de todo esto: el cargador sabe NAVEGAR (buscar, entrar, ubicar la fila,
escribir, guardar) pero no sabe EN QUE WEB. Los selectores y las URLs son datos,
no codigo. Apuntar el pipeline a otro sistema es editar un YAML.

Y como una web real tiene varios formularios, el mapeo se organiza por
formulario: cada uno trae su camino de busqueda, sus selectores y su propia
lista blanca de campos escribibles.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

RUTA_DEFAULT = Path("config/mapeo_web.yaml")


@dataclass
class Formulario:
    """Todo lo que hay que saber de la web para completar UN formulario."""

    nombre: str
    url_busqueda: str
    selectores: dict[str, str]
    campos: dict[str, str]      # nombre logico -> selector. Es la LISTA BLANCA.

    def sel(self, nombre: str) -> str:
        try:
            return self.selectores[nombre]
        except KeyError:
            raise KeyError(
                f"al formulario {self.nombre!r} le falta el selector {nombre!r} "
                f"en config/mapeo_web.yaml") from None


@dataclass
class Mapeo:
    base_url: str
    formularios: dict[str, Formulario]
    timeout_ms: int = 5000

    @classmethod
    def cargar(cls, ruta: str | Path = RUTA_DEFAULT) -> "Mapeo":
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
        formularios = {
            nombre: Formulario(nombre=nombre,
                               url_busqueda=bloque["url_busqueda"],
                               selectores=bloque["selectores"],
                               campos=bloque["campos"])
            for nombre, bloque in datos["formularios"].items()
        }
        return cls(base_url=datos["base_url"].rstrip("/"),
                   formularios=formularios,
                   timeout_ms=int(datos.get("timeout_ms", 5000)))

    def formulario(self, nombre: str) -> Formulario:
        try:
            return self.formularios[nombre]
        except KeyError:
            raise KeyError(
                f"no hay un formulario {nombre!r} en config/mapeo_web.yaml. "
                f"Hay: {sorted(self.formularios)}") from None

    def url_busqueda(self, formulario: str, **fmt) -> str:
        return self.base_url + self.formulario(formulario).url_busqueda.format(**fmt)
