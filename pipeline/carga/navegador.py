"""
Cargador web con Playwright. Cumple el contrato `Cargador` de contratos.py.

Sabe navegar; no sabe en que web. Todas las URLs y selectores vienen del Mapeo
(config/mapeo_web.yaml). Para apuntar a otro sistema se edita ese YAML.

UNA WEB TIENE VARIOS FORMULARIOS. Este cargador maneja dos, y estan resueltos de
forma deliberadamente asimetrica:

  * lo que CAMBIA entre formularios es el camino para llegar a la fila, y vive
    en un metodo chiquito por formulario (`_ir_a_la_tabla`);
  * lo que NO cambia —lista blanca, escritura, guardado, read-back, verificacion
    de que no se movio nada de mas— esta escrito UNA sola vez.

Sumar un tercer formulario es agregar un bloque al YAML y un `elif` de tres
lineas. Lo que no hay que hacer nunca es copiar el cargador entero: las defensas
se irian despegando entre copias, y la copia que se quede vieja va a ser la que
pise datos.

Los caminos que maneja hoy:

    referencias:  buscar por CUIT -> entrar a la solicitud -> ubicar la fila -> lapiz
    alertas:      buscar por CUIT -> entrar a alertas      -> ubicar la fila -> lapiz

El id de la fila no se calcula ni se cachea: se cosecha del href cada vez. Es
mas lento, y es a proposito: un id inventado escribe en la fila de otro.

Tres defensas, en orden de importancia:

  1. LISTA BLANCA. Solo se escriben los campos que estan en `campos` del
     formulario. Un campo fuera de la lista ABORTA la fila; no se escribe "lo
     que se pueda".

  2. NADA MAS SE MOVIO. Se saca una foto de todos los inputs del formulario
     antes y despues. Si cambio algo que no estaba en la lista blanca, la fila
     se reporta como error aunque el guardado haya "funcionado". Asi la lista
     blanca es una defensa verificada y no un comentario.

  3. READ-BACK. Despues de guardar se vuelve a abrir el formulario y se compara
     lo que quedo contra lo que se quiso escribir. Que el submit no explote no
     significa que el dato entro.
"""
from __future__ import annotations

from playwright.sync_api import TimeoutError as ErrorDeTimeout, sync_playwright

from pipeline.carga.mapeo import Formulario, Mapeo
from pipeline.contratos import ItemDeCarga, Resultado


