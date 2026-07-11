"""Convierte los artículos recopilados en el periódico del día.

Construye el prompt editorial, llama al LLM (vía llm.py), valida que el
JSON devuelto tenga la estructura esperada y resuelve las fuentes reales
(el LLM solo cita IDs de artículos; los enlaces nunca los escribe él,
así no puede inventarlos).

Uso directo (para probar):  python src/generar.py
(necesita _trabajo/articulos.json generado antes por recopilar.py)
"""

import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from llm import llamar_llm

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ARTICULOS = RAIZ / "_trabajo" / "articulos.json"
ARCHIVO_PERIODICO = RAIZ / "_trabajo" / "periodico.json"
ARCHIVO_CONCEPTOS = RAIZ / "config" / "conceptos_usados.json"

# Definición editorial de los bloques, en el orden del periódico
BLOQUES = [
    {
        "id": "geopolitica",
        "titulo": "🌍 Geopolítica e internacional",
        "cuantas": "3-4",
        "criterio": (
            "Prioriza lo que un estudiante de Relaciones Internacionales "
            "debe dominar: conflictos, cumbres, giros diplomáticos, "
            "elecciones relevantes, sanciones."
        ),
    },
    {
        "id": "economia",
        "titulo": "📈 Economía y mercados",
        "cuantas": "3-4",
        "criterio": (
            "Incluye contexto de mercados si hay movimiento relevante: qué "
            "hacen bolsas, tipos de interés, divisas o materias primas."
        ),
    },
    {
        "id": "tecnologia",
        "titulo": "🤖 IA y tecnología",
        "cuantas": "2-3",
        "criterio": (
            "Prioriza IA, lanzamientos importantes y lo que afecte a la "
            "consultoría y la automatización."
        ),
    },
    {
        "id": "espana",
        "titulo": "🇪🇸 España",
        "cuantas": "2-3",
        "criterio": "Política y economía nacional; evita sucesos y deportes.",
    },
    {
        "id": "cultura",
        "titulo": "🎭 Cultura y ciencia",
        "cuantas": "1-2",
        "criterio": "Noticias o hallazgos genuinamente interesantes.",
    },
]

PLANTILLA_PROMPT = """Eres el redactor jefe de "El Primer Café", un briefing diario personal \
en español de España para un lector formado (estudiante de Relaciones Internacionales que \
trabaja en consultoría). Tono: claro y directo, como un analista explicando las noticias en \
el café. Sin jerga innecesaria, sin infantilizar, sin clickbait.

Hoy es {fecha}. Abajo tienes los artículos de las últimas 24 horas, agrupados por bloque, \
cada uno con un ID. Con ellos redacta el periódico de hoy.

REGLAS EDITORIALES (obligatorias):
1. Para cada bloque elige las mejores historias según su criterio. Si varios artículos \
cuentan LA MISMA historia, fúndelos en una sola noticia citando todos sus IDs.
2. Cada noticia lleva: "titular" (reescrito por ti, informativo, sin clickbait), \
"que_ha_pasado" (2-3 frases con los hechos) y "por_que_importa" (2-3 frases con contexto: \
antecedentes, implicaciones, conexiones con otros temas; esto es lo más valioso, ayuda a \
ENTENDER, no solo a enterarse).
3. REDACCIÓN PROPIA SIEMPRE: prohibido copiar frases de los artículos originales.
4. No inventes hechos del día que no estén en los artículos; para el contexto de \
"por_que_importa" sí puedes usar tu conocimiento general (historia, antecedentes, cómo \
funciona un mercado o una institución).
5. En "articulos" lista los IDs de los artículos en los que se basa cada noticia. Solo IDs \
que existan en el material. Nunca escribas URLs.
6. "titulares_portada": las 5 noticias más importantes del día en conjunto, cada una con su \
titular y un resumen de máximo 2 líneas. Son para el email matinal.
7. "concepto_del_dia": un término de finanzas, geopolítica o economía explicado en unas 100 \
palabras + un ejemplo real reciente. PROHIBIDO repetir estos ya usados: {conceptos_usados}.

BLOQUES Y CRITERIOS:
{descripcion_bloques}

MATERIAL DEL DÍA:
{material}

Responde SOLO con un JSON válido exactamente con esta estructura:
{{
  "titulares_portada": [
    {{"titular": "...", "resumen": "..."}}
  ],
  "bloques": [
    {{"id": "geopolitica", "noticias": [
      {{"titular": "...", "que_ha_pasado": "...", "por_que_importa": "...", "articulos": ["geo1"]}}
    ]}},
    {{"id": "economia", "noticias": [...]}},
    {{"id": "tecnologia", "noticias": [...]}},
    {{"id": "espana", "noticias": [...]}},
    {{"id": "cultura", "noticias": [...]}}
  ],
  "concepto_del_dia": {{"termino": "...", "explicacion": "...", "ejemplo": "..."}}
}}"""


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower().strip())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _indexar_articulos(articulos: dict) -> dict[str, dict]:
    """Asigna un ID corto a cada artículo (geo1, eco2...) y devuelve el índice."""
    prefijos = {"geopolitica": "geo", "economia": "eco", "tecnologia": "tec",
                "espana": "esp", "cultura": "cul"}
    indice = {}
    for bloque, lista in articulos.items():
        prefijo = prefijos.get(bloque, bloque[:3])
        for n, articulo in enumerate(lista, 1):
            indice[f"{prefijo}{n}"] = articulo
    return indice


