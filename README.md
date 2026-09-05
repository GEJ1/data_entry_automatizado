# data_entry_automatizado

Un esqueleto para automatizar **cualquier** tarea de data entry: leer datos de
un archivo, **validarlos y normalizarlos**, y **cargarlos en un formulario web**,
fila por fila, de forma confiable y repetible.

El repo trae un caso completo de punta a punta a modo de ejemplo (fichas
crediticias de clientes: referencias comerciales y alertas), pero **el dominio
es la pieza reemplazable**, no el punto. Si tu data entry es de facturas, de
historias clínicas, de inventario o de altas de usuarios, el andamiaje es el
mismo: cambia un archivo.

> Material educativo. **Todo es falso**: los datos, los documentos de entrada y
> también la web de destino, que viene incluida en el repo (`web_demo/`). No hay
> datos reales ni credenciales, y no hace falta acceso a ningún sistema externo:
> se clona, se instala y corre entero de punta a punta.

## La idea

Lo interesante no es el parser: es que **cada pieza se pueda cambiar sola**.

```
archivo ──[Extractor]──> FichaCruda ──> Cliente ──> ItemDeCarga ──[Cargador]──> web
  PDF                    (texto crudo)  (validado)   (qué escribir)             form
  DOCX
```

- ¿Tenés otro **formato de entrada**? Escribí una clase en
  `pipeline/extractores/` que cumpla el contrato y agregala al registro. El
  resto del pipeline no se entera. Vienen dos (PDF y DOCX) justamente para
  demostrarlo: producen exactamente el mismo resultado.
- ¿Tenés otra **web de destino**? Editá `config/mapeo_web.yaml`. Cero código.
- ¿Tenés **otro dominio**? Reescribí `pipeline/dominio/esquema.py` (qué entidades
  hay y cómo se llaman las columnas). Los normalizadores de al lado —fechas,
  montos, identificadores, texto sucio— sobreviven casi intactos, porque el
  data entry siempre pelea contra los mismos problemas.

Los dos enchufes están definidos en [`pipeline/contratos.py`](pipeline/contratos.py).
Es el archivo por el que conviene empezar a leer.

## Instalación

Requiere **Python 3.10 o superior**.

```bash
python3.10 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # sólo para la etapa de carga web
```

Todo se corre desde la raíz del repo.

## Recorrido completo

### 1. Generar los documentos de prueba

Con las mismas trampas sembradas a propósito, en dos formatos:

```bash
python demo/generar_pdf_fake.py                  # data/entrada/lote17.pdf
python demo/generar_docx_fake.py                 # data/entrada/lote17.docx
python demo/generar_pdf_fake.py --clientes 300   # escalar el volumen
```

Cada uno imprime un **manifiesto** (qué cliente muestra qué trampa: antigüedad
en todas sus formas, plazo basura, CUIT inválido, secciones vacías, cliente que
se derrama a varias páginas, filas duplicadas…) y deja al lado un
`lote17.verdad.json`: el **ground truth**, o sea exactamente lo que un extractor
correcto debería devolver.

### 2. Verificar el extractor contra el ground truth

```bash
python -m tests.verificar_extractor data/entrada/lote17.pdf
python -m tests.verificar_extractor data/entrada/lote17.docx
```

Esto es lo que reemplaza a "mirar las columnas a ojo": un parser puede leer 299
clientes perfecto y comerse una fila del trescientos, y a ojo no se ve nunca.

### 3. Extraer → JSONL

```bash
python -m pipeline.cli extraer data/entrada/lote17.pdf
```

Escribe `data/salida/lote17.jsonl` (un cliente por línea, ya validado) e imprime
una **reconciliación**: cuántos clientes, cuántas filas, cuántas se descartaron
por inactivas y qué quedó dudoso. Los números tienen que cerrar contra el
documento; que no haya habido excepciones no alcanza.

### 4. Revisar en Excel

```bash
python -m pipeline.cli revisar data/salida/lote17.jsonl
```

