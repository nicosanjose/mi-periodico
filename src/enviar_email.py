"""Envía el email matinal (o un aviso de error) vía Resend.

Modo normal:  python src/enviar_email.py
    Envía los 5 titulares del día + botón a la web.
    Necesita _trabajo/periodico.json (generado por generar.py).

Modo aviso:   python src/enviar_email.py --aviso
    Envía un email de alerta indicando que la edición de hoy ha fallado
    (lo usa el workflow cuando cualquier paso revienta).

Variables de entorno: RESEND_API_KEY, EMAIL_DESTINO
"""

import json
import os
import sys
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from publicar import fecha_larga, _listar_ediciones

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_PERIODICO = RAIZ / "_trabajo" / "periodico.json"
ARCHIVO_ESTADO = RAIZ / "_trabajo" / "estado.txt"

URL_API = "https://api.resend.com/emails"
REMITENTE = "El Primer Café <onboarding@resend.dev>"
URL_PERIODICO = os.environ.get(
    "URL_PERIODICO", "https://nicosanjose.github.io/mi-periodico/"
)


def _enviar(asunto: str, html: str) -> None:
    clave = os.environ.get("RESEND_API_KEY")
    destino = os.environ.get("EMAIL_DESTINO")
    if not clave or not destino:
        raise RuntimeError(
            "Faltan las variables RESEND_API_KEY y/o EMAIL_DESTINO"
        )
    respuesta = requests.post(
        URL_API,
        json={"from": REMITENTE, "to": [destino], "subject": asunto, "html": html},
        headers={"Authorization": f"Bearer {clave}"},
        timeout=30,
    )
    if respuesta.status_code >= 300:
        raise RuntimeError(
            f"Resend devolvió HTTP {respuesta.status_code}: {respuesta.text[:300]}"
        )
    print(f"Email enviado a {destino}: {asunto}")


def enviar_resumen(periodico: dict) -> None:
    """Email con los 5 titulares de portada y botón hacia la web."""
    entorno = Environment(
        loader=FileSystemLoader(RAIZ / "plantillas"),
        autoescape=select_autoescape(["html"]),
    )
    fecha = periodico["fecha"]
    numero = _listar_ediciones().index(fecha) + 1 if fecha in _listar_ediciones() else 1
    html = entorno.get_template("email.html").render(
        titulares=periodico["titulares_portada"][:5],
        fecha_larga=fecha_larga(fecha),
        numero=numero,
        url_periodico=URL_PERIODICO,
    )
    _enviar(f"☕ El Primer Café — {fecha_larga(fecha)}", html)


def enviar_aviso() -> None:
    """Email de alerta cuando la edición del día no se ha podido publicar."""
    paso = "desconocido"
    if ARCHIVO_ESTADO.exists():
        paso = ARCHIVO_ESTADO.read_text(encoding="utf-8").strip() or paso
    # Fuera de GitHub Actions solo puede ser una prueba manual: se marca en el
    # asunto para que nunca se confunda con un fallo real del periódico
    prueba = "" if os.environ.get("GITHUB_ACTIONS") == "true" else "[Prueba local] "
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#b3261e;">⚠️ El Primer Café no se ha publicado hoy</h2>
      <p>La generación del periódico ha fallado en el paso: <strong>{paso}</strong>.</p>
      <p>Puedes ver el detalle del error en los registros de GitHub Actions:</p>
      <p><a href="https://github.com/nicosanjose/mi-periodico/actions">
        github.com/nicosanjose/mi-periodico/actions</a></p>
      <p style="color:#6e675c;font-size:13px;">Si es un fallo puntual (un feed caído,
      un 429 de la API...), puedes relanzarlo a mano desde esa página con
      «Run workflow».</p>
    </div>"""
    _enviar(f"⚠️ {prueba}El Primer Café no se ha publicado hoy", html)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--aviso" in sys.argv:
        enviar_aviso()
    else:
        with open(ARCHIVO_PERIODICO, encoding="utf-8") as f:
            enviar_resumen(json.load(f))
