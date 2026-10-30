# Daily Reel – how it works

One Spanish (Colombia) Reel per day about the best tracked offer, same format as the approved
Aruba Reel (`reels/aruba-abril-2027-cartoon-es`). Three scheduled tasks run it:

| Bogotá time | Task | What it does |
|---|---|---|
| 06:41 | **A · prepare** | picks the offer, writes the script and 5 picture prompts, creates today's Drive folder, sends the prompts to the owner |
| (owner) | — | makes the 5 pictures in the Gemini app and uploads them to today's Drive folder **before 11:20** |
| 11:23 | **B · build** | downloads the pictures, places stick man / sticker / sound, renders the video, checks it |
| 12:14 | **C · post** | publishes the rendered Reel on Instagram |

State lives in `reels/daily.json` (one entry per Bogotá date):
`{"2026-10-30": {"id": "lima-2027-01-16", "destino": "Lima", "status": "prompts_sent", "drive_folder_id": "...", "note": ""}}`
Status flow: `prompts_sent` → `rendered` → `published`, or `skipped` (with a note).

Common facts
- Repo: `emilwoivalin-boop/viajespillados` (GitHub Pages site viajespillados.com). In a fresh session attach it with the
  add_repo tool (owner `emilwoivalin-boop`, repo `viajespillados`, access `push`), clone it to `/home/claude/viajespillados`,
  set `git config user.name "viajespillados-bot"` and `git config user.email "41898282+github-actions[bot]@users.noreply.github.com"`.
  Always `git pull --rebase` before committing; retry `git pull --rebase && git push` if a push is rejected.
- Workflows are started with
  `gh api -X POST repos/emilwoivalin-boop/viajespillados/actions/workflows/reel.yml/dispatches -f ref=main -f 'inputs[mode]=<render|publish|fetch>' -f 'inputs[id]=<id>'`
  then find the run with `gh run list -R emilwoivalin-boop/viajespillados -w reel.yml -L 1` and poll `gh run view <run> --json status,conclusion` every 20 s.
  On failure read `reels/<id>/error.txt` (after `git pull`).
- Offers sheet: `1us2JZr8rQRmeYlMTke9k2nPU26Cp6MLYQbtz3fHeL3c` (tab `Ofertas`, columns A Publicar … P Fechas; tab `Qué hacer (captions)`:
  A Destino, B País, C Región, D Qué hacer, E Ojo).
  Price log: `1SO2lHr3GvY01kRaBNPLtGPZ-OgWoNblqm7XtTIJO9PY` tab `Price log` (headers row 4; C Destination (English), D Trip type,
  H Price, Q Depart date, R Return date, S Workdays off, X Score 0–10, Y Final flag).
- Drive parent folder "Viajes Pillados – Reels": `1_9RYH30SlCRgR-MGv_Kpq3K-jFLMBuSm` (shared "anyone with the link can view",
  so the GitHub workflow can download the pictures).
- Helper: `python scripts/reel_plan.py info <ida> <vuelta>` (Spanish dates, days, workdays off),
  `python scripts/reel_plan.py build <id>` (plan.json → storyboard.json), `python scripts/reel_plan.py preview <id> <out.jpg>`
  (one frame per scene with stick man + sticker – look at it with the Read tool).

---------------------------------------------------------------------------------------------------

## A · prepare (06:41)

1. Today = Bogotá date. If `reels/daily.json` already has today with status other than `skipped`, stop (already done).
2. **Pick the offer** ("best tracked offer"):
   - Candidates = rows of `Ofertas` with A Publicar ≠ "no", a ROUND-TRIP date in P (`YYYY-MM-DD/YYYY-MM-DD`), departure at least
     4 days from today, and the Destino present in column A of `Qué hacer (captions)`.
   - Exclude destinations that already had a daily Reel in the last 14 days (`reels/daily.json`, statuses other than `skipped`),
     and the exact same offer (destino + dates) ever.
   - Rank: find the matching `Price log` row (same depart/return dates and price within 3 %; destination names are English there,
     e.g. "Panama City" = "Ciudad de Panamá") and use its Score (X), highest first; ties → fewer workdays off (S) → bigger
     "% below usual low" (L) → newest Publicado (B). An offer without a matching log row ranks after all matched ones.
   - If there is no candidate: add today as `skipped` with note "no tracked round-trip offer", commit, and tell the owner in one line. Stop.