class CargadorPlaywright:
    """Carga contra una web real (o contra web_demo). Se usa con `with`."""

    def __init__(self, mapeo: Mapeo, dry_run: bool = True,
                 headless: bool = True, lento_ms: int = 0):
        self.mapeo = mapeo
        self.dry_run = dry_run
        self.headless = headless
        self.lento_ms = lento_ms
        self._pw = self._browser = self._page = None

    # -- ciclo de vida -------------------------------------------------------

    def __enter__(self) -> "CargadorPlaywright":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless,
                                                 slow_mo=self.lento_ms)
        self._page = self._browser.new_page()
        self._page.set_default_timeout(self.mapeo.timeout_ms)
        return self

    def __exit__(self, *_exc) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    # -- API del contrato ----------------------------------------------------

    def cargar(self, item: ItemDeCarga) -> Resultado:
        """
        Nunca lanza por un problema de datos o de navegacion: devuelve
        Resultado(ok=False). Una fila mala no puede voltear un lote de 3000.
        """
        try:
            return self._cargar(item)
        except ErrorDeTimeout as e:
            return Resultado(item.clave, False,
                             f"timeout esperando la pagina: {str(e).splitlines()[0]}")
        except Exception as e:                      # noqa: BLE001
            return Resultado(item.clave, False, f"{type(e).__name__}: {e}")

    # -- el recorrido, comun a todos los formularios -------------------------

    def _cargar(self, item: ItemDeCarga) -> Resultado:
        p = self._page
        form = self.mapeo.formulario(item.formulario)

        # DEFENSA 1: lista blanca. Antes de abrir nada.
        fuera = sorted(set(item.campos) - set(form.campos))
        if fuera:
            return Resultado(item.clave, False,
                             f"campos fuera de la lista blanca de {item.formulario!r}: "
                             f"{fuera}. Fila abortada sin tocar la web.")

        # 1. buscar por CUIT
        p.goto(self.mapeo.url_busqueda(item.formulario, cuit=item.busqueda["cuit"]))
        if p.locator(form.sel("sin_resultados")).count():
            return Resultado(item.clave, False,
                             f"la web no conoce el CUIT {item.busqueda['cuit']}")

        # 2. llegar hasta la tabla que contiene la fila (esto SI depende del
        #    formulario: es lo unico que cambia entre uno y otro)
        problema = self._ir_a_la_tabla(item, form)
        if problema:
            return Resultado(item.clave, False, problema)

        # 3. ubicar la fila y cosechar el href del lapiz
        href_edicion, cuantas = self._href_de_edicion(
            form, item.busqueda["fecha"], item.busqueda["quien"])
        if cuantas == 0:
            return Resultado(item.clave, False,
                             f"no hay fila con fecha={item.busqueda['fecha']} "
                             f"y {item.busqueda['quien']!r}")
        if cuantas > 1:
            # No se elige "la primera": eso escribe en la fila equivocada.
            return Resultado(item.clave, False,
                             f"{cuantas} filas matchean fecha+nombre: ambiguo, "
                             f"no se carga")
        p.goto(self.mapeo.base_url + href_edicion)

        # 4. foto ANTES (para poder probar que no se movio nada de mas)
        antes = self._foto()

        for campo, valor in item.campos.items():
            p.fill(form.campos[campo], valor)

        if self.dry_run:
            return Resultado(item.clave, True,
                             f"dry-run: formulario {item.formulario} completo con "
                             f"{len(item.campos)} campos, SIN guardar")

        # 5. guardar y confirmar que el guardado ocurrio
        p.click(form.sel("boton_guardar"))
        p.wait_for_selector(form.sel("aviso_guardado"))

        # 6. READ-BACK: volver a abrir y mirar que quedo de verdad
        p.goto(self.mapeo.base_url + href_edicion)
        despues = self._foto()

        difieren = [f"{c}: escribi {v!r}, quedo {despues.get(c)!r}"
                    for c, v in item.campos.items() if despues.get(c) != v]
        if difieren:
            return Resultado(item.clave, False, "read-back fallo -> " + "; ".join(difieren))

        # DEFENSA 2: nada fuera de la lista blanca se movio
        tocados = [c for c in antes
                   if c not in item.campos and antes[c] != despues.get(c)]
        if tocados:
            return Resultado(item.clave, False,
                             f"se modificaron campos fuera de la lista blanca: {tocados}")

        return Resultado(item.clave, True,
                         f"{item.formulario}: {len(item.campos)} campos cargados y verificados")

    # -- lo unico que cambia entre formularios -------------------------------

    def _ir_a_la_tabla(self, item: ItemDeCarga, form: Formulario) -> str | None:
        """
        Navega desde la pagina de busqueda hasta la tabla con la fila buscada.
        Devuelve None si llego bien, o el motivo si no pudo.

        Para sumar un formulario nuevo: un `elif` aca y un bloque en el YAML.
        """
        p = self._page

        if item.formulario == "referencias":
            # Las filas financieras cuelgan de una solicitud: hay que elegir cual.
            href = self._href_de_solicitud(form, item.busqueda["solicitud"])
            if href is None:
                return f"no encontre la solicitud {item.busqueda['solicitud']!r}"
            p.goto(self.mapeo.base_url + href)
            return None

        if item.formulario == "alertas":
            # Las alertas cuelgan del cliente: un solo link y listo.
            link = p.locator(form.sel("link_alertas"))
            if link.count() == 0:
                return "el cliente no tiene seccion de alertas en la web"
            p.goto(self.mapeo.base_url + link.first.get_attribute("href"))
            return None

        return (f"no se como navegar hasta el formulario {item.formulario!r}. "
                f"Agregale un caso a _ir_a_la_tabla().")

    # -- helpers de navegacion -----------------------------------------------

    def _href_de_solicitud(self, form: Formulario, titulo: str) -> str | None:
        """El href de la solicitud cuyo titulo coincide exactamente."""
        p = self._page
        for fila in p.locator(form.sel("fila_solicitud")).all():
            link = fila.locator(form.sel("link_solicitud"))
            if link.count() == 0:
                continue
            celda = fila.locator("td").first
            if celda.count() and celda.inner_text().strip() == titulo:
                return link.first.get_attribute("href")
        return None

    def _href_de_edicion(self, form: Formulario, fecha: str,
                         quien: str) -> tuple[str | None, int]:
        """
        (href del lapiz, cuantas filas matchearon).

        `quien` es el informante en referencias y el alertante en alertas: el
        selector lo dice el YAML, asi que el codigo no necesita saber cual es.

        Se devuelve el conteo a proposito: 2 matches no es "agarra el primero",
        es un error. Ver la trampa de informante+fecha duplicados.
        """
        p = self._page
        encontrados = []
        for fila in p.locator(form.sel("fila")).all():
            f = fila.locator(form.sel("celda_fecha")).inner_text().strip()
            q = fila.locator(form.sel("celda_quien")).inner_text().strip()
            if f == fecha and q == quien:
                lapiz = fila.locator(form.sel("link_editar"))
                if lapiz.count():
                    encontrados.append(lapiz.first.get_attribute("href"))
        return (encontrados[0] if encontrados else None), len(encontrados)

    def _foto(self) -> dict[str, str]:
        """
        Todos los inputs de texto del formulario, por id.

        A proposito NO se listan los campos prohibidos por nombre: se fotografia
        todo y se compara. Asi, si la web agrega un campo nuevo manana, tambien
        queda protegido sin tocar el codigo.
        """
        foto = {}
        for el in self._page.locator("form input[type=text]").all():
            clave = el.get_attribute("id") or el.get_attribute("name")
            if clave:
                foto[clave] = el.input_value()
        return foto


class CargadorNulo:
    """
    No abre ningun navegador: solo dice que haria. Sirve para probar el resto
    del pipeline (claves, conflictos, idempotencia) sin depender de la web.
    """

    def __init__(self, mapeo: Mapeo):
        self.mapeo = mapeo

    def __enter__(self) -> "CargadorNulo":
        return self

    def __exit__(self, *_exc) -> None:
        pass

    def cargar(self, item: ItemDeCarga) -> Resultado:
        try:
            form = self.mapeo.formulario(item.formulario)
        except KeyError as e:
            return Resultado(item.clave, False, str(e))
        fuera = sorted(set(item.campos) - set(form.campos))
        if fuera:
            return Resultado(item.clave, False,
                             f"campos fuera de la lista blanca de {item.formulario!r}: {fuera}")
        return Resultado(item.clave, True,
                         f"simulado: {item.formulario}, {len(item.campos)} campos")
