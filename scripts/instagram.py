#!/usr/bin/env python3
"""
Viajes Pillados -> Instagram publisher.

Reads the offers from the Google Sheet "Viajes Pillados - Ofertas (web)" (tab "Ofertas",
the same sheet the website reads), renders a 1080x1350 image for each offer that is
approved for Instagram, and publishes it with the Instagram API (Instagram Login).

Sheet columns (row 1 = headers):
  A Publicar | B Publicado (AAAA-MM-DD) | C Destino | D Aerolínea | E Precio (COP) | F Tipo
  G Escalas | H Mes de viaje | I Categoría | J Link vuelo | K Foto (URL) | L Crédito foto
  M Link crédito | N Instagram | O Texto Instagram | P Fechas | Q Escala larga (layover city with time to
  explore it, e.g. "Toronto" – adds a line to the caption) | R Captura (URL) (1–2 links to the owner's screenshots of the flight,
  separated by a space, added on the Offer check page; the offer image then shows them – design C)
Column N decides Instagram:  "sí"/"auto" = publish,  "revisar" or empty = wait for approval,
"no" = never.  Column O is the caption (optional; a basic caption is built if empty).

Modes:
  publish  – 2 posts a day (SLOT=morning/evening): all pending offers as one carousel (or one post)
  preview  – only render images + captions (no posting), saved to instagram/preview/
  check    – verify that the token works and show the account name and token expiry

Env: IG_ACCESS_TOKEN, IG_USER_ID (GitHub secrets), optional SLOT, MAX_AGE_DAYS,
     DESTINO (only this destination; used for "publish now" from the Actions tab).
"""
import csv, io, json, os, re, subprocess, sys, time, unicodedata, urllib.parse
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IG_DIR = os.path.join(ROOT, "instagram")
FONTS = os.path.join(IG_DIR, "fonts")
STATE = os.path.join(IG_DIR, "published.json")

SHEET_ID = "1us2JZr8rQRmeYlMTke9k2nPU26Cp6MLYQbtz3fHeL3c"
SHEET_TAB = "Ofertas"
SITE = "https://viajespillados.com"
RAW = "https://raw.githubusercontent.com/emilwoivalin-boop/viajespillados/main"
GRAPH = "https://graph.instagram.com"
UA = {"User-Agent": "ViajesPilladosBot/1.0 (https://viajespillados.com; instagram publisher)"}
BOGOTA = timezone(timedelta(hours=-5))

W, H = 1080, 1350
MAX_CAROUSEL = 10   # Instagram API limit for carousel items
YELLOW = (255, 198, 49)
NAVY = (20, 34, 59)


# ---------------------------------------------------------------- sheet
def load_offers():
    url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
           f"&sheet={urllib.parse.quote(SHEET_TAB)}&_={int(time.time())}")
    r = requests.get(url, timeout=30, headers=UA)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))
    if not rows or not re.match(r"publicar", rows[0][0], re.I):
        sys.exit("La hoja no tiene el formato esperado (A1 = Publicar).")
    keys = ["publicar", "publicado", "destino", "aerolinea", "precio", "tipo", "escalas", "mes",
            "categoria", "link", "foto", "credito", "credito_link", "instagram", "texto", "fechas", "escala_larga", "captura"]
    offers = []
    for i, row in enumerate(rows[1:], start=2):
        row = (row + [""] * len(keys))[: len(keys)]
        o = {k: (v or "").strip() for k, v in zip(keys, row)}
        if not o["destino"]:
            continue
        o["row"] = i
        o["precio_num"] = int(re.sub(r"[^\d]", "", o["precio"]) or 0)
        o["id"] = f"{slug(o['destino'])}-{o['publicado']}-{o['precio_num']}"
        offers.append(o)
    lib = load_photo_library()
    for o in offers:   # no photo on the offer row -> use the destination's photo from the tab "Fotos"
        if not o["foto"] and slug(o["destino"]) in lib:
            o["foto"], o["credito"], o["credito_link"] = lib[slug(o["destino"])]
    return offers


def load_photo_library():
    """Tab "Fotos": Destino | Foto (URL) | Crédito foto | Link crédito (one good photo per destination)."""
    try:
        url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
               f"&sheet={urllib.parse.quote('Fotos')}&_={int(time.time())}")
        r = requests.get(url, timeout=30, headers=UA)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))[1:]
        return {slug(r[0]): (r[1].strip(), r[2].strip(), r[3].strip()) for r in rows if len(r) >= 4 and r[0] and r[1]}
    except Exception as e:
        print("No se pudo leer la pestaña 'Fotos':", e)
        return {}


