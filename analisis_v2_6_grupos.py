from pathlib import Path
import json
from statistics import mean

# ============================================================
# XOLOS FUERZAS BÁSICAS
# ANALISIS V2.6
# ============================================================
# Conserva:
#   1) análisis actual de Xolos
#   2) comparativo de las 4 categorías
#   3) tabla General completa
#   4) tabla Ofensiva completa
#   5) tabla Defensiva completa
#   6) histórico semanal
#
# No modifica los JSON originales del scraper.
# ============================================================

BASE = Path(".")
DATOS = BASE / "datos"
ACTUAL = DATOS / "actual"
HISTORICO = DATOS / "historico"

SALIDA_ACTUAL = DATOS / "analisis_actual.json"
SALIDA_HISTORICO = DATOS / "analisis_historico.json"

CATEGORIAS = ["Sub 21", "Sub 19", "Sub 17", "Sub 15"]


def cargar_json(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def numero(valor):
    if valor is None or valor == "":
        return 0.0
    try:
        return float(str(valor).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def entero(valor):
    return int(round(numero(valor)))


def media(valores):
    valores = list(valores)
    return round(mean(valores), 4) if valores else 0.0


def lista_json(data):
    # Los archivos actuales son listas, pero aceptamos también
    # contenedores comunes para hacer el sistema más resistente.
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for clave in ("datos", "equipos", "tabla", "data", "results"):
            if isinstance(data.get(clave), list):
                return data[clave]

    return []


def es_xolos(nombre):
    texto = str(nombre or "").lower()
    return (
        "xolo" in texto
        or "tijuana" in texto
    )


def por_categoria(registros, categoria):
    return [
        dict(x)
        for x in registros
        if str(x.get("categoria", "")).strip() == categoria
    ]


def asignar_grupos(registros):
    """
    Sub 15 y Sub 17 llegan desde el scraper como una sola lista de 18
    registros. La fuente no entrega un campo 'grupo', pero conserva la
    estructura oficial: posiciones 1-9 y después vuelven a 1-9.

    No inventamos la clasificación: la reconstruimos a partir del
    reinicio de la posición. Si en el futuro el scraper ya entrega
    'grupo', ese valor se conserva.
    """
    resultado = []

    for categoria in ("Sub 15", "Sub 17"):
        bloque = [
            dict(x) for x in registros
            if str(x.get("categoria", "")).strip() == categoria
        ]

        grupo_actual = 1
        posicion_anterior = None

        for x in bloque:
            if x.get("grupo"):
                # Si el scraper ya trae el grupo, respetarlo.
                grupo = x.get("grupo")
            else:
                posicion = entero(x.get("posicion"))

                # El salto 9 -> 1 identifica el segundo grupo.
                if (
                    posicion_anterior is not None
                    and posicion <= posicion_anterior
                ):
                    grupo_actual += 1

                grupo = f"Grupo {grupo_actual}"

            x["grupo"] = grupo
            posicion_anterior = entero(x.get("posicion"))
            resultado.append(x)

    # Categorías sin división: no se les asigna grupo.
    for x in registros:
        categoria = str(x.get("categoria", "")).strip()
        if categoria not in ("Sub 15", "Sub 17"):
            resultado.append(dict(x))

    return resultado


def encontrar_xolos(registros):
    return next(
        (x for x in registros if es_xolos(x.get("club"))),
        None
    )


def pct_mayor_mejor(valor, valores):
    valores = list(valores)
    n = len(valores)

    if n <= 1:
        return 100.0

    inferiores_o_iguales = sum(1 for x in valores if x <= valor)

    # Percentil por posición relativa dentro de los equipos.
    return round(
        (inferiores_o_iguales - 1) / (n - 1) * 100,
        1
    )


def pct_menor_mejor(valor, valores):
    valores = list(valores)
    n = len(valores)

    if n <= 1:
        return 100.0

    superiores_o_iguales = sum(1 for x in valores if x >= valor)

    # Menor valor = mejor rendimiento defensivo.
    return round(
        (superiores_o_iguales - 1) / (n - 1) * 100,
        1
    )


def preparar_general(registros):
    equipos = []

    for original in registros:
        x = dict(original)

        jj = numero(x.get("JJ"))

        if jj > 0:
            x["_PPG"] = numero(x.get("TPTS")) / jj
            x["_JG_pct"] = numero(x.get("JG")) / jj * 100
            x["_Invicto_pct"] = (
                numero(x.get("JG")) + numero(x.get("JE"))
            ) / jj * 100
            x["_GF_PJ"] = numero(x.get("GF")) / jj
            x["_GC_PJ"] = numero(x.get("GC")) / jj
            x["_Dif_PJ"] = numero(x.get("Dif")) / jj
        else:
            x["_PPG"] = 0.0
            x["_JG_pct"] = 0.0
            x["_Invicto_pct"] = 0.0
            x["_GF_PJ"] = 0.0
            x["_GC_PJ"] = 0.0
            x["_Dif_PJ"] = 0.0

        equipos.append(x)

    return equipos


def limpiar_tabla(registros, campos):
    """
    Devuelve solamente los campos oficiales necesarios para el dashboard.
    Los datos originales permanecen intactos.
    """
    resultado = []

    for x in registros:
        fila = {}

        for campo in campos:
            fila[campo] = x.get(campo)

        resultado.append(fila)

    return resultado


def metadata_categoria(metadata, categoria):
    categorias = metadata.get("categorias", {})

    if isinstance(categorias, dict):
        return categorias.get(categoria, {})

    return {}


def analizar_categoria(
    categoria,
    general,
    ofensiva,
    defensiva,
    metadata
):
    equipos = por_categoria(general, categoria)
    ataques = por_categoria(ofensiva, categoria)
    defensas = por_categoria(defensiva, categoria)

    equipos_calculados = preparar_general(equipos)

    if not equipos_calculados:
        return None

    xolos = encontrar_xolos(equipos_calculados)

    if xolos is None:
        return None

    ataque_xolos = encontrar_xolos(ataques)
    defensa_xolos = encontrar_xolos(defensas)

    # Sub 15 y Sub 17 compiten por grupos. Para las métricas
    # competitivas, la referencia correcta es el grupo de Xolos.
    grupo_xolos = xolos.get("grupo")
    if categoria in {"Sub 15", "Sub 17"}:
        if not grupo_xolos:
            raise ValueError(
                f"{categoria}: no fue posible determinar el grupo de Xolos."
            )

        equipos_competencia = [
            x for x in equipos_calculados
            if x.get("grupo") == grupo_xolos
        ]
    else:
        equipos_competencia = equipos_calculados

    promedio = {
        "PPG": media(x["_PPG"] for x in equipos_competencia),
        "JG_pct": media(x["_JG_pct"] for x in equipos_calculados),
        "Invicto_pct": media(
            x["_Invicto_pct"] for x in equipos_calculados
        ),
        "GF_PJ": media(x["_GF_PJ"] for x in equipos_calculados),
        "GC_PJ": media(x["_GC_PJ"] for x in equipos_calculados),
        "Dif_PJ": media(x["_Dif_PJ"] for x in equipos_calculados),
    }

    percentil_ofensivo = pct_mayor_mejor(
        xolos["_GF_PJ"],
        [x["_GF_PJ"] for x in equipos_competencia]
    )

    percentil_defensivo = pct_menor_mejor(
        xolos["_GC_PJ"],
        [x["_GC_PJ"] for x in equipos_competencia]
    )

    percentil_competitivo = pct_mayor_mejor(
        xolos["_PPG"],
        [x["_PPG"] for x in equipos_competencia]
    )

    percentil_diferencia = pct_mayor_mejor(
        xolos["_Dif_PJ"],
        [x["_Dif_PJ"] for x in equipos_competencia]
    )

    meta = metadata_categoria(metadata, categoria)

    return {
        "categoria": categoria,
        "jornada": meta.get("jornada"),
        "grupo": xolos.get("grupo"),

        # ----------------------------------------------------
        # Xolos — datos oficiales
        # ----------------------------------------------------
        "posicion": entero(xolos.get("posicion")),
        "JJ": entero(xolos.get("JJ")),
        "JG": entero(xolos.get("JG")),
        "JE": entero(xolos.get("JE")),
        "JP": entero(xolos.get("JP")),
        "GF": entero(xolos.get("GF")),
        "GC": entero(xolos.get("GC")),
        "Dif": entero(xolos.get("Dif")),
        "PTS": entero(xolos.get("PTS")),
        "PE": entero(xolos.get("PE")),
        "TPTS": entero(xolos.get("TPTS")),

        # ----------------------------------------------------
        # Métricas derivadas
        # ----------------------------------------------------
        "PPG": round(xolos["_PPG"], 2),
        "JG_pct": round(xolos["_JG_pct"], 1),
        "Invicto_pct": round(xolos["_Invicto_pct"], 1),
        "GF_PJ": round(xolos["_GF_PJ"], 2),
        "GC_PJ": round(xolos["_GC_PJ"], 2),
        "Dif_PJ": round(xolos["_Dif_PJ"], 2),

        # ----------------------------------------------------
        # Rankings oficiales
        # ----------------------------------------------------
        "ranking_ofensivo_oficial": (
            entero(ataque_xolos.get("posicion"))
            if ataque_xolos else None
        ),

        "valor_ofensivo_oficial": (
            ataque_xolos.get("valor")
            if ataque_xolos else None
        ),

        "ranking_defensivo_oficial": (
            entero(defensa_xolos.get("posicion"))
            if defensa_xolos else None
        ),

        "valor_defensivo_oficial": (
            defensa_xolos.get("valor")
            if defensa_xolos else None
        ),

        # ----------------------------------------------------
        # Percentiles
        # ----------------------------------------------------
        "percentil_competitivo": percentil_competitivo,
        "percentil_ofensivo": percentil_ofensivo,
        "percentil_defensivo": percentil_defensivo,
        "percentil_diferencia": percentil_diferencia,

        # ----------------------------------------------------
        # Promedio de Liga
        # ----------------------------------------------------
        "promedio_liga": {
            "PPG": round(promedio["PPG"], 2),
            "JG_pct": round(promedio["JG_pct"], 1),
            "Invicto_pct": round(promedio["Invicto_pct"], 1),
            "GF_PJ": round(promedio["GF_PJ"], 2),
            "GC_PJ": round(promedio["GC_PJ"], 2),
            "Dif_PJ": round(promedio["Dif_PJ"], 2),
        },

        "vs_promedio": {
            "PPG": round(
                xolos["_PPG"] - promedio["PPG"], 2
            ),
            "GF_PJ": round(
                xolos["_GF_PJ"] - promedio["GF_PJ"], 2
            ),
            "GC_PJ": round(
                xolos["_GC_PJ"] - promedio["GC_PJ"], 2
            ),
            "Dif_PJ": round(
                xolos["_Dif_PJ"] - promedio["Dif_PJ"], 2
            ),
        },

        # ----------------------------------------------------
        # TABLAS COMPLETAS — 18 equipos por categoría
        # ----------------------------------------------------
        "tabla_general": limpiar_tabla(
            equipos,
            [
                "categoria",
                "grupo",
                "posicion",
                "club",
                "JJ",
                "JG",
                "JE",
                "JP",
                "GF",
                "GC",
                "Dif",
                "PTS",
                "PE",
                "TPTS",
            ]
        ),

        "tabla_ofensiva": limpiar_tabla(
            ataques,
            [
                "categoria",
                "posicion",
                "club",
                "valor",
            ]
        ),

        "tabla_defensiva": limpiar_tabla(
            defensas,
            [
                "categoria",
                "posicion",
                "club",
                "valor",
            ]
        ),
    }


def analizar_snapshot(carpeta):
    metadata = cargar_json(carpeta / "metadata.json")

    general = lista_json(
        cargar_json(carpeta / "general.json")
    )

    # La fuente actual no trae 'grupo' en el JSON, pero sí entrega
    # Sub 15 y Sub 17 como 1-9 + 1-9. Reconstruimos esa estructura
    # antes de cualquier cálculo.
    general = asignar_grupos(general)

    ofensiva = lista_json(
        cargar_json(carpeta / "ofensiva.json")
    )

    defensiva = lista_json(
        cargar_json(carpeta / "defensiva.json")
    )

    categorias = {}

    for categoria in CATEGORIAS:
        resultado = analizar_categoria(
            categoria,
            general,
            ofensiva,
            defensiva,
            metadata
        )

        if resultado:
            categorias[categoria] = resultado

    comparativo = []

    for categoria in CATEGORIAS:
        datos = categorias.get(categoria)

        if not datos:
            continue

        comparativo.append({
            "categoria": categoria,
            "jornada": datos.get("jornada"),
            "grupo": datos.get("grupo"),
            "posicion": datos.get("posicion"),
            "TPTS": datos.get("TPTS"),
            "PPG": datos.get("PPG"),
            "GF_PJ": datos.get("GF_PJ"),
            "GC_PJ": datos.get("GC_PJ"),
            "Dif_PJ": datos.get("Dif_PJ"),
            "ranking_ofensivo": datos.get(
                "ranking_ofensivo_oficial"
            ),
            "ranking_defensivo": datos.get(
                "ranking_defensivo_oficial"
            ),
            "percentil_competitivo": datos.get(
                "percentil_competitivo"
            ),
            "percentil_ofensivo": datos.get(
                "percentil_ofensivo"
            ),
            "percentil_defensivo": datos.get(
                "percentil_defensivo"
            ),
        })

    return {
        "metadata": metadata,
        "comparativo_categorias": comparativo,
        "categorias": categorias,
    }


def validar_estructura(resultado):
    errores = []

    if len(resultado.get("categorias", {})) != 4:
        errores.append(
            "No se encontraron las 4 categorías."
        )

    for categoria in CATEGORIAS:
        datos = resultado.get("categorias", {}).get(categoria)

        if not datos:
            errores.append(
                f"{categoria}: falta análisis."
            )
            continue

        for nombre_tabla in (
            "tabla_general",
            "tabla_ofensiva",
            "tabla_defensiva",
        ):
            tabla = datos.get(nombre_tabla, [])

            if len(tabla) != 18:
                errores.append(
                    f"{categoria}: {nombre_tabla} "
                    f"contiene {len(tabla)} registros; "
                    f"se esperaban 18."
                )

        # La tabla General de Sub 15 y Sub 17 debe conservar
        # explícitamente la estructura competitiva 9 + 9.
        if categoria in {"Sub 15", "Sub 17"}:
            general = datos.get("tabla_general", [])
            conteo_grupos = {}
            for fila in general:
                grupo = fila.get("grupo")
                conteo_grupos[grupo] = conteo_grupos.get(grupo, 0) + 1

            if conteo_grupos.get("Grupo 1", 0) != 9:
                errores.append(
                    f"{categoria}: Grupo 1 contiene "
                    f"{conteo_grupos.get('Grupo 1', 0)} registros; "
                    "se esperaban 9."
                )

            if conteo_grupos.get("Grupo 2", 0) != 9:
                errores.append(
                    f"{categoria}: Grupo 2 contiene "
                    f"{conteo_grupos.get('Grupo 2', 0)} registros; "
                    "se esperaban 9."
                )

            grupos = [fila.get("grupo") for fila in general]
            if grupos[:9] != ["Grupo 1"] * 9:
                errores.append(
                    f"{categoria}: la secuencia de Grupo 1 no es 1-9."
                )

            if grupos[9:] != ["Grupo 2"] * 9:
                errores.append(
                    f"{categoria}: la secuencia de Grupo 2 no es 1-9."
                )

    return errores


# ============================================================
# EJECUCIÓN
# ============================================================

print("=" * 70)
print("XOLOS FUERZAS BÁSICAS")
print("ANÁLISIS V2.6")
print("=" * 70)

if not ACTUAL.exists():
    raise FileNotFoundError(
        "No existe la carpeta datos/actual/"
    )

resultado_actual = analizar_snapshot(ACTUAL)

errores = validar_estructura(resultado_actual)

if errores:
    print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("ANÁLISIS CANCELADO: ESTRUCTURA INCOMPLETA")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    for error in errores:
        print(f"  ✗ {error}")

    raise RuntimeError(
        "No se generó analisis_actual.json porque "
        "faltan datos o tablas completas."
    )


with open(SALIDA_ACTUAL, "w", encoding="utf-8") as f:
    json.dump(
        resultado_actual,
        f,
        ensure_ascii=False,
        indent=2
    )


print("\nGRUPOS")
for categoria in ("Sub 21", "Sub 19", "Sub 17", "Sub 15"):
    datos = resultado_actual["categorias"].get(categoria)
    if datos:
        grupo = datos.get("grupo")
        if grupo:
            print(f"  {categoria}: {grupo}")
        else:
            print(f"  {categoria}: competencia general")

print("\nACTUAL")

for fila in resultado_actual["comparativo_categorias"]:
    print(
        f"  {fila['categoria']}: "
        f"Pos {fila['posicion']} | "
        f"PPG {fila['PPG']} | "
        f"GF/PJ {fila['GF_PJ']} | "
        f"GC/PJ {fila['GC_PJ']} | "
        f"Of {fila['ranking_ofensivo']}º | "
        f"Def {fila['ranking_defensivo']}º"
    )


print("\nTABLAS")

for categoria in CATEGORIAS:
    datos = resultado_actual["categorias"][categoria]

    print(
        f"  {categoria}: "
        f"General {len(datos['tabla_general'])} | "
        f"Ofensiva {len(datos['tabla_ofensiva'])} | "
        f"Defensiva {len(datos['tabla_defensiva'])}"
    )


# ============================================================
# HISTÓRICO
# ============================================================

historico = {}

if HISTORICO.exists():

    carpetas = sorted(
        p for p in HISTORICO.iterdir()
        if p.is_dir()
        and (p / "metadata.json").exists()
        and (p / "general.json").exists()
        and (p / "ofensiva.json").exists()
        and (p / "defensiva.json").exists()
    )

    for carpeta in carpetas:
        try:
            snapshot = analizar_snapshot(carpeta)

            # Un snapshot histórico incompleto no se incorpora.
            errores_snapshot = validar_estructura(snapshot)

            if errores_snapshot:
                print(
                    f"\n⚠ Histórico omitido: {carpeta.name}"
                )
                for error in errores_snapshot:
                    print(f"  {error}")
                continue

            historico[carpeta.name] = snapshot

        except Exception as error:
            print(
                f"\n⚠ Error en snapshot "
                f"{carpeta.name}: {error}"
            )


with open(SALIDA_HISTORICO, "w", encoding="utf-8") as f:
    json.dump(
        historico,
        f,
        ensure_ascii=False,
        indent=2
    )


print("\nHISTÓRICO")
print(
    f"  Snapshots analizados: {len(historico)}"
)

print("\nArchivos generados:")
print(f"  {SALIDA_ACTUAL}")
print(f"  {SALIDA_HISTORICO}")

print("\n✓ Comparativo de 4 categorías | orden Sub 21 → Sub 15")
print("✓ Tabla General completa | Grupos preservados")
print("✓ Tabla Ofensiva completa")
print("✓ Tabla Defensiva completa")
print("✓ Validación 18 equipos por categoría | Sub 15/17: 9 + 9 por grupo")
print("✓ Histórico conservado")
print("✓ Datos originales no modificados")

print("\nANÁLISIS V2.6 COMPLETADO")
