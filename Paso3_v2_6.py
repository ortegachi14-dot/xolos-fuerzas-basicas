import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
import re

# ---------------------------------------------------------------------------
# XOLOS FUERZAS BÁSICAS
# PASO 3 - VALIDACIÓN + METADATOS
#
# Flujo:
#   scraper_completo_v2_6_grupos_sub17.py
#       ↓
#   datos.json
#   datos_ofensiva.json
#   datos_defensiva.json
#       ↓
#   Paso3.py
#       ↓
#   datos/actual/
#   datos/historico/AAAA-MM-DD/
#
# IMPORTANTE:
# Paso 3 NO vuelve a extraer las tablas. Conserva exactamente los datos
# producidos por el scraper, incluido el campo "grupo".
# ---------------------------------------------------------------------------

CATEGORIAS = {
    "Sub 15": ("sub15", "40ba6dc245483f"),
    "Sub 17": ("sub17", "242877dd20f435"),
    "Sub 19": ("sub19", "9823df9f7707d5"),
    "Sub 21": ("sub21", "ee65df74eba6e9"),
}

HEADERS = {"User-Agent": "Mozilla/5.0"}
MIN_EQUIPOS = 18

BASE_DIR = Path(".")
ACTUAL_DIR = BASE_DIR / "datos" / "actual"
HISTORICO_DIR = BASE_DIR / "datos" / "historico"

GENERAL_SRC = BASE_DIR / "datos.json"
OFENSIVA_SRC = BASE_DIR / "datos_ofensiva.json"
DEFENSIVA_SRC = BASE_DIR / "datos_defensiva.json"


def normalizar_texto(texto):
    texto = str(texto or "").upper()
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def cargar_json(ruta):
    if not ruta.exists():
        raise FileNotFoundError(f"No existe: {ruta}")

    with open(ruta, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


def guardar_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)

    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(
            datos,
            archivo,
            ensure_ascii=False,
            indent=2
        )


def contar_por_categoria(datos):
    conteo = {}

    for registro in datos:
        categoria = registro.get("categoria")

        if categoria:
            conteo[categoria] = (
                conteo.get(categoria, 0) + 1
            )

    return conteo


def validar_datos(general, ofensiva, defensiva):
    errores = []

    cg = contar_por_categoria(general)
    co = contar_por_categoria(ofensiva)
    cd = contar_por_categoria(defensiva)

    for categoria in CATEGORIAS:
        g = cg.get(categoria, 0)
        o = co.get(categoria, 0)
        d = cd.get(categoria, 0)

        if g != MIN_EQUIPOS:
            errores.append(
                f"{categoria}: general contiene {g}; "
                f"se esperaban exactamente {MIN_EQUIPOS}"
            )

        if o != MIN_EQUIPOS:
            errores.append(
                f"{categoria}: ofensiva contiene {o}; "
                f"se esperaban exactamente {MIN_EQUIPOS}"
            )

        if d != MIN_EQUIPOS:
            errores.append(
                f"{categoria}: defensiva contiene {d}; "
                f"se esperaban exactamente {MIN_EQUIPOS}"
            )

    # Validación específica de grupos.
    for categoria in ("Sub 15", "Sub 17"):
        registros = [
            x for x in general
            if x.get("categoria") == categoria
        ]

        grupos = {}
        for registro in registros:
            grupo = registro.get("grupo")
            grupos[grupo] = grupos.get(grupo, 0) + 1

        if grupos.get("Grupo 1", 0) != 9:
            errores.append(
                f"{categoria}: Grupo 1 contiene "
                f"{grupos.get('Grupo 1', 0)}; se esperaban 9"
            )

        if grupos.get("Grupo 2", 0) != 9:
            errores.append(
                f"{categoria}: Grupo 2 contiene "
                f"{grupos.get('Grupo 2', 0)}; se esperaban 9"
            )

    return errores


