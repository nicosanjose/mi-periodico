# El Primer Café — contexto del proyecto

Periódico personal diario 100% automatizado y 100% gratuito de Nico. Se publica
solo cada mañana (~6:30 Madrid) vía GitHub Actions: RSS → Gemini → web estática
en GitHub Pages + email por Resend. Nico no programa: explica los cambios paso
a paso y no des nada por sabido.

- **Web:** https://nicosanjose.github.io/mi-periodico/ (Pages sirve `docs/` de `main`)
- **Repo:** nicosanjose/mi-periodico (público; es PERSONAL, no de Snowden)
- **Email:** Resend, remitente `onboarding@resend.dev` → solo puede enviar al email
  de la cuenta de Nico (sin dominio verificado). Secrets: `GEMINI_API_KEY`,
  `RESEND_API_KEY`, `EMAIL_DESTINO`.

## Arquitectura y decisiones clave

- `src/diario.py` orquesta todo y aplica DOS GUARDAS: nunca antes de las 06:00
  de Madrid (SIN tope superior — GOTCHA: los cron de GitHub son best-effort y
  el 12-jul-2026 llegaron con ~3h de retraso y un disparo perdido; una ventana
  con techo dejó el día sin periódico) e idempotencia (si
  `docs/ediciones/<hoy>.html` existe, no repite). El cron dispara 4 veces
  (04:25, 05:25, 07:25, 09:25 UTC): verano/invierno + 2 respaldos; solo el
  primero que llegue publica. `FORZAR=true` o `--forzar` salta las guardas
  (es el default del workflow_dispatch).
- `src/llm.py` es la ÚNICA capa que conoce al proveedor (Gemini REST v1beta,
  `gemini-2.5-flash`, sin SDK). Cambiar de proveedor = reescribir solo este
  archivo manteniendo el contrato `llamar_llm(prompt) -> str` (texto JSON).
  Backoff exponencial 20/60/180s ante 429 y 5xx.
- `src/generar.py`: el LLM NUNCA escribe URLs; cita IDs de artículos (`geo1`,
  `eco2`...) y `_resolver_fuentes()` pone los enlaces reales. Validación
  estricta del JSON con 1 reintento citando el error. Los bloques y el prompt
  editorial viven en `BLOQUES` y `PLANTILLA_PROMPT` al principio del archivo.
- El concepto del día se acumula en `config/conceptos_usados.json` (el workflow
  lo commitea junto a `docs/`); la validación rechaza repetidos.
- `src/publicar.py`: Jinja2 desde `plantillas/`; fecha en español con mapas
  propios (sin locale); número de edición = posición cronológica del archivo en
  `docs/ediciones/`. `index.html` solo se sobrescribe si la edición es la más
  reciente. `raiz` ("" o "../") ajusta rutas relativas portada/archivo.
- Feeds en `config/fuentes.yaml`: un feed caído se loguea y se sigue. OJO:
  Reuters cerró sus RSS públicos; se usan The Guardian World/Business en su lugar.
- Si cualquier paso falla, el workflow manda email de aviso (`--aviso`); el paso
  actual queda apuntado en `_trabajo/estado.txt`.
- `_trabajo/` es efímero y está en .gitignore (artículos del día, periodico.json,
  capturas de verificación).

## Convenciones

- Código, comentarios, logs y commits en español. Nombres de archivo/función en
  español (recopilar, generar, publicar).
- Windows local: stdout se reconfigura a UTF-8 en cada `__main__`; `tzdata` está
  en requirements porque zoneinfo lo necesita en Windows.
- Sin frameworks en la web: HTML + CSS puro (`docs/estilo.css`), mobile-first.
  Sistema de diseño (rediseño jul-2026, skills Snowden): Fraunces (serif
  variable, Google Fonts) para masthead/titulares + Instrument Sans para
  cuerpo; paleta papel #f8f3ea / tinta #211d17 / UN solo acento café #7c4a23;
  grano de papel (SVG feTurbulence en capa fija pointer-events:none); SIN
  emojis en la UI (secciones numeradas 01-06 estilo FT); "Por qué importa"
  como bloque con filete café; "Concepto del día" como placa espresso oscura
  #251d14 (el único card de la página); animación solo de entrada
  (cabecera/índice/esencial, 700ms cubic-bezier(0.23,1,0.32,1)) con
  prefers-reduced-motion y hover tras @media (hover:hover).
- Cada edición archiva también su JSON en `docs/ediciones/<fecha>.json`:
  para rediseñar, re-renderizar desde ahí (nunca reconstruir del HTML).

## Probar

- Local sin API keys: `python src/recopilar.py` (RSS reales) y
  `python src/publicar.py` (si hay `_trabajo/periodico.json`).
- Local completo: exportar los 3 secrets y `python src/diario.py --forzar`.
- En GitHub: pestaña Actions → "El Primer Café diario" → Run workflow.
- Verificación visual: capturas Playwright (`channel="chrome"`) como en
  `_trabajo/capturas.py`.
