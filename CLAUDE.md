# Proyecto: data_entry_automatizado

Esqueleto genérico de data entry: archivo (PDF/DOCX) → validación/normalización
→ revisión en Excel → carga en un formulario web. **Es material para un curso**:
todo es falso (los datos, los documentos y también la web objetivo, que vive en
`web_demo/`). Este archivo prioriza decisiones y trampas: lo que NO se deduce
leyendo el código.

El caso que trae implementado —fichas crediticias con referencias comerciales y
alertas— es **un ejemplo, no el proyecto**. Cuando toque adaptarlo a otro rubro,
lo que se reescribe es `pipeline/dominio/esquema.py`; el resto queda igual.

## Principio rector

Convertir errores silenciosos en ruidosos. Un dato que "se ve bien pero está
mal" tiene que delatarse (validación, reconciliación, read-back), nunca cargarse
a ciegas. Ante la duda, no cargar: mandar a la vista de problemas.

## Objetivo pedagógico: cada pieza se cambia sola

El valor del repo no es el parser: son las **costuras**. Alguien tiene que poder
enchufar otro formato de entrada u otra web sin tocar el resto. De ahí:

- `pipeline/contratos.py` define los dos enchufes (`Extractor` y `Cargador`).
  Leerlo primero: es el mapa.
- Entre etapa y etapa hay un **archivo en disco** (JSONL), no una llamada de
  función. Se puede cortar, mirar y retomar.
- **Otro formato de entrada** = una clase nueva en `pipeline/extractores/` y una
  línea en su `__init__.py`. Hay dos (PDF y DOCX) justamente para probar que el
  contrato aguanta: producen FichaCruda idénticas.
- **Otra web objetivo** = editar `config/mapeo_web.yaml`. Cero código.
- **Otro formulario en la misma web** = un bloque en el YAML + un `elif` en
  `_ir_a_la_tabla()`. Lo que NO se hace nunca es copiar el cargador: las
  defensas se despegarían entre copias, y la copia vieja es la que pisa datos.
- **Otro dominio** = reescribir `pipeline/dominio/esquema.py`. Los normalizadores
  de al lado no se tocan: fechas ambiguas, montos con separadores raros e
  identificadores con dígito verificador aparecen en cualquier data entry.

## Convenciones

- Comentarios y nombres en español (rioplatense). Sin tildes en identificadores.
- Python 3.10+ (el `python3` del sistema es 3.8: usar el venv). Simple y legible
  antes que abstracto. No sobre-ingenierizar.
- Todo se corre desde la raíz del repo con `python -m pipeline.<modulo>`; así no
  hacen falta trucos de `sys.path` ni instalar el paquete.
- NUNCA credenciales ni datos reales. Los datos de ejemplo son 100% inventados.
- Cada eslabón se prueba en chico (`--limite`, `--dry-run`) antes de escalar.

## Decisiones de diseño (no cambiar sin motivo explícito)

- **Determinismo**: los valores relativos de antigüedad ("2 meses", "1 año") se
  anclan a la FECHA DE EMISIÓN del documento, nunca a `date.today()`. Mismo
  archivo ⇒ misma salida siempre.
- **Fuente de verdad = JSONL** (un cliente por línea). El Excel es una VISTA
  derivada. Las correcciones NO vuelven editando el Excel: se corrige la regla
  en el código y se re-corre.
- **El extractor no sabe de negocio.** Devuelve cabecera + tablas de texto crudo
  y nada más. Toda interpretación vive en `pipeline/dominio/`. Es lo que permite
  que PDF y DOCX compartan el mismo dominio.
- **Idempotencia**: estado por fila en SQLite (`data/salida/estado_carga.db`),
  clave compuesta que **arranca con el nombre del formulario**
  (`referencias|cuit|solicitud|fecha|informante`, `alertas|cuit|fecha|alertante`).
  El prefijo no es cosmético: el estado es una sola tabla para todo el lote, y
  sin él dos formularios podrían pisarse la clave. Se corta y se
  retoma sin duplicar. Ojo: `--dry-run` y `--simular` NO anotan estado, porque
  si anotaran, la corrida real saltearía filas que nunca se escribieron.
- **Lista blanca de campos escribibles**, una por formulario (`campos` en el
  YAML). En referencias: SOLO Condición, Crédito Otorgado, Crédito Tomado,
  Otorgado USD, Tomado USD, Antigüedad — NUNCA Monto Asegurado, Seguro ni Doc.
  En alertas: SOLO Tipo, Estado, Monto, Comentarios — NUNCA el expediente.
  Está verificada, no declamada: el cargador fotografía todos los inputs antes
  y después y falla si se movió algo fuera de la lista.
