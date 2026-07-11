"""Capa de proveedor LLM. ÚNICO archivo que sabe qué API se usa.

Hoy: Gemini Flash (Google AI Studio, tier gratuito) vía REST, sin SDK.
Para cambiar de proveedor (Groq, Anthropic...) basta con reescribir
`llamar_llm()` en este archivo: el resto del código no cambia.

Contrato:  llamar_llm(prompt: str) -> str   (texto de la respuesta, que
debe ser JSON porque así se le pide; el parseo/validación se hace fuera)
"""

import os
import time

import requests

MODELO = os.environ.get("MODELO_GEMINI", "gemini-2.5-flash")
URL_API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"

INTENTOS_MAX = 4
ESPERA_INICIAL = 20  # segundos; se triplica en cada reintento (20, 60, 180)
TIMEOUT_PETICION = 300  # el modelo puede tardar con 50 artículos


def llamar_llm(prompt: str) -> str:
    """Envía el prompt a Gemini y devuelve el texto de la respuesta.

    Reintenta con espera exponencial ante 429 (límite del tier gratuito)
    y errores 5xx. Lanza RuntimeError si se agotan los intentos.
    """
    clave = os.environ.get("GEMINI_API_KEY")
    if not clave:
        raise RuntimeError(
            "Falta la variable de entorno GEMINI_API_KEY "
            "(en local: set GEMINI_API_KEY=...; en GitHub: secret del repo)"
        )

    cuerpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "response_mime_type": "application/json",
        },
    }

    espera = ESPERA_INICIAL
    ultimo_error = ""
    for intento in range(1, INTENTOS_MAX + 1):
        try:
            respuesta = requests.post(
                URL_API,
                json=cuerpo,
                headers={"x-goog-api-key": clave},
                timeout=TIMEOUT_PETICION,
            )
        except requests.RequestException as error:
            ultimo_error = f"error de red: {error}"
            respuesta = None

        if respuesta is not None:
            if respuesta.status_code == 200:
                datos = respuesta.json()
                try:
                    return datos["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    ultimo_error = f"respuesta sin texto: {str(datos)[:500]}"
            elif respuesta.status_code in (429, 500, 502, 503, 504):
                ultimo_error = f"HTTP {respuesta.status_code}: {respuesta.text[:300]}"
            else:
                # 400, 401, 403... reintentar no lo va a arreglar
                raise RuntimeError(
                    f"Gemini devolvió HTTP {respuesta.status_code}: "
                    f"{respuesta.text[:500]}"
                )

        if intento < INTENTOS_MAX:
            print(f"  [LLM] intento {intento} fallido ({ultimo_error}); "
                  f"espero {espera}s y reintento...")
            time.sleep(espera)
            espera *= 3

    raise RuntimeError(f"Gemini falló tras {INTENTOS_MAX} intentos: {ultimo_error}")