def _material_para_prompt(indice: dict[str, dict], articulos: dict) -> str:
    """Texto compacto con los artículos del día, agrupados por bloque."""
    ids_por_articulo = {id(art): clave for clave, art in indice.items()}
    lineas = []
    for bloque_def in BLOQUES:
        lista = articulos.get(bloque_def["id"], [])
        if not lista:
            continue
        lineas.append(f"\n## Bloque {bloque_def['id']}")
        for articulo in lista:
            clave = ids_por_articulo[id(articulo)]
            medios = ", ".join(f["nombre"] for f in articulo["fuentes"])
            lineas.append(
                f"[{clave}] ({medios}) {articulo['titular']} — "
                f"{articulo['descripcion'] or 'sin descripción'}"
            )
    return "\n".join(lineas)


def _validar(periodico: dict, indice: dict, conceptos_usados: list) -> None:
    """Comprueba la estructura del JSON del LLM. Lanza ValueError si falla."""
    if not isinstance(periodico, dict):
        raise ValueError("la raíz no es un objeto JSON")

    portada = periodico.get("titulares_portada")
    if not isinstance(portada, list) or len(portada) < 3:
        raise ValueError("titulares_portada debe ser una lista de 5 elementos")
    for item in portada:
        if not item.get("titular") or not item.get("resumen"):
            raise ValueError("cada titular de portada necesita titular y resumen")

    bloques = periodico.get("bloques")
    if not isinstance(bloques, list):
        raise ValueError("falta la lista bloques")
    ids_recibidos = {b.get("id") for b in bloques}
    ids_esperados = {b["id"] for b in BLOQUES}
    if not ids_esperados.issubset(ids_recibidos):
        raise ValueError(f"faltan bloques: {ids_esperados - ids_recibidos}")
    for bloque in bloques:
        noticias = bloque.get("noticias")
        if not isinstance(noticias, list) or not noticias:
            raise ValueError(f"el bloque {bloque.get('id')} no tiene noticias")
        for noticia in noticias:
            for campo in ("titular", "que_ha_pasado", "por_que_importa"):
                if not noticia.get(campo):
                    raise ValueError(
                        f"noticia sin campo '{campo}' en {bloque.get('id')}"
                    )
            refs = noticia.get("articulos")
            if not isinstance(refs, list) or not refs:
                raise ValueError(
                    f"noticia '{noticia['titular'][:40]}' sin IDs de artículos"
                )
            desconocidos = [r for r in refs if r not in indice]
            if desconocidos:
                raise ValueError(f"IDs de artículos inexistentes: {desconocidos}")

    concepto = periodico.get("concepto_del_dia")
    if not isinstance(concepto, dict):
        raise ValueError("falta concepto_del_dia")
    for campo in ("termino", "explicacion", "ejemplo"):
        if not concepto.get(campo):
            raise ValueError(f"concepto_del_dia sin campo '{campo}'")
    usados = {_normalizar(c) for c in conceptos_usados}
    if _normalizar(concepto["termino"]) in usados:
        raise ValueError(
            f"el concepto '{concepto['termino']}' ya se usó otro día; elige otro"
        )


