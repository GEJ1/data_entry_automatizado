"""
Los DATOS de prueba, separados de como se renderizan.

Este archivo arma el lote de clientes falsos (con las trampas sembradas) y sabe
escupir el GROUND TRUTH: exactamente lo que un extractor correcto tendria que
devolver al leer el archivo generado.

Por que separado del render: el mismo lote se materializa en PDF y en DOCX. Si
los datos vivieran adentro del generador de PDF, el generador de DOCX seria una
copia y los dos se irian despegando. Aca hay una sola fuente y dos renders, y
por eso los dos comparten un unico ground truth: si el extractor de PDF y el de
DOCX cumplen el contrato, los dos tienen que dar EL MISMO resultado.

Los datos son 100% inventados. Semilla fija => salida reproducible.
"""
import random
from datetime import date, timedelta

random.seed(17)  # Lote17, y determinismo

EMISION = date(2026, 7, 3)  # fecha de emision del lote (ancla de "N meses/años")

COLS_REF = ["Fecha", "Informante", "¿Es cliente?", "CO ($)", "CT ($)",
            "CO (USD)", "CT (U$D)", "Condición de venta", "Plazo",
            "Concepto", "Antigüedad", "Inactivo"]

COLS_ALE = ["Fecha", "Alertante", "Tipo", "Estado", "Monto", "Comentarios"]

# ---------------------------------------------------------------------------
# Utilidades de datos falsos
# ---------------------------------------------------------------------------
def cuit_valido(tipo=None):
    """Genera un CUIT de 11 digitos con digito verificador correcto."""
    tipo = tipo or random.choice(["20", "23", "27", "30", "33"])
    medio = "".join(str(random.randint(0, 9)) for _ in range(8))
    base = tipo + medio
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
    verif = 0 if resto == 0 else (9 if resto == 1 else 11 - resto)
    return base + str(verif)

def cuit_invalido():
    """CUIT de 11 digitos con verificador MAL (para la trampa de checksum)."""
    c = cuit_valido()
    mal = (int(c[-1]) + 1) % 10
    return c[:-1] + str(mal)

NOMBRES = ["SERVICIOS CCI SRL", "AIR COMPUTER SA", "SOLUTIONBOX SA",
           "ELIT SA", "STENFAR SA", "MICROGLOBAL SA", "MASNET SA",
           "LICENCIAS ON LINE SA", "DISTRECOM SRL", "NEXSYS DE ARGENTINA",
           "PC ARTS ARGENTINA SA", "AFECTIVA SA", "NB TECH SRL",
           "DINSER SERVICIOS SRL", "GRUPO NUCLEO SA", "MEGATONE SA"]
INFORMANTES = ["FREE (Perez, G.)", "AIR COMPUTER", "SOLUTIONBOX", "STENFAR",
               "MICROGLOBAL", "MASNET S.A.", "ELIT S.A.", "NEXSYS",
               "DISTECNA", "PC ARTS"]
CONDIC = ["Cuenta corriente", "Cheque diferido", "Contado", "Sin especificar"]
CONCEPTO = ["Insumos", "Hardware", "Licencias", "Servicios", "Equipamiento"]
TIPO_ALE = ["Mora", "Cheque rechazado", "Concurso preventivo", "Denuncia"]
ESTADO_ALE = ["Abierta", "Cerrada", "En análisis"]

def fecha_rand(desde=date(2023, 1, 1), hasta=date(2026, 6, 30)):
    d = (hasta - desde).days
    return (desde + timedelta(days=random.randint(0, d))).strftime("%d/%m/%Y")

def monto_rand():
    return random.choice(["$0", f"{random.randint(1, 90)},000",
                          f"{random.randint(1, 500)*100:,}", "1", "$0"])

def fila_ref(informante=None, antiguedad="-", plazo="30", inactivo="-",
             co_ars=None, co_usd="USD 0", condicion=None, concepto=None,
             fecha=None):
    return {
        "Fecha": fecha or fecha_rand(),
        "Informante": informante or random.choice(INFORMANTES),
        "¿Es cliente?": random.choice(["Sí", "No"]),
        "CO ($)": co_ars if co_ars is not None else monto_rand(),
        "CT ($)": monto_rand(),
        "CO (USD)": co_usd,
        "CT (U$D)": "USD 0",
        "Condición de venta": condicion or random.choice(CONDIC),
        "Plazo": plazo,
        "Concepto": concepto or random.choice(CONCEPTO),
        "Antigüedad": antiguedad,
        "Inactivo": inactivo,
    }

