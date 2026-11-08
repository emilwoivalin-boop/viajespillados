# Daily Reel – how it works

One Spanish (Colombia) Reel per day about the best tracked offer, same format as the approved
Aruba Reel (`reels/aruba-abril-2027-cartoon-es`). Three scheduled tasks run it:

| Bogotá time | Task | What it does |
|---|---|---|
| 06:41 | **A · prepare** | picks the offer, writes the script and 6 picture prompts (7 on 4-day trips, 8 on 5+ days), makes the pictures with Picsart (automatic), checks them, tells the owner |
| (owner) | — | nothing – only if Picsart failed: makes the 5 pictures in the Gemini app and uploads them to today's Drive folder **before 11:20** |
| 11:23 | **B · build** | downloads the pictures, places stick man / sticker / sound, renders the video, checks it |
| 12:14 | **C · post** | publishes the rendered Reel on Instagram |

State lives in `reels/daily.json` (one entry per Bogotá date):
`{"2026-10-30": {"id": "lima-2027-01-16", "destino": "Lima", "status": "prompts_sent", "drive_folder_id": "...", "note": ""}}`
Status flow: `pictures_ready` (Picsart) or `prompts_sent` (manual fallback) → `rendered` → `published`, or `skipped` (with a note).

Common facts
- Repo: `emilwoivalin-boop/viajespillados` (GitHub Pages site viajespillados.com). In a fresh session attach it with the
  add_repo tool (owner `emilwoivalin-boop`, repo `viajespillados`, access `push`), clone it to `/home/claude/viajespillados`,
  set `git config user.name "viajespillados-bot"` and `git config user.email "41898282+github-actions[bot]@users.noreply.github.com"`.
  Always `git pull --rebase` before committing; retry `git pull --rebase && git push` if a push is rejected.
- Workflows are started with
  `gh api -X POST repos/emilwoivalin-boop/viajespillados/actions/workflows/reel.yml/dispatches -f ref=main -f 'inputs[mode]=<render|publish|fetch>' -f 'inputs[id]=<id>'`
  then find the run with `gh run list -R emilwoivalin-boop/viajespillados -w reel.yml -L 1` and poll `gh run view <run> --json status,conclusion` every 20 s.
  On failure read `reels/<id>/error.txt` (after `git pull`).