Tres hojas, tres preguntas: **Resumen** (¿está todo el mundo?), **Detalle**
(¿este dato quedó bien?) y **Problemas** (¿qué tengo que mirar?). Si la hoja
Problemas está vacía, se puede cargar tranquilo.

> El Excel es una vista **derivada**. Las correcciones no vuelven editando el
> Excel: se corrige la regla en el código y se re-corre.

### 5. Levantar la web falsa y sembrarla

```bash
python web_demo/sembrar.py data/salida/lote17.jsonl
python web_demo/app.py            # http://127.0.0.1:5000
```

Las filas se siembran **vacías**, que es la situación real: ya existen en el
sistema y lo que falta es completarles los datos financieros a mano.

### 6. Cargar

```bash
python -m pipeline.cli cargar data/salida/lote17.jsonl --simular          # sin navegador
python -m pipeline.cli cargar data/salida/lote17.jsonl --dry-run --limite 3
python -m pipeline.cli cargar data/salida/lote17.jsonl --ver --lento 300  # mirándolo
python -m pipeline.cli cargar data/salida/lote17.jsonl                    # de verdad
```

Cortala a la mitad con Ctrl-C y volvé a correrla: retoma donde iba, sin duplicar.

## Las defensas

El principio del proyecto es **convertir errores silenciosos en ruidosos**. Un
dato que "se ve bien pero está mal" tiene que delatarse.

- **Lista blanca de campos.** Sólo se escriben los seis campos declarados en el
  YAML. La web tiene además Monto Asegurado, Seguro y Doc, que se pisarían sin
  ruido. Un campo fuera de la lista **aborta la fila** sin tocar la web.
- **Nada más se movió.** El cargador fotografía *todos* los inputs del
  formulario antes y después de guardar. Si cambió algo fuera de la lista
  blanca, la fila se reporta como error aunque el guardado haya funcionado. Así
  la lista blanca es una defensa verificada, no un comentario.
- **Read-back.** Después de guardar se reabre el formulario y se compara. Que el
  submit no explote no significa que el dato entró.
- **Idempotencia.** Estado por fila en SQLite con clave
  `(cliente, solicitud, fecha, informante)`. `--dry-run` y `--simular` no anotan
  nada, justamente para que la corrida real no saltee filas vacías.
- **Ante la duda, no cargar.** Si dos filas del documento comparten clave, en la
  web las dos matchean igual: elegir "la primera" escribiría en la fila
  equivocada. Se informan como conflicto y no se cargan.
- **Los campos en None no se escriben.** Mandar `""` pisaría con vacío un dato
  que quizá ya estaba bien.

## Estructura

```
pipeline/
  contratos.py           # los enchufes: FichaCruda, Extractor, ItemDeCarga, Cargador
  cli.py                 # extraer | revisar | cargar
  jsonl.py               # la costura entre etapas
  dominio/
    normalizadores.py    # genérico: fechas, montos, identificadores, texto sucio
    esquema.py           # <- el dominio del EJEMPLO: Cliente / Referencia / Alerta
  extractores/
    comun.py             # lo que comparten todos los formatos
    pdf_plumber.py       # PDF
    docx_.py             # DOCX
  vistas/excel.py        # las tres hojas
  carga/
    mapeo.py             # lee config/mapeo_web.yaml
    items.py             # Cliente -> qué escribir, con qué clave
    navegador.py         # Playwright + las defensas
    estado.py            # idempotencia en SQLite
config/mapeo_web.yaml    # <- lo único que se toca para apuntar a otra web
web_demo/                # la web falsa de destino (Flask + SQLite)
demo/
  datos_fake.py          # los datos y el ground truth
  generar_pdf_fake.py    # render PDF
  generar_docx_fake.py   # render DOCX
tests/verificar_extractor.py
```

## Documentación

Las decisiones de diseño, las reglas del dominio de ejemplo y las trampas de
cada formato están en [`CLAUDE.md`](CLAUDE.md).
