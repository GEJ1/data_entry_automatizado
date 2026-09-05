"""
Saca una captura de una pagina de la web demo y la guarda como PNG.

Existe como script aparte por una razon concreta: la API sincronica de
Playwright no se puede usar adentro de un notebook, porque Jupyter ya tiene
corriendo un event loop de asyncio y las dos cosas chocan. Llamarlo como
proceso separado (que es lo que hace curso.ipynb) evita el problema sin tener
que reescribir nada en async.

Uso:
    python demo/captura.py "http://127.0.0.1:5000/admin/buscar?cuit=..." /tmp/shot.png
    python demo/captura.py URL SALIDA --alto 900
"""
import argparse

from playwright.sync_api import sync_playwright


def capturar(url: str, salida: str, ancho: int = 1200, alto: int = 700) -> str:
    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        pagina = navegador.new_page(viewport={"width": ancho, "height": alto})
        pagina.goto(url)
        pagina.screenshot(path=salida, full_page=True)
        navegador.close()
    return salida


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("salida")
    ap.add_argument("--ancho", type=int, default=1200)
    ap.add_argument("--alto", type=int, default=700)
    args = ap.parse_args()
    print(capturar(args.url, args.salida, args.ancho, args.alto))
