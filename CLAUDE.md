# Proyecto: Carga de Solicitudes Financieras

Pipeline de data entry: PDF (fichas de clientes) → validación/normalización →
carga en un formulario web. En construcción. Detalle completo en `README.md` y
en `docs/` (diseño y manual). Este archivo prioriza decisiones, convenciones y
trampas: lo que NO se deduce leyendo el código.

## Principio rector

Convertir errores silenciosos en ruidosos. Un dato que "se ve bien pero está
mal" tiene que delatarse (validación, reconciliación, read-back), nunca cargarse
a ciegas. Ante la duda, no cargar: mandar a la vista de problemas.

## Convenciones

- Comentarios y nombres en español (rioplatense). Sin tildes en identificadores.
- Python 3.10+. Simple y legible antes que abstracto. No sobre-ingenierizar.
- NUNCA credenciales, datos reales ni PDFs reales en el repo. Los datos de
  ejemplo son 100% inventados.
- Cada eslabón nuevo se prueba en chico (dry-run / un solo cliente) antes de
  escalar. La parte web se prueba primero en dry-run: llenar el form sin guardar.

## Decisiones de diseño (no cambiar sin motivo explícito)

- **Determinismo**: los valores relativos de antigüedad ("2 meses", "1 año") se
  anclan a la FECHA DE EMISIÓN del PDF, nunca a `date.today()`. Mismo PDF ⇒ misma
  salida siempre.
- **Fuente de verdad = JSON** (JSONL, un cliente por línea). El Excel es una
  VISTA derivada para revisión humana. Las correcciones NO vuelven editando el
  Excel: se corrige la regla en el código y se re-corre.
- **Idempotencia** en la carga: estado por fila en SQLite (pendiente/ok/error),
  clave compuesta `(cliente, solicitud, fecha, informante)`. Se puede cortar y
  retomar sin duplicar.
- **Lista blanca de campos escribibles** en la web: SOLO Condición, Crédito
  Otorgado, Crédito Tomado, Otorgado USD, Tomado USD, Antigüedad. NUNCA tocar
  Monto Asegurado, Seguro, Doc, ni eliminar. Intentar escribir fuera de la lista
  debe abortar la fila, no hacerlo en silencio.

## Reglas de dominio (implementadas en `src/esquema.py`, respetarlas)

- **Antigüedad**: matcher de prioridad, gana el primer patrón que matchea:
  `d/m/aaaa`; `m/aaaa` (día=01); `m/aa` (día=01, siglo por pivote 26: 00–26⇒20xx,
  27–99⇒19xx); `aaaa` solo (⇒ 01/07/aaaa); "N meses"/"N años" (resta a emisión);
  número de 1–3 dígitos (⇒ N años); palabra sola / "-" / "n/c" ⇒ None.
- **Plazo**: válido 0–90 (son cuotas). No numérico o fuera de rango (ej. "3060")
  ⇒ campo None + marca de problema; la fila igual se carga.
- **Inactivo = "Sí"**: descartar esa fila de referencia entera (exclusión
  legítima, no error). Contarla aparte para reconciliar.
- **CUIT**: clave del cliente, con dígito verificador. Inválido NO bloquea ni
  rompe: se carga y se marca (`cuit_ok`). Un cliente nunca desaparece en silencio.
- **Montos**: coma = miles, punto = decimal ("23,000"→23000; "10044.71"→10044.71).

## Estructura del PDF de entrada (clave para el parser)

- Una ficha por cliente. Encabezado `Cliente: NOMBRE (CUIT: XXXXXXXXXXX)` +
  `Fecha de Emisión`.
- Sección "1. Solicitudes de Referencia": 12 columnas, subagrupada por filas
  "Solicitud hecha el X por Y". Puede decir "No hay...".
- Sección "2. Alertas / Denuncias": 6 columnas. Puede decir "No hay...".
- Las fichas SE DERRAMAN a varias páginas y las de continuación NO repiten el
  encabezado del cliente (sí repiten los encabezados de columna). El parser debe
  streamear el documento entero y cortar por el encabezado `Cliente:(CUIT:)`.
  Nunca procesar página por página de forma aislada.
- El PDF es nativo (texto seleccionable). Usar `pdfplumber`.

## Estado

- LISTO: `src/esquema.py` (validación/normalización). Smoke test: `python src/esquema.py`.
- LISTO: `demo/generar_pdf_fake.py` (PDFs de prueba con trampas sembradas;
  imprime un manifiesto; flags `--clientes N`, `--salida`).
- PENDIENTE: parser de extracción (PDF → dicts crudos → modelos de `esquema.py`).
- PENDIENTE: vistas Excel (resumen / detalle / problemas) generadas desde el JSONL.
- PENDIENTE: carga web con Playwright (descubrimiento + carga idempotente).

## Pregunta de diseño abierta (bloquea SOLO la parte web)

Cómo se llega del CUIT a la solicitud del cliente en la web para armar la URL de
edición `/admin/solicitudes/{id}/financieras/{id}/edit`. Ninguno de los dos IDs
está en el PDF. Hay un buscador por CUIT (falta confirmar si su URL es
templateable). El id de fila SIEMPRE se cosecha del `href` del lápiz de la tabla.
Ver "Lo que falta definir" en `docs/Documento_de_diseño.docx`.

## Próximo paso sugerido

Construir el parser contra los PDFs que genera `demo/generar_pdf_fake.py`.
Empezar por un cliente, verificar columnas a ojo, y recién ahí escalar. Ideal:
que el generador emita también un "ground truth" para verificar el parser
automáticamente.
