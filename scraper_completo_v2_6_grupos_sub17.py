import json
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 1. Cada categoría tiene un "código" único en su URL (el texto después de
#    /sp/). Ese mismo código se repite para las tablas (general, ofensivas/
#    defensivas) -- solo cambia el nombre de la tabla.
#    Por eso basta con guardar dominio + código UNA vez por categoría.
# ---------------------------------------------------------------------------
CATEGORIAS = {
    "Sub 15": ("sub15", "40ba6dc245483f"),
    "Sub 17": ("sub17", "242877dd20f435"),
    "Sub 19": ("sub19", "9823df9f7707d5"),
    "Sub 21": ("sub21", "ee65df74eba6e9"),
}

HEADERS = {"User-Agent": "Mozilla/5.0"}


def url_de(dominio, tabla, codigo):
    return f"https://{dominio}.ligamx.net/cancha/tablas/{tabla}/sp/{codigo}"


# ---------------------------------------------------------------------------
# 2. TABLA GENERAL (posiciones)
# ---------------------------------------------------------------------------
def obtener_tabla_posiciones(url):
    respuesta = requests.get(url, headers=HEADERS)
    respuesta.raise_for_status()
    sopa = BeautifulSoup(respuesta.text, "html.parser")
    return sopa.select_one("table.tbl_grals, table.tbl_grpos")


def extraer_equipos(tabla, categoria):
    equipos = []
    grupo_actual = None

    for fila in tabla.select("tbody tr"):
        celdas = fila.find_all("td", recursive=False)
        texto_fila = fila.get_text(" ", strip=True)

        # La tabla oficial inserta filas separadoras para Grupo 1 y Grupo 2.
        # Conservamos ese contexto y lo asociamos a cada equipo siguiente.
        texto_normalizado = " ".join(texto_fila.split()).lower()
        if texto_normalizado in {"grupo 1", "grupo 2"}:
            grupo_actual = texto_normalizado.title()
            continue

        if len(celdas) < 10:
            continue

        posicion = celdas[0].get_text(strip=True)

        nombre_club = "Desconocido"
        indice_club = None

        for i, celda in enumerate(celdas):
            for enlace in celda.find_all("a"):
                texto = enlace.get_text(strip=True)
                if texto:
                    nombre_club = texto
                    indice_club = i
                    break
            if indice_club is not None:
                break

        if indice_club is None:
            continue

        stats = celdas[indice_club + 1: indice_club + 9]
        if len(stats) < 8:
            continue

        jj, jg, je, jp, gf, gc, dif, pts = [
            c.get_text(strip=True) for c in stats
        ]

        extra = celdas[indice_club + 9: indice_club + 11]
        pe = extra[0].get_text(strip=True) if len(extra) > 0 else ""
        tpts = extra[1].get_text(strip=True) if len(extra) > 1 else pts

        equipos.append({
            "categoria": categoria,
            "grupo": grupo_actual,
            "posicion": posicion,
            "club": nombre_club,
            "JJ": jj,
            "JG": jg,
            "JE": je,
            "JP": jp,
            "GF": gf,
            "GC": gc,
            "Dif": dif,
            "PTS": pts,
            "PE": pe,
            "TPTS": tpts,
        })

    return equipos


# ---------------------------------------------------------------------------
# 2B. GRUPOS DE SUB 17 DESDE LA PÁGINA PRINCIPAL
# ---------------------------------------------------------------------------
def normalizar_nombre_club(nombre):
    return " ".join(str(nombre or "").lower().split())


def extraer_mapa_grupos_sub17(url):
    """
    Obtiene la relación equipo -> grupo desde la página principal de Sub 17.

    La tabla de posiciones de Sub 17 llega como una clasificación 1-18,
    por lo que NO se asignan grupos por posición. Se busca explícitamente
    la información de grupos en la página principal.

    Si no se puede identificar la estructura, devuelve None para que el
    proceso pueda detenerse antes de generar datos incorrectos.
    """
    respuesta = requests.get(url, headers=HEADERS)
    respuesta.raise_for_status()

    sopa = BeautifulSoup(respuesta.text, "html.parser")

    mapa = {}

    # Buscamos tablas que contengan referencias explícitas a Grupo 1/Grupo 2.
    for tabla in sopa.find_all("table"):
        texto = " ".join(tabla.stripped_strings)
        texto_lower = texto.lower()

        if "grupo 1" not in texto_lower and "grupo 2" not in texto_lower:
            continue

        grupo_actual = None

        for fila in tabla.select("tr"):
            texto_fila = " ".join(fila.stripped_strings)
            normalizado = texto_fila.lower()

            if "grupo 1" in normalizado and len(normalizado) < 80:
                grupo_actual = "Grupo 1"
                continue

            if "grupo 2" in normalizado and len(normalizado) < 80:
                grupo_actual = "Grupo 2"
                continue

            if not grupo_actual:
                continue

            enlaces = [
                a.get_text(" ", strip=True)
                for a in fila.find_all("a")
                if a.get_text(" ", strip=True)
            ]

            if enlaces:
                nombre = enlaces[0]
            else:
                celdas = fila.find_all("td")
                nombre = (
                    celdas[0].get_text(" ", strip=True)
                    if celdas else ""
                )

            if nombre:
                mapa[normalizar_nombre_club(nombre)] = grupo_actual

        if mapa:
            break

    return mapa or None


def aplicar_grupos_sub17(equipos, mapa_grupos):
    """
    Cruza los equipos extraídos de la tabla 1-18 contra el mapa oficial
    de grupos de la página principal.
    """
    resultado = []

    faltantes = []

    for equipo in equipos:
        nombre = normalizar_nombre_club(equipo.get("club"))
        grupo = mapa_grupos.get(nombre)

        if not grupo:
            faltantes.append(equipo.get("club", "Desconocido"))
        else:
            equipo = dict(equipo)
            equipo["grupo"] = grupo
            resultado.append(equipo)

    if faltantes:
        raise RuntimeError(
            "Sub 17: no fue posible asignar grupo a: "
            + ", ".join(faltantes)
        )

    conteo = {}
    for equipo in resultado:
        grupo = equipo.get("grupo")
        conteo[grupo] = conteo.get(grupo, 0) + 1

    if conteo.get("Grupo 1", 0) != 9 or conteo.get("Grupo 2", 0) != 9:
        raise RuntimeError(
            "Sub 17: estructura de grupos inesperada. "
            f"Grupo 1={conteo.get('Grupo 1', 0)}, "
            f"Grupo 2={conteo.get('Grupo 2', 0)}; se esperaban 9 + 9."
        )

    return resultado


# ---------------------------------------------------------------------------
# 3. TABLA OFENSIVA / DEFENSIVA
# ---------------------------------------------------------------------------
def extraer_ofensiva_defensiva(url, categoria):
    respuesta = requests.get(url, headers=HEADERS)
    respuesta.raise_for_status()
    sopa = BeautifulSoup(respuesta.text, "html.parser")

    # la página repite estas tablas para la pestaña "Fase Final" (vacía) --
    # por eso solo tomamos las DOS PRIMERAS que aparecen (ofensiva, defensiva)
    tablas = sopa.select("table.tbl_ofdef")[:2]

    ofensiva, defensiva = [], []
    for indice, tabla in enumerate(tablas):
        destino = ofensiva if indice == 0 else defensiva
        for fila in tabla.select("tbody tr"):
            celdas = fila.find_all("td")
            if len(celdas) < 3:
                continue
            destino.append({
                "categoria": categoria,
                "posicion": celdas[0].get_text(strip=True),
                "club": celdas[1].get_text(strip=True),
                "valor": celdas[2].get_text(strip=True),
            })
    return ofensiva, defensiva


# ---------------------------------------------------------------------------
# 4. Recorremos las 4 categorías y guardamos TODO en archivos separados
# ---------------------------------------------------------------------------
todos_los_equipos = []
toda_la_ofensiva = []
toda_la_defensiva = []

for nombre_categoria, (dominio, codigo) in CATEGORIAS.items():
    print(f"Descargando {nombre_categoria}...")

    url_posiciones = url_de(dominio, "tablaGeneralClasificacion", codigo)

    # Sub 15 y Sub 17 compiten en dos grupos y la fuente oficial
    # publica ambas clasificaciones bajo "Tabla por Grupos".
    if nombre_categoria in {"Sub 15", "Sub 17"}:
        url_posiciones = url_de(dominio, "tablaGrupos", codigo)
    tabla = obtener_tabla_posiciones(url_posiciones)
    equipos = extraer_equipos(tabla, nombre_categoria) if tabla else []

    if nombre_categoria == "Sub 17":
        url_principal = f"https://{dominio}.ligamx.net"
        mapa_grupos = extraer_mapa_grupos_sub17(url_principal)

        if not mapa_grupos:
            raise RuntimeError(
                "Sub 17: no se encontró la estructura de grupos "
                "en la página principal."
            )

        equipos = aplicar_grupos_sub17(equipos, mapa_grupos)

    todos_los_equipos.extend(equipos)
    grupos = sorted({
        e.get("grupo") for e in equipos
        if e.get("grupo")
    })
    detalle_grupos = (
        " | ".join(grupos)
        if grupos else "Tabla general"
    )

    if nombre_categoria in {"Sub 15", "Sub 17"}:
        conteo = {}
        for equipo in equipos:
            grupo = equipo.get("grupo")
            conteo[grupo] = conteo.get(grupo, 0) + 1

        detalle_grupos = (
            f"Grupo 1: {conteo.get('Grupo 1', 0)} | "
            f"Grupo 2: {conteo.get('Grupo 2', 0)}"
        )

    print(
        f"  Posiciones: {len(equipos)} equipos | "
        f"Estructura: {detalle_grupos}"
    )

    url_ofdef = url_de(dominio, "tablaOfnsDfns", codigo)
    ofensiva, defensiva = extraer_ofensiva_defensiva(url_ofdef, nombre_categoria)
    toda_la_ofensiva.extend(ofensiva)
    toda_la_defensiva.extend(defensiva)
    print(f"  Ofensiva/Defensiva: {len(ofensiva)}/{len(defensiva)} equipos")

with open("datos.json", "w", encoding="utf-8") as archivo:
    json.dump(todos_los_equipos, archivo, ensure_ascii=False, indent=2)

with open("datos_ofensiva.json", "w", encoding="utf-8") as archivo:
    json.dump(toda_la_ofensiva, archivo, ensure_ascii=False, indent=2)

with open("datos_defensiva.json", "w", encoding="utf-8") as archivo:
    json.dump(toda_la_defensiva, archivo, ensure_ascii=False, indent=2)

print("\nListo. Archivos generados: datos.json, datos_ofensiva.json, "
      "datos_defensiva.json")
