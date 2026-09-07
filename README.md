# data_entry_automatizado

Un esqueleto para automatizar **cualquier** tarea de data entry: leer datos de un
archivo, validarlos y normalizarlos, y cargarlos en un formulario web — sin
escribir basura en el sistema de destino.

El repo trae un caso completo a modo de ejemplo (fichas crediticias), pero **el
dominio es la pieza reemplazable**. Si tu data entry es de facturas, historias
clínicas o altas de usuarios, el andamiaje es el mismo.

> Material educativo. **Todo es falso**: los datos, los documentos y también la
> web de destino, que viene en el repo. Se clona, se instala y corre entero, sin
> credenciales ni acceso a ningún sistema externo.

## El curso

Tres cuadernos. El primero explica el método, el segundo te lo hace construir, y
el tercero lo apunta a tu caso.

| | Cuaderno | Dónde | Qué hacés |
|---|---|---|---|
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GEJ1/data_entry_automatizado/blob/main/01_metodo.ipynb) | [`01_metodo`](01_metodo.ipynb) | Colab | Las tres ideas: costuras, ground truth, defensas |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GEJ1/data_entry_automatizado/blob/main/02_construir.ipynb) | [`02_construir`](02_construir.ipynb) | Colab / local | **Escribís el pipeline vos**, con checkpoints |
| — | [`03_tu_caso`](03_tu_caso.ipynb) | Tu máquina | Lo adaptás a **tu** archivo y **tu** web |

`02` es un taller: cada paso tiene un ejercicio con `# TODO`, un checkpoint que
te dice qué falla, una solución plegada y el prompt para pedirle esa pieza a
Claude.

> ⚠️ **La carga se corre en una terminal, no en el cuaderno.** Es el único
> momento donde ves el navegador llenando los campos en tiempo real.

## La idea

Lo interesante no es el parser: es que **cada pieza se pueda cambiar sola**.
Entre corchetes va el código que se reemplaza; suelto, los datos.

```
      PDF ─┐
           ├──[ Extractor ]──→   FichaCruda        texto crudo, sin interpretar
     DOCX ─┘         ▲
                     └── otro FORMATO: una clase en pipeline/extractores/
                                      │
                                      ▼
                      [ Dominio ]──→   Cliente      tipado y validado
                            ▲
                            └── otro RUBRO: pipeline/dominio/esquema.py
                                      │
                                      ▼
                                  lote.jsonl        fuente de verdad, en disco
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
                   lote.xlsx                   ItemDeCarga
              (revisión humana)                     │
                                                    ▼
                                        [ Cargador ]──→  formulario web
                                              ▲
                                              └── otra WEB: config/mapeo_web.yaml
```

Entre etapa y etapa hay **un archivo en disco**, no una llamada de función: por
eso se puede cortar un lote de 3000 y retomar, y reemplazar una etapa sin tocar
las otras.

Los dos enchufes están definidos en
[`pipeline/contratos.py`](pipeline/contratos.py). Es el archivo por el que
conviene empezar a leer.

## Instalación

Requiere **Python 3.10+**.

```bash
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium      # sólo para la carga web
```

## Correrlo entero

```bash
# 1. generar los documentos de prueba (con once trampas sembradas)
python demo/generar_pdf_fake.py
python demo/generar_docx_fake.py

# 2. verificar el extractor contra el ground truth
python -m tests.verificar_extractor data/entrada/lote17.pdf

# 3. extraer → JSONL, e imprimir la reconciliación
python -m pipeline.cli extraer data/entrada/lote17.pdf

# 4. la planilla de revisión (4 hojas; si "Problemas" está vacía, cargás tranquilo)
python -m pipeline.cli revisar data/salida/lote17.jsonl

# 5. levantar la web de destino, con las filas vacías
python web_demo/sembrar.py data/salida/lote17.jsonl
python web_demo/app.py            # http://127.0.0.1:5000

# 6. cargar — el dry-run llena el formulario y NO guarda
python -m pipeline.cli cargar data/salida/lote17.jsonl --dry-run --limite 3 --ver --lento 400
python -m pipeline.cli cargar data/salida/lote17.jsonl
```

Cortá el paso 6 con Ctrl-C a la mitad y volvé a correrlo: retoma sin duplicar.

## El principio

**Convertir errores silenciosos en ruidosos.** Un dato que se ve bien pero está
mal tiene que delatarse, nunca cargarse a ciegas. De ahí salen la lista blanca
de campos escribibles, el read-back después de guardar, la reconciliación y la
idempotencia.

Y la regla que las abarca a todas: **ante la duda, no cargar.** Si dos filas del
documento son indistinguibles, no se elige "la primera" — se reportan y se dejan
para un humano.

El detalle de cada decisión, con su porqué, está en [`CLAUDE.md`](CLAUDE.md).

## Estructura

```
pipeline/
  contratos.py           # los enchufes: FichaCruda, Extractor, ItemDeCarga, Cargador
  cli.py                 # extraer | revisar | cargar
  jsonl.py               # la costura entre etapas
  dominio/               # normalizadores genéricos + el dominio del EJEMPLO
  extractores/           # PDF y DOCX, intercambiables
  vistas/excel.py        # las cuatro hojas
  carga/                 # Playwright, lista blanca, idempotencia
config/mapeo_web.yaml    # ← lo único que se toca para apuntar a otra web
web_demo/                # la web falsa de destino (Flask + SQLite)
demo/                    # datos falsos, ground truth y reconocimiento de la web
tests/verificar_extractor.py
```