- **La navegación es lo único que cambia entre formularios.** Las referencias
  cuelgan de una solicitud y las alertas del cliente, así que el camino difiere;
  todo lo demás (lista blanca, escritura, guardado, read-back, verificación) está
  escrito una sola vez y lo comparten.
- **Read-back**: después de guardar se reabre el formulario y se compara. Que el
  submit no explote no significa que el dato entró.
- **Campos en None no se escriben** (no se manda ""): pisar con vacío un dato
  que ya estaba bien es el error que no se nota hasta que es tarde.

## Reglas del dominio de EJEMPLO (en `pipeline/dominio/`, respetarlas)

Valen para el caso crediticio que trae el repo. Si se adapta a otro rubro, esta
sección entera se reemplaza; las de arriba y abajo no.

- **Antigüedad**: matcher de prioridad, gana el primer patrón que matchea:
  `d/m/aaaa`; `m/aaaa` (día=01); `m/aa` (día=01, siglo por pivote 26: 00–26⇒20xx,
  27–99⇒19xx); `aaaa` solo (⇒ 01/07/aaaa); "N meses"/"N años" (resta a emisión);
  número de 1–3 dígitos (⇒ N años); palabra sola / "-" / "n/c" ⇒ None.
- **Plazo**: válido 0–90 (son cuotas). No numérico o fuera de rango (ej. "3060")
  ⇒ campo None + marca de problema; la fila igual se carga.
- **Inactivo = "Sí"**: descartar esa fila entera (exclusión legítima, no error).
  Se cuenta en `Cliente.descartadas` para reconciliar.
- **CUIT**: clave del cliente, con dígito verificador. Inválido NO bloquea ni
  rompe: se carga y se marca (`cuit_ok`). Un cliente nunca desaparece en silencio.
- **Montos**: coma = miles, punto = decimal ("23,000"→23000; "10044.71"→10044.71).
- **Claves duplicadas**: si dos referencias comparten
  `(cliente, solicitud, fecha, informante)`, NO se cargan. En la web las dos
  filas matchean igual y elegir "la primera" escribe en la fila equivocada.

## Trampas de cada formato (por qué el extractor es así)

- **Las fichas se derraman** a varias páginas y la continuación NO repite el
  encabezado del cliente (sí los encabezados de columna). Se streamea el
  documento entero y se corta por `Cliente: ... (CUIT: ...)`. Nunca página por
  página de forma aislada.
- **Qué tabla es cuál** se decide por sus ENCABEZADOS ("Informante" ⇒
  referencias, "Alertante" ⇒ alertas), no por el título de sección: la página de
  continuación no lo repite.
- **Las filas de subgrupo no son datos.** "Solicitud hecha el X por Y" es una
  celda combinada que abarca las 12 columnas; hay que detectarla y bajar ese
  título a las filas que le siguen, porque la solicitud es parte de la clave.
  Cada librería la entrega distinto: **pdfplumber** devuelve el título en la
  primera celda y `None` en las otras once; **python-docx** lo devuelve
  **repetido** en las doce. Distinta maña, misma detección de fondo (una sola
  celda con texto ⇒ es un título, no una fila).
- **DOCX**: además, `doc.paragraphs` y `doc.tables` pierden el orden entre sí:
  hay que recorrer el cuerpo del XML a mano (`_bloques`).

## Estado

Todo el pipeline anda end-to-end contra `web_demo/`.

| Etapa | Estado |
|---|---|
| Normalizadores + dominio | listo, smoke tests propios |
| Extractor PDF (pdfplumber) | listo, 300/300 fichas vs ground truth |
| Extractor DOCX (python-docx) | listo, 300/300, salida idéntica al PDF |
| Vistas Excel (4 hojas) | listo |
| Web demo (Flask + SQLite) | listo: dos formularios |
| Carga web (Playwright) | listo: 80/80 con read-back, idempotente |

Verificación: el generador emite un **ground truth** (`<archivo>.verdad.json`)
con lo que el extractor debería devolver, y `tests/verificar_extractor.py`
compara. Mirar columnas a ojo no escala más allá del tercer cliente.

## Lo que quedó pendiente

Nada del pipeline: las dos entidades del documento (referencias y alertas) se
extraen, se validan, se revisan y se cargan de punta a punta.