3. `id` = `<slug-destino>-<ida>` (e.g. `lima-2027-01-16`). Create `reels/<id>/plan.json` (format in `scripts/reel_plan.py`):
   `offer` = destino, aerolinea, precio (number), escalas ("directo" / "1 escala" / "N escalas"), ida, vuelta, link (J), sheet_row;
   `hora_salida` = null (only fill it, e.g. "4 de la tarde", if you verified the airline's scheduled departure time for that
   weekday from a reliable timetable page; otherwise leave null); `que_hacer` = column D of `Qué hacer`; `end_image` = "dia1".
4. **Script lines** (`lines`, Spanish from Colombia, tú, short and lively like the Aruba Reel; 8–20 words each; no prices, no airline):
   - `vuelo`: the flight, e.g. "Dos horas de vuelo directo, y el mar abajo se pone turquesa." Only state the flight time if you
     know it (Price log Notes "N hrs"); say "directo" only for non-stop.
   - `llegada`: "¡Bienvenido a <Destino>! …" + one sensory detail of arriving there.
   - `dia1`, `dia2`, `dia3`: start with "Día uno:", "Día dos:", "Día tres:" (for trips of 2–3 days use "Primer día:", "Luego:",
     "Antes de volver:"), one activity each, taken from the three activities in `Qué hacer` column D, in that order, with one
     concrete vivid detail. Only facts you are sure about.
   The opening line (date + El Dorado), the return line (with the workdays-off sentence) and the price ending are added
   automatically by `reel_plan.py build` – don't write them.
5. **Picture prompts** (`prompts`, English, one per key). Every prompt = this style block + scene description + layout rule:
   - Style block: `Very simple flat cartoon illustration, clean bold black outlines, flat bright colors, minimal detail, no gradients, children's book style, no people, no text, no letters, vertical 9:16.`
   - `vuelo`: view from high above the clouds with a small white airplane, and the landscape of the destination region far below (sea and islands, mountains, city…).
   - `llegada`: outside the destination's airport or arrival spot, with a typical local detail (palms, mountains, skyline…), with an empty sidewalk in the lower third.
   - `dia1`/`dia2`/`dia3`: the place of that day's activity, recognisable (landmark shapes, colours, nature), and a clear empty area where a small stick figure can stand / sit / walk (say where: "empty sand in the lower half", "the trail is clearly visible and empty").
   - Use the time of day that fits the line (evening activities → sunset sky).
6. **Drive**: in the parent folder create a folder `<YYYY-MM-DD> <Destino>` (Drive tool create_file, mimeType folder, parentId above),
   and inside it a Google Doc "Prompts" with the 5 prompts numbered 1–5 in the order vuelo, llegada, dia1, dia2, dia3.
   Save its id as `drive_folder_id` in plan.json and in `reels/daily.json` (status `prompts_sent`). Commit + push.
7. **Final output** (the owner reads this on the phone; keep it short, Spanish is fine):
   destino, fechas, precio, why it was picked (score / % below usual), the Drive folder link
   `https://drive.google.com/drive/folders/<id>`, and the 5 prompts numbered 1–5, each in its own code block so they are easy to copy.
   Remind: "Sube las 5 imágenes a la carpeta en este orden (o nómbralas 1–5) antes de las 11:20."

## B · build (11:23)

1. Load today's entry from `reels/daily.json`; continue only if status is `prompts_sent`.
2. List the images in the Drive folder (search_files `parentId = '<folder>' and mimeType contains 'image/'`, excludeContentSnippets).
   Order: files whose names start with 1–5 by that number, otherwise by createdTime (oldest first). Map to vuelo, llegada, dia1, dia2, dia3.
   - If fewer than 5 images: if it is before 11:50, wait 5 minutes and check again (up to 5 times). Still missing → set status
     `skipped` with note "faltaron imágenes (N/5)", commit, tell the owner in one line, stop.