def load_tips():
    """Tab "Qué hacer (captions)": Destino | País | Región | Qué hacer | Ojo | Caption listo."""
    try:
        url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
               f"&sheet={urllib.parse.quote('Qué hacer (captions)')}")
        r = requests.get(url, timeout=30, headers=UA)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))[1:]
        return {slug(r[0]): (r[3].strip(), r[4].strip(), (r[5] if len(r) > 5 else "").strip(), r[1].strip())
                for r in rows if len(r) >= 5 and r[0]}
    except Exception as e:
        print("No se pudo leer la pestaña 'Qué hacer (captions)':", e)
        return {}


TIPS = None


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def cop(n):
    return "$" + f"{n:,}".replace(",", ".")


def age_days(date_str):
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str or "")
    if not m:
        return 10**6
    d = datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=BOGOTA).date()
    return (datetime.now(BOGOTA).date() - d).days


def approved(o):
    """Every offer shown on the website is posted on Instagram:
    only "no" in column A (Publicar) or column N (Instagram) keeps it off Instagram; "revisar" in A means the
    owner still has to check the layovers, so it stays off too until it is changed to "sí"."""
    return slug(o["publicar"]) not in ("no", "revisar") and slug(o["instagram"]) != "no"


# ---------------------------------------------------------------- state
def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"posts": []}


def save_state(state):
    with open(STATE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- image
def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, f"InterDisplay-{name}.otf"), size)


def fit_font(draw, text, name, size, max_w, min_size=40):
    while size > min_size:
        f = font(name, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(name, min_size)


def download_photo(url):
    r = requests.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    im = ImageOps.exif_transpose(im).convert("RGB")
    # trim 2% on each side: removes thin frames/borders some photos have
    w, h = im.size
    im = im.crop((int(w * .02), int(h * .02), int(w * .98), int(h * .98)))
    return ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.5))


def gradient(top_alpha_stops, bottom=False):
    """Vertical black-navy gradient mask. stops: list of (y_fraction, alpha 0..1)."""
    g = Image.new("L", (1, H))
    for y in range(H):
        f = y / (H - 1)
        if bottom:
            f = 1 - f
        a = 0.0
        for (f0, a0), (f1, a1) in zip(top_alpha_stops, top_alpha_stops[1:]):
            if f0 <= f <= f1:
                a = a0 + (a1 - a0) * ((f - f0) / (f1 - f0) if f1 > f0 else 0)
                break
        g.putpixel((0, y), int(255 * a))
    return g.resize((W, H))


def draw_text_with_shadow(base, xy, text, fnt, fill, anchor="mt"):
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((xy[0], xy[1] + 6), text, font=fnt, fill=(0, 0, 0, 150), anchor=anchor)
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    base.alpha_composite(shadow)
    ImageDraw.Draw(base).text(xy, text, font=fnt, fill=fill, anchor=anchor)


# ---------------------------------------------------------------- dates
# Colombian public holidays (same list as the "Holidays" tab of the price log)
FESTIVOS = {
    "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25",
    "2027-01-01", "2027-01-11", "2027-03-22", "2027-03-25", "2027-03-26", "2027-05-01", "2027-05-10",
    "2027-05-31", "2027-06-07", "2027-07-05", "2027-07-12", "2027-07-20", "2027-08-07", "2027-08-16",
    "2027-10-18", "2027-11-01", "2027-11-15", "2027-12-08", "2027-12-25",
}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


def trip_dates(o):
    """Column P "Fechas": "YYYY-MM-DD" (one way) or "YYYY-MM-DD/YYYY-MM-DD" (round trip)."""
    found = re.findall(r"\d{4}-\d{2}-\d{2}", o.get("fechas", ""))
    try:
        ds = [datetime.strptime(x, "%Y-%m-%d").date() for x in found[:2]]
    except ValueError:
        return []
    return ds


def is_workday(d):
    return d.weekday() < 5 and d.isoformat() not in FESTIVOS


def days_off(dep, ret):
    """Workdays you need to take off: you leave after work on a Friday (or on a weekend/holiday)
    and are back before work the next working day."""
    n, d = 0, dep
    while d <= ret:
        if is_workday(d) and not (d == dep and d.weekday() == 4):
            n += 1
        d += timedelta(days=1)
    return n


def no_days_off(o):
    ds = trip_dates(o)
    return len(ds) == 2 and ds[1] > ds[0] and days_off(*ds) == 0


def fmt_short(d):
    return f"{DIAS[d.weekday()][:3]} {d.day} {MESES[d.month - 1][:3]}"


def fmt_long(d, with_month=True):
    return f"{DIAS[d.weekday()]} {d.day}" + (f" de {MESES[d.month - 1]}" if with_month else "")


