"""Daily Reel helper: turns a small plan (reels/<id>/plan.json) into a full storyboard.json with the
same structure as the approved Aruba Reel, and makes a quick placement preview.

    python scripts/reel_plan.py build <id>      # plan.json -> storyboard.json
    python scripts/reel_plan.py preview <id>    # contact sheet of every scene with stick man + sticker
    python scripts/reel_plan.py info <ida> <vuelta>   # Spanish dates + workdays off, for writing the plan
    python scripts/reel_plan.py buddy [<YYYY-MM-DD>]  # "yes" if today's Reel is a travel-buddy Reel (every third)

plan.json (written by the morning task, completed by the build task):
{
  "id": "lima-2027-01-16",
  "offer": {"destino": "Lima", "pais": "Perú", "region": "Sudamérica", "aerolinea": "JetSMART", "precio": 608490, "escalas": "directo",
            "ida": "2027-01-16", "vuelta": "2027-01-20", "link": "https://...", "sheet_row": 14},
  "hora_salida": null,                       # e.g. "4 de la tarde" ONLY if verified, else null
  "teaser": null,                            # optional: how the opening names the destination before landing,
                                             # e.g. "el Caribe" -> "nos vamos pa'l Caribe" (default: from offer.region)
  "drive_folder_id": "...",
  "lines":   {"vuelo": "...", "llegada": "...", "dia1": "...", "dia2": "...", "dia3": "..."},   # + "dia4" (4-day trips), + "dia5" (5+ days)
  "prompts": {"vuelo": "...", "llegada": "...", "dia1": "...", "dia2": "...", "dia3": "..."},
  "buddy": false,                            # every third Reel: true (see `buddy`) – the travel buddy joins him
  "scenes":  {"vuelo":   {"stick": {...} | null, "pop": {...} | null, "ambience": "waves" | ["waves", "steeldrum"] | null,
                          "crowd": [{"look": "buddy", ...}], "sfx": [{"kind", "at" | "frac", "gain"}]},
              "llegada": {...}, "dia1": {...}, "dia2": {...}, "dia3": {...}},
  "end_image": "dia1"                        # which picture sits behind the price card
}
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import instagram as ig  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS = ["vuelo", "llegada", "dia1", "dia2", "dia3"]
EXTRA = ["dia4", "dia5"]      # owner's rule: a 4-day trip gets day 4, trips of 5+ days get days 4 and 5


def keys_for(plan):
    """Scene keys of this plan: the 5 basic ones, plus dia4 (4-day trips) or dia4 + dia5 (5+ days)."""
    o = plan["offer"]
    dias = info(o["ida"], o["vuelta"])["dias"]
    extra = EXTRA[:max(0, min(dias, 5) - 3)]
    missing = [k for k in extra if not (plan.get("lines") or {}).get(k)]
    assert not missing, f"viaje de {dias} días: faltan las líneas {missing} (Día cuatro / Día cinco)"
    return KEYS + extra
ICONS = {"sun", "heart", "sparkle", "pin", "plane", "fish", "suitcase", "clock", "camera"}
AMBIENCE = {"waves", "crickets", "underwater", "birds", "steeldrum"}
SFX = {"bell", "splash", "clink", "engine", "bubbles", "shutter", "boing", "chime", "sparkle", "pop"}
ACTIONS = {"walk", "suitcase", "wave", "celebrate", "relax", "swim", "drive", "photo", "none",
           "wade", "dance", "lookout", "point", "sip", "dive", "float", "stand", "run", "sit", "hammock", "shrug",
           "selfie", "scared", "laugh", "eat", "kayak", "parachute"}

# fixed opening and closing scenes (same pictures and stick man moves as the approved Aruba Reel)
SALIDA_STICK = {"action": "suitcase", "x0": 0.2, "x1": 0.5, "y": 0.97, "y1": 0.68, "size": 520, "size1": 260}
REGRESO_STICK = {"action": "suitcase", "x0": 0.5, "x1": 0.75, "y": 0.68, "y1": 0.97, "size": 260, "size1": 520}
# travel buddy (every third Reel): walks next to him in the airport scenes
SALIDA_BUDDY = {"look": "buddy", "action": "suitcase", "x0": 0.05, "x1": 0.36, "y": 0.99, "y1": 0.70, "size": 480,
                "size1": 245}
REGRESO_BUDDY = {"look": "buddy", "action": "suitcase", "x0": 0.36, "x1": 0.58, "y": 0.70, "y1": 0.99, "size": 245,
                 "size1": 480}


def buddy_next(today=None):
    """True if the next daily Reel (the one being prepared today) is a 'buddy' Reel: every third Reel that was
    actually made (statuses other than skipped) has the travel buddy."""
    today = today or date.today().isoformat()
    daily = json.load(open(os.path.join(ROOT, "reels", "daily.json")))
    made = sum(1 for k, v in daily.items() if k < today and v.get("status") != "skipped")
    return (made + 1) % 3 == 0


def check_figure(f, line, where):
    """Validate a stick figure (single move or beats) of a scene."""
    assert f.get("action", "none") in ACTIONS, f"{where}: acción desconocida {f.get('action')}"
    for b in f.get("beats") or []:
        assert b.get("action", "stand") in ACTIONS, f"{where}: acción desconocida {b.get('action')}"
        if b.get("word"):
            assert b["word"].lower() in line.lower(), f"{where}: la palabra '{b['word']}' no está en el texto"

NUM = {1: "un", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}


def d(s):
    return date.fromisoformat(s)


def info(ida, vuelta):
    a, b = d(ida), d(vuelta)
    return {"ida_larga": ig.fmt_long(a), "vuelta_larga": ig.fmt_long(b), "dias": (b - a).days + 1,
            "dias_libres": ig.days_off(a, b)}


def pesos(n):
    n = int(round(n / 1000.0)) * 1000
    mill, mil = divmod(n, 1_000_000)
    parts = []
    if mill:
        parts.append("un millón" if mill == 1 else f"{mill} millones")
    if mil:
        parts.append(f"{mil // 1000} mil")
    return " ".join(parts) + " pesos"


def cop(n):
    return "$" + f"{int(n):,}".replace(",", ".")


def days_off_line(n):
    if n == 0:
        return "¡Y sin pedir ni un día libre!"
    if n <= 5:
        return f"¡Y solo pediste {NUM.get(n, n)} {'día libre' if n == 1 else 'días libres'}!"
    return ""


# Owner's rule: the destination is a surprise until the "llegada" scene – before that only the region is named.
REGION_TEASER = {"caribe e islas": "el Caribe", "centroamérica": "Centroamérica", "norteamérica": "Norteamérica",
                 "sudamérica": "Sudamérica", "europa": "Europa", "asia": "Asia", "oceanía": "Oceanía",
                 "áfrica y medio oriente": "el otro lado del mundo", "colombia": "un rincón de Colombia"}


# Owner's rule: Mexico and the Central American countries are "Centroamérica" in the videos (not Norteamérica),
# and South American trips name the country right away ("nos vamos pa' Perú"); the city stays a surprise.
CENTRAL = {"mexico", "guatemala", "belice", "belize", "el-salvador", "honduras", "nicaragua", "costa-rica", "panama"}
SOUTH = {"argentina", "bolivia", "brasil", "brazil", "chile", "ecuador", "paraguay", "peru", "uruguay", "venezuela",
         "guyana", "surinam", "suriname"}


def _s(x):
    import unicodedata
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
    return "-".join(w for w in x.replace(".", " ").split())


def teaser(plan):
    """'el Caribe' -> "pa'l Caribe", 'Europa' -> "pa' Europa" (plan["teaser"] overrides everything)."""
    o = plan["offer"]
    pais, region = (o.get("pais") or "").strip(), (o.get("region") or "").strip().lower()
    t = plan.get("teaser")
    if not t and _s(pais) in CENTRAL:
        t = "Centroamérica"
    elif not t and (_s(pais) in SOUTH or (region == "sudamérica" and pais)):
        t = pais
    t = t or REGION_TEASER.get(region)
    if not t:
        return "de viaje. ¿Adivinas pa' dónde?"
    return "pa'l " + t[3:] if t.startswith("el ") else f"pa' {t}"


def cap(s):
    return s[:1].upper() + s[1:]


def build(rid):
    base = os.path.join(ROOT, "reels", rid)
    plan = json.load(open(os.path.join(base, "plan.json")))
    o = plan["offer"]
    a, b = d(o["ida"]), d(o["vuelta"])
    inf = info(o["ida"], o["vuelta"])
    img = lambda k: f"reels/{rid}/img/{k}.jpg"  # noqa: E731

    hora = plan.get("hora_salida")
    salida = (f"{cap(ig.DIAS[a.weekday()])} {a.day} de {ig.MESES[a.month - 1]}" + (f", {hora}" if hora else "")
              + f". Llegas al aeropuerto El Dorado. ¡Agarra la maleta, que nos vamos {teaser(plan)}!")
    dest = o["destino"].lower()
    for k in ("vuelo",):             # no spoilers before landing
        assert dest not in plan["lines"][k].lower(), f"{k}: no digas el destino antes de aterrizar ({o['destino']})"
    regreso = f"El {ig.DIAS[b.weekday()]} aterrizas en Bogotá, feliz y descansado. {days_off_line(inf['dias_libres'])}".strip()

    scenes = [{"text": salida, "media": {"type": "file", "path": "reels/common/eldorado-day.jpg", "focus": 0.5},
               "stick": SALIDA_STICK, "pops": [], "ambience": [],
               "crowd": [SALIDA_BUDDY] if plan.get("buddy") else []}]
    for k in keys_for(plan):
        sc = (plan.get("scenes") or {}).get(k) or {}
        st = sc.get("stick") or {"action": "none"}
        check_figure(st, plan["lines"][k], k)
        crowd = sc.get("crowd") or []
        for c in crowd:
            check_figure(c, plan["lines"][k], k + " (crowd)")
        sfx = sc.get("sfx") or []
        assert all(e["kind"] in SFX for e in sfx), f"{k}: sonido desconocido"
        pops = []
        if sc.get("pop"):
            p = sc["pop"]
            assert p["icon"] in ICONS, f"{k}: sticker desconocido {p['icon']}"
            assert p["word"].lower().strip("¡!¿?,.") in plan["lines"][k].lower(), f"{k}: la palabra del sticker no está en el texto"
            pops = [{"icon": p["icon"], "word": p["word"], "x": p["x"], "y": p["y"], "size": p.get("size", 190)}]
        amb = sc.get("ambience") or []
        amb = [a for a in ([amb] if isinstance(amb, str) else amb) if a in AMBIENCE]
        scenes.append({"text": plan["lines"][k], "media": {"type": "file", "path": img(k), "focus": 0.5},
                       "stick": st, "pops": pops, "ambience": amb, "crowd": crowd, "sfx": sfx,
                       "steps": sc.get("steps", False),
                       "action_sfx": sc.get("action_sfx", not amb)})
    scenes.append({"text": regreso, "media": {"type": "file", "path": "reels/common/eldorado-night.jpg", "focus": 0.5},
                   "stick": REGRESO_STICK, "pops": [], "ambience": [],
                   "crowd": [REGRESO_BUDDY] if plan.get("buddy") else []})

    escalas = "vuelo directo" if o["escalas"] == "directo" else o["escalas"]
    if (o.get("escala_larga") or "").strip():          # owner: long layover with time to explore it (Ofertas column Q)
        escalas += f" · escala larga en {o['escala_larga'].strip()}"
    fechas = f"{a.day} {ig.MESES[a.month - 1][:3]} – {b.day} {ig.MESES[b.month - 1][:3]}"
    title = f"{inf['dias']} días en {o['destino']}"
    tips = plan.get("que_hacer", "")
    sb = {
        "id": rid, "offer_id": o.get("offer_id", ""), "voice": "es-CO-GonzaloNeural", "rate": "+35%", "pad": 0.3,
        "stick_style": "classic", "caption_margin": 400, "caption_align": 8, "banner": {"logo": False},
        "scenes": scenes,
        "end": {"text": f"¿Y el precio? Ida y vuelta con {o['aerolinea']}, por solo {pesos(o['precio'])}. "
                        "¡Mira esta oferta y muchas más en viajespillados punto com!",
                "title": title, "kicker": "", "airline": f"{o['aerolinea']} · {escalas}", "price": cop(o["precio"]),
                "detail": f"ida y vuelta · {fechas}", "cta": "viajespillados.com",
                "small": "Mira esta oferta y muchas más · link en la bio",
                "media": {"type": "file", "path": img(plan.get("end_image", "dia1")), "focus": 0.5}},
        "caption": (f"{title} desde Bogotá ✈️ {tips} Ida y vuelta con {o['aerolinea']} desde {cop(o['precio'])} "
                    f"({fechas}). Mira la oferta en viajespillados.com – link en la bio.\n\n"
                    f"#viajespillados #vuelosbaratos #vuelosdesdebogota {ig.tag(o['destino'])} #ofertasdevuelos"),
    }
    json.dump(sb, open(os.path.join(base, "storyboard.json"), "w"), ensure_ascii=False, indent=1)
    print(f"storyboard listo: reels/{rid}/storyboard.json")
    for s in scenes:
        print(" -", s["text"])
    print(" - FIN:", sb["end"]["text"])


def preview(rid, out=None):
    """One frame per scene (stick man at 85 % of its move, sticker shown) side by side."""
    import reelfx
    import reel
    from PIL import Image
    sb = json.load(open(os.path.join(ROOT, "reels", rid, "storyboard.json")))
    tiles = []
    for sc in sb["scenes"]:
        im = Image.open(os.path.join(ROOT, sc["media"]["path"])).convert("RGB")
        k = max(1080 / im.width, 1920 / im.height)
        im = im.resize((round(im.width * k), round(im.height * k)))
        ox, oy = (im.width - 1080) // 2, (im.height - 1920) // 2
        base = im.crop((ox, oy, ox + 1080, oy + 1920)).convert("RGBA")
        n = 120                                   # beats are spread evenly here (in the video they follow the words)
        figs = [dict(c) for c in sc.get("crowd") or []] + [dict(sc.get("stick") or {"action": "none"})]
        picks = (int(n * 0.45), int(n * 0.85)) if any(f.get("beats") for f in figs) else (int(n * 0.85),)
        got = []
        for f in figs:
            reel.resolve_beats(f, [], 4.0)
            got.append({i: p for i, p in enumerate(reel.figure_frames(f, n, patch=True)) if i in picks})
        for i in picks:
            fr = base.copy()
            for g in got:
                if g.get(i):
                    fr.alpha_composite(g[i][0], g[i][1])
            reelfx.draw_pops(fr, [{**p, "t": 0} for p in sc.get("pops", [])], 1.0, 1080, 1920)
            tiles.append(fr.convert("RGB").resize((270, 480)))
    cols = min(len(tiles), 7)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (270 * cols, 480 * rows), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 270, (i // cols) * 480))
    out = out or os.path.join(ROOT, "reels", rid, "preview.jpg")
    sheet.save(out, quality=85)
    print("preview:", out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2])
    elif cmd == "preview":
        preview(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "buddy":
        print("yes" if buddy_next(sys.argv[2] if len(sys.argv) > 2 else None) else "no")
    elif cmd == "info":
        print(json.dumps(info(sys.argv[2], sys.argv[3]), ensure_ascii=False))
