# Viajes Pillados

Web de ofertas de vuelos desde Colombia: https://www.instagram.com/viajespillados/

- `index.html` — la web completa (un solo archivo). Lee las ofertas de la hoja de Google "Viajes Pillados - Ofertas (web)" cada vez que alguien abre la página, así que para publicar una oferta basta con añadir una fila a la hoja.
- `logo-icon.png` — icono del logo.

Publicado con GitHub Pages.

## Instagram automático

- `scripts/instagram.py` + `.github/workflows/instagram-publish.yml` publican en @viajespillados a las 7:00 y 18:00 (Bogotá).
- Lee la misma hoja "Ofertas": **toda oferta que sale en la web se publica en Instagram** (columna N = `no` la deja fuera). Columna **O** = texto opcional; si está vacía se usa el "Caption listo" de la pestaña "Qué hacer (captions)".
- 2 posts al día: a las 7:00 sale la mitad de las ofertas pendientes y a las 18:00 el resto. Si hay varias, se publican juntas como carrusel (máx. 10); si hay una, como post normal. Solo ofertas con fecha "Publicado" de los últimos 3 días.
- Cada post lleva 5 hashtags (el máximo de Instagram): #viajespillados #vuelosbaratos #vuelosdesdebogota + destino y país (o #ofertasdevuelos #viajarbarato en carruseles).
- Imágenes en `instagram/img/`, registro de lo publicado en `instagram/published.json`.
- Probar sin publicar: Actions → "Instagram – publicar ofertas" → Run workflow → `preview` (o `check` para probar la conexión).
- Secretos: `IG_ACCESS_TOKEN`, `IG_USER_ID`. El token se renueva solo cada 2 semanas (`instagram-token.yml`).
