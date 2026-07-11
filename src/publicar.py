"""Renderiza el periódico (dict) a HTML estático en docs/ (GitHub Pages).

- docs/ediciones/YYYY-MM-DD.html  (edición archivada)
- docs/index.html                 (siempre la edición más reciente)
- docs/hemeroteca.html            (listado de todas las ediciones)

Uso directo (para probar):  python src/publicar.py
(necesita _trabajo/periodico.json generado antes por generar.py)
"""

import json
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DOCS = RAIZ / "docs"
CARPETA_EDICIONES = CARPETA_DOCS / "ediciones"
ARCHIVO_PERIODICO = RAIZ / "_trabajo" / "periodico.json"

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_entorno = Environment(
    loader=FileSystemLoader(RAIZ / "plantillas"),
    autoescape=select_autoescape(["html"]),
)


def fecha_larga(fecha_iso: str) -> str:
    """'2026-07-11' -> 'Sábado, 11 de julio de 2026' (sin depender del locale)."""
    fecha = date.fromisoformat(fecha_iso)
    return (f"{DIAS[fecha.weekday()]}, {fecha.day} de "
            f"{MESES[fecha.month - 1]} de {fecha.year}")


def _listar_ediciones() -> list[str]:
    """Fechas (ISO) de las ediciones ya publicadas, de más antigua a más nueva."""
    if not CARPETA_EDICIONES.exists():
        return []
    return sorted(p.stem for p in CARPETA_EDICIONES.glob("????-??-??.html"))


def publicar(periodico: dict) -> Path:
    """Escribe la edición, la portada y la hemeroteca. Devuelve la ruta index."""
    fecha = periodico["fecha"]
    fechas = _listar_ediciones()
    if fecha not in fechas:
        fechas.append(fecha)
        fechas.sort()
    numero = fechas.index(fecha) + 1

    plantilla = _entorno.get_template("periodico.html")
    contexto = {
        "periodico": periodico,
        "fecha_larga": fecha_larga(fecha),
        "numero": numero,
    }

    CARPETA_EDICIONES.mkdir(parents=True, exist_ok=True)
    ruta_edicion = CARPETA_EDICIONES / f"{fecha}.html"
    ruta_edicion.write_text(
        plantilla.render(raiz="../", **contexto), encoding="utf-8"
    )
    # El JSON de cada edición se archiva junto al HTML: permite re-renderizar
    # ediciones antiguas cuando cambie el diseño de las plantillas
    (CARPETA_EDICIONES / f"{fecha}.json").write_text(
        json.dumps(periodico, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # La portada solo se sobrescribe si esta edición es la más reciente
    if fecha == fechas[-1]:
        (CARPETA_DOCS / "index.html").write_text(
            plantilla.render(raiz="", **contexto), encoding="utf-8"
        )

    ediciones = [
        {"fecha": f, "fecha_larga": fecha_larga(f), "numero": n}
        for n, f in enumerate(fechas, 1)
    ]
    ediciones.reverse()  # la más reciente primero
    (CARPETA_DOCS / "hemeroteca.html").write_text(
        _entorno.get_template("hemeroteca.html").render(ediciones=ediciones),
        encoding="utf-8",
    )

    print(f"Publicado: {ruta_edicion.name} (edicion n.{numero}), "
          f"index.html y hemeroteca.html actualizados")
    return CARPETA_DOCS / "index.html"


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ARCHIVO_PERIODICO, encoding="utf-8") as f:
        publicar(json.load(f))
