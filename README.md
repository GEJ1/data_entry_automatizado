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

## El curso

Tres cuadernos. El primero explica el método, el segundo te lo hace construir, y
el tercero lo apunta a tu caso.

| | Cuaderno | Dónde corre | Qué hacés |
|---|---|---|---|
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GEJ1/data_entry_automatizado/blob/main/01_metodo.ipynb) | [`01_metodo`](01_metodo.ipynb) | Colab | Entendés las tres ideas: costuras, ground truth, defensas |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GEJ1/data_entry_automatizado/blob/main/02_construir.ipynb) | [`02_construir`](02_construir.ipynb) | Colab / local | **Escribís el pipeline vos**, con checkpoints que te corrigen |
| — | [`03_tu_caso`](03_tu_caso.ipynb) | Tu máquina | Lo adaptás a **tu** archivo y **tu** web |

`02` es un taller, no una lectura: cada paso tiene un ejercicio con `# TODO`, un
checkpoint que te dice qué falla, una solución plegada por si te trabás, y el
prompt concreto para pedirle esa pieza a Claude.

> ⚠️ **La etapa de carga se corre en una terminal, no en el cuaderno.** Es a
> propósito: es el único momento donde ves el navegador llenando los campos en
> tiempo real, y eso una celda no lo puede mostrar.

## La idea

Lo interesante no es el parser: es que **cada pieza se pueda cambiar sola**.

En el diagrama, lo que está `[ entre corchetes ]` es **código** —las piezas que
se reemplazan— y lo que está suelto son **datos**: la misma información cambiando
de forma. Cada flecha es un punto donde cambia de quién es la responsabilidad.

```
      PDF ─┐
           ├──[ Extractor ]──→   FichaCruda        texto crudo, sin interpretar
     DOCX ─┘         ▲                             (cabecera + tablas de strings)
                     │
                     └── otro FORMATO se enchufa acá: una clase en pipeline/extractores/

                                      │
                                      ▼
                      [ Dominio ]──→   Cliente      ya tipado y validado
                            ▲                       (date, Decimal, int, y los problemas)
                            │
                            └── otro RUBRO se enchufa acá: pipeline/dominio/esquema.py

                                      │
                                      ▼
                                  lote.jsonl        fuente de verdad, en disco
                                      │             (se puede cortar y retomar acá)
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
                   lote.xlsx                   ItemDeCarga    qué escribir, y con qué clave
          resumen / detalle / problemas             │
              (revisión humana)                     ▼
                                        [ Cargador ]──→  formulario web
                                              ▲
                                              └── otra WEB se enchufa acá:
                                                  config/mapeo_web.yaml
```

Cada etapa es un comando que lee un archivo y escribe otro:

```
python -m pipeline.cli extraer   lote.pdf      →  lote.jsonl
python -m pipeline.cli revisar   lote.jsonl    →  lote.xlsx
python -m pipeline.cli cargar    lote.jsonl    →  la web
```

### El mismo dato, en cada forma

Una fila del PDF (una referencia comercial), atravesando el pipeline:

| | Antigüedad | Crédito otorgado | Plazo |
|---|---|---|---|
| **FichaCruda** (texto crudo) | `'12/5/2006'` | `'1'` | `'30'` |
| **Cliente** (validado) | `date(2006, 5, 12)` | `Decimal('1')` | `30` |
| **ItemDeCarga** (a escribir) | `'12/05/2006'` | `'1'` | *no se carga* |

El plazo se extrae y se valida, pero no aparece en el `ItemDeCarga`: el
formulario de destino no tiene ese campo, así que no está en la lista blanca.
Un dato puede ser perfectamente válido y aun así no corresponder que se escriba.

Que vuelva a ser texto al final no es un rodeo: **ese viaje de ida y vuelta es lo
que lo normaliza**. Fijate que `12/5/2006` salió como `12/05/2006`. Y es lo único
que hace posible el caso `"2 meses"`, que sin pasar por `date` no hay manera de
convertir en una fecha concreta.

La otra razón es que el cargador es tonto a propósito: recibe strings y los
escribe. Si tuviera que decidir cómo formatear una fecha, ese error aparecería
recién frente al navegador, que es el peor lugar para descubrirlo.

### Los tres puntos de reemplazo

- ¿Tenés otro **formato de entrada**? Escribí una clase en
  `pipeline/extractores/` que cumpla el contrato y agregala al registro. El
  resto del pipeline no se entera. Vienen dos (PDF y DOCX) justamente para
  demostrarlo: producen exactamente el mismo resultado.
- ¿Tenés otra **web de destino**? Editá `config/mapeo_web.yaml`. Cero código.
- ¿La web tiene **varios formularios**? Ya son dos (referencias y alertas), y se
  llega a ellos por caminos distintos. Lo único que se duplica es la navegación;
  las defensas están escritas una sola vez.
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

Cuatro hojas, cuatro preguntas: **Resumen** (¿está todo el mundo?), **Detalle**
(¿este dato quedó bien?), **Alertas** (¿y los antecedentes?) y **Problemas**
(¿qué tengo que mirar?). Si la hoja Problemas está vacía, se puede cargar
tranquilo.

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
  vistas/excel.py        # las cuatro hojas
  carga/
    mapeo.py             # lee config/mapeo_web.yaml
    items.py             # Cliente -> qué escribir, con qué clave
    navegador.py         # Playwright + las defensas
    estado.py            # idempotencia en SQLite
config/mapeo_web.yaml    # <- lo único que se toca para apuntar a otra web
                         #    (un bloque por formulario de destino)
web_demo/                # la web falsa de destino (Flask + SQLite, 2 formularios)
demo/
  datos_fake.py          # los datos y el ground truth
  generar_pdf_fake.py    # render PDF
  generar_docx_fake.py   # render DOCX
  captura.py             # screenshot de la web (lo usa el cuaderno)
  reconocer_web.py       # lee una página y arma el borrador del mapeo
tests/verificar_extractor.py
01_metodo.ipynb          # el método
02_construir.ipynb       # el taller: lo construís vos
03_tu_caso.ipynb         # adaptarlo a lo tuyo
```

## Documentación

Las decisiones de diseño, las reglas del dominio de ejemplo y las trampas de
cada formato están en [`CLAUDE.md`](CLAUDE.md).
