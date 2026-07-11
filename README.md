# ☕ El Primer Café

Tu periódico personal automatizado. Cada mañana (~6:30, hora de Madrid) este
repositorio se despierta solo, lee las noticias de las últimas 24 horas en
~18 medios, las convierte en un briefing de analista con IA (Gemini) y:

- **Publica la web:** https://nicosanjose.github.io/mi-periodico/
- **Te envía un email** con los 5 titulares del día y enlace al periódico completo.

**Todo el sistema es 100% gratuito**: GitHub Actions + GitHub Pages (gratis en
repos públicos), Gemini Flash (tier gratuito de Google AI Studio) y Resend
(100 emails/día gratis).

---

## Configuración inicial (solo se hace una vez, ~15 minutos)

### Paso 1 — Consigue tu API key de Gemini (gratis)

1. Entra en **https://aistudio.google.com** e inicia sesión con tu cuenta de Google.
2. Pulsa **"Get API key"** (arriba a la izquierda o en el menú).
3. Pulsa **"Create API key"** y elige el proyecto que te proponga por defecto.
4. Copia la clave (una cadena larga que empieza por `AIza...`) y guárdala un momento
   en el bloc de notas. **No la compartas con nadie ni la pegues en ningún archivo del repo.**

> El tier gratuito da cientos de peticiones al día. El periódico usa **1 o 2 al día**.
> No hace falta meter ninguna tarjeta.

### Paso 2 — Crea tu cuenta de Resend (el email, gratis)

1. Entra en **https://resend.com** y regístrate **con tu email personal**
   (el mismo en el que quieres recibir el periódico).
2. Confirma tu cuenta desde el email que te llega.
3. En el menú lateral, ve a **API Keys → Create API Key**. Dale un nombre
   (p. ej. `periodico`), permiso "Sending access" y pulsa crear.
4. Copia la clave (empieza por `re_...`) y guárdala un momento.

> **Importante:** sin verificar un dominio propio, Resend solo permite enviar emails
> **a la dirección con la que te registraste**, desde el remitente `onboarding@resend.dev`.
> Para un periódico personal es exactamente lo que necesitamos, así que no hay que
> configurar nada más. (Si algún día quieres un remitente bonito tipo
> `cafe@tudominio.com`, se verifica un dominio en Resend → Domains.)

### Paso 3 — Guarda las claves como "secrets" en GitHub

Los secrets son la caja fuerte de GitHub: el código los usa pero nunca se ven.

1. Abre **https://github.com/nicosanjose/mi-periodico/settings/secrets/actions**
2. Pulsa **"New repository secret"** y crea estos (uno por uno):

| Nombre del secret | Valor |
|---|---|
| `GEMINI_API_KEY` | la clave del Paso 1 (`AIza...`) |
| `RESEND_API_KEY` | la clave del Paso 2 (`re_...`) |
| `EMAIL_DESTINO` | tu email (donde recibirás el periódico) |

Escribe los nombres EXACTAMENTE así, en mayúsculas.

### Paso 4 — Comprueba que GitHub Pages está activo

1. Abre **https://github.com/nicosanjose/mi-periodico/settings/pages**
2. En "Build and deployment" debe poner: **Source: Deploy from a branch**,
   rama **main**, carpeta **/docs**. Si no, selecciónalo y pulsa Save.
3. En unos minutos la web estará en https://nicosanjose.github.io/mi-periodico/

### Paso 5 — Lanza una edición de prueba

1. Abre **https://github.com/nicosanjose/mi-periodico/actions**
2. Entra en el workflow **"El Primer Café diario"** (menú izquierdo).
3. Pulsa **"Run workflow" → "Run workflow"** (el botón verde).
4. En 2-3 minutos: revisa tu bandeja de entrada (mira spam la primera vez y marca
   "no es spam") y abre la web. Si algo falla, te llegará un email de aviso con
   el enlace a los registros.

**Listo.** A partir de ahora se publica solo cada mañana. No hay que hacer nada más.

---

## Uso diario

- **Email a primera hora** con los 5 titulares → botón para leer el periódico completo.
- **Web:** portada siempre con la edición de hoy; la **Hemeroteca** guarda todas las anteriores.
- Si un día no llega: mira https://github.com/nicosanjose/mi-periodico/actions y
  relanza con "Run workflow" (o espera al día siguiente; no se rompe nada).

## Cómo cambiar cosas

Todo se puede editar desde la web de GitHub: abre el archivo, pulsa el lápiz ✏️,
edita y pulsa "Commit changes".

| Quiero... | Archivo |
|---|---|
| Añadir/quitar medios (fuentes RSS) | `config/fuentes.yaml` (sigue el formato existente) |
| Cambiar los bloques del periódico o su criterio editorial | `src/generar.py` (lista `BLOQUES` al principio) |
| Cambiar el tono o las reglas de redacción | `src/generar.py` (`PLANTILLA_PROMPT`) |
| Cambiar el diseño de la web | `docs/estilo.css` y `plantillas/periodico.html` |
| Cambiar el email | `plantillas/email.html` |
| Cambiar la hora de publicación | `.github/workflows/diario.yml` (el `cron`, en UTC) y la ventana horaria en `src/diario.py` |
| Cambiar de proveedor de IA (si Gemini cambia sus límites) | **solo** `src/llm.py` |

## Cómo funciona por dentro

```
GitHub Actions (cron diario, 2 disparos UTC para cubrir verano/invierno)
   └── src/diario.py           ¿Es la hora en Madrid? ¿Ya existe la edición de hoy?
         ├── src/recopilar.py  Lee los RSS, filtra 24h, deduplica, máx. 50 artículos
         ├── src/generar.py    Prompt editorial → Gemini → JSON validado (reintentos)
         ├── src/publicar.py   Renderiza docs/ (edición, portada, hemeroteca)
         └── src/enviar_email.py  Email vía Resend
   └── (si algo falla) → email de aviso automático
```

- El concepto del día no se repite: los usados se guardan en `config/conceptos_usados.json`.
- El LLM nunca escribe URLs: cita IDs de artículos y el código pone los enlaces reales.
- Un feed caído no rompe nada: se registra el error y se sigue con el resto.

## Ejecutar en local (opcional, para curiosos)

```bash
pip install -r requirements.txt
set GEMINI_API_KEY=AIza...      # en PowerShell: $env:GEMINI_API_KEY="AIza..."
set RESEND_API_KEY=re_...
set EMAIL_DESTINO=tu@email.com
python src/diario.py --forzar
```
