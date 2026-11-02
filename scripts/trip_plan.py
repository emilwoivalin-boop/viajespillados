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
           "wade", "dance", "lookout", "sip", "dive", "float"}
VOICE = {"es": ("es-CO-GonzaloNeural", "+35%"), "en": ("en-US-AndrewNeural", "+25%")}


def build(tid):
    base = os.path.join(ROOT, "trips", tid)
    plan = json.load(open(os.path.join(base, "plan.json")))
    for lang in ("es", "en"):
        scenes = []
        for sc in plan["scenes"]:
            st = sc.get("stick") or {"action": "none"}
            assert st.get("action", "none") in ACTIONS, f"{sc['key']}: unknown action {st.get('action')}"
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
                           "sfx": sfx, "steps": sc.get("steps", False), "crowd": sc.get("crowd") or [],
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
        fr = im.crop((ox, oy, ox + 1080, oy + 1920)).convert("RGBA")
        for st in (sc.get("crowd") or []) + [sc.get("stick") or {"action": "none"}]:
          if st.get("action", "none") != "none":
            n = 40
            band = list(stickman.frames(st["action"], n, 30, x0=st.get("x0", 0.5), x1=st.get("x1", st.get("x0", 0.5)),
                                        feet=int(st.get("y", 0.8) * 1920), feet1=int(st.get("y1", st.get("y", 0.8)) * 1920),
                                        size=st.get("size", 330), size1=st.get("size1"), facing=st.get("facing", 1),
                                        band_h=1920))[int(n * 0.85)]
            fr.alpha_composite(band)
        reelfx.draw_pops(fr, [{**p, "t": 0} for p in sc.get("pops", [])], 1.0, 1080, 1920)
        if sc.get("tag"):
            fr.alpha_composite(reel.tag_png(sc["tag"]))
        tiles.append(fr.convert("RGB").resize((270, 480)))
    cols = min(len(tiles), 5)
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
