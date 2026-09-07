"""
Reconocimiento de una pagina: que campos tiene, como se identifican sus filas,
y de donde sale el link de edicion.

Sirve para armar `config/mapeo_web.yaml` sin ir clickeando el inspector campo
por campo. Es la parte ABURRIDA del trabajo, y es completamente mecanica: no
hace falta ningun modelo para listar los `id` de un formulario. Alcanza con
abrir la pagina y mirar el DOM.

Lo que este script NO hace, a proposito:

  * no decide que campos van en la lista blanca
  * no escribe ni envia nada

El borrador de YAML que emite (`--yaml`) sale con TODOS los campos comentados.
Descomentarlos es una decision de negocio y la toma una persona. Un script que
te arme la lista blanca solo te esta devolviendo la lista negra al reves, que es
justo lo que no queremos.

Acepta VARIAS urls y las junta, porque lo que hace falta suele estar repartido:
la tabla con el link de edicion en una pagina, el formulario en otra.

Uso:
    python demo/reconocer_web.py URL_DE_LA_TABLA
    python demo/reconocer_web.py URL_DE_LA_TABLA URL_DEL_FORMULARIO --yaml
    python demo/reconocer_web.py URL --salida recon.json --ver
"""
from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright

# Se ejecuta dentro de la pagina. Todo lo que devuelve es descriptivo: no toca
# nada, no escribe en ningun input, no dispara ningun evento.
SONDA = r"""
() => {
  const sel = (el) => el.id ? `#${el.id}`
    : (el.name ? `[name="${el.name}"]` : (el.className ? `${el.tagName.toLowerCase()}.${el.className.trim().split(/\s+/)[0]}` : null));

  const etiquetaDe = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    const cont = el.closest('div,p,li,td');
    const lab = cont && cont.querySelector('label');
    return lab ? lab.innerText.trim() : null;
  };

  // --- campos de formulario, agrupados por seccion (fieldset/legend) --------
  const campos = [...document.querySelectorAll('form input, form select, form textarea')]
    .filter(el => !['hidden', 'submit', 'button'].includes(el.type))
    .map(el => ({
      selector: sel(el),
      tipo: el.tagName.toLowerCase() + (el.type ? `[${el.type}]` : ''),
      etiqueta: etiquetaDe(el),
      seccion: el.closest('fieldset')?.querySelector('legend')?.innerText.trim() || null,
      solo_lectura: !!(el.readOnly || el.disabled),
      valor_actual: (el.value || '').slice(0, 40),
    }));

  const botones = [...document.querySelectorAll('form button, form input[type=submit]')]
    .map(b => ({ selector: sel(b), texto: (b.innerText || b.value || '').trim() }));

  // --- tablas: como se identifica una fila y de donde sale el link ----------
  const tablas = [...document.querySelectorAll('table')].map(t => {
    const filas = [...t.querySelectorAll('tr')].filter(r => r.querySelector('td'));
    const f0 = filas[0];
    if (!f0) return null;
    const links = [...f0.querySelectorAll('a[href]')].map(a => ({
      selector: sel(a),
      texto: (a.innerText || a.title || '').trim().slice(0, 20),
      href: a.getAttribute('href'),
      patron: a.getAttribute('href').replace(/\d+/g, '{id}'),
    }));
    return {
      selector_fila: f0.className ? `tr.${f0.className.trim().split(/\s+/)[0]}` : 'tr',
      filas: filas.length,
      encabezados: [...t.querySelectorAll('th')].map(x => x.innerText.trim()),
      // Las celdas con clase propia son las candidatas a identificar la fila.
      celdas_con_clase: [...f0.querySelectorAll('td[class]')].map(td => ({
        selector: `td.${td.className.trim().split(/\s+/)[0]}`,
        texto: td.innerText.trim().slice(0, 30),
      })),
      links: links,
    };
  }).filter(Boolean);

  // --- pistas de "no hay resultados" ---------------------------------------
  const vacios = [...document.querySelectorAll('[id*="sin"],[id*="vacio"],[class*="vacio"],[class*="empty"]')]
    .map(el => ({ selector: sel(el), texto: el.innerText.trim().slice(0, 60) }));

  return { url: location.href, titulo: document.title, campos, botones, tablas, pistas_sin_resultados: vacios };
}
"""


def reconocer(url: str, ver: bool = False) -> dict:
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=not ver)
        pagina = navegador.new_page()
        pagina.goto(url)
        datos = pagina.evaluate(SONDA)
        navegador.close()
    return datos