def _resolver_fuentes(periodico: dict, indice: dict) -> None:
    """Sustituye los IDs de artículos por las fuentes reales (nombre + URL)."""
    for bloque in periodico["bloques"]:
        for noticia in bloque["noticias"]:
            fuentes, vistos = [], set()
            for ref in noticia.pop("articulos"):
                for fuente in indice[ref]["fuentes"]:
                    if fuente["nombre"] not in vistos:
                        vistos.add(fuente["nombre"])
                        fuentes.append(fuente)
            noticia["fuentes"] = fuentes


def generar(articulos: dict, conceptos_usados: list) -> dict:
    """Punto de entrada: artículos recopilados -> periódico validado (dict)."""
    indice = _indexar_articulos(articulos)
    fecha_hoy = datetime.now(ZoneInfo("Europe/Madrid"))
    prompt = PLANTILLA_PROMPT.format(
        fecha=fecha_hoy.strftime("%Y-%m-%d"),
        conceptos_usados=", ".join(conceptos_usados) or "(ninguno todavía)",
        descripcion_bloques="\n".join(
            f"- {b['id']} («{b['titulo']}», {b['cuantas']} noticias): {b['criterio']}"
            for b in BLOQUES
        ),
        material=_material_para_prompt(indice, articulos),
    )

    ultimo_error = None
    for intento in (1, 2):  # si el JSON no valida, un único reintento
        prompt_final = prompt if intento == 1 else (
            prompt + f"\n\nATENCIÓN: tu respuesta anterior falló la validación "
            f"({ultimo_error}). Corrígelo y responde de nuevo SOLO con el JSON."
        )
        texto = llamar_llm(prompt_final)
        try:
            periodico = json.loads(texto)
            _validar(periodico, indice, conceptos_usados)
            break
        except (json.JSONDecodeError, ValueError) as error:
            ultimo_error = str(error)
            print(f"  [GENERAR] intento {intento} no válido: {ultimo_error}")
            if intento == 2:
                raise RuntimeError(
                    f"El LLM no devolvió un periódico válido: {ultimo_error}"
                )

    _resolver_fuentes(periodico, indice)

    # Orden canónico de bloques y títulos con emoji definidos aquí, no por el LLM
    titulos = {b["id"]: b["titulo"] for b in BLOQUES}
    orden = [b["id"] for b in BLOQUES]
    periodico["bloques"] = sorted(
        [b for b in periodico["bloques"] if b["id"] in titulos],
        key=lambda b: orden.index(b["id"]),
    )
    for bloque in periodico["bloques"]:
        bloque["titulo"] = titulos[bloque["id"]]
    periodico["titulares_portada"] = periodico["titulares_portada"][:5]
    periodico["fecha"] = fecha_hoy.strftime("%Y-%m-%d")
    return periodico


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ARCHIVO_ARTICULOS, encoding="utf-8") as f:
        articulos = json.load(f)
    with open(ARCHIVO_CONCEPTOS, encoding="utf-8") as f:
        conceptos = json.load(f)
    periodico = generar(articulos, conceptos)
    with open(ARCHIVO_PERIODICO, "w", encoding="utf-8") as f:
        json.dump(periodico, f, ensure_ascii=False, indent=2)
    print(f"Periodico generado -> {ARCHIVO_PERIODICO}")
    print(f"Concepto del dia: {periodico['concepto_del_dia']['termino']}")