def extraer_metadatos(texto):
    texto = normalizar_texto(texto)

    torneo = None
    temporada = None
    jornada = None

    m_torneo = re.search(
        r"\b(APERTURA|CLAUSURA)\s*[-/]?\s*(20\d{2})\b",
        texto
    )

    if m_torneo:
        torneo = m_torneo.group(1).title()
        temporada = m_torneo.group(2)

    m_jornada = re.search(
        r"\bJORNADA\s*[:\-]?\s*(\d{1,2})\b",
        texto
    )

    if m_jornada:
        jornada = int(m_jornada.group(1))

    return torneo, temporada, jornada


def obtener_metadatos(dominio, codigo):
    urls = [
        f"https://{dominio}.ligamx.net/",
        f"https://{dominio}.ligamx.net/cancha/tablas/"
        f"tablaGeneralClasificacion/sp/{codigo}",
    ]

    textos = []

    for url in urls:
        try:
            respuesta = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )
            respuesta.raise_for_status()

            sopa = BeautifulSoup(
                respuesta.text,
                "html.parser"
            )

            textos.append(
                sopa.get_text(" ", strip=True)
            )
            textos.append(respuesta.text)

        except Exception:
            continue

    torneo = None
    temporada = None
    jornada = None

    for texto in textos:
        t, s, j = extraer_metadatos(texto)

        if torneo is None and t is not None:
            torneo = t

        if temporada is None and s is not None:
            temporada = s

        if jornada is None and j is not None:
            jornada = j

        if torneo and temporada and jornada:
            break

    if not (torneo and temporada and jornada):
        return None

    return {
        "torneo": torneo,
        "temporada": temporada,
        "jornada": jornada,
    }


def validar_grupos_en_datos(general):
    """
    Comprueba que el scraper haya entregado realmente los grupos.
    No los reconstruye ni los inventa.
    """
    errores = []

    for categoria in ("Sub 15", "Sub 17"):
        registros = [
            x for x in general
            if x.get("categoria") == categoria
        ]

        grupos = {
            x.get("grupo")
            for x in registros
        }

        if "Grupo 1" not in grupos or "Grupo 2" not in grupos:
            errores.append(
                f"{categoria}: el scraper no entregó "
                "Grupo 1 y Grupo 2."
            )

    return errores


# ---------------------------------------------------------------------------
# EJECUCIÓN
# ---------------------------------------------------------------------------

print("=" * 65)
print("XOLOS FUERZAS BÁSICAS")
print("PASO 3 - VALIDACIÓN + METADATOS")
print("=" * 65)

fecha_extraccion = datetime.now().strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# 1. Cargar exactamente los archivos producidos por el scraper
# ---------------------------------------------------------------------------

try:
    general = cargar_json(GENERAL_SRC)
    ofensiva = cargar_json(OFENSIVA_SRC)
    defensiva = cargar_json(DEFENSIVA_SRC)

except Exception as error:
    print("\n" + "!" * 60)
    print("ACTUALIZACIÓN CANCELADA")
    print("!" * 60)
    print(f"  {error}")
    print(
        "\nEjecuta primero el scraper y después Paso3.py."
    )
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# 2. Validar cantidades y grupos antes de tocar actual/histórico
# ---------------------------------------------------------------------------

errores = validar_datos(
    general,
    ofensiva,
    defensiva
)

errores.extend(
    validar_grupos_en_datos(general)
)

if errores:
    print("\n" + "!" * 60)
    print("ACTUALIZACIÓN CANCELADA: DATOS INVÁLIDOS")
    print("!" * 60)

    for error in errores:
        print(f"  - {error}")

    print(
        "\nNo se modificaron datos actuales ni históricos."
    )

    raise SystemExit(1)


# ---------------------------------------------------------------------------
# 3. Obtener metadatos por categoría
# ---------------------------------------------------------------------------

metadatos_categoria = {}
errores_metadata = []

for categoria, (dominio, codigo) in CATEGORIAS.items():

    print(f"\nMetadatos {categoria}...")

    meta = obtener_metadatos(
        dominio,
        codigo
    )

    if meta is None:
        errores_metadata.append(
            f"{categoria}: no se pudo identificar "
            "torneo, temporada y jornada"
        )
        continue

    metadatos_categoria[categoria] = meta

    print(
        f"  Torneo: {meta['torneo']} "
        f"{meta['temporada']}"
    )
    print(
        f"  Jornada: {meta['jornada']}"
    )


