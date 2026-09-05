# Carga de Solicitudes Financieras

Pipeline para automatizar una tarea de data entry: leer un PDF con datos de
muchos clientes, **validar y normalizar** esa información, y **cargarla en un
formulario web**, fila por fila, de forma confiable y repetible.

> Proyecto en construcción, pensado también como ejemplo educativo. Los datos de
> demostración son 100% inventados. **No hay datos reales ni credenciales en este
> repositorio.**

## Qué hace

El flujo tiene cuatro etapas:

1. **Extracción**: lee el PDF (una ficha por cliente, con dos sub-tablas) y arma
   registros estructurados.
2. **Validación y normalización**: verifica y limpia cada dato (fechas, montos,
   CUIT, antigüedad, plazo). Lo dudoso se separa para revisión humana en vez de
   cargarse a ciegas.
3. **Revisión**: se genera una vista en Excel para controlar antes de cargar.
4. **Carga web**: completa el formulario con Playwright, de forma idempotente
   (se puede cortar y retomar sin duplicar).

El diseño completo, con el porqué de cada decisión, está en
[`docs/Documento_de_diseño.docx`](docs/Documento_de_diseño.docx).

## Estructura del repo

```
.
├── src/
│   └── esquema.py            # Validación y normalización (Pydantic). Núcleo del pipeline.
├── demo/
│   └── generar_pdf_fake.py   # Genera PDFs de prueba con casos difíciles sembrados.
├── docs/
│   ├── Documento_de_diseño.docx  # Diseño completo del sistema.
│   └── Manual_de_uso.docx        # Manual para la persona que opere el sistema.
├── data/
│   ├── entrada/              # Poné acá los PDF a procesar (vacío en el repo).
│   └── salida/              # Acá se generan las planillas y reportes.
├── requirements.txt
└── README.md
```

## Requisitos

- Python 3.10 o superior.

## Instalación

```bash
git clone <URL-de-tu-repo>
cd carga-solicitudes-financieras

# Entorno virtual (recomendado)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Uso

### 1. Generar PDFs de prueba

Crea un PDF falso con la misma estructura que los reales y con los casos difíciles
sembrados a propósito (útil para desarrollar y para el video):

```bash
python demo/generar_pdf_fake.py                       # 15 clientes
python demo/generar_pdf_fake.py --clientes 300        # escala el volumen
python demo/generar_pdf_fake.py --salida data/entrada/lote.pdf
```

Al correr imprime un **manifiesto** que indica qué cliente muestra qué caso
(antigüedad en todas sus formas, plazo basura, CUIT inválido, secciones vacías,
cliente que se derrama a varias páginas, etc.). La salida es reproducible
(semilla fija).

### 2. Validación y normalización

El módulo [`src/esquema.py`](src/esquema.py) define los modelos y las reglas de
limpieza. Correrlo directamente ejecuta una batería de pruebas rápidas:

```bash
python src/esquema.py
```

Para usarlo desde otro código:

```python
from esquema import parse_antiguedad, parse_plazo, Cliente
from datetime import date

parse_antiguedad("2 meses", emision=date(2026, 7, 3))  # -> date(2026, 5, 3)
parse_plazo("3060")                                     # -> (None, True)  (a revisar)
```

## Estado del proyecto

| Etapa | Estado |
|---|---|
| Validación y normalización (`esquema.py`) | Listo y probado |
| Generador de PDFs de prueba | Listo y probado |
| Parser del PDF (extracción) | Pendiente |
| Carga web (Playwright) | Pendiente |

La etapa de carga web depende de resolver una pieza de diseño (cómo se llega
desde el CUIT a la solicitud en la web). Ver la sección "Lo que falta definir"
en el documento de diseño.

## Documentación

- **Diseño del sistema**: [`docs/Documento_de_diseño.docx`](docs/Documento_de_diseño.docx)
- **Manual de uso** (para el operador): [`docs/Manual_de_uso.docx`](docs/Manual_de_uso.docx)
