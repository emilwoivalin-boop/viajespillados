# Viajes Pillados

Web de ofertas de vuelos desde Colombia: https://www.instagram.com/viajespillados/

- `index.html` — la web completa (un solo archivo). Lee las ofertas de la hoja de Google "Viajes Pillados - Ofertas (web)" cada vez que alguien abre la página, así que para publicar una oferta basta con añadir una fila a la hoja.
- `logo-icon.png` — icono del logo.

Publicado con GitHub Pages.

## Instagram (publicación manual con música)

- Cada día a las 6:37 y 13:07 (Bogotá) `.github/workflows/instagram-publish.yml` prepara los posts: imagen 1080×1350 + texto, en **https://viajespillados.com/publicar/** (página oculta, no indexada).
- Desde el celular: Copiar texto → Compartir imagen a Instagram → agregar música → pegar texto → publicar → "Ya lo publiqué".
- Aparecen las ofertas de "Ofertas" con fecha "Publicado" de los últimos 3 días. Columna **N "Instagram"**: `sí` = Recomendado, `revisar`/vacío = Por revisar, `no` o `publicado` = no aparece.
- El texto sale de la pestaña "Qué hacer (captions)" (columna "Caption listo"); la columna **O** de "Ofertas" lo reemplaza si tiene algo.
- Actions → "Instagram – publicar ofertas" → Run workflow: `prepare` (actualizar ya), `preview`, `check` (probar conexión) o `publish` + destino (publicar directo por API, sin música).
- Secretos: `IG_ACCESS_TOKEN`, `IG_USER_ID`. El token se renueva solo cada 2 semanas (`instagram-token.yml`).