if errores_metadata:

    print("\n" + "!" * 60)
    print("ACTUALIZACIÓN CANCELADA: METADATOS INCOMPLETOS")
    print("!" * 60)

    for error in errores_metadata:
        print(f"  - {error}")

    print(
        "\nNo se modificaron datos actuales ni históricos."
    )

    raise SystemExit(1)


# ---------------------------------------------------------------------------
# 4. Validar torneo/temporada
# ---------------------------------------------------------------------------

torneo_temporada = {
    (
        meta["torneo"],
        meta["temporada"]
    )
    for meta in metadatos_categoria.values()
}

if len(torneo_temporada) != 1:

    print("\n" + "!" * 60)
    print(
        "ACTUALIZACIÓN CANCELADA: "
        "TORNEO/TEMPORADA INCONSISTENTES"
    )
    print("!" * 60)

    for categoria, meta in metadatos_categoria.items():
        print(
            f"{categoria}: "
            f"{meta['torneo']} "
            f"{meta['temporada']} "
            f"Jornada {meta['jornada']}"
        )

    print(
        "\nNo se modificaron datos actuales ni históricos."
    )

    raise SystemExit(1)


torneo, temporada = next(
    iter(torneo_temporada)
)


# ---------------------------------------------------------------------------
# 5. Metadata final
# ---------------------------------------------------------------------------

metadata = {
    "torneo": torneo,
    "temporada": temporada,
    "fecha_extraccion": fecha_extraccion,
    "categorias": metadatos_categoria,
}


# ---------------------------------------------------------------------------
# 6. Guardar histórico y actual
# ---------------------------------------------------------------------------

carpeta_historico = (
    HISTORICO_DIR / fecha_extraccion
)

guardar_json(
    carpeta_historico / "metadata.json",
    metadata
)

guardar_json(
    carpeta_historico / "general.json",
    general
)

guardar_json(
    carpeta_historico / "ofensiva.json",
    ofensiva
)

guardar_json(
    carpeta_historico / "defensiva.json",
    defensiva
)

guardar_json(
    ACTUAL_DIR / "metadata.json",
    metadata
)

guardar_json(
    ACTUAL_DIR / "general.json",
    general
)

guardar_json(
    ACTUAL_DIR / "ofensiva.json",
    ofensiva
)

guardar_json(
    ACTUAL_DIR / "defensiva.json",
    defensiva
)


# ---------------------------------------------------------------------------
# 7. Resumen
# ---------------------------------------------------------------------------

print("\n" + "=" * 65)
print("ACTUALIZACIÓN COMPLETADA")
print("=" * 65)

print(
    f"\nTorneo: {torneo} {temporada}"
)

print("Jornadas por categoría:")

for categoria in CATEGORIAS:
    meta = metadatos_categoria[categoria]

    print(
        f"  {categoria}: Jornada {meta['jornada']}"
    )

print(
    f"\nFecha de extracción: {fecha_extraccion}"
)

print("\nEstructura:")

for categoria in (
    "Sub 21",
    "Sub 19",
    "Sub 17",
    "Sub 15"
):
    registros = [
        x for x in general
        if x.get("categoria") == categoria
    ]

    if categoria in ("Sub 15", "Sub 17"):
        g1 = sum(
            x.get("grupo") == "Grupo 1"
            for x in registros
        )
        g2 = sum(
            x.get("grupo") == "Grupo 2"
            for x in registros
        )
        print(
            f"  {categoria}: "
            f"Grupo 1 {g1} | Grupo 2 {g2}"
        )
    else:
        print(
            f"  {categoria}: "
            f"Tabla general {len(registros)}"
        )

print("\nDatos actuales:")
print(f"  {ACTUAL_DIR}/")

print("\nHistórico:")
print(f"  {carpeta_historico}/")

print("\n✓ Datos del scraper conservados")
print("✓ Grupos conservados")
print("✓ Metadatos identificados")
print("✓ Datos validados")
print("✓ Histórico guardado")
print("✓ Datos actuales actualizados")