3. Write `drive_files` {key: fileId} into plan.json, commit + push, run the workflow with mode `fetch`. `git pull`; the pictures are
   now in `reels/<id>/img/<key>.jpg`.
4. **Look at each picture** (Read tool) and fill `plan.scenes[key]`:
   - `stick`: the classic stick man doing something that fits the line and the picture, placed ON the ground / sand / path / water
     where it is empty. Coordinates are fractions of the 1080×1920 frame (pictures are cover-fitted to 9:16): `x0`/`x1` = start/end x
     of his body centre, `y` (and optional `y1`) = where his FEET are, `size` (and optional `size1`) = body height in px
     (≈ 500 close to the camera at the bottom, ≈ 250–350 in the middle distance, ≈ 150 far away), `facing` 1 = right, −1 = left.
     Actions: `walk`, `suitcase`, `wave`, `celebrate` (arrival!), `relax` (lying on a towel – beaches/parks), `swim` (snorkel – `y`
     is the water level of his body), `drive` (jeep on a road), `photo` (viewpoints, landmarks, sunsets), `none` (flight scene).
     Keep him out of the top 33 % (captions live there) unless he swims.
     Reference values that looked right in the Aruba Reel: arrival celebrate {x0 .45, y .9, size 400}; beach relax {x .63, y .475,
     size 380} (on sand in the tree shadow); jeep coming down a path {x0 .47→.40, y .60→.97, size 150→460, facing −1};
     swim {x0 .10→.65, y .37, size 380}; lighthouse photo {x .28, y .67, size 340}.
   - `pop` (optional, max 1, only when it adds meaning): one sticker `{icon, word, x, y, size}` – icons: sun, heart, sparkle, pin,
     plane, fish, suitcase, clock, camera. `word` must be a word of that scene's line (it pops when the voice says it); put it next
     to the thing it refers to (sun in the sky, pin on the place, sparkle on a sign…), not on the stick man and not in y .18–.33.
     Size 170–230. Use stickers on at most 3 of the 5 pictures.
   - `ambience` (optional, max 1): `waves` (beach / sea at the coast) or `crickets` (warm night). If set, the stick man's action
     sound is muted on that picture (max one extra sound per picture). The whoosh between pictures and the chime at the price
     reveal are always there.
5. `python scripts/reel_plan.py build <id>` and `python scripts/reel_plan.py preview <id> /tmp/preview.jpg`; Read the preview and
   fix anything that looks wrong (floating stick man, sticker on top of something, stick man hidden). Commit + push.
6. Run the workflow with mode `render`. `git pull`, check `reels/<id>/reel.mp4` exists (duration 30–55 s) and look at a contact
   sheet: `ffmpeg -i reels/<id>/reel.mp4 -vf "fps=1/3,scale=216:-1,tile=8x2" -frames:v 1 /tmp/sheet.jpg`. If something is clearly
   broken, fix and render again (time allows one retry).
7. Set status `rendered`, commit + push. Output one short line: "Reel de <Destino> listo, se publica a las 12:14", plus any problem.

## C · post (12:14)

1. Load today's entry; continue only if status is `rendered` (if `prompts_sent`: tell the owner the Reel wasn't built; stop).
2. Run the workflow with mode `publish` and id. When it succeeds, `git pull` and read `reels/<id>/published.json` (permalink).
3. Set status `published` (+ permalink) in `reels/daily.json`, commit + push.
4. **TikTok (manual for now)**: automatic TikTok drafts are OFF until TikTok approves the app (the sandbox app does not
   deliver drafts to the phone) – do NOT run tiktok.yml. The publish step already added the Reel to `tiktok/feed.json`, which feeds
   https://viajespillados.com/tiktok/hoy.html (the owner saves the video there and posts it in TikTok by hand).
5. Output: "✅ Reel de <Destino> publicado: <permalink>" and a second line
   "📲 Para TikTok: https://viajespillados.com/tiktok/hoy.html (guardar video › copiar texto › TikTok + › subir)", followed by the
   caption from `reels/<id>/storyboard.json` ("caption") in a code block so it is easy to copy. On failure: the error in one line.