def dates_short(o):
    ds = trip_dates(o)
    if len(ds) == 2:
        if ds[0].month == ds[1].month:
            return f"{DIAS[ds[0].weekday()][:3]} {ds[0].day} – {fmt_short(ds[1])}"
        return f"{fmt_short(ds[0])} – {fmt_short(ds[1])}"
    if len(ds) == 1:
        return fmt_short(ds[0])
    return o["mes"]


def dates_long(o):
    ds = trip_dates(o)
    if len(ds) == 2:
        return f"del {fmt_long(ds[0], ds[0].month != ds[1].month)} al {fmt_long(ds[1])}"
    if len(ds) == 1:
        return f"el {fmt_long(ds[0])}"
    return f"en {o['mes']}" if o["mes"] else ""


def days_off_sentence(o):
    if not no_days_off(o):
        return ""
    dep, ret = trip_dates(o)
    salida = ("Sales el viernes después del trabajo" if dep.weekday() == 4 and dep.isoformat() not in FESTIVOS
              else f"Sales el {DIAS[dep.weekday()]}" + (" festivo" if dep.isoformat() in FESTIVOS else ""))
    vuelta = f"vuelves el {DIAS[ret.weekday()]}" + (" festivo" if ret.isoformat() in FESTIVOS else "")
    return f"{salida} y {vuelta}: no necesitas pedir días libres."


def render(o, out_path):
    photo = download_photo(o["foto"]) if o["foto"] else Image.new("RGB", (W, H), NAVY)
    img = photo.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (10, 18, 34, 255))
    # same top gradient as the website cards, plus a soft one at the bottom for the logo
    img = Image.composite(shade, img, gradient([(0, .74), (.40, .36), (.64, 0), (1, 0)]))
    img = Image.composite(shade, img, gradient([(0, .55), (.16, 0), (1, 0)], bottom=True))

    d = ImageDraw.Draw(img)
    cx, max_w = W // 2, W - 120
    l1 = f"Vuelos de {o['aerolinea']}"
    city = f"a {o['destino']}"
    price = cop(o["precio_num"])
    sub = " · ".join(x for x in [o["tipo"], o["escalas"]] if x)
    when = dates_short(o)

    f1 = fit_font(d, l1, "ExtraBold", 68, max_w)
    f2 = fit_font(d, city, "Black", 124, max_w, 64)
    f3 = font("Black", 136)
    f4 = fit_font(d, sub, "SemiBold", 48, max_w, 30)
    f5 = fit_font(d, when, "Bold", 50, max_w, 30)

    y = 92
    draw_text_with_shadow(img, (cx, y), l1, f1, "white"); y += f1.size + 14
    draw_text_with_shadow(img, (cx, y), city, f2, "white"); y += f2.size + 18
    draw_text_with_shadow(img, (cx, y), price, f3, YELLOW); y += f3.size + 26
    draw_text_with_shadow(img, (cx, y), sub, f4, "white"); y += f4.size + 14
    if when:
        draw_text_with_shadow(img, (cx, y), when, f5, "white"); y += f5.size + 26
    if no_days_off(o):
        badge = "SIN PEDIR DÍAS LIBRES"
        fbg = font("Black", 40)
        tw = d.textlength(badge, font=fbg)
        box = [cx - tw / 2 - 30, y, cx + tw / 2 + 30, y + 72]
        ImageDraw.Draw(img).rounded_rectangle(box, radius=36, fill=YELLOW)
        ImageDraw.Draw(img).text((cx, y + 36), badge, font=fbg, fill=NAVY, anchor="mm")
        y += 72 + 18
    if (o.get("escala_larga") or "").strip():      # owner: a long layover the owner approved is shown on the picture too
        badge = f"ESCALA LARGA: CONOCE {o['escala_larga'].strip().upper()}"
        fbg = fit_font(d, badge, "Black", 40, max_w - 60, 26)
        tw = d.textlength(badge, font=fbg)
        box = [cx - tw / 2 - 30, y, cx + tw / 2 + 30, y + 72]
        ImageDraw.Draw(img).rounded_rectangle(box, radius=36, fill="white")
        ImageDraw.Draw(img).text((cx, y + 36), badge, font=fbg, fill=NAVY, anchor="mm")

    # bottom: logo + site, photo credit
    logo = Image.open(os.path.join(ROOT, "logo-icon.png")).convert("RGBA").resize((84, 84), Image.LANCZOS)
    img.alpha_composite(logo, (48, H - 48 - 84))
    fb = font("ExtraBold", 40)
    draw_text_with_shadow(img, (48 + 84 + 18, H - 48 - 42), "viajespillados.com", fb, "white", anchor="lm")
    if o["credito"]:
        fc = font("SemiBold", 20)
        credit = "Foto: " + o["credito"]
        while d.textlength(credit, font=fc) > 560 and len(credit) > 10:
            credit = credit[:-2]
        if credit != "Foto: " + o["credito"]:
            credit = credit.rstrip(" ,/") + "…"
        ImageDraw.Draw(img).text((W - 40, H - 30), credit, font=fc, fill=(255, 255, 255, 190), anchor="rs")

    img.convert("RGB").save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
    return out_path


