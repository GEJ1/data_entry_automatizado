"""
Carga el mapeo de la web desde `config/mapeo_web.yaml`.

El punto de todo esto: el cargador sabe NAVEGAR (buscar, entrar, encontrar la
fila, escribir, guardar) pero no sabe EN QUE WEB. Los selectores y las URLs son
datos, no codigo. Apuntar el pipeline a otro sistema es editar un YAML.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

RUTA_DEFAULT = Path("config/mapeo_web.yaml")


@dataclass
class Mapeo:
    base_url: str
    urls: dict[str, str]
    selectores: dict[str, str]
    campos: dict[str, str]      # nombre logico -> selector. Es la LISTA BLANCA.
    timeout_ms: int = 5000

    @classmethod
    def cargar(cls, ruta: str | Path = RUTA_DEFAULT) -> "Mapeo":
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
        return cls(
            base_url=datos["base_url"].rstrip("/"),
            urls=datos["urls"],
            selectores=datos["selectores"],
            campos=datos["campos"],
            timeout_ms=int(datos.get("timeout_ms", 5000)),
        )

    def url(self, nombre: str, **fmt) -> str:
        return self.base_url + self.urls[nombre].format(**fmt)

    def sel(self, nombre: str) -> str:
        return self.selectores[nombre]
