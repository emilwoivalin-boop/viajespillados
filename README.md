# Viajes Pillados

Web de ofertas de vuelos desde Colombia: https://www.instagram.com/viajespillados/

- `index.html` — la web completa (un solo archivo). Lee las ofertas de la hoja de Google "Viajes Pillados - Ofertas (web)" cada vez que alguien abre la página, así que para publicar una oferta basta con añadir una fila a la hoja.
- `logo-icon.png` — icono del logo.

Publicado con GitHub Pages.

## Instagram automático

- `scripts/instagram.py` + `.github/workflows/instagram-publish.yml` publican en @viajespillados a las 7:00 y 18:00 (Bogotá).
- Lee la misma hoja "Ofertas". Columna **N "Instagram"**: `sí`/`auto` = publicar, `revisar` o vacío = espera aprobación, `no` = nunca. Columna **O "Texto Instagram"** = texto del post opcional; si está vacía se usa el "Caption listo" de la pestaña "Qué hacer (captions)".
- Solo publica ofertas con fecha "Publicado" de los últimos 3 días, una por turno, y no repite destino en 5 días.
- Imágenes en `instagram/img/`, registro de lo publicado en `instagram/published.json`.
- Probar sin publicar: Actions → "Instagram – publicar ofertas" → Run workflow → `preview` (o `check` para probar la conexión).
- Secretos: `IG_ACCESS_TOKEN`, `IG_USER_ID`. El token se renueva solo cada 2 semanas (`instagram-token.yml`).
