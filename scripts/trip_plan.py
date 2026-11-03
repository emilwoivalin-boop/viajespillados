"""Travel-plan videos (stick-man style, not tied to a flight offer): trips/<id>/plan.json -> two storyboards.

    python scripts/trip_plan.py build <id>             # plan.json -> storyboard_es.json + storyboard_en.json
    python scripts/trip_plan.py preview <id> <out.jpg>  # one frame per scene (stick man + sticker + day chip)

Spanish version: Colombian voice, low-key sign-off (small logo + viajespillados.com in the last seconds, and the
last line may mention viajespillados punto com). English version: no brand at all.

plan.json:
{
  "id": "medellin-3-dias", "destino": "Medellín", "pais": "Colombia", "dias": 3,
  "scenes": [            # in order; the first one is the hook
    {"key": "hook", "img": "hook",                      # picture trips/<id>/img/<img>.jpg
     "tag": {"es": "MEDELLÍN · 3 DÍAS", "en": "MEDELLÍN · 3 DAYS"},   # optional chip at the top
     "text": {"es": "...", "en": "..."},
     "stick": {"action": "walk", "x0": .3, "x1": .6, "y": .85, "size": 380, "facing": 1} | null,
     "pop": {"icon": "pin", "word": {"es": "Guatapé", "en": "Guatapé"}, "x": .7, "y": .4, "size": 190} | null,
     "ambience": "waves" | ["waves", "steeldrum"] | null,   # also crickets, underwater, birds
     "sfx": [{"kind": "bell", "at": 0.3, "gain": 0.25}], "steps": true, "action_sfx": true},   # optional extras
    ...
  ],
  "caption": {"es": "...", "en": "..."}
}
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = {"sun", "heart", "sparkle", "pin", "plane", "fish", "suitcase", "clock", "camera"}
AMBIENCE = {"waves", "crickets", "underwater", "birds", "steeldrum"}
SFX = {"bell", "splash", "clink", "engine", "bubbles", "shutter", "boing", "chime", "sparkle", "pop", "coin"}
ACTIONS = {"walk", "suitcase", "wave", "celebrate", "relax", "swim", "drive", "photo", "none",
           "wade", "dance", "lookout", "sip", "dive", "float", "stand", "run", "sit", "hammock", "shrug", "selfie",
           "scared", "laugh", "eat", "kayak", "parachute", "point"}
VOICE = {"es": ("es-CO-GonzaloNeural", "+35%"), "en": ("en-US-AndrewNeural", "+25%")}


def build(tid):
    base = os.path.join(ROOT, "trips", tid)
    plan = json.load(open(os.path.join(base, "plan.json")))
    for lang in ("es", "en"):
        scenes = []
        for sc in plan["scenes"]:
            def figure(f):
                f = json.loads(json.dumps(f))
                for b in f.get("beats") or []:
                    assert b.get("action", "stand") in ACTIONS, f"{sc['key']}: unknown beat action {b.get('action')}"
                    if isinstance(b.get("word"), dict):
                        b["word"] = b["word"][lang]
                        assert b["word"].lower() in text.lower(), f"{sc['key']} ({lang}): beat word {b['word']} not in text"
                assert f.get("action", "none") in ACTIONS, f"{sc['key']}: unknown action {f.get('action')}"
                return f
            text = sc["text"][lang]
            st = figure(sc.get("stick") or {"action": "none"})
            for c in sc.get("crowd") or []:      # extra stick people (party, beach), behind the main one
                assert c.get("action", "wave") in ACTIONS, f"{sc['key']}: unknown crowd action"
            text = sc["text"][lang]
            pops = []
            if sc.get("pop"):
                p = sc["pop"]
                word = p["word"][lang] if isinstance(p["word"], dict) else p["word"]
                assert p["icon"] in ICONS, f"{sc['key']}: unknown sticker {p['icon']}"
                assert word.lower().strip("¡!¿?,.") in text.lower(), f"{sc['key']} ({lang}): sticker word not in text"
                pops = [{"icon": p["icon"], "word": word, "x": p["x"], "y": p["y"], "size": p.get("size", 190)}]
            amb = sc.get("ambience") or []
            amb = [a for a in ([amb] if isinstance(amb, str) else amb) if a in AMBIENCE]
            sfx = sc.get("sfx") or []
            assert all(e["kind"] in SFX for e in sfx), f"{sc['key']}: unknown sfx"
            img = f"trips/{tid}/img/{sc.get('img', sc['key'])}.jpg"
            assert os.path.exists(os.path.join(ROOT, img)), f"missing picture {img}"
            tag = (sc.get("tag") or {}).get(lang)
            scenes.append({"text": text, "media": {"type": "file", "path": img, "focus": sc.get("focus", 0.5)},
                           "stick": st, "pops": pops, "ambience": amb, "action_sfx": sc.get("action_sfx", not amb),
                           "sfx": sfx, "steps": sc.get("steps", False), "crowd": [figure(c) for c in sc.get("crowd") or []],
                           **({"tag": tag} if tag else {})})
        scenes[-1]["hold"] = plan.get("end_hold", 1.6)          # let the last picture breathe (no end card in travel plans)
        voice, rate = VOICE[lang]
        rate = (plan.get("rate") or {}).get(lang, rate)          # optional per-trip speed, e.g. {"es": "+45%"}
        sb = {"id": f"{tid}-{lang}", "voice": voice, "rate": rate, "pad": plan.get("pad", 0.25), "stick_style": "classic",
              "caption_margin": 400, "caption_align": 8, "banner": {"logo": False}, "scenes": scenes,
              "end": None, "caption": (plan.get("caption") or {}).get(lang, "")}
        if lang == "es":
            sb["outro"] = {"text": "viajespillados.com", "dur": 3.0}
        json.dump(sb, open(os.path.join(base, f"storyboard_{lang}.json"), "w"), ensure_ascii=False, indent=1)
        print(f"\n[{lang}] trips/{tid}/storyboard_{lang}.json")
        for s in scenes:
            print(" -", (s.get("tag") or "").ljust(16), s["text"])


def preview(tid, out):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import stickman
    import reelfx
    import reel
    from PIL import Image
    sb = json.load(open(os.path.join(ROOT, "trips", tid, "storyboard_es.json")))
    tiles = []
    for sc in sb["scenes"]:
        im = Image.open(os.path.join(ROOT, sc["media"]["path"])).convert("RGB")
        k = max(1080 / im.width, 1920 / im.height)
        im = im.resize((round(im.width * k), round(im.height * k)))
        ox, oy = (im.width - 1080) // 2, (im.height - 1920) // 2
        base = im.crop((ox, oy, ox + 1080, oy + 1920)).convert("RGBA")
        n, dur = 120, 4.0                     # beats without word timing are spread evenly over the preview
        figs = [dict(c) for c in sc.get("crowd") or []] + [dict(sc.get("stick") or {"action": "none"})]
        for f in figs:
            reel.resolve_beats(f, [], dur)
        picks = (int(n * 0.15), int(n * 0.5), int(n * 0.85))
        frames = []
        for k, f in enumerate(figs):          # keep only the frames we show (full frames are big)
            g = reel.figure_frames({"action": "wave", **f} if k < len(figs) - 1 else f, n)
            frames.append({i: im for i, im in enumerate(g) if i in picks})
        for j, i in enumerate(picks):
            fr = base.copy()
            for fl in frames:
                fr.alpha_composite(fl[i])
            if j < 2:
                tiles.append(fr.convert("RGB").resize((270, 480)))
        reelfx.draw_pops(fr, [{**p, "t": 0} for p in sc.get("pops", [])], 1.0, 1080, 1920)
        if sc.get("tag"):
            fr.alpha_composite(reel.tag_png(sc["tag"]))
        tiles.append(fr.convert("RGB").resize((270, 480)))
    cols = min(len(tiles), 6)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (270 * cols, 480 * rows), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 270, (i // cols) * 480))
    sheet.save(out, quality=85)
    print("preview:", out)


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2])
    elif sys.argv[1] == "preview":
        preview(sys.argv[2], sys.argv[3])