# ---------------------------------------------------------------- owner's flight screenshot (column R)
def drive_download_urls(url):
    """Google Drive share/view links -> direct download links to try in order; other https links as they are."""
    m = re.search(r"(?:/d/|[?&]id=)([A-Za-z0-9_-]{20,})", url or "")
    if m and "google" in url:
        fid = m.group(1)
        return [f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t",
                f"https://lh3.googleusercontent.com/d/{fid}=s2000",
                f"https://drive.google.com/uc?export=download&id={fid}"]
    return [url]


def download_screenshot(url):
    """The owner's screenshot (or None if there is none or it can't be read: then the post keeps the old format)."""
    if not (url or "").startswith("http"):
        return None
    for u in drive_download_urls(url):
        try:
            r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ViajesPillados"})
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content))
            return ImageOps.exif_transpose(im).convert("RGB")
        except Exception as e:
            ct = getattr(locals().get("r"), "headers", {}).get("content-type", "?") if "r" in locals() else "?"
            print(f"Captura no disponible ({u}): {type(e).__name__} {str(e)[:120]} [{ct}]", file=sys.stderr)
    return None


CORAL = (255, 90, 78)


def _shot_card(shot, width, label=None, pad=16, radius=26):
    """A screenshot on a white rounded card with a soft shadow, optional chip ("IDA") on its top-left corner.
    Returns the image and the offset of the card's own top-left corner inside it."""
    sc = (width - 2 * pad) / shot.width
    sw, sh = max(1, int(shot.width * sc)), max(1, int(shot.height * sc))
    s = shot.resize((sw, sh), Image.LANCZOS)
    top = 34 if label else 0
    cw, ch = width, sh + 2 * pad
    im = Image.new("RGBA", (cw + 40, ch + top + 40), (0, 0, 0, 0))
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((24, top + 30, 20 + cw + 4, top + 20 + ch + 10), radius, fill=(0, 0, 0, 120))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, top + 20, 20 + cw, top + 20 + ch), radius, fill="white")
    m = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, sw - 1, sh - 1), max(4, radius - pad), fill=255)
    im.paste(s, (20 + pad, top + 20 + pad), m)
    if label:
        f = font("Black", 30)
        tw = d.textlength(label, font=f)
        d.rounded_rectangle((38, 20, 38 + tw + 36, 72), 26, fill=CORAL)
        d.text((38 + 18 + tw / 2, 46), label, font=f, fill="white", anchor="mm")
    return im, 20, 20


