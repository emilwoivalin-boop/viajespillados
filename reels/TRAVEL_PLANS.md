---
name: travel-plan-video
description: Make a Viajes Pillados stick-man travel-plan video (hook + itinerary, Spanish and English) for a destination the owner picks.
---

# Travel-plan video (Viajes Pillados)

Short vertical stick-man videos with a hook and a travel itinerary, NOT tied to a flight offer. Two versions:
**Spanish** (very Colombian, low-key Viajes Pillados sign-off) and **English** (no brand at all). They are not
published: they are saved on the owner's computer in `~/Movies/Viajes Pillados - Travel plans/<Destino>/`.

Three rounds with the owner. Keep every message short and easy to answer on a phone.

## Setup (every session)
- Repo: add_repo (owner `emilwoivalin-boop`, repo `viajespillados`, access `push`), clone to
  `/home/claude/viajespillados`, git user `viajespillados-bot` /
  `41898282+github-actions[bot]@users.noreply.github.com`. `git pull --rebase` before every commit.
- Code: `scripts/trip_plan.py` (plan.json → storyboard_es.json + storyboard_en.json, and a preview),
  `scripts/reel.py trip <id>` (renderer), workflow `.github/workflows/trip.yml` (input `id`).
- Folder on the computer: `~/Movies/Viajes Pillados - Travel plans/` (remote-devices tools). If the
  computer isn't linked or the folder isn't connected, ask for access to `~/Movies` with
  device_request_folder_access. If it can't be reached, send the files with SendUserFile instead.

## Round 1 – destination → activities to pick
1. The owner names a destination (and maybe the number of days; default 3).
2. Research it with WebSearch (current, real places; opening/closure facts). Pick **16 options**, 4 per category:
   **Famous sights**, **Nature & views**, **Day trips**, **Food & local life** (markets, dishes, nightlife,
   experiences). Prefer the iconic + a couple of local gems; each must be doable from the destination.
3. Ask with **AskUserQuestion**: 4 questions (one per category), `multiSelect: true`, 4 options each.
   Label = the place/activity (≤5 words); description = one short line (what + why). Put the 2 strongest
   first and add "(Recommended)" to them. In the same reply, one line: "Pick what you want – about 2 per day.
   Type extra ideas under Other."
4. If the owner picks too many for the days, keep the order of the itinerary sensible and say which
   ones you merged (e.g. two sights in the same area on one day). Create `trips/<slug>-<dias>-dias/`.

## Round 2 – script + picture prompts
Write the plan: **1 hook scene + one scene per activity (group 1–3 per day) + the last scene is the wrap-up**.
6–9 scenes, 35–55 s of speech in total, 8–20 words per scene.

**Spanish (es)** – fast, informative, really Colombian (parce, qué chimba, bacano, pilas, berraco, ¡uy!,
"vamos pa'", "de una", "no se lo pierda", "plan completico"), tú-form, one concrete detail per scene
(a name, a number, a taste, a time of day) and one practical tip somewhere. Each day starts with
"Día uno:", "Día dos:"… The **hook** is the first scene: 1 short punchy sentence that makes people stay
(question, bold promise or surprising fact), e.g. "¿Medellín en tres días sin perder ni un minuto? Pilla
este plan, parce." The last scene wraps up + "Guárdalo pa' tu viaje" and may end very softly with
"…y los vuelos baratos, en viajespillados punto com." (only once, only at the end).
**English (en)** – the same content and rhythm, natural punchy English (a Colombian word here and there is
fine, e.g. "parce"), "Day one:", "Day two:"… **No Viajes Pillados, no website, no logo.** Ends with
"Save this for your trip!" or similar.
Only facts you are sure of; no prices, no airlines, no dates.

**Picture prompts** (English, one per scene, numbered 1…N in scene order). These can be more detailed than
the daily Reels. Each = style block + scene + layout rule:
- Style block: `Detailed flat cartoon illustration, clean outlines, rich warm colors, soft shading,
  recognizable landmark shapes and local details, no people, no text, no letters, vertical 9:16.`
- Scene: the exact place of that line, recognisable (landmark shapes, colours, nature, food), time of day
  that fits the line (night plans → night sky).
- Layout: a clear empty area where a small stick figure can stand/sit/walk (say where, e.g. "empty plaza in
  the lower third"); keep the top 30 % calm (sky/wall) because captions and the day chip sit there.
- Hook picture: the most iconic view of the destination, wide.

Deliver in chat: the Spanish script (numbered, with the day chip for each scene), the English script, and the
N prompts each in its own code block. Save the same as `script.md` in the computer folder
`~/Movies/Viajes Pillados - Travel plans/<Destino>/` (write it there with device_bash). Ask for the
pictures: "Make the N pictures in Gemini and attach them here in order (or name them 1–N)."
If the owner asks for changes, edit and resend only what changed.

## Round 3 – pictures → videos
1. Pictures arrive as chat attachments (or a Drive folder link). Map them 1…N in order (by file name
   number if present, else upload order). Save to `trips/<id>/img/<key>.jpg` (≤1080 px wide, JPEG q92).
2. Look at every picture (Read) and write `trips/<id>/plan.json` (format in `scripts/trip_plan.py`):
   - `tag`: hook → `{"es": "MEDELLÍN · 3 DÍAS", "en": "MEDELLÍN · 3 DAYS"}`; day scenes →
     `{"es": "DÍA 1", "en": "DAY 1"}`; the wrap-up scene may have none.
   - `stick`: classic stick man ON the ground/path/sand where it's empty; same rules and reference values as
     `reels/AUTOMATION.md` section B.4 (x0/x1/y fractions of 1080×1920, size ≈500 near / 250–350 middle /
     150 far, actions walk, wave, celebrate, relax, swim, drive, photo, suitcase, none). Out of the top 33 %.
     Vary the actions; the hook can be `none` or `wave`.
   - `pop`: max 1 per scene and on at most 3 scenes, `word` = a word of that scene's line in each language.
   - `ambience`: `waves` (sea) or `crickets` (warm night) where it fits, max 1 per scene.
3. `python scripts/trip_plan.py build <id>` and `python scripts/trip_plan.py preview <id> /tmp/p.jpg`; Read
   the preview, fix placements. Commit + push.
4. Render: `gh api -X POST repos/emilwoivalin-boop/viajespillados/actions/workflows/trip.yml/dispatches -f ref=main -f 'inputs[id]=<id>'`,
   find the run (`gh run list -R emilwoivalin-boop/viajespillados -w trip.yml -L 1`) and poll every 20 s
   (Monitor until-loop, ~6–10 min). On failure: `git pull` and read `trips/<id>/error.txt`.
5. Get the videos from the branch `trip-videos` (never published, not on the website):
   `git fetch origin trip-videos:refs/remotes/origin/trip-videos && git show origin/trip-videos:<id>/video_es.mp4 > /mnt/user-data/outputs/<id>_es.mp4`
   (same for `_en`). Check each with a contact sheet
   (`ffmpeg -i X.mp4 -vf "fps=1/3,scale=216:-1,tile=8x2" -frames:v 1 /tmp/s.jpg`) and fix + re-render if
   something is clearly broken.
6. Save to the computer with device_commit_files (stagedPath `/mnt/user-data/outputs/<id>_es.mp4` →
   `~/Movies/Viajes Pillados - Travel plans/<Destino>/<Destino> – ES.mp4`, same for EN, plus the captions as
   `captions.txt`). Reply in 2–3 lines: where they are, length of each video, and offer one tweak.

Never publish these videos anywhere and never commit them to `main` (the website serves `main`).
