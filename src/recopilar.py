"""Recopila los artículos de las últimas 24 horas desde los feeds RSS.

Lee config/fuentes.yaml, descarga cada feed (tolerando fallos), filtra por
fecha, deduplica historias repetidas entre medios y limita el total a
MAX_ARTICULOS antes de pasarlos al LLM.

Uso directo (para probar):  python src/recopilar.py
"""

import difflib
import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_FUENTES = RAIZ / "config" / "fuentes.yaml"
ARCHIVO_TRABAJO = RAIZ / "_trabajo" / "articulos.json"

MAX_ARTICULOS = 50
HORAS_VENTANA = 24
TIMEOUT_FEED = 15  # segundos por feed
MAX_DESCRIPCION = 300  # caracteres de la descripción que viajan al LLM

# Reparto del cupo global de 50 artículos entre bloques (suma 50)
CUPO_POR_BLOQUE = {
    "geopolitica": 12,
    "economia": 12,
    "tecnologia": 10,
    "espana": 10,
    "cultura": 6,
}

CABECERAS_HTTP = {
    # Algunos medios rechazan peticiones sin User-Agent de navegador
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ElPrimerCafe/1.0",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _limpiar_texto(texto: str) -> str:
    """Quita etiquetas HTML y espacios repetidos de un campo del RSS."""
    if not texto:
        return ""
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_titular(titular: str) -> str:
    """Versión sin tildes, minúsculas y sin signos, para comparar titulares."""
    texto = unicodedata.normalize("NFKD", titular.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", texto)


def _fecha_entrada(entrada) -> datetime | None:
    """Fecha de publicación de una entrada del feed, en UTC, si existe."""
    for campo in ("published_parsed", "updated_parsed"):
        valor = entrada.get(campo)
        if valor:
            try:
                return datetime(*valor[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _leer_feed(nombre: str, url: str) -> list[dict]:
    """Descarga y parsea un feed. Si falla, devuelve lista vacía (no rompe)."""
    respuesta = requests.get(url, headers=CABECERAS_HTTP, timeout=TIMEOUT_FEED)
    respuesta.raise_for_status()
    feed = feedparser.parse(respuesta.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"XML ilegible ({feed.bozo_exception})")

    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_VENTANA)
    articulos = []
    for entrada in feed.entries:
        titular = _limpiar_texto(entrada.get("title", ""))
        enlace = entrada.get("link", "")
        if not titular or not enlace:
            continue
        fecha = _fecha_entrada(entrada)
        if fecha and fecha < limite:
            continue  # más antiguo que la ventana de 24h
        descripcion = _limpiar_texto(
            entrada.get("summary", "") or entrada.get("description", "")
        )[:MAX_DESCRIPCION]
        articulos.append(
            {
                "titular": titular,
                "descripcion": descripcion,
                "fecha": fecha.isoformat() if fecha else None,
                "fuentes": [{"nombre": nombre, "url": enlace}],
            }
        )
    return articulos


def _deduplicar(articulos: list[dict]) -> list[dict]:
    """Fusiona artículos con titulares casi idénticos (misma historia en
    varios medios): se queda el primero y acumula las fuentes del resto."""
    unicos: list[dict] = []
    for articulo in articulos:
        clave = _normalizar_titular(articulo["titular"])
        duplicado_de = None
        for existente in unicos:
            parecido = difflib.SequenceMatcher(
                None, clave, _normalizar_titular(existente["titular"])
            ).ratio()
            if parecido >= 0.85:
                duplicado_de = existente
                break
        if duplicado_de:
            ya_citados = {f["nombre"] for f in duplicado_de["fuentes"]}
            for fuente in articulo["fuentes"]:
                if fuente["nombre"] not in ya_citados:
                    duplicado_de["fuentes"].append(fuente)
        else:
            unicos.append(articulo)
    return unicos


def _priorizar(articulos: list[dict], cupo: int) -> list[dict]:
    """Si un bloque supera su cupo, reparte por rondas entre medios (para no
    quedarse solo con el más prolífico) priorizando lo más reciente."""
    if len(articulos) <= cupo:
        return articulos

    por_medio: dict[str, list[dict]] = {}
    for articulo in articulos:
        por_medio.setdefault(articulo["fuentes"][0]["nombre"], []).append(articulo)
    for lista in por_medio.values():
        lista.sort(key=lambda a: a["fecha"] or "", reverse=True)

    seleccion: list[dict] = []
    while len(seleccion) < cupo and any(por_medio.values()):
        for medio in list(por_medio):
            if por_medio[medio]:
                seleccion.append(por_medio[medio].pop(0))
                if len(seleccion) >= cupo:
                    break
    return seleccion


def recopilar() -> dict[str, list[dict]]:
    """Punto de entrada: devuelve {bloque: [artículos]} listo para el LLM."""
    with open(ARCHIVO_FUENTES, encoding="utf-8") as f:
        fuentes = yaml.safe_load(f)

    resultado: dict[str, list[dict]] = {}
    errores = []
    for bloque, medios in fuentes.items():
        articulos_bloque: list[dict] = []
        for medio in medios:
            try:
                articulos = _leer_feed(medio["nombre"], medio["url"])
                print(f"  [OK]    {medio['nombre']}: {len(articulos)} articulos en 24h")
                articulos_bloque.extend(articulos)
            except Exception as error:  # un feed caído nunca rompe el periódico
                print(f"  [ERROR] {medio['nombre']}: {error}")
                errores.append(f"{medio['nombre']}: {error}")
        articulos_bloque = _deduplicar(articulos_bloque)
        cupo = CUPO_POR_BLOQUE.get(bloque, 8)
        resultado[bloque] = _priorizar(articulos_bloque, cupo)
        print(f"[{bloque}] {len(resultado[bloque])} articulos tras dedupe y cupo")

    total = sum(len(v) for v in resultado.values())
    if total == 0:
        raise RuntimeError(
            "Ningún feed ha devuelto artículos. Errores: " + "; ".join(errores)
        )

    ARCHIVO_TRABAJO.parent.mkdir(exist_ok=True)
    with open(ARCHIVO_TRABAJO, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"\nTotal: {total} articulos (max {MAX_ARTICULOS}) -> {ARCHIVO_TRABAJO}")
    return resultado


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    recopilar()