def juntar(paginas: list[dict]) -> dict:
    """Une el reconocimiento de varias paginas en una sola vista."""
    unido = {"url": " + ".join(p["url"] for p in paginas),
             "titulo": paginas[0]["titulo"] if paginas else "",
             "campos": [], "botones": [], "tablas": [], "pistas_sin_resultados": []}
    vistos = set()
    for p in paginas:
        for c in p["campos"]:
            if c["selector"] not in vistos:
                vistos.add(c["selector"])
                unido["campos"].append(c)
        for clave in ("botones", "tablas", "pistas_sin_resultados"):
            unido[clave] += p[clave]
    return unido


def resumir(d: dict) -> str:
    lineas = [f"URL     {d['url']}", f"Título  {d['titulo']}", ""]

    if d["campos"]:
        lineas.append("CAMPOS DEL FORMULARIO (agrupados como los agrupa la página)")
        por_seccion: dict[str, list] = {}
        for c in d["campos"]:
            por_seccion.setdefault(c["seccion"] or "(sin sección)", []).append(c)
        for seccion, campos in por_seccion.items():
            lineas.append(f"  {seccion}")
            for c in campos:
                marca = "  [solo lectura]" if c["solo_lectura"] else ""
                etiqueta = f"  · {c['etiqueta']}" if c["etiqueta"] else ""
                lineas.append(f"      {c['selector']:<24}{etiqueta}{marca}")
        lineas.append("")

    if d["botones"]:
        lineas.append("BOTONES")
        for b in d["botones"]:
            lineas.append(f"      {b['selector']:<24}  · {b['texto']}")
        lineas.append("")

    for i, t in enumerate(d["tablas"], start=1):
        lineas.append(f"TABLA {i}  ({t['filas']} filas)")
        lineas.append(f"      fila         {t['selector_fila']}")
        for c in t["celdas_con_clase"]:
            lineas.append(f"      celda        {c['selector']:<20} ej: {c['texto']!r}")
        for l in t["links"]:
            lineas.append(f"      link         {l['selector']:<20} → {l['patron']}")
        lineas.append("")

    if d["pistas_sin_resultados"]:
        lineas.append("POSIBLE 'NO HAY RESULTADOS'")
        for v in d["pistas_sin_resultados"]:
            lineas.append(f"      {v['selector']:<24}  · {v['texto']!r}")
        lineas.append("")

    return "\n".join(lineas)


def borrador_yaml(d: dict) -> str:
    """
    Borrador del bloque de config/mapeo_web.yaml.

    Los campos salen COMENTADOS a proposito: la lista blanca la decide una
    persona, mirando el formulario y sabiendo de que sistema es cada dato.
    """
    tabla = d["tablas"][0] if d["tablas"] else None
    celdas = (tabla or {}).get("celdas_con_clase", [])
    link = next((l for l in (tabla or {}).get("links", []) if "edit" in (l["href"] or "")),
                None)
    guardar = d["botones"][0]["selector"] if d["botones"] else "#TODO"
    vacio = d["pistas_sin_resultados"][0]["selector"] if d["pistas_sin_resultados"] else "#TODO"

    l = ["formularios:", "", "  mi_formulario:",
         '    url_busqueda: "/TODO?cuit={cuit}"',
         "    selectores:",
         f'      sin_resultados: "{vacio}"',
         f'      fila: "{(tabla or {}).get("selector_fila", "TODO")}"',
         f'      celda_fecha: "{celdas[0]["selector"] if celdas else "TODO"}"',
         f'      celda_quien: "{celdas[1]["selector"] if len(celdas) > 1 else "TODO"}"',
         f'      link_editar: "{link["selector"] if link else "TODO"}"',
         f'      boton_guardar: "{guardar}"',
         '      aviso_guardado: "#TODO"   # cómo confirma la web que guardó',
         "",
         "    # LISTA BLANCA — descomentá SOLO lo que el pipeline debe escribir.",
         "    # Están todos comentados a propósito: esta decisión no la toma un script.",
         "    campos:"]

    for c in d["campos"]:
        if c["solo_lectura"] or not c["selector"]:
            continue
        nombre = (c["selector"].lstrip("#").replace("-", "_")
                  if c["selector"].startswith("#") else "TODO")
        pista = f"   # {c['seccion']}" if c["seccion"] else ""
        l.append(f'      # {nombre}: "{c["selector"]}"{pista}')

    return "\n".join(l)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("url", nargs="+", help="una o mas paginas a reconocer")
    ap.add_argument("--yaml", action="store_true",
                    help="imprimir el borrador del bloque de mapeo_web.yaml")
    ap.add_argument("--salida", help="guardar el reconocimiento crudo en un JSON")
    ap.add_argument("--ver", action="store_true", help="mostrar el navegador")
    args = ap.parse_args()

    datos = juntar([reconocer(u, ver=args.ver) for u in args.url])

    if args.yaml:
        print(borrador_yaml(datos))
    else:
        print(resumir(datos))

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        print(f"\n(reconocimiento crudo guardado en {args.salida})")
