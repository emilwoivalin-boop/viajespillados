#!/usr/bin/env python3
"""
Viajes Pillados -> Instagram publisher.

Reads the offers from the Google Sheet "Viajes Pillados - Ofertas (web)" (tab "Ofertas",
the same sheet the website reads), renders a 1080x1350 image for each offer that is
approved for Instagram, and publishes it with the Instagram API (Instagram Login).

Sheet columns (row 1 = headers):
  A Publicar | B Publicado (AAAA-MM-DD) | C Destino | D Aerolínea | E Precio (COP) | F Tipo
  G Escalas | H Mes de viaje | I Categoría | J Link vuelo | K Foto (URL) | L Crédito foto
  M Link crédito | N Instagram | O Texto Instagram
Column N decides Instagram:  "sí"/"auto" = publish,  "revisar" or empty = wait for approval,
"no" = never.  Column O is the caption (optional; a basic caption is built if empty).

Modes:
  publish  – publish up to MAX_PER_RUN approved, fresh, not-yet-published offers
  preview  – only render images + captions (no posting), saved to instagram/preview/
  check    – verify that the token works and show the account name and token expiry

Env: IG_ACCESS_TOKEN, IG_USER_ID (GitHub secrets), optional MAX_PER_RUN, MAX_AGE_DAYS,
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
            "categoria", "link", "foto", "credito", "credito_link", "instagram", "texto"]
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
    return offers


def load_tips():
    """Tab "Qué hacer (captions)": Destino | País | Región | Qué hacer | Ojo | Caption listo."""
    try:
        url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
               f"&sheet={urllib.parse.quote('Qué hacer (captions)')}")
        r = requests.get(url, timeout=30, headers=UA)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))[1:]
        return {slug(r[0]): (r[3].strip(), r[4].strip()) for r in rows if len(r) >= 5 and r[0]}
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
    v = slug(o["instagram"])
    return v in ("si", "auto", "yes", "aprobado", "ok")


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
    sub = " · ".join(x for x in [o["tipo"], o["escalas"], o["mes"]] if x)

    f1 = fit_font(d, l1, "ExtraBold", 68, max_w)
    f2 = fit_font(d, city, "Black", 124, max_w, 64)
    f3 = font("Black", 136)
    f4 = fit_font(d, sub, "SemiBold", 48, max_w, 30)

    y = 92
    draw_text_with_shadow(img, (cx, y), l1, f1, "white"); y += f1.size + 14
    draw_text_with_shadow(img, (cx, y), city, f2, "white"); y += f2.size + 18
    draw_text_with_shadow(img, (cx, y), price, f3, YELLOW); y += f3.size + 26
    draw_text_with_shadow(img, (cx, y), sub, f4, "white")

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


# ---------------------------------------------------------------- caption
def caption(o):
    if o["texto"]:
        body = o["texto"].replace("\\n", "\n").strip()
    else:
        global TIPS
        if TIPS is None:
            TIPS = load_tips()
        que, ojo = TIPS.get(slug(o["destino"]), ("", ""))
        detalles = " · ".join(x for x in [o["escalas"], o["mes"]] if x)
        body = f"✈️ Vuelos de {o['aerolinea']} a {o['destino']} por {cop(o['precio_num'])} COP {o['tipo']}\n"
        body += f"📅 {detalles} · desde Bogotá\n\n"
        if que:
            body += f"{que}\n\n"
        if ojo:
            body += f"⚠️ Ojo: {ojo}\n\n"
        body += ("🔎 Revisa la información del vuelo en la web: viajespillados.com (link en la bio). "
                 "Los precios cambian rápido.")
    extra = []
    if o["credito"] and "foto" not in body.lower():
        extra.append(f"📷 Foto: {o['credito']}")
    if "#" not in body:
        extra.append(f"#viajespillados #vuelosbaratos #ofertasdevuelos #viajardesdecolombia #{slug(o['destino']).replace('-', '')}")
    text = body + ("\n\n" + "\n".join(extra) if extra else "")
    return text[:2200]


# ---------------------------------------------------------------- git + hosting
def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_push(paths, message):
    git("add", *paths)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    git("commit", "-m", message)
    for attempt in range(3):
        try:
            git("pull", "--rebase", "-q")
            git("push", "-q")
            return
        except subprocess.CalledProcessError:
            time.sleep(5)
    raise RuntimeError("git push failed")


def public_image_url(rel_path, wait_s=240):
    """Prefer viajespillados.com (GitHub Pages); fall back to raw.githubusercontent.com."""
    site_url = f"{SITE}/{rel_path}"
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            r = requests.head(site_url, timeout=15, headers=UA)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
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


def publish_to_instagram(image_url, text):
    uid = os.environ["IG_USER_ID"]
    container = api("POST", f"{uid}/media", image_url=image_url, caption=text)["id"]
    for _ in range(30):
        st = api("GET", container, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram no pudo procesar la imagen: {st}")
        time.sleep(4)
    media_id = api("POST", f"{uid}/media_publish", creation_id=container)["id"]
    permalink = api("GET", media_id, fields="permalink").get("permalink", "")
    return media_id, permalink


# ---------------------------------------------------------------- main
def summary(md):
    print(md)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as f:
            f.write(md + "\n")


def candidates(offers, state, destino=None, max_age=3):
    done = {p["id"] for p in state["posts"]}
    recent_dest = {slug(p["destino"]) for p in state["posts"]
                   if age_days(p.get("published_at", "")[:10]) < 5}
    out = []
    for o in offers:
        if o["id"] in done or slug(o["publicar"]) == "no" or slug(o["instagram"]) == "no":
            continue
        if destino:
            if slug(o["destino"]) == slug(destino):
                out.append(o)
            continue
        if approved(o) and 0 <= age_days(o["publicado"]) <= max_age and slug(o["destino"]) not in recent_dest:
            out.append(o)
    out.sort(key=lambda o: (age_days(o["publicado"]), -o["row"]))   # newest first
    return out


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "publish").lower()
    destino = os.environ.get("DESTINO", "").strip() or None
    max_per_run = int(os.environ.get("MAX_PER_RUN") or 1)
    max_age = int(os.environ.get("MAX_AGE_DAYS") or 3)

    if mode == "check":
        me = api("GET", "me", fields="user_id,username,account_type")
        ok = str(me.get("user_id")) == os.environ.get("IG_USER_ID", "").strip()
        summary(f"✅ Conectado a Instagram como **@{me.get('username')}** ({me.get('account_type')}), "
                f"user_id {me.get('user_id')}. " + ("IG_USER_ID coincide." if ok else
                f"⚠️ IG_USER_ID ({os.environ.get('IG_USER_ID')}) no coincide con el user_id de la cuenta."))
        return

    offers = load_offers()
    state = load_state()

    if mode == "preview":
        todo = candidates(offers, state, destino, max_age) or ([o for o in offers if slug(o["destino"]) == slug(destino)] if destino else [])
        if not todo and not destino:
            todo = sorted(offers, key=lambda o: age_days(o["publicado"]))[:3]
            summary("No hay ofertas aprobadas pendientes; muestro las 3 más recientes como ejemplo.")
        paths = []
        for o in todo[:5]:
            rel = f"instagram/preview/{o['id']}.jpg"
            render(o, os.path.join(ROOT, rel))
            paths.append(rel)
            with open(os.path.join(ROOT, f"instagram/preview/{o['id']}.txt"), "w") as f:
                f.write(caption(o) + "\n")
            paths.append(f"instagram/preview/{o['id']}.txt")
            summary(f"### {o['destino']} ({o['id']})\n![]({RAW}/{rel})\n\n```\n{caption(o)}\n```\n")
        if paths:
            commit_push(paths, "Instagram: vista previa")
        return

    todo = candidates(offers, state, destino, max_age)[:max_per_run]
    if not todo:
        summary("Nada que publicar: no hay ofertas aprobadas (columna N = sí/auto), nuevas (≤ "
                f"{max_age} días) y sin publicar.")
        return
    for o in todo:
        rel = f"instagram/img/{o['id']}.jpg"
        render(o, os.path.join(ROOT, rel))
        commit_push([rel], f"Instagram: imagen {o['destino']}")
        url = public_image_url(rel)
        media_id, permalink = publish_to_instagram(url, caption(o))
        state = load_state()
        state["posts"].append({
            "id": o["id"], "destino": o["destino"], "precio": o["precio_num"], "sheet_row": o["row"],
            "media_id": media_id, "permalink": permalink, "image": url,
            "published_at": datetime.now(BOGOTA).strftime("%Y-%m-%d %H:%M"),
        })
        save_state(state)
        commit_push(["instagram/published.json"], f"Instagram: publicado {o['destino']}")
        summary(f"✅ Publicado **{o['destino']}** ({cop(o['precio_num'])}): {permalink}")


if __name__ == "__main__":
    main()
