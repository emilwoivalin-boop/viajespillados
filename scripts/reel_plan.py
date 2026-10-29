"""Daily Reel helper: turns a small plan (reels/<id>/plan.json) into a full storyboard.json with the
same structure as the approved Aruba Reel, and makes a quick placement preview.

    python scripts/reel_plan.py build <id>      # plan.json -> storyboard.json
    python scripts/reel_plan.py preview <id>    # contact sheet of every scene with stick man + sticker
    python scripts/reel_plan.py info <ida> <vuelta>   # Spanish dates + workdays off, for writing the plan

plan.json (written by the morning task, completed by the build task):
{
  "id": "lima-2027-01-16",
  "offer": {"destino": "Lima", "aerolinea": "JetSMART", "precio": 608490, "escalas": "directo",
            "ida": "2027-01-16", "vuelta": "2027-01-20", "link": "https://...", "sheet_row": 14},
  "hora_salida": null,                       # e.g. "4 de la tarde" ONLY if verified, else null
  "drive_folder_id": "...",
  "lines":   {"vuelo": "...", "llegada": "...", "dia1": "...", "dia2": "...", "dia3": "..."},
  "prompts": {"vuelo": "...", "llegada": "...", "dia1": "...", "dia2": "...", "dia3": "..."},
  "scenes":  {"vuelo":   {"stick": {...} | null, "pop": {...} | null, "ambience": "waves" | "crickets" | null},
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
ICONS = {"sun", "heart", "sparkle", "pin", "plane", "fish", "suitcase", "clock", "camera"}
AMBIENCE = {"waves", "crickets"}
ACTIONS = {"walk", "suitcase", "wave", "celebrate", "relax", "swim", "drive", "photo", "none"}

# fixed opening and closing scenes (same pictures and stick man moves as the approved Aruba Reel)
SALIDA_STICK = {"action": "suitcase", "x0": 0.2, "x1": 0.5, "y": 0.97, "y1": 0.68, "size": 520, "size1": 260}
REGRESO_STICK = {"action": "suitcase", "x0": 0.5, "x1": 0.75, "y": 0.68, "y1": 0.97, "size": 260, "size1": 520}

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
              + f". Llegas al aeropuerto El Dorado. ¡Agarra la maleta, que nos vamos pa' {o['destino']}!")
    regreso = f"El {ig.DIAS[b.weekday()]} aterrizas en Bogotá, feliz y descansado. {days_off_line(inf['dias_libres'])}".strip()

    scenes = [{"text": salida, "media": {"type": "file", "path": "reels/common/eldorado-day.jpg", "focus": 0.5},
               "stick": SALIDA_STICK, "pops": [], "ambience": []}]
    for k in KEYS:
        sc = (plan.get("scenes") or {}).get(k) or {}
        st = sc.get("stick") or {"action": "none"}
        assert st.get("action", "none") in ACTIONS, f"{k}: acción desconocida {st.get('action')}"
        pops = []
        if sc.get("pop"):
            p = sc["pop"]
            assert p["icon"] in ICONS, f"{k}: sticker desconocido {p['icon']}"
            assert p["word"].lower().strip("¡!¿?,.") in plan["lines"][k].lower(), f"{k}: la palabra del sticker no está en el texto"
            pops = [{"icon": p["icon"], "word": p["word"], "x": p["x"], "y": p["y"], "size": p.get("size", 190)}]
        amb = [sc["ambience"]] if sc.get("ambience") in AMBIENCE else []
        scenes.append({"text": plan["lines"][k], "media": {"type": "file", "path": img(k), "focus": 0.5},
                       "stick": st, "pops": pops, "ambience": amb,
                       "action_sfx": not amb})      # max one extra sound per picture
    scenes.append({"text": regreso, "media": {"type": "file", "path": "reels/common/eldorado-night.jpg", "focus": 0.5},
                   "stick": REGRESO_STICK, "pops": [], "ambience": []})

    escalas = "vuelo directo" if o["escalas"] == "directo" else o["escalas"]
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
                    "Ilustraciones: Viajes Pillados (con ayuda de IA).\n\n"
                    f"#viajespillados #vuelosbaratos #vuelosdesdebogota {ig.tag(o['destino'])} #ofertasdevuelos"),
    }
    json.dump(sb, open(os.path.join(base, "storyboard.json"), "w"), ensure_ascii=False, indent=1)
    print(f"storyboard listo: reels/{rid}/storyboard.json")
    for s in scenes:
        print(" -", s["text"])
    print(" - FIN:", sb["end"]["text"])


def preview(rid, out=None):
    """One frame per scene (stick man at 85 % of its move, sticker shown) side by side."""
    import stickman
    import reelfx
    from PIL import Image
    sb = json.load(open(os.path.join(ROOT, "reels", rid, "storyboard.json")))
    tiles = []
    for sc in sb["scenes"]:
        im = Image.open(os.path.join(ROOT, sc["media"]["path"])).convert("RGB")
        k = max(1080 / im.width, 1920 / im.height)
        im = im.resize((round(im.width * k), round(im.height * k)))
        ox, oy = (im.width - 1080) // 2, (im.height - 1920) // 2
        fr = im.crop((ox, oy, ox + 1080, oy + 1920)).convert("RGBA")
        st = sc.get("stick") or {"action": "none"}
        if st.get("action", "none") != "none":
            n = 40
            band = list(stickman.frames(st["action"], n, 30, x0=st.get("x0", 0.5), x1=st.get("x1", st.get("x0", 0.5)),
                                        feet=int(st.get("y", 0.8) * 1920), feet1=int(st.get("y1", st.get("y", 0.8)) * 1920),
                                        size=st.get("size", 330), size1=st.get("size1"), facing=st.get("facing", 1),
                                        band_h=1920))[int(n * 0.85)]
            fr.alpha_composite(band)
        reelfx.draw_pops(fr, [{**p, "t": 0} for p in sc.get("pops", [])], 1.0, 1080, 1920)
        tiles.append(fr.convert("RGB").resize((270, 480)))
    sheet = Image.new("RGB", (270 * len(tiles), 480), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 270, 0))
    out = out or os.path.join(ROOT, "reels", rid, "preview.jpg")
    sheet.save(out, quality=85)
    print("preview:", out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2])
    elif cmd == "preview":
        preview(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "info":
        print(json.dumps(info(sys.argv[2], sys.argv[3]), ensure_ascii=False))