- Where Next Atlas (the owner's travel site, English): `data/wherenext.json` – ~280 destinations with tagline, `todo`
  (activities), fact, best months, good/skip, similar places and airport `iata`. A copy of the artifact
  https://claude.ai/artifact/Bv5dZXxTTX2totQ3HcWA54 – refreshed when the owner asks.
- Offers sheet: `1us2JZr8rQRmeYlMTke9k2nPU26Cp6MLYQbtz3fHeL3c` (tab `Ofertas`, columns A Publicar … P Fechas; tab `Qué hacer (captions)`:
  A Destino, B País, C Región, D Qué hacer, E Ojo).
  Price log: `1SO2lHr3GvY01kRaBNPLtGPZ-OgWoNblqm7XtTIJO9PY` tab `Price log` (headers row 4; C Destination (English), D Trip type,
  H Price, Q Depart date, R Return date, S Workdays off, X Score 0–10, Y Final flag).
- Drive parent folder "Viajes Pillados – Reels": `1_9RYH30SlCRgR-MGv_Kpq3K-jFLMBuSm` (shared "anyone with the link can view",
  so the GitHub workflow can download the pictures).
- Picsart (owner's Pro account): `gh api -X POST repos/emilwoivalin-boop/viajespillados/actions/workflows/picsart.yml/dispatches
  -f ref=main -f 'inputs[mode]=pictures' -f 'inputs[kind]=reels' -f 'inputs[id]=<id>' [-f 'inputs[keys]=dia2,cover']` makes the
  pictures from plan.json `prompts` into `reels/<id>/img/<key>.jpg` (Nano Banana 2, falls back to Nano Banana Pro) and writes
  `img/picsart.json` (done / failed + credits left in the run summary). Poll the run like reel.yml (`-w picsart.yml`), then `git pull`.
  If the run fails with a sign-in error ("Not authenticated", "session expired"), the sign-in must be renewed: that needs the owner
  (see "Renew the Picsart sign-in" at the end) – use the manual fallback for today and tell the owner.
- Helper: `python scripts/reel_plan.py info <ida> <vuelta>` (Spanish dates, days, workdays off),
  `python scripts/reel_plan.py build <id>` (plan.json → storyboard.json), `python scripts/reel_plan.py preview <id> <out.jpg>`
  (one frame per scene with stick man + sticker – look at it with the Read tool).

---------------------------------------------------------------------------------------------------

## A · prepare (06:41)

1. Today = Bogotá date. If `reels/daily.json` already has today with status other than `skipped`, stop (already done).
2. **Pick the offer** ("best tracked offer"):
   - Candidates = rows of `Ofertas` with A Publicar = "sí" (never "no" or "revisar"), a ROUND-TRIP date in P (`YYYY-MM-DD/YYYY-MM-DD`), departure at least
     4 days from today, and the Destino present in column A of `Qué hacer (captions)`.
   - Exclude destinations that already had a daily Reel in the last 14 days (`reels/daily.json`, statuses other than `skipped`),
     and the exact same offer (destino + dates) ever.
   - Rank: find the matching `Price log` row (same depart/return dates and price within 3 %; destination names are English there,
     e.g. "Panama City" = "Ciudad de Panamá") and use its Score (X).
   - **Owner's rule: prefer trips that leave soon.** Reel score = Score (X) + a "soon" bonus from the days until departure:
     4–30 days **+2**, 31–60 days **+1**, 61–120 days **0**, more than 120 days **−1**. Highest Reel score first; ties → earlier
     departure → fewer workdays off (S) → bigger "% below usual low" (L) → newest Publicado (B). An offer without a matching
     log row ranks after all matched ones (among them: earlier departure first). Say the days until departure in the note.
   - If there is no candidate: add today as `skipped` with note "no tracked round-trip offer", commit, and tell the owner in one line. Stop.
3. `id` = `<slug-destino>-<ida>` (e.g. `lima-2027-01-16`). Create `reels/<id>/plan.json` (format in `scripts/reel_plan.py`):
   `offer` = destino, aerolinea, precio (number), escalas ("directo" / "1 escala" / "N escalas"), ida, vuelta, link (J), sheet_row,
   escala_larga (column Q, the layover city with time to explore – empty for most offers; the end card then says
   "escala larga en <ciudad>" and the `regreso` or a day line may mention it), region (column I Categoría, e.g. "Caribe e islas" – the opening says "nos vamos pa'l Caribe" instead of the destination;
   optional `teaser` in plan.json overrides it, e.g. "el Pacífico" or "la costa", never the destination's name);
   `hora_salida` = null (only fill it, e.g. "4 de la tarde", if you verified the airline's scheduled departure time for that
   weekday from a reliable timetable page; otherwise leave null); `que_hacer` = column D of `Qué hacer`; `end_image` = "dia1";
   `buddy` = true if `python scripts/reel_plan.py buddy` prints "yes" (every third Reel that was actually made has the travel
   buddy – a second stick figure with a ponytail and a flower – walking next to him), else false. Also save `buddy` in today's
   `reels/daily.json` entry.
4. **Script lines** (`lines`, Spanish from Colombia, tú, short and lively like the Aruba Reel; 8–20 words each; no prices, no airline):
   - `vuelo`: the flight, e.g. "Dos horas de vuelo directo, y el mar abajo se pone turquesa." Only state the flight time if you
     know it (Price log Notes "N hrs"); say "directo" only for non-stop.
   - **No spoilers (owner's rule):** the destination is revealed only in `llegada`. The `vuelo` line must not name the destination,
     its country or a landmark that gives it away – tease the region instead (e.g. "Vuelo directo de dos horas… ¿y abajo? Mar
     turquesa del Caribe."). `reel_plan.py build` refuses a `vuelo` line that contains the destination's name.
   - `llegada`: the reveal – "¡Bienvenido a <Destino>! …" + one sensory detail of arriving there.
   - `dia1`, `dia2`, `dia3`: start with "Día uno:", "Día dos:", "Día tres:" (for trips of 2–3 days use "Primer día:", "Luego:",
     "Antes de volver:"), one activity each, with one concrete vivid detail. Only facts you are sure about.
     **Source of the activities:** first the Where Next Atlas data – `python scripts/reel_caption.py find <IATA>` (the IATA
     code from the offer's link, column J), or `find "<name>"` with the English name (e.g. "Havana") – and its `todo` list
     (4 activities with a short description); otherwise the three activities in `Qué hacer` column D, in that order.
   - **Longer trips get more days (owner's rule):** a 4-day trip gets `dia4` ("Día cuatro:"); trips of 5 days or more get
     `dia4` and `dia5` ("Día cuatro:", "Día cinco:"), each with its own picture (prompts `dia4`, `dia5`, same rules as dia1–3).
     `Qué hacer` only has three activities, so pick the extra ones yourself – different and real (a day trip, a beach or nature
     spot, a local food or market, a famous neighbourhood); check anything you are not sure of with a web search.
     `reel_plan.py build` refuses a plan without them. Trips of 2–3 days keep the three day scenes.
   The opening line (date + El Dorado), the return line (with the workdays-off sentence) and the price ending are added
   automatically by `reel_plan.py build` – don't write them.
4a. **4a · Fechas y ocasiones.** The storyline must take the trip dates (ida–vuelta) into account. Check whether the trip overlaps
   (1) Nochebuena/Navidad (24–25 Dec), Nochevieja/Año Nuevo (31 Dec–1 Jan), Semana Santa, Halloween/Día de Muertos, or a Colombian
   holiday weekend (tab "Holidays" of the Price log), or (2) a famous local event or season at the destination (e.g. carnival,
   national day, a big festival, cherry blossoms, northern lights, whale season). Fixed-date occasions can be used directly; for any
   event whose dates change from year to year, confirm with a web search that it happens during the trip dates in that year, and
   only use it if the overlap is clear – never guess. Pick at most one occasion (the most relevant). If there is one: save it in
   plan.json as `"ocasion": {"nombre": ..., "fechas": ..., "fuente": <url or "fecha fija">}`; mention it naturally in the "llegada"
   line (e.g. "¡Bienvenido a La Habana en plena Navidad! …"); turn the day line that best fits into the occasion (it may start with
   "En Nochebuena:", "El 31:" etc. instead of "Día dos:"), keeping the other Qué hacer activities; add matching visual details to
   the picture prompts of those scenes (e.g. Christmas lights and decorations, a night sky with fireworks, carnival colours and
   streamers – still no people, no text); start "que_hacer" (it becomes the start of the Instagram caption) with a short sentence
   such as "Navidad en La Habana."; and mention the occasion in the final message to the owner. Only state facts you are sure
   about. If nothing applies, change nothing.
4b. **Instagram caption** (`caption_es`, owner's format – see `scripts/reel_caption.py` for the fields and the Madrid example).
   Written in Colombian Spanish (tú, natural, like the script), **few emojis** (the builder adds only 📍 and ✈️ – write none
   yourself) and **no flight offer** (no price, airline or dates – the offer is only shown at the end of the Reel).
   - `hook`: one punchy line, e.g. "¿Madrid en 3 días sin perder ni un minuto? Pilla este plan, parce." (use the number of day
     scenes; mention the occasion here if there is one).
   - `intro` (from Where Next `tagline`), `pais` (country in Spanish), `dias` = one `{titulo, texto}` per day scene, the SAME
     activities and order as `dia1`, `dia2`… (titulo 2–5 words, texto one short sentence), optional `bonus` (another `todo`
     item, e.g. nightlife), `dato` (from `fact`, without "¿Sabías que"), `epoca` (from `months`, e.g. "abril a junio y
     septiembre a octubre"), `para` (from `good`, "te gusta…"), `no_para` (from `skip`, "odias… / quieres…"), `versus` (the
     Spanish name of one `similar` place) and 2–4 `hashtags` (destination, country, #quehaceren<destino>).
   - Translate and adapt – don't add facts that aren't in the data unless you are sure of them. If the destination is not in
     Where Next, fill what you can from `Qué hacer` (que_hacer → dias, ojo → no_para) and leave the rest out.
   - Check it with `python scripts/reel_caption.py show <id>` (it runs automatically at publish time).
5. **Picture prompts** (`prompts`, English, one per key). Every prompt = this style block + scene description + layout rule:
   - Style block: `Very simple flat cartoon illustration, clean bold black outlines, flat bright colors, minimal detail, no gradients, children's book style. Empty scenery only: no people, no human figures, no stick figures, no silhouettes, no characters, no text, no letters, vertical 9:16.`
   - `vuelo`: view from high above the clouds with a small white airplane, and the landscape of the destination region far below (sea and islands, mountains, city…) – generic for the region, no recognisable landmark of the destination (it is revealed at landing).
   - `llegada`: outside the destination's airport or arrival spot, with a typical local detail (palms, mountains, skyline…), with an empty sidewalk in the lower third.
   - `dia1`/`dia2`/`dia3` (+ `dia4` on 4-day trips, `dia4`/`dia5` on 5+ day trips): the place of that day's activity, recognisable (landmark shapes, colours, nature), and a clear empty area for our stick figure (in the prompt describe only the empty space – never write "figure", "person" or "stick man", or the image model draws them; say where: "empty sand in the lower half", "the trail is clearly visible and empty"). On a buddy Reel ask for a wider empty area ("wide, empty stretch of sand across the lower third"). If a line has a hammock, a dock or a wall to sit on, mention it so the stick man can use it (hammock between two palms, wooden dock edge).
   - `cover` (the grid cover / thumbnail): the single most iconic, colourful view of the destination, bright daylight, the middle
     of the picture calm (open sky or sea – a big title goes there), an empty beach / plaza / path in the bottom fifth.
   - Use the time of day that fits the line (evening activities → sunset sky).
6. **Pictures with Picsart (automatic)**: commit + push plan.json, run the Picsart workflow with mode `pictures` (see Common facts),
   poll until it finishes (≈ 3–8 min), `git pull`. Then **look at every picture** (Read `reels/<id>/img/<key>.jpg`) and check: it
   shows the right place, no text / letters / logos / people / stick figures, the empty area for the stick man really exists, the
   top third is calm, it looks like the same simple cartoon style as the others. Redo only the bad ones (`keys`), improving their
   prompt in plan.json first (be more explicit about what was wrong). At most 2 redo rounds; then keep the best version.
   If all pictures are fine: set today's entry in `reels/daily.json` to status `pictures_ready` (no Drive folder needed). Commit + push.
   **Fallback** (Picsart run failed, sign-in expired, no credits, or fewer than 5 usable pictures after the redos): do the old
   manual flow – in the Drive parent folder create a folder `<YYYY-MM-DD> <Destino>` (Drive tool create_file, mimeType folder,
   parentId above) with a Google Doc "Prompts" containing the prompts numbered 1–5 (vuelo, llegada, dia1, dia2, dia3; 1–6 / 1–7 with dia4 / dia4 + dia5 on 4-day / 5+ day trips); save its id
   as `drive_folder_id` in plan.json and in `reels/daily.json` with status `prompts_sent`. Commit + push.
7. **Final output** (the owner reads this on the phone; keep it short, Spanish is fine): destino, fechas, precio, why it was picked
   (Reel score, days until departure, % below usual), the occasion if any, and whether it is a buddy Reel.
   - `pictures_ready`: "Las imágenes ya están hechas con Picsart – no tienes que subir nada. El Reel se arma a las 11:23 y se
     publica a las 12:14." If you can send files, send a contact sheet of all the pictures
     (`python -c` with PIL, 6 thumbnails side by side) so the owner can see them.
   - `prompts_sent` (fallback): say why Picsart failed, then the Drive folder link `https://drive.google.com/drive/folders/<id>`
     and the 5 prompts numbered 1–5, each in its own code block, and "Sube las 5 imágenes a la carpeta en este orden (o nómbralas
     1–5) antes de las 11:20." If the Picsart sign-in expired, add: "Pídele a Claude que renueve el acceso a Picsart."

## B · build (11:23)

1. Load today's entry from `reels/daily.json`. If status is `pictures_ready`, the pictures are already in `reels/<id>/img/` –
   skip steps 2–3. If status is `prompts_sent` (manual fallback), do steps 2–3. Any other status: stop.
2. List the images in the Drive folder (search_files `parentId = '<folder>' and mimeType contains 'image/'`, excludeContentSnippets).
   Order: files whose names start with 1–5 by that number, otherwise by createdTime (oldest first). Map to vuelo, llegada, dia1, dia2, dia3 (+ dia4 on 4-day trips, dia4 + dia5 on 5+ day trips).
   - If fewer than 5 images: if it is before 11:50, wait 5 minutes and check again (up to 5 times). Still missing → set status
     `skipped` with note "faltaron imágenes (N/5)", commit, tell the owner in one line, stop.
3. Write `drive_files` {key: fileId} into plan.json, commit + push, run the workflow with mode `fetch`. `git pull`; the pictures are
   now in `reels/<id>/img/<key>.jpg`.
4. **Look at each picture** (Read tool) and fill `plan.scenes[key]`:
   - `stick`: the classic stick man doing something that fits the line and the picture, placed ON the ground / sand / path / water
     where it is empty. Coordinates are fractions of the 1080×1920 frame (pictures are cover-fitted to 9:16): `x0`/`x1` = start/end x
     of his body centre, `y` (and optional `y1`) = where his FEET are, `size` (and optional `size1`) = body height in px
     (≈ 450–550 close to the camera at the bottom, ≈ 250–350 in the middle distance, ≈ 150 far away), `facing` 1 = right, −1 = left.
     **Moves** (pick the one that matches the line; vary them, don't use the same move on two pictures in a row):
     `walk`, `run` (speed lines), `suitcase`, `stand`, `wave`, `celebrate` (arrival!), `point` (pointing at a view or landmark),
     `photo`, `selfie`, `laugh`, `shrug`, `scared` (jumps back, sweat drops – animals, heights, spicy food), `relax` (lying on a
     towel – beaches/parks), `hammock` (lies in a hammock hung between x0 and x1 at height y), `sit` (on an edge – dock, wall,
     rock; y = the edge surface), `eat` (plate of fried fish – food lines), `sip` (coconut drink – bars, sunsets), `dance`
     (music notes – parties, festivals), `swim` (snorkel – `y` is the water level of his body), `wade` (knee-deep in the sea),
     `float` (on his back in the water), `dive` (jumps from x0/y into the water at x1/y1, splash), `kayak` (on water, x0→x1),
     `drive` (jeep on a road), `parachute` (drops in from above and lands at y – fun for the arrival), `none` (flight scene).
     **Several moves in one picture** (`beats`), timed to the words of the line – use them on at least 2 of the pictures:
     `"stick": {"y": .87, "size": 400, "beats": [{"action": "run", "x0": -0.15, "x1": .45},
     {"action": "point", "word": "iglesia"}, {"action": "selfie", "word": "vista"}]}` – each beat starts when the voice says its
     `word` (a word of that line) and starts where the previous beat ended unless it gives its own x0/y/size/facing. Optional
     `"mood": "love" | "laugh" | "scared" | "wow"` changes his face for a beat (e.g. heart eyes at a sunset).
     Keep him out of the top 33 % (captions live there) unless he swims.
     Reference values that looked right in the Aruba Reel: arrival celebrate {x0 .45, y .9, size 400}; beach relax {x .63, y .475,
     size 380} (on sand in the tree shadow); jeep coming down a path {x0 .47→.40, y .60→.97, size 150→460, facing −1};
     swim {x0 .10→.65, y .37, size 380}; lighthouse photo {x .28, y .67, size 340}.
   - `crowd` (optional): extra stick people behind him, each like a `stick` (single move or beats):
     - **Buddy Reel** (`buddy: true` in plan.json): put the travel buddy `{"look": "buddy", ...}` in the `crowd` of the
       `llegada` picture and of at least 2 day pictures, next to him (not on top: ~0.2–0.3 apart in x), doing a matching or
       reacting move (both scared at the animal, she takes the photo while he points, both dance). The airport scenes add her
       automatically. On other Reels: no buddy.
     - Party / beach / bar lines (any Reel): 2–4 extra people (`dance` with `speed` 0.8–1.2 so they aren't in sync, `sip`, `relax`).
   - `pop` (optional, max 1, only when it adds meaning): one sticker `{icon, word, x, y, size}` – icons: sun, heart, sparkle, pin,
     plane, fish, suitcase, clock, camera. `word` must be a word of that scene's line (it pops when the voice says it); put it next
     to the thing it refers to (sun in the sky, pin on the place, sparkle on a sign…), not on the stick man and not in y .18–.33.
     Size 170–230. Use stickers on at most 3 pictures.
   - `ambience` (optional, one or a list): `waves` (beach / sea), `crickets` (warm night), `birds` (nature, parks, jungle),
     `steeldrum` (beach party / Caribbean vibe, sunsets), `underwater`. `sfx` (optional): one-off sounds
     `[{"kind": "bell" | "splash" | "clink" | "engine" | "bubbles" | "shutter" | "boing" | "chime", "at": seconds or "frac": 0–1}]`.
     Moves inside `beats` bring their own sounds (photo/selfie click, dive splash, scared/run whoosh, parachute landing).
     For a single move with an ambience, add `"action_sfx": true` to keep its sound. The whoosh between pictures and the chime at
     the price reveal are always there.
5. `python scripts/reel_plan.py build <id>` and `python scripts/reel_plan.py preview <id> /tmp/preview.jpg`; Read the preview and
   fix anything that looks wrong (floating stick man, sticker on top of something, stick man hidden, buddy overlapping him).
   The preview shows two moments for pictures with beats. Commit + push.
6. Run the workflow with mode `render` (it also makes the grid cover `reels/<id>/cover_ig.jpg`: the `cover` picture – or dia1 –
   with "DESDE BOGOTÁ", the destination, days and the stick man – no price; step C uploads it as the Reel's cover). `git pull`, Read
   `cover_ig.jpg` and check the text is readable and nothing important is hidden. Check `reels/<id>/reel.mp4` exists (duration 30–55 s; up to 70 s on longer trips) and look at a contact
   sheet: `ffmpeg -i reels/<id>/reel.mp4 -vf "fps=1/3,scale=216:-1,tile=8x2" -frames:v 1 /tmp/sheet.jpg`. If something is clearly
   broken, fix and render again (time allows one retry).
7. Set status `rendered`, commit + push. Output one short line: "Reel de <Destino> listo, se publica a las 12:14", plus any problem.

## C · post (12:14)

Caption rule (owner): Reel captions are a destination plan in the owner's format (`caption_es` in plan.json, built by
`scripts/reel_caption.py`: hook, plan per day, fun fact, best months, who it suits, question, website line, hashtags) –
few emojis and never the flight offer (the video shows it at the end). `reel.py publish` builds it automatically; without
`caption_es` it falls back to the "Qué hacer (captions)" text. Offer posts and carousels keep the "Qué hacer" text.


**Automatic since 2026-11-06 – no Claude session.** The schedule in `.github/workflows/reel.yml` runs
`scripts/reel.py daily-post today` every day at 12:14 Bogotá, with backup runs at 13:44 and 15:14 because GitHub sometimes
starts scheduled runs hours late or skips them (a run after the Reel is published does nothing). It:
1. loads today's entry in `reels/daily.json`; publishes only if the status is `rendered` (never twice: `published.json` guards it).
   Any other status → the run fails with the reason in `reels/daily_error.txt` and GitHub emails the failure;
2. publishes on Instagram + X + Facebook and adds the Reel to the download page (`tiktok/feed.json`);
3. sets status `published` + permalink in `reels/daily.json` and rewrites `reels/reels_por_destino.csv`;
3a. the Price log tab `Reels por destino` fills columns D (☑) and E (link) by itself from that CSV
   (IMPORTDATA of https://viajespillados.com/reels/reels_por_destino.csv; a destination name matches column B,
   or its first part before " / "). Do not type in D/E. A new destination only needs a row with A–C.
To run it by hand (e.g. after fixing a late render): reel.yml with mode `daily-post`, id `today`.
4. **TikTok (manual for now)**: automatic TikTok drafts are OFF until TikTok approves the app (the sandbox app does not
   deliver drafts to the phone) – do NOT run tiktok.yml. The publish step already added the Reel to `tiktok/feed.json`, which feeds
   https://viajespillados.com/tiktok/hoy.html (the owner saves the video there and posts it in TikTok and YouTube Shorts by hand).
5. Output: "✅ Reel de <Destino> publicado: <permalink>" and a second line
   "📲 Para TikTok y YouTube: https://viajespillados.com/tiktok/hoy.html (guardar video › copiar texto/título › subir)", followed by
   the YouTube title (`yt_title`) and the TikTok/YouTube text (`caption`) of the newest item in `tiktok/feed.json`, each in a code
   block so they are easy to copy. That text is about the destination (no price/airline/dates). On failure: the error in one line.

## Renew the Picsart sign-in (only when a Picsart run says it is not signed in)

Needs the owner (one minute on the phone). Run `picsart.yml` with mode `login`, then poll
`git fetch -q origin picsart-login && git show FETCH_HEAD:login.txt` every 10 s: when it shows `status: waiting`, send the owner
the `direct:` link and the `code:` ("Abre este link, entra con tu cuenta Picsart Pro y aprueba"). The run waits up to ~15 min for
the approval and then shows `status: ok` (with the account and credits) or `failed`. The sign-in is kept encrypted in the Actions
cache and refreshes itself on every run; it is lost only if nothing uses Picsart for 7 days (cache eviction) or the owner revokes it.
