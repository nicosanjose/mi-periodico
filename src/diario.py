"""Orquestador diario de El Primer Café.

Ejecuta la cadena completa: recopilar RSS -> generar con el LLM ->
publicar la web -> enviar el email. Antes comprueba dos guardas:

1. Que en Madrid sean ya las 06:00 o más tarde. Solo hay tope inferior:
   su única función es descartar el disparo "de invierno" que cae a las
   05:25 locales. No hay tope superior porque los cron de GitHub son
   "best effort" y pueden llegar con horas de retraso (el 12-jul-2026
   llegó a las 09:04 y una ventana con techo dejó el día sin periódico).
2. Que la edición de hoy no exista ya (idempotencia: de los varios
   disparos diarios de respaldo, solo el primero publica).

Con FORZAR=true (o --forzar) se saltan ambas guardas, para pruebas.

Va apuntando el paso actual en _trabajo/estado.txt para que, si algo
revienta, el email de aviso diga en qué paso fue.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from recopilar import recopilar
from generar import generar
from publicar import publicar, CARPETA_EDICIONES
from enviar_email import enviar_resumen

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_CONCEPTOS = RAIZ / "config" / "conceptos_usados.json"
ARCHIVO_PERIODICO = RAIZ / "_trabajo" / "periodico.json"
ARCHIVO_ESTADO = RAIZ / "_trabajo" / "estado.txt"


def _paso(nombre: str) -> None:
    print(f"\n=== {nombre} ===")
    ARCHIVO_ESTADO.parent.mkdir(exist_ok=True)
    ARCHIVO_ESTADO.write_text(nombre, encoding="utf-8")


def main() -> None:
    forzar = "--forzar" in sys.argv or os.environ.get("FORZAR", "").lower() == "true"
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    hoy = ahora.strftime("%Y-%m-%d")

    if not forzar:
        if ahora.hour < 6:
            print(f"Son las {ahora:%H:%M} en Madrid (antes de las 06:00): "
                  f"este disparo no publica. Todo bien.")
            return
        if (CARPETA_EDICIONES / f"{hoy}.html").exists():
            print(f"La edición de {hoy} ya está publicada: nada que hacer.")
            return

    _paso("recopilar")
    articulos = recopilar()

    _paso("generar")
    with open(ARCHIVO_CONCEPTOS, encoding="utf-8") as f:
        conceptos = json.load(f)
    periodico = generar(articulos, conceptos)
    with open(ARCHIVO_PERIODICO, "w", encoding="utf-8") as f:
        json.dump(periodico, f, ensure_ascii=False, indent=2)
    conceptos.append(periodico["concepto_del_dia"]["termino"])
    with open(ARCHIVO_CONCEPTOS, "w", encoding="utf-8") as f:
        json.dump(conceptos, f, ensure_ascii=False, indent=2)

    _paso("publicar")
    publicar(periodico)

    _paso("enviar_email")
    enviar_resumen(periodico)

    ARCHIVO_ESTADO.unlink(missing_ok=True)
    print(f"\nEdición de {hoy} completada. ☕")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