def fila_ale():
    return {
        "Fecha": fecha_rand(), "Alertante": random.choice(INFORMANTES),
        "Tipo": random.choice(TIPO_ALE), "Estado": random.choice(ESTADO_ALE),
        "Monto": random.choice(["$ 10044.71", "$0", "23,000", "$ 5000"]),
        "Comentarios": random.choice(["Sin regularizar", "Regularizado",
                                      "En seguimiento", "-"]),
    }

def subgrupo(titulo, filas):
    return {"titulo": titulo, "filas": filas}

# ---------------------------------------------------------------------------
# Clientes con TRAMPAS sembradas (cada uno = un momento del video)
# ---------------------------------------------------------------------------
def clientes_trampa():
    L = []

    # 1) BASELINE: limpio, ambas secciones, una pagina
    L.append(("baseline: caso limpio", dict(
        nombre="SERVICIOS CCI SRL", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 09/01/2025 por FREE (Perez, G.)",
                              [fila_ref(informante="AIR COMPUTER", antiguedad="12/5/2006"),
                               fila_ref(informante="SOLUTIONBOX", antiguedad="05/2019")])],
        alertas=[fila_ale()])))

    # 2) ANTIGÜEDAD ZOO: las 7 formas + palabra sola
    zoo = [("12/5/2006", "fecha d/m/aaaa"), ("05/2019", "m/aaaa"),
           ("05/18", "m/aa"), ("2011", "año solo"), ("2 meses", "relativo meses"),
           ("1 año", "relativo años"), ("3", "numero solo = años"),
           ("reciente", "palabra sola = sin fecha"), ("-", "vacio"),
           ("n/c", "n/c")]
    L.append(("antigüedad: las 7 formas + palabra sola", dict(
        nombre="AIR COMPUTER SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 15/03/2025 por STENFAR",
                              [fila_ref(informante=f"REF {i+1}", antiguedad=a)
                               for i, (a, _) in enumerate(zoo)])],
        alertas=None)))

    # 3) PLAZO BASURA: validos + '3060' y '150'
    L.append(("plazo: basura 3060/150 mezclada con validos", dict(
        nombre="SOLUTIONBOX SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 20/02/2025 por MICROGLOBAL",
                              [fila_ref(plazo=p) for p in
                               ["30", "60", "7", "15", "21", "90", "0", "3060", "150"]])],
        alertas=None)))

    # 4) CUIT INVALIDO (verificador mal) -> debe ir a problemas, no bloquear
    L.append(("cuit: verificador invalido", dict(
        nombre="ELIT SA", cuit=cuit_invalido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 01/04/2025 por NEXSYS",
                              [fila_ref(antiguedad="2020")])],
        alertas=[fila_ale()])))

    # 5) DUPLICADO: mismo informante + misma fecha en la misma solicitud
    L.append(("matching: informante+fecha duplicados (colision)", dict(
        nombre="STENFAR SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 02/06/2026 por MASNET S.A.",
                              [fila_ref(informante="MICROGLOBAL", fecha="02/06/2026", plazo="30"),
                               fila_ref(informante="MICROGLOBAL", fecha="02/06/2026", plazo="60")])],
        alertas=None)))

    # 6) SIN REFERENCIAS (seccion 1 vacia), con alertas
    L.append(("seccion vacia: sin referencias", dict(
        nombre="MASNET SA", cuit=cuit_valido(), emision=EMISION,
        referencias=None, alertas=[fila_ale(), fila_ale()])))

    # 7) SIN ALERTAS (seccion 2 vacia), con referencias
    L.append(("seccion vacia: sin alertas", dict(
        nombre="LICENCIAS ON LINE SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 10/01/2025 por DISTECNA",
                              [fila_ref(antiguedad="7/2005")])],
        alertas=None)))

    # 8) VACIO TOTAL: ambas secciones vacias
    L.append(("ambas secciones vacias", dict(
        nombre="DISTRECOM SRL", cuit=cuit_valido(), emision=EMISION,
        referencias=None, alertas=None)))

    # 9) GORDO: se derrama a otra pagina (continuacion sin encabezado de cliente)
    L.append(("multipágina: se derrama, la 2da hoja repite solo columnas", dict(
        nombre="NEXSYS DE ARGENTINA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 05/05/2025 por PC ARTS",
                              [fila_ref(antiguedad=random.choice(["2010", "3 años", "05/2018", "-"]))
                               for _ in range(38)])],
        alertas=[fila_ale()])))

    # 10) MONTOS SUCIOS + celda que envuelve (nombre largo)
    L.append(("montos sucios + celda multilinea (wrap)", dict(
        nombre="PC ARTS ARGENTINA SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 12/03/2025 por GRUPO NUCLEO",
                              [fila_ref(informante="NETPOINT DE ARGENTINA COMUNICACIONES Y SERVICIOS INTEGRALES S.A.",
                                        co_ars="23,000", co_usd="USD 10044.71",
                                        condicion="Cheque diferido a 30/60/90 días",
                                        antiguedad="04/2010"),
                               fila_ref(co_ars="$0", antiguedad="1"),
                               fila_ref(co_ars="45,000", antiguedad="05/98")])],
        alertas=None)))

    # 11) INACTIVO: fila con Inactivo = "Sí (fecha)" -> se descarta
    L.append(("inactivo: fila 'Sí (fecha)' que debe descartarse", dict(
        nombre="AFECTIVA SA", cuit=cuit_valido(), emision=EMISION,
        referencias=[subgrupo("Solicitud hecha el 22/04/2019 por CORCISA",
                              [fila_ref(informante="CORCISA", inactivo="Sí (30/10/2017)",
                                        antiguedad="-", plazo="0"),
                               fila_ref(informante="DINSER", antiguedad="2 años")])],
        alertas=None)))

    return L