def render_with_shots(o, shots, out_path):
    """Owner's rule (18 Nov 2026), design C "capturas protagonistas": when the offer has screenshots, they go INTO
    the offer image – big, slightly tilted cards over the photo (IDA / VUELTA on round trips with 2 screenshots),
    a yellow "DESDE <price>" sticker (the price must match the screenshot: the owner fixes it on the Offer check page)
    and "Así lo pillamos en Google Flights · <date>"."""
    photo = download_photo(o["foto"]) if o["foto"] else Image.new("RGB", (W, H), NAVY)
    img = photo.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (10, 18, 34, 255))
    img = Image.composite(shade, img, gradient([(0, .80), (.30, .45), (.6, .45), (1, .75)]))
    d = ImageDraw.Draw(img)
    cx, mw = W // 2, W - 120
    city = o["destino"]
    sub = " · ".join(x for x in [o["tipo"], o["escalas"]] if x)
    when = dates_short(o)
    f2 = fit_font(d, city, "Black", 128, mw, 64)
    y = 70
    draw_text_with_shadow(img, (cx, y), "VUELOS A", font("ExtraBold", 50), YELLOW); y += 62
    draw_text_with_shadow(img, (cx, y), city, f2, "white"); y += f2.size + 14
    draw_text_with_shadow(img, (cx, y), sub, fit_font(d, sub, "SemiBold", 44, mw, 28), "white"); y += 58
    if when:
        draw_text_with_shadow(img, (cx, y), when, fit_font(d, when, "Bold", 46, mw, 28), "white"); y += 60
    if no_days_off(o):
        draw_text_with_shadow(img, (cx, y), "SIN PEDIR DÍAS LIBRES", font("Black", 36), YELLOW); y += 54
    if (o.get("escala_larga") or "").strip():
        t = f"ESCALA LARGA: CONOCE {o['escala_larga'].strip().upper()}"
        draw_text_with_shadow(img, (cx, y), t, fit_font(d, t, "Black", 34, mw, 24), "white"); y += 52
    # the cards: as wide as possible, but together they must fit between the title and the footer
    labs = ["IDA", "VUELTA"] if len(shots) == 2 and o["tipo"].startswith("ida y vuelta") else [None] * len(shots)
    angles = [-2.2, 1.8] if len(shots) == 2 else [-1.5]
    top = max(y + 40, 520)
    avail = (H - 275) - top - 30 * (len(shots) - 1)
    width = W - 90
    for sh_ in shots:     # shrink tall (phone) screenshots so every card fits
        hmax = avail / len(shots) - 2 * 16 - 34
        width = min(width, int(hmax * sh_.width / sh_.height) + 32)
    width = max(width, 260)
    yb = top
    for s, lab, a in zip(shots, labs, angles):
        im, ox, oy = _shot_card(s, width, lab)
        r = im.rotate(a, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(r, (int(W / 2 - r.width / 2), int(yb - (r.height - im.height) / 2 - oy)))
        yb += im.height - 40 - 6
    # price sticker
    st = Image.new("RGBA", (420, 170), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    sd.rounded_rectangle((10, 10, 410, 160), 40, fill=YELLOW, outline=NAVY, width=6)
    sd.text((210, 58), "DESDE", font=font("ExtraBold", 30), fill=NAVY, anchor="mm")
    price = cop(o["precio_num"])
    sd.text((210, 108), price, font=fit_font(sd, price, "Black", 64, 370, 36), fill=NAVY, anchor="mm")
    st = st.rotate(5, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(st, (W - st.width - 30, min(int(yb) + 10, H - 190 - st.height)))
    seen = o["publicado"].lstrip("'")
    try:
        sd_ = datetime.strptime(seen, "%Y-%m-%d")
        line = f"Así lo pillamos en Google Flights · {sd_.day} {MESES[sd_.month - 1][:3]}"
    except ValueError:
        line = "Así lo pillamos en Google Flights"
    draw_text_with_shadow(img, (cx, H - 205), line, font("Bold", 30), "white")
    logo = Image.open(os.path.join(ROOT, "logo-icon.png")).convert("RGBA").resize((84, 84), Image.LANCZOS)
    img.alpha_composite(logo, (48, H - 48 - 84))
    draw_text_with_shadow(img, (48 + 84 + 18, H - 48 - 42), "viajespillados.com", font("ExtraBold", 40), "white",
                          anchor="lm")
    if o["credito"]:
        fc = font("SemiBold", 20)
        c = "Foto: " + o["credito"]
        while d.textlength(c, font=fc) > 520 and len(c) > 10:
            c = c[:-2]
        ImageDraw.Draw(img).text((W - 40, H - 30), c, font=fc, fill=(255, 255, 255, 190), anchor="rs")
    img.convert("RGB").save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
    return out_path


def render_slides(o, folder):
    """One image per offer: with the owner's screenshots (column R, max 2 links separated by spaces) the
    "capturas protagonistas" design, without them (or if none can be read) the old format."""
    rel = f"{folder}/{o['id']}.jpg"
    shots = [im for im in (download_screenshot(u) for u in (o.get("captura") or "").split()[:2]) if im is not None]
    if shots:
        render_with_shots(o, shots, os.path.join(ROOT, rel))
    else:
        render(o, os.path.join(ROOT, rel))
    return [rel]


# ---------------------------------------------------------------- caption
def tips(o):
    global TIPS
    if TIPS is None:
        TIPS = load_tips()
    return TIPS.get(slug(o["destino"]), ("", "", "", ""))


def tag(text):
    return "#" + re.sub(r"[^a-z0-9]", "", slug(text))


# Instagram allows max 5 hashtags per post: brand + 2 niche + destination/country (or 2 more niche)
BASE_TAGS = ["#viajespillados", "#vuelosbaratos", "#vuelosdesdebogota"]


def hashtags(offers):
    tags = list(BASE_TAGS)
    if len(offers) == 1:
        o = offers[0]
        tags.append(tag(o["destino"]))
        pais = tips(o)[3]
        if pais and slug(pais) != slug(o["destino"]):
            tags.append(tag(pais))
        else:
            tags.append("#ofertasdevuelos")
    else:
        tags += ["#ofertasdevuelos", "#viajarbarato"]
    return " ".join(dict.fromkeys(tags[:5]))


def headline(o):
    h = f"Vuelos de {o['aerolinea']} a {o['destino']} por {cop(o['precio_num'])} {o['tipo']} desde Bogotá"
    when = dates_long(o)
    h += (f", {when}." if when else ".")
    extra = days_off_sentence(o)
    return h + (f" {extra}" if extra else "")


def destination_caption(destinos):
    """Owner's rule: Instagram captions talk about the DESTINATION (what to do + a practical tip), not the flight –
    the picture/video already shows price and dates. Same text as the TikTok/YouTube download page."""
    try:
        import tiktok_feed
        text, _ = tiktok_feed.destination_text(list(destinos))
        return text
    except Exception as e:
        print("destination caption:", e)
        return None


def with_layover(text, offers):
    """Long layover the owner approved (column Q "Escala larga" = city): say there is time to explore it."""
    import tiktok_feed
    return tiktok_feed.with_extra(text, tiktok_feed.layover_lines(offers))[:2200]


def caption(o):
    """Single post: text about the destination (sheet tab "Qué hacer (captions)") + hashtags.
    Column O of "Ofertas" (Texto Instagram) still overrides everything."""
    if not o["texto"]:
        text = destination_caption([o["destino"]])
        if text:
            return with_layover(text, [o])
    if o["texto"]:
        body = o["texto"].replace("\\n", "\n").strip()
    else:
        que, ojo, listo, _ = tips(o)
        if listo:
            body = listo
        else:
            parts = [que] if que else []
            if ojo:
                parts.append(f"Ojo: {ojo}")
            parts.append("Revisa la información del vuelo en la web.")
            body = " ".join(parts)
    return with_layover(f"{headline(o)}\n\n{body}\n\n{hashtags([o])}", [o])


def caption_carousel(offers):
    text = destination_caption(dict.fromkeys(o["destino"] for o in offers))
    if text:
        return with_layover(text, offers)
    lines = ["Vuelos baratos desde Bogotá pillados hoy:", ""]
    for o in offers:
        det = ", ".join(x for x in [o["tipo"], o["escalas"], dates_short(o)] if x)
        badge = " – sin pedir días libres" if no_days_off(o) else ""
        lines.append(f"• {o['destino']} con {o['aerolinea']}: {cop(o['precio_num'])} ({det}){badge}")
    lines += ["", "Desliza para verlas todas. Revisa la información de los vuelos en la web.", "", hashtags(offers)]
    return with_layover("\n".join(lines), offers)


# ---------------------------------------------------------------- git + hosting
def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_push(paths, message):
    git("add", *paths)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    git("commit", "-m", message)
    for attempt in range(4):
        try:
            git("pull", "--rebase", "--autostash", "-q")
            git("push", "-q")
            return
        except subprocess.CalledProcessError:
            # another workflow changed the same log files (feed.json, published.json…) at the same time:
            # take the remote version and merge our new entries into it instead of failing
            subprocess.run(["git", "rebase", "--abort"], cwd=ROOT, capture_output=True)
            _merge_onto_remote(paths, message)
            time.sleep(3)
    raise RuntimeError("git push failed")


def _merge_json(ours, theirs):
    if isinstance(ours, list) and isinstance(theirs, list):
        seen = {json.dumps(x, sort_keys=True) for x in theirs}
        keys = {(x.get("id") or x.get("feed_id")) for x in theirs if isinstance(x, dict)} - {None}
        new = [x for x in ours if json.dumps(x, sort_keys=True) not in seen
               and not (isinstance(x, dict) and (x.get("id") or x.get("feed_id")) in keys)]
        return new + theirs
    if isinstance(ours, dict) and isinstance(theirs, dict):
        out = dict(theirs)
        for k, v in ours.items():
            out[k] = _merge_json(v, theirs[k]) if k in theirs else v
        return out
    return ours


def _merge_onto_remote(paths, message):
    """Rebuild our commit on top of origin/main: JSON files are merged, other files are ours."""
    mine = {}
    for p in paths:
        fp = os.path.join(ROOT, p)
        if os.path.isfile(fp):
            mine[p] = open(fp, "rb").read()
    git("fetch", "-q", "origin")
    git("reset", "-q", "--hard", "origin/main")
    for p, data in mine.items():
        fp = os.path.join(ROOT, p)
        if p.endswith(".json") and os.path.isfile(fp):
            try:
                merged = _merge_json(json.loads(data), json.load(open(fp)))
                json.dump(merged, open(fp, "w"), ensure_ascii=False, indent=1)
                continue
            except ValueError:
                pass
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "wb").write(data)
    git("add", *mine)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        git("commit", "-q", "-m", message)


def public_image_url(rel_path, wait_s=240):
    """Prefer viajespillados.com (GitHub Pages); fall back to raw.githubusercontent.com."""
    site_url = f"{SITE}/{rel_path}"
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            r = requests.head(site_url, timeout=15, headers=UA)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith(("image/", "video/")):
                return site_url
        except requests.RequestException:
            pass
        time.sleep(15)
    return f"{RAW}/{rel_path}"


# ---------------------------------------------------------------- Instagram API
def api(method, path, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    r = requests.request(method, f"{GRAPH}/{path}", params=params if method == "GET" else None,
                         data=params if method != "GET" else None, timeout=60)
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        if err.get("code") == 190:
            raise SystemExit("❌ El token de Instagram no es válido o venció. Genera uno nuevo en Meta "
                             "(API setup with Instagram login → Generate token) y guárdalo en el secreto IG_ACCESS_TOKEN.")
        raise RuntimeError(f"Instagram API error {r.status_code}: {json.dumps(data, ensure_ascii=False)}")
    return data


def wait_ready(container):
    for _ in range(40):
        st = api("GET", container, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram no pudo procesar la imagen: {st}")
        time.sleep(4)
    raise RuntimeError("Instagram tardó demasiado en procesar la imagen")


def finish(container):
    uid = os.environ["IG_USER_ID"]
    media_id = api("POST", f"{uid}/media_publish", creation_id=container)["id"]
    permalink = api("GET", media_id, fields="permalink").get("permalink", "")
    return media_id, permalink


def publish_to_instagram(image_url, text):
    uid = os.environ["IG_USER_ID"]
    container = api("POST", f"{uid}/media", image_url=image_url, caption=text)["id"]
    wait_ready(container)
    return finish(container)


def publish_carousel(image_urls, text):
    uid = os.environ["IG_USER_ID"]
    children = []
    for url in image_urls:
        c = api("POST", f"{uid}/media", image_url=url, is_carousel_item="true")["id"]
        wait_ready(c)
        children.append(c)
    parent = api("POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(children), caption=text)["id"]
    wait_ready(parent)
    return finish(parent)


# ---------------------------------------------------------------- main
def summary(md):
    print(md)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as f:
            f.write(md + "\n")


def candidates(offers, state, destino=None, max_age=3):
    done = {p["id"] for p in state["posts"]}
    # same sheet row + destination + date = same offer, even if the owner corrected its price afterwards
    done_rows = {(p.get("sheet_row"), slug(p.get("destino", "")), p["id"].rsplit("-", 1)[0]) for p in state["posts"]}
    out = []
    for o in offers:
        key = (o["row"], slug(o["destino"]), o["id"].rsplit("-", 1)[0])
        if o["id"] in done or key in done_rows or not approved(o):
            continue
        if destino:
            if slug(o["destino"]) == slug(destino):
                out.append(o)
        elif 0 <= age_days(o["publicado"]) <= max_age:
            out.append(o)
    if destino:
        out.sort(key=lambda o: (age_days(o["publicado"]), -o["row"]))   # newest first
    else:
        # oldest first, so every offer gets posted before it is too old
        out.sort(key=lambda o: (-age_days(o["publicado"]), o["row"]))
    return out


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "publish").lower()
    destino = os.environ.get("DESTINO", "").strip() or None
    max_age = int(os.environ.get("MAX_AGE_DAYS") or 3)

    if mode == "check":
        me = api("GET", "me", fields="user_id,username,account_type")
        ok = str(me.get("user_id")) == os.environ.get("IG_USER_ID", "").strip()
        summary(f"✅ Conectado a Instagram como **@{me.get('username')}** ({me.get('account_type')}), "
                f"user_id {me.get('user_id')}. " + ("IG_USER_ID coincide." if ok else
                f"⚠️ IG_USER_ID ({os.environ.get('IG_USER_ID')}) no coincide con el user_id de la cuenta."))
        return

    if mode == "diag":
        # read-only diagnosis: publishing quota + create (but never publish) test containers
        uid = os.environ["IG_USER_ID"]
        out = []
        img = f"{SITE}/instagram/img/aruba-2026-10-26-645976.jpg"
        for label, fn in [
            ("content_publishing_limit", lambda: api("GET", f"{uid}/content_publishing_limit", fields="config,quota_usage")),
            ("single container", lambda: api("POST", f"{uid}/media", image_url=img, caption="test")),
            ("carousel item container", lambda: api("POST", f"{uid}/media", image_url=img, is_carousel_item="true")),
        ]:
            try:
                out.append(f"{label}: OK {json.dumps(fn())}")
            except BaseException as e:
                out.append(f"{label}: FAIL {e}")
        with open(os.path.join(ROOT, "instagram/diag.txt"), "w") as f:
            f.write(datetime.now(BOGOTA).strftime("%Y-%m-%d %H:%M") + "\n" + "\n".join(out) + "\n")
        commit_push(["instagram/diag.txt"], "Instagram: diagnóstico")
        return

    offers = load_offers()
    state = load_state()

    if mode == "preview":
        todo = candidates(offers, state, destino, max_age) or ([o for o in offers if slug(o["destino"]) == slug(destino)] if destino else [])
        if not todo and not destino:
            todo = sorted(offers, key=lambda o: age_days(o["publicado"]))[:3]
            summary("No hay ofertas aprobadas pendientes; muestro las 3 más recientes como ejemplo.")
        paths = []
        for o in todo[:MAX_CAROUSEL]:
            slides = render_slides(o, "instagram/preview")
            rel = slides[0]
            paths += slides
            with open(os.path.join(ROOT, f"instagram/preview/{o['id']}.txt"), "w") as f:
                f.write(caption(o) + "\n")
            paths.append(f"instagram/preview/{o['id']}.txt")
            summary(f"### {o['destino']} ({o['id']})\n" + "".join(f"![]({RAW}/{r})\n" for r in slides) +
                    f"\n```\n{caption(o)}\n```\n")
        if len(todo) > 1:
            with open(os.path.join(ROOT, "instagram/preview/carrusel.txt"), "w") as f:
                f.write(caption_carousel(todo[:MAX_CAROUSEL]) + "\n")
            paths.append("instagram/preview/carrusel.txt")
            summary(f"### Texto si se publican juntas (carrusel)\n```\n{caption_carousel(todo[:MAX_CAROUSEL])}\n```\n")
        if paths:
            commit_push(paths, "Instagram: vista previa")
        return

    pending = candidates(offers, state, destino, max_age)
    if destino:
        todo = pending[:1]
    else:
        # 2 posts a day: the morning post takes half of the pending offers, the evening post the rest.
        slot = os.environ.get("SLOT", "manual")
        n = len(pending)
        take = (n + 1) // 2 if slot == "morning" else n
        todo = pending[:min(take, MAX_CAROUSEL)]
    if not todo:
        summary("Nada que publicar: no hay ofertas nuevas (≤ "
                f"{max_age} días) y sin publicar.")
        return

    rels, per = [], []
    for o in todo:
        slides = render_slides(o, "instagram/img")
        if rels and len(rels) + len(slides) > MAX_CAROUSEL:      # max 10 slides: later offers wait for the next post
            break
        rels += slides
        per.append(slides)
    todo = todo[:len(per)]
    commit_push(rels, "Instagram: imágenes " + ", ".join(o["destino"] for o in todo))
    urls = [public_image_url(r) for r in rels]
    try:
        if len(urls) == 1:
            media_id, permalink = publish_to_instagram(urls[0], caption(todo[0]))
        else:
            media_id, permalink = publish_carousel(urls, caption(todo[0]) if len(todo) == 1 else caption_carousel(todo))
    except BaseException as e:
        # keep the error in the repo so it can be read without the Actions logs
        with open(os.path.join(ROOT, "instagram/last_error.txt"), "w") as f:
            f.write(f"{datetime.now(BOGOTA):%Y-%m-%d %H:%M} – {type(e).__name__}: {e}\nURLs: {urls}\n")
        commit_push(["instagram/last_error.txt"], "Instagram: error al publicar")
        raise

    state = load_state()
    now = datetime.now(BOGOTA).strftime("%Y-%m-%d %H:%M")
    k = 0
    for o, slides in zip(todo, per):
        state["posts"].append({
            "id": o["id"], "destino": o["destino"], "precio": o["precio_num"], "sheet_row": o["row"],
            "media_id": media_id, "permalink": permalink, "image": urls[k], "published_at": now,
            "carousel": len(urls) > 1, "captura": len(slides) > 1,
        })
        k += len(slides)
    save_state(state)
    names = ", ".join(o["destino"] for o in todo)
    import tiktok_feed   # same post, ready to repost on TikTok by hand
    text = caption(todo[0]) if len(todo) == 1 else caption_carousel(todo)
    feed = tiktok_feed.add("photos", "Ofertas: " + names, rels, text, permalink,
                           destinos=[o["destino"] for o in todo], extra=tiktok_feed.layover_lines(todo))
    import x_post        # same post on X (skipped if the X keys are not set)
    xp = x_post.share_latest()
    import fb_post       # and on the Facebook Page (skipped if not connected)
    xp += fb_post.share_latest()
    commit_push(["instagram/published.json", feed] + xp, f"Instagram: publicado {names}")
    summary(f"✅ Publicado ({'carrusel de ' + str(len(urls)) if len(urls) > 1 else 'post'}): **{names}** – {permalink}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        if not isinstance(e, SystemExit) or e.code not in (0, None):
            with open(os.path.join(ROOT, "instagram/last_error.txt"), "w") as f:
                f.write(f"{datetime.now(BOGOTA):%Y-%m-%d %H:%M} – {(sys.argv[1:] or ['publish'])[0]} – "
                        f"{type(e).__name__}: {e}\n")
            try:
                commit_push(["instagram/last_error.txt"], "Instagram: error")
            except Exception:
                pass
        raise