def cliente_relleno():
    """Cliente 'normal' aleatorio para inflar el volumen."""
    tiene_ref = random.random() > 0.15
    tiene_ale = random.random() > 0.5
    refs = None
    if tiene_ref:
        subs = []
        for _ in range(random.randint(1, 2)):
            subs.append(subgrupo(
                f"Solicitud hecha el {fecha_rand()} por {random.choice(INFORMANTES)}",
                [fila_ref(antiguedad=random.choice(
                    ["12/5/2006", "05/2019", "2011", "3 años", "-", "n/c", "2015"]))
                 for _ in range(random.randint(1, 4))]))
        refs = subs
    ales = [fila_ale() for _ in range(random.randint(1, 2))] if tiene_ale else None
    return ("relleno", dict(nombre=random.choice(NOMBRES), cuit=cuit_valido(),
                            emision=EMISION, referencias=refs, alertas=ales))


def armar_lote(n_clientes: int):
    """Las trampas primero, despues relleno hasta llegar a n_clientes."""
    random.seed(17)   # re-sembrar: el lote no depende de que se importo antes
    clientes = list(clientes_trampa())
    while len(clientes) < n_clientes:
        clientes.append(cliente_relleno())
    return clientes[:max(n_clientes, len(clientes_trampa()))]


# ---------------------------------------------------------------------------
# GROUND TRUTH
# ---------------------------------------------------------------------------
def verdad(clientes) -> list[dict]:
    """
    Lo que un extractor correcto TIENE que devolver: una FichaCruda por cliente,
    con el texto tal cual va a quedar en el documento.

    Ojo con lo que NO esta aca: `origen` queda afuera a proposito, porque depende
    del archivo concreto (nombre y numero de pagina) y no del contenido. Comparar
    contra esto es la unica forma honesta de saber si el parser anda: mirar
    columnas a ojo no escala mas alla del tercer cliente.
    """
    fichas = []
    for _, cli in clientes:
        referencias = []
        for sg in (cli["referencias"] or []):
            for f in sg["filas"]:
                # La columna "Solicitud" es SINTETICA: en el documento es un
                # titulo de subgrupo que abarca varias filas. El extractor tiene
                # que bajarlo a cada fila, porque despues forma parte de la clave.
                referencias.append({"Solicitud": sg["titulo"], **f})
        fichas.append({
            "cabecera": {
                "Cliente": cli["nombre"],
                "CUIT": cli["cuit"],
                "Fecha de Emisión": cli["emision"].strftime("%d/%m/%Y") + " 19:00",
            },
            "tablas": {
                "referencias": referencias,
                "alertas": list(cli["alertas"] or []),
            },
        })
    return fichas


def manifiesto(clientes) -> str:
    """Que cliente muestra que trampa (para guionar el video)."""
    lineas = ["MANIFIESTO DE TRAMPAS (cliente -> que muestra):", "-" * 64]
    for i, (nota, cli) in enumerate(clientes):
        if nota == "relleno":
            continue
        lineas.append(f"  Cliente {i+1:>2}  {cli['nombre']:<26}  {nota}")
    lineas += ["-" * 64, "El resto son clientes de relleno (datos limpios aleatorios)."]
    return "\n".join(lineas)
