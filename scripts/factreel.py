#!/usr/bin/env python3
"""
Fact Reels – "Did you know…" videos on a cartoon map (1080x1920), in the Map Verse spirit but in the
Viajes Pillados cartoon style: flat OpenStreetMap map, the city outline, a camera that flies from fact to
fact, a pin, a real photo as a polaroid sticker, the stick man, AI voice + big captions.

  reels/facts/<id>/storyboard.json  → reels/facts/<id>/reel.mp4 (+ cover.jpg, caption.txt)
  reels/facts/<id>/map/osm.json.gz  (from scripts/factmap_fetch.py, GitHub workflow factreel.yml mode fetch)
  reels/facts/<id>/img/<n>.jpg      (from `photos`, Wikimedia Commons, credits in img/credits.json)

storyboard.json:
{
  "voice": "en-US-BrianNeural", "rate": "+10%", "city": "Amsterdam",
  "facts": [{"text": "Did you know …", "lat": 52.37, "lon": 4.89, "view": 1100, "label": "Royal Palace",
             "photo": "File:….jpg", "stick": {"action": "point"}}],
  "end": {"text": "Which one surprised you the most?", "line1": "…", "line2": "…"},
  "caption": "…"
}

Usage: python scripts/factreel.py photos <id>
       python scripts/factreel.py render <id> [--dry]    (--dry: no TTS, estimated timing, silent – local tests)
       python scripts/factreel.py frame <id> <t> <out.jpg> [--dry]   (one frame, to check the look)
"""
import gzip, io, json, math, os, re, subprocess, sys, time

import cairo
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instagram as ig  # noqa: E402
import reel  # noqa: E402
import reelfx  # noqa: E402
import stickman  # noqa: E402

W, H, FPS = 1080, 1920, 30
R = 6378137.0
UA = {"User-Agent": "ViajesPilladosBot/1.0 (https://viajespillados.com; fact reels)"}

# cartoon palette
LAND = (247, 238, 218)
WATER, WATER_E = (122, 197, 235), (78, 158, 206)
GREEN, GREEN_E = (172, 216, 128), (128, 184, 96)
BUILD, BUILD_E = (236, 223, 199), (210, 192, 160)
ROAD, ROAD_E = (255, 255, 255), (222, 206, 178)
MAJOR, MAJOR_E = (255, 214, 102), (226, 168, 58)
LINE = (255, 92, 72)
YELLOW = (255, 214, 0)
NAVY = (20, 34, 59)

LANG = {"en": {"fact": "FACT", "photo": "Photo", "map": "Map © OpenStreetMap contributors"},
        "es": {"fact": "DATO", "photo": "Foto", "map": "Mapa © colaboradores de OpenStreetMap"}}
TXT = dict(LANG["en"])
FLY_FIRST, FLY = 1.9, 1.3          # camera flight at the start of a scene (s)
INTRO_HOLD, INTRO_FLY = 0.55, 1.5  # continent → country → city intro
INTRO_T = 3 * INTRO_HOLD + 2 * INTRO_FLY + 0.2 - INTRO_HOLD


# ------------------------------------------------------------------ geometry
def merc(lon, lat):
    lon, lat = np.asarray(lon, float), np.clip(np.asarray(lat, float), -85, 85)
    return R * np.radians(lon), R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


class Feat:
    """A list of shapes in mercator metres, with a bbox per shape for fast culling."""

    def __init__(self, shapes):
        self.shapes, self.per = [], []
        for rings in shapes:
            arrs = []
            for ring in rings:
                a = np.asarray(ring, float)
                if len(a) < 2:
                    continue
                x, y = merc(a[:, 0], a[:, 1])
                arrs.append(np.stack([x, y], 1))
            if arrs:
                self.per.append([float(np.abs(np.diff(r, axis=0)).sum()) for r in arrs])
                self.shapes.append(arrs)
        if self.shapes:
            self.bb = np.array([[min(r[:, 0].min() for r in s), min(r[:, 1].min() for r in s),
                                 max(r[:, 0].max() for r in s), max(r[:, 1].max() for r in s)] for s in self.shapes])
        else:
            self.bb = np.zeros((0, 4))

    def visible(self, vb, min_size=0.0):
        if not len(self.bb):
            return []
        b = self.bb
        ok = (b[:, 2] >= vb[0]) & (b[:, 0] <= vb[2]) & (b[:, 3] >= vb[1]) & (b[:, 1] <= vb[3])
        if min_size:
            ok &= np.maximum(b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]) >= min_size
        return [(self.shapes[i], self.per[i]) for i in np.nonzero(ok)[0]]


def fact_base(rid):
    """Daily fact Reels live in reels/<id>/ (with plan.json), one-off/test ones in reels/facts/<id>/."""
    d = os.path.join(ROOT, "reels", rid)
    return d if os.path.exists(os.path.join(d, "plan.json")) else os.path.join(ROOT, "reels", "facts", rid)


def load_map(base, iso=None):
    d = json.load(gzip.open(os.path.join(base, "map", "osm.json.gz"), "rt"))
    m = {
        "boundary": Feat([d["boundary"]]),
        "water": Feat([p["o"] + p["i"] for p in d["water"]]),
        "green": Feat([p["o"] + p["i"] for p in d["green"]]),
        "major": Feat([[ln] for ln in d["roads"]["major"]]),
        "minor": Feat([[ln] for ln in d["roads"]["minor"]]),
        "rail": Feat([[ln] for ln in d["rail"]]),
        "build": Feat([[b] for b in d["buildings"]]),
        "bbox": d["bbox"],
        "coast": [np.stack(merc(np.asarray(c)[:, 0], np.asarray(c)[:, 1]), 1) for c in d.get("coast", []) if len(c) > 1],
        "sand": Feat([p["o"] + p["i"] for p in d.get("sand", [])]),
    }
    if iso:
        ne = json.load(gzip.open(os.path.join(ROOT, "data", "naturalearth.json.gz"), "rt"))
        m["ne_countries"] = Feat([[r for p in c["polys"] for r in p] for c in ne["countries"]])
        m["ne_lakes"] = Feat(ne["lakes"])
        cn = next(c for c in ne["countries"] if c["iso"] == iso)
        main = max(cn["polys"], key=lambda p: len(p[0]))          # mainland only (no overseas islands)
        m["country"] = Feat([main])
    return m


# ------------------------------------------------------------------ camera
class Cam:
    """Point (tx, ty) (mercator) is drawn at screen (W/2, ay); w = ground metres across the screen width."""

    def __init__(self, tx, ty, w, ay):
        self.tx, self.ty, self.w, self.ay = tx, ty, w, ay

    def scale(self, k):                       # px per mercator metre; k = 1/cos(lat)
        return W / (self.w * k)


def smooth(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def fly(a, b, p, k):
    """Camera between a and b at progress p: log-zoom with a zoom-out bump when the points are far apart;
    on big zoom changes the centre follows the zoom so the target doesn't slide."""
    u = smooth(p)
    dist = math.hypot(b.tx - a.tx, b.ty - a.ty) / k
    la, lb = math.log(a.w), math.log(b.w)
    bump = min(1.6, max(0.0, dist / max(a.w, b.w) * 1.1 - 0.3))
    lw = la + (lb - la) * u + bump * math.sin(math.pi * u)
    w = math.exp(lw)
    ratio = max(a.w, b.w) / min(a.w, b.w)
    if ratio > 3 and bump < 0.05:
        uc = (1 / w - 1 / a.w) / (1 / b.w - 1 / a.w)
        uc = min(1.0, max(0.0, uc))
    else:
        uc = u
    return Cam(a.tx + (b.tx - a.tx) * uc, a.ty + (b.ty - a.ty) * uc, w, a.ay + (b.ay - a.ay) * u)


# ------------------------------------------------------------------ map drawing
def lerp_log(w, pts):
    """pts: [(ground width m, value)] sorted by width; value interpolated in log(width)."""
    lw = math.log(w)
    if w <= pts[0][0]:
        return pts[0][1]
    for (w0, v0), (w1, v1) in zip(pts, pts[1:]):
        if w <= w1:
            f = (lw - math.log(w0)) / (math.log(w1) - math.log(w0))
            return v0 + (v1 - v0) * f
    return pts[-1][1]


def rgb(c, a=1.0):
    return (c[0] / 255, c[1] / 255, c[2] / 255, a)


def _ctx_fns(c, mat, s, vb):
    px = 1.0 / s

    def path(shapes, close):
        c.save()
        c.set_matrix(mat)
        for rings, per in shapes:
            for r, pr in zip(rings, per):
                keep = max(4, int(pr * s / 2.5))          # about one point every 2.5 screen pixels
                pts = r if keep >= len(r) else np.concatenate([r[::int(math.ceil(len(r) / keep))], r[-1:]])
                c.move_to(pts[0, 0], pts[0, 1])
                for x, y in pts[1:]:
                    c.line_to(x, y)
                if close:
                    c.close_path()
        c.restore()

    def fill(feat, col, edge=None, ew=1.0, min_px=1.5, alpha=1.0):
        sh = feat.visible(vb, min_px * px)
        if not sh:
            return
        path(sh, True)
        c.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        c.set_source_rgba(*rgb(col, alpha))
        if edge:
            c.fill_preserve()
            c.set_source_rgba(*rgb(edge, alpha))
            c.set_line_width(ew)
            c.stroke()
        else:
            c.fill()

    def stroke(feat, col, width, casing=None, cw=0.0, min_px=3, alpha=1.0):
        if width < 0.4:
            return
        sh = feat.visible(vb, min_px * px)
        if not sh:
            return
        if casing:
            path(sh, False)
            c.set_source_rgba(*rgb(casing, alpha))
            c.set_line_width(width + cw)
            c.stroke()
        path(sh, False)
        c.set_source_rgba(*rgb(col, alpha))
        c.set_line_width(width)
        c.stroke()

    return path, fill, stroke


SAND = (246, 228, 172)


def sea_fill(surf, coast, cam, s):
    """OpenStreetMap coastlines have the land on their left: draw them, split the screen into regions and paint
    the regions that lie on the right (water) side of a coastline."""
    from scipy import ndimage
    mask = cairo.ImageSurface(cairo.FORMAT_A8, W, H)
    c = cairo.Context(mask)
    c.set_line_width(2.5)
    c.set_source_rgba(0, 0, 0, 1)
    seeds = []
    x0v, x1v = cam.tx - W / 2 / s, cam.tx + W / 2 / s
    y0v, y1v = cam.ty - (H - cam.ay) / s, cam.ty + cam.ay / s
    for ln in coast:
        if ln[:, 0].max() < x0v or ln[:, 0].min() > x1v or ln[:, 1].max() < y0v or ln[:, 1].min() > y1v:
            continue
        sx = W / 2 + (ln[:, 0] - cam.tx) * s
        sy = cam.ay - (ln[:, 1] - cam.ty) * s
        c.move_to(sx[0], sy[0])
        for a, b in zip(sx[1:], sy[1:]):
            c.line_to(a, b)
        c.stroke()
        step = max(1, len(sx) // 40)
        for i in range(0, len(sx) - 1, step):
            dx, dy = sx[i + 1] - sx[i], sy[i + 1] - sy[i]
            ln_ = math.hypot(dx, dy)
            if ln_ < 0.5:
                continue
            # screen y points down, so the water (right of travel in map space) is on the left of travel on screen
            nx, ny = dy / ln_, -dx / ln_
            mx, my = (sx[i] + sx[i + 1]) / 2, (sy[i] + sy[i + 1]) / 2
            seeds.append((mx - nx * 5, my - ny * 5, mx + nx * 5, my + ny * 5))
    if not seeds:
        return
    mask.flush()
    m = np.ndarray((H, mask.get_stride()), np.uint8, mask.get_data())[:, :W] > 0
    lab, n = ndimage.label(~m)
    votes = np.zeros(n + 1)
    for wx, wy, lx, ly in seeds:
        for px_, py_, v in ((wx, wy, 1), (lx, ly, -1)):
            xi, yi = int(px_), int(py_)
            if 0 <= xi < W and 0 <= yi < H:
                votes[lab[yi, xi]] += v
    sea = np.nonzero(votes > 0)[0]
    sea = sea[sea > 0]
    if not len(sea):
        return
    wm = np.isin(lab, sea)
    wm = ndimage.binary_dilation(wm, iterations=2)        # cover the drawn coastline itself
    buf = np.ndarray((H, W, 4), np.uint8, surf.get_data())
    buf[wm] = (WATER[2], WATER[1], WATER[0], 255)
    surf.mark_dirty()


def _surface_np(surf):
    surf.flush()
    return np.ndarray((H, W, 4), np.uint8, surf.get_data())


def ramp(w, w_full, w_zero):
    """1 when the view is at w_full, 0 at w_zero (log scale, either direction)."""
    f = (math.log(w) - math.log(w_zero)) / (math.log(w_full) - math.log(w_zero))
    return min(1.0, max(0.0, f))


def draw_map(m, cam, k, city_frac=1.0, country_frac=1.0):
    s = cam.scale(k)
    hw, hh0, hh1 = W / 2 / s, cam.ay / s, (H - cam.ay) / s
    vb = (cam.tx - hw, cam.ty - hh1, cam.tx + hw, cam.ty + hh0)
    mat = cairo.Matrix(s, 0, 0, -s, W / 2 - cam.tx * s, cam.ay + cam.ty * s)
    w = cam.w

    # 1) world base (Natural Earth): sea, countries, lakes
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(surf)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_source_rgba(*rgb(WATER))
    c.paint()
    path, fill, stroke = _ctx_fns(c, mat, s, vb)
    if "ne_countries" in m:
        fill(m["ne_countries"], LAND, (255, 255, 255), lerp_log(w, [(60e3, 0.0), (300e3, 2.0), (3e6, 1.6)]), min_px=2)
        fill(m["ne_lakes"], WATER, None, min_px=2)

    # 2) city detail (OpenStreetMap) on its own layer, faded in while zooming and feathered at its edges
    osm_a = ramp(w, 90e3, 220e3)
    if osm_a > 0:
        so = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        co = cairo.Context(so)
        co.set_line_join(cairo.LINE_JOIN_ROUND)
        co.set_line_cap(cairo.LINE_CAP_ROUND)
        co.set_source_rgba(*rgb(LAND))
        co.paint()
        if m.get("coast"):
            sea_fill(so, m["coast"], cam, s)
            co = cairo.Context(so)
            co.set_line_join(cairo.LINE_JOIN_ROUND)
            co.set_line_cap(cairo.LINE_CAP_ROUND)
        _, f2, s2 = _ctx_fns(co, mat, s, vb)
        f2(m["sand"], SAND, None, 1.0, min_px=lerp_log(w, [(2000, 1.5), (30000, 6.0)]))
        far = w > 6000
        f2(m["green"], GREEN, None if w > 3000 else GREEN_E, 1.5,
           min_px=lerp_log(w, [(2000, 2.0), (8000, 5.0), (30000, 9.0), (120000, 14.0)]))
        if w < 5000:
            f2(m["build"], BUILD, BUILD_E if w < 2500 else None, 1.0, min_px=2)
        f2(m["water"], WATER, None if far else WATER_E, lerp_log(w, [(800, 2.5), (6000, 1.2)]),
           min_px=lerp_log(w, [(2000, 1.0), (8000, 3.0), (30000, 6.0), (120000, 10.0)]))
        s2(m["minor"], ROAD, lerp_log(w, [(600, 9.0), (1500, 4.5), (4000, 1.6), (8000, 0.0)]), ROAD_E, 2.0)
        s2(m["rail"], (170, 160, 150), lerp_log(w, [(1000, 4.0), (8000, 2.0), (40000, 1.0), (100000, 0.0)]))
        s2(m["major"], MAJOR, lerp_log(w, [(600, 14.0), (2000, 7.0), (8000, 3.0), (40000, 1.2), (100000, 0.6)]),
           None if far else MAJOR_E, lerp_log(w, [(1000, 3.0), (6000, 1.0)]),
           min_px=lerp_log(w, [(4000, 3), (30000, 25), (100000, 40)]))
        base, top = _surface_np(surf), _surface_np(so)
        x0, y0 = merc(m["bbox"][0], m["bbox"][1])
        x1, y1 = merc(m["bbox"][2], m["bbox"][3])
        sx0, sx1 = W / 2 + (x0 - cam.tx) * s, W / 2 + (x1 - cam.tx) * s
        sy0, sy1 = cam.ay - (y1 - cam.ty) * s, cam.ay - (y0 - cam.ty) * s
        fe = max(40.0, min(220.0, (sx1 - sx0) * 0.08))
        xs = np.arange(W, dtype=np.float32)
        ys = np.arange(H, dtype=np.float32)
        mx = np.clip(np.minimum(xs - sx0, sx1 - xs) / fe, 0, 1)
        my = np.clip(np.minimum(ys - sy0, sy1 - ys) / fe, 0, 1)
        mask = (my[:, None] * mx[None, :] * osm_a)[:, :, None]
        base[:] = (base * (1 - mask) + top * mask).astype(np.uint8)
        surf.mark_dirty()

    # 3) highlight: dim outside the country (far) / the city (near), red outlines
    c = cairo.Context(surf)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    path, fill, stroke = _ctx_fns(c, mat, s, vb)
    country_a = ramp(w, 120e3, 40e3) if "country" in m else 0.0
    city_a = ramp(w, 40e3, 90e3)
    for feat, a, frac in ((m.get("country"), country_a, country_frac), (m["boundary"], city_a, city_frac)):
        if feat is None or a <= 0 or not feat.shapes:
            continue
        shp = [(feat.shapes[0], feat.per[0])]
        c.rectangle(0, 0, W, H)
        path(shp, True)
        c.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        c.set_source_rgba(0.08, 0.12, 0.2, 0.32 * a)
        c.fill()
        if frac > 0:
            lw = lerp_log(w, [(1500, 12.0), (8000, 8.0), (40000, 6.0), (3e6, 6.0)])
            total = sum(feat.per[0]) * s
            for col, width in ((WHITE_T, lw + 7), (LINE, lw)):
                path(shp, True)
                if frac < 1:
                    c.set_dash([total * frac, total * 2])
                c.set_source_rgba(*rgb(col, a))
                c.set_line_width(width)
                c.stroke()
                c.set_dash([])
    buf = _surface_np(surf)
    return Image.fromarray(buf[:, :, [2, 1, 0]].copy(), "RGB").convert("RGBA")


WHITE_T = (255, 255, 255)


# ------------------------------------------------------------------ overlays
def font(name, size):
    return ig.font(name, size)


def outlined_text(img, xy, text, fnt, fill, stroke, sw, anchor="mm"):
    d = ImageDraw.Draw(img)
    d.text(xy, text, font=fnt, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


def title_layer(city, n, total):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ig.fit_font(d, city.upper(), "Black", 112, W - 120)
    outlined_text(img, (W // 2, 175), city.upper(), f, YELLOW, (0, 0, 0), 9)
    if n:
        lab = f"{TXT['fact']} {n}/{total}"
        f2 = font("ExtraBold", 40)
        tw = d.textlength(lab, font=f2)
        d.rounded_rectangle((W / 2 - tw / 2 - 26, 255, W / 2 + tw / 2 + 26, 315), 30, fill=(0, 0, 0, 215))
        d.text((W / 2, 286), lab, font=f2, fill=(255, 255, 255), anchor="mm")
    d.text((W - 24, H - 18), TXT["map"], font=font("SemiBold", 22),
           fill=(40, 40, 40, 170), anchor="rs")
    return img


def polaroid(path, credit, width=640, tilt=-3.0):
    ph = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    pw, phh = width - 44, int((width - 44) * 0.72)
    ph = ImageOps.fit(ph, (pw, phh), Image.LANCZOS, centering=(0.5, 0.45))
    card = Image.new("RGBA", (width, phh + 22 + 64), (255, 255, 255, 255))
    card.paste(ph, (22, 22))
    d = ImageDraw.Draw(card)
    f = font("SemiBold", 21)
    txt = credit
    while d.textlength(txt, font=f) > width - 40 and len(txt) > 10:
        txt = txt[:-2]
    if txt != credit:
        txt = txt.rstrip() + "…"
    d.text((width / 2, phh + 22 + 34), txt, font=f, fill=(110, 110, 110), anchor="mm")
    card = card.rotate(tilt, Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", (card.width + 60, card.height + 60), (0, 0, 0, 0))
    mask = card.split()[3].point(lambda v: int(v * 0.45))
    sh.paste((0, 0, 0, 255), (36, 42), mask)
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    sh.alpha_composite(card, (30, 30))
    return sh


def pin_img(size=120):
    S = 4
    s = size * S
    im = Image.new("RGBA", (s, int(s * 1.35)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = s * 0.42
    cx, cy = s / 2, r + s * 0.06
    d.polygon([(cx - r * 0.78, cy + r * 0.55), (cx + r * 0.78, cy + r * 0.55), (cx, s * 1.3)], fill=(20, 20, 20))
    d.ellipse((cx - r - S * 4, cy - r - S * 4, cx + r + S * 4, cy + r + S * 4), fill=(20, 20, 20))
    d.polygon([(cx - r * 0.7, cy + r * 0.5), (cx + r * 0.7, cy + r * 0.5), (cx, s * 1.24)], fill=LINE)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=LINE)
    d.ellipse((cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42), fill=(255, 255, 255))
    return im.resize((size, int(size * 1.35)), Image.LANCZOS)


def label_img(text):
    f = font("ExtraBold", 40)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(d0.textlength(text, font=f))
    im = Image.new("RGBA", (tw + 56, 76), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((3, 3, tw + 53, 73), 36, fill=(255, 255, 255), outline=(20, 20, 20), width=4)
    d.text((im.width / 2, 39), text, font=f, fill=NAVY, anchor="mm")
    return im


def end_layer(e):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f1 = ig.fit_font(d, e.get("line1", ""), "Black", 84, W - 140)
    f2 = ig.fit_font(d, e.get("line2", ""), "ExtraBold", 50, W - 160)
    y = 470
    outlined_text(img, (W // 2, y), e.get("line1", ""), f1, (0, 0, 0), (255, 255, 255), 8)
    if e.get("line2"):
        tw = d.textlength(e["line2"], font=f2)
        d.rounded_rectangle((W / 2 - tw / 2 - 34, y + 80, W / 2 + tw / 2 + 34, y + 160), 40, fill=(0, 0, 0, 220))
        d.text((W / 2, y + 120), e["line2"], font=f2, fill=(255, 255, 255), anchor="mm")
    return img


def pop_scale(t):
    """0 → overshoot → 1 over 0.35 s."""
    if t <= 0:
        return 0.0
    if t >= 0.35:
        return 1.0
    p = t / 0.35
    return 1 + 0.12 * math.sin(math.pi * p) - (1 - p) ** 3


def paste_scaled(fr, im, cx, cy, sc, alpha=1.0):
    if sc <= 0.02 or alpha <= 0.01:
        return
    if abs(sc - 1) > 0.01:
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BICUBIC)
    if alpha < 1:
        a = im.split()[3].point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    fr.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


# ------------------------------------------------------------------ stickers (Twemoji, CC BY 4.0)
def emoji_code(e):
    return "-".join(f"{ord(ch):x}" for ch in e if ord(ch) != 0xFE0F)


_STK = {}


def sticker_img(emoji, size):
    key = (emoji, size)
    if key not in _STK:
        src = Image.open(os.path.join(ROOT, "assets", "stickers", emoji_code(emoji) + ".png")).convert("RGBA")
        pad = int(size * 0.12)
        im = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
        im.alpha_composite(src.resize((size, size), Image.LANCZOS), (pad, pad))
        a = im.split()[3]
        border = a.filter(ImageFilter.MaxFilter(2 * (size // 22) + 1)).point(lambda v: 255 if v > 40 else 0)
        out = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.paste((0, 0, 0, 110), (0, 0), border)
        sh = sh.filter(ImageFilter.GaussianBlur(size // 28))
        out.alpha_composite(sh, (size // 40, size // 25))
        white = Image.new("RGBA", im.size, (255, 255, 255, 0))
        white.paste((255, 255, 255, 255), (0, 0), border)
        out.alpha_composite(white)
        out.alpha_composite(im)
        _STK[key] = out
    return _STK[key]


def stat_img(big, small):
    f1 = font("Black", 150)
    f2 = font("ExtraBold", 46)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w1 = d0.textlength(big, font=f1)
    if w1 > W - 120:
        f1 = font("Black", int(150 * (W - 120) / w1))
        w1 = d0.textlength(big, font=f1)
    w2 = d0.textlength(small, font=f2) if small else 0
    im = Image.new("RGBA", (int(max(w1, w2) + 120), 290), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((im.width / 2, 100), big, font=f1, fill=YELLOW, stroke_width=11, stroke_fill=(0, 0, 0), anchor="mm")
    if small:
        d.rounded_rectangle((im.width / 2 - w2 / 2 - 30, 205, im.width / 2 + w2 / 2 + 30, 275), 35, fill=(0, 0, 0, 225))
        d.text((im.width / 2, 241), small, font=f2, fill=(255, 255, 255), anchor="mm")
    return im


def count_text(big, p):
    """'847,000' / '847.000' at progress p → '423,500' / '423.500' (keeps prefix/suffix and the thousands separator)."""
    m = re.search(r"\d[\d,\.]*", big)
    if not m or p >= 1:
        return big
    num = m.group(0)
    sep = "," if "," in num else ("." if re.fullmatch(r"\d{1,3}(\.\d{3})+", num) else "")
    v = float(re.sub(r"\D", "", num)) if sep else float(num)
    cur = v * smooth(p)
    txt = f"{int(round(cur)):,}".replace(",", sep) if sep else str(int(round(cur)))
    return big[:m.start()] + txt + big[m.end():]


def word_time(sc, key):
    """Scene-relative time of a cue: a number (s after the voice starts) or the first word starting with key."""
    if isinstance(key, (int, float)):
        return sc["lead"] + float(key)
    k = re.sub(r"[^\w]", "", str(key).lower())
    for a, b, w in sc["words"]:
        if re.sub(r"[^\w]", "", w.lower()).startswith(k):
            return sc["lead"] + a
    # numbers are often spoken as several words ("twelve seventy-five"): use the position in the text instead
    toks = [re.sub(r"[^\w]", "", t.lower()) for t in sc["fc"]["text"].split()]
    idx = next((i for i, t in enumerate(toks) if t.startswith(k)), None)
    if idx is not None and sc["words"]:
        j = min(len(sc["words"]) - 1, round(idx * len(sc["words"]) / max(1, len(toks))))
        return sc["lead"] + sc["words"][j][0]
    return sc["lead"] + 0.4


# ------------------------------------------------------------------ captions
def ass(chunks, path):
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Sub,Inter Display Black,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,"
        "7,3,2,70,70,250,1\n"
        "Style: Hi,Inter Display Black,78,&H0000D6FF,&H0000D6FF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,"
        "7,3,2,70,70,250,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n")
    with open(path, "w") as f:
        f.write(head)
        for s, e, t, hi in chunks:
            t = t.replace("{", "(").replace("}", ")")
            f.write(f"Dialogue: 0,{reel.ass_time(s)},{reel.ass_time(e)},{'Hi' if hi else 'Sub'},,0,0,0,,{t}\n")


def fake_voice(text, work, i):
    """--dry: estimated word timings and silence (no internet needed)."""
    words, t = [], 0.0
    for w in text.split():
        d = 0.12 + 0.055 * len(w)
        words.append((t, t + d, w))
        t += d + 0.04
    wav = os.path.join(work, f"v{i}.wav")
    reel.sh("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{t:.3f}", wav)
    return wav, t, words


# ------------------------------------------------------------------ photos
def photos(rid):
    base = fact_base(rid)
    sb = json.load(open(os.path.join(base, "storyboard.json")))
    os.makedirs(os.path.join(base, "img"), exist_ok=True)
    cpath = os.path.join(base, "img", "credits.json")
    credits = json.load(open(cpath)) if os.path.exists(cpath) else {}
    for i, fc in enumerate(sb["facts"]):
        title = fc.get("photo")
        dst = os.path.join(base, "img", f"{i}.jpg")
        if not title or (os.path.exists(dst) and credits.get(str(i), {}).get("title") == title):
            continue
        for attempt in range(6):
            r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=60, params={
                "action": "query", "format": "json", "titles": title, "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": 1400})
            if r.ok and r.text.startswith("{"):
                break
            time.sleep(10 * (attempt + 1))
        page = next(iter(r.json()["query"]["pages"].values()))
        ii = page["imageinfo"][0]
        meta = ii.get("extmetadata", {})
        clean = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h or "")).strip()
        author = clean(meta.get("Artist", {}).get("value"))
        lic = clean(meta.get("LicenseShortName", {}).get("value"))
        for attempt in range(6):
            img = requests.get(ii["thumburl"], headers=UA, timeout=120)
            if img.ok and img.headers.get("content-type", "").startswith("image"):
                break
            time.sleep(10 * (attempt + 1))
        img.raise_for_status()
        ImageOps.exif_transpose(Image.open(io.BytesIO(img.content))).convert("RGB").save(dst, "JPEG", quality=92)
        credits[str(i)] = {"title": title, "author": author, "license": lic, "page": ii.get("descriptionurl")}
        print(i, title, author, lic)
        time.sleep(2)
    json.dump(credits, open(cpath, "w"), indent=1, ensure_ascii=False)
    return credits


# ------------------------------------------------------------------ render
def plan(rid, dry=False):
    base = fact_base(rid)
    sb = json.load(open(os.path.join(base, "storyboard.json")))
    work = os.path.join("/tmp", "factreel-" + rid)
    os.makedirs(work, exist_ok=True)
    TXT.update(LANG.get(sb.get("lang", "en"), LANG["en"]))
    mbase = fact_base(sb["map_from"]) if sb.get("map_from") else base
    m = load_map(mbase, sb.get("country"))
    credits = json.load(open(os.path.join(base, "img", "credits.json"))) if os.path.exists(
        os.path.join(base, "img", "credits.json")) else {}
    bb = m["boundary"].bb[0]
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    lat0 = math.degrees(2 * math.atan(math.exp(cy / R)) - math.pi / 2)
    k = 1 / math.cos(math.radians(lat0))
    city_w = max((bb[2] - bb[0]) / k * 1.12, (bb[3] - bb[1]) / k * 1.12 * W / 1250)
    city = Cam(cx, cy, city_w, 1010)
    intro = None
    if "country" in m:                     # continent → country → city at the start
        cb = m["country"].bb[0]
        ccx, ccy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
        cw = max((cb[2] - cb[0]) / k * 1.6, (cb[3] - cb[1]) / k * 1.6 * W / 1300)
        intro = [Cam(ccx, ccy, sb.get("continent_view", 3.2e6), 1010), Cam(ccx, ccy, cw, 1010), city]
    voice, rate = sb.get("voice", "en-US-BrianNeural"), sb.get("rate", "+35%")

    scenes, t = [], 0.0
    end = dict(sb.get("end", {}), end=True)
    offer = None
    if os.path.exists(os.path.join(base, "plan.json")):        # daily fact Reel: ends with the offer (price card)
        import reel_plan
        plan_ = json.load(open(os.path.join(base, "plan.json")))
        offer = plan_.get("offer")
    if offer:
        deal = reel_plan.deal_text(plan_, os.path.basename(base), offer["aerolinea"], reel_plan.pesos(offer["precio"]))
        for plug in reel_plan.DEAL_PLUGS:                       # no website plug in fact Reels
            deal = deal.replace(plug, "").strip()
        end["q_words"] = len(end.get("text", "").split())
        end["text"] = (end.get("text", "") + " " + deal).strip()
        end["deal"] = deal
        inf = reel_plan.info(offer["ida"], offer["vuelta"])
        from datetime import date as _d
        a_, b_ = _d.fromisoformat(offer["ida"]), _d.fromisoformat(offer["vuelta"])
        esc = "vuelo directo" if offer["escalas"] == "directo" else offer["escalas"]
        if (offer.get("escala_larga") or "").strip():
            esc += f" · escala larga en {offer['escala_larga'].strip()}"
        end["card"] = {"title": f"{inf['dias']} días en {offer['destino']}", "airline": f"{offer['aerolinea']} · {esc}",
                       "price": reel_plan.cop(offer["precio"]),
                       "detail": f"ida y vuelta · {a_.day} {ig.MESES[a_.month - 1][:3]} – {b_.day} {ig.MESES[b_.month - 1][:3]}",
                       "cta": ""}
    items = list(sb["facts"]) + [end]
    for i, fc in enumerate(items):
        if dry:
            wav, vdur, words = fake_voice(fc["text"], work, i)
        else:
            wav, vdur, words = reel.tight_voice(fc["text"], voice, os.path.join(work, f"v{i}.mp3"), rate)
        fly_t = FLY_FIRST if i == 0 else FLY
        is_intro = i == 0 and intro is not None and "lat" not in fc
        if is_intro:
            fly_t = INTRO_T
        lead = 0.0 if i == 0 else 0.35          # small breath between facts (camera already moving)
        dur = lead + vdur + fc.get("hold", 0.45)
        dur = max(dur, fly_t + 1.2)
        if fc.get("end"):
            cam = Cam(city.tx, city.ty, city.w, 1010)
            dur += 1.6
        elif "lat" not in fc:
            cam = city if is_intro else Cam(city.tx, city.ty, city.w * fc.get("zoom", 0.62), 1080)
            dur = max(dur, fly_t + 0.8)
        else:
            x, y = merc(fc["lon"], fc["lat"])
            cam = Cam(float(x), float(y), fc.get("view", 1100), 1130)
        ph = os.path.join(base, "img", f"{i}.jpg")
        cr = credits.get(str(i), {})
        credit = f"{TXT['photo']}: {cr.get('author', '')} · {cr.get('license', '')}" if cr else ""
        scenes.append({"i": i, "t0": t, "dur": dur, "lead": lead, "fly": fly_t, "cam": cam, "fc": fc,
                       "wav": wav, "vdur": vdur, "words": words,
                       "photo": ph if os.path.exists(ph) and "lat" in fc else None, "credit": credit,
                       "intro": intro if is_intro else None, "loc": "lat" in fc})
        t += dur
    return sb, base, work, m, k, city, scenes, t


def scene_at(scenes, t):
    for sc in scenes:
        if t < sc["t0"] + sc["dur"]:
            return sc
    return scenes[-1]


class Renderer:
    def __init__(self, rid, dry=False):
        (self.sb, self.base, self.work, self.m, self.k, self.city, self.scenes, self.total) = plan(rid, dry)
        nfacts = len(self.sb["facts"])
        self.titles = [title_layer(self.sb["city"], n, nfacts) for n in range(nfacts + 1)]
        self.pin = pin_img(110)
        self.labels = [label_img(sc["fc"]["label"]) if sc["fc"].get("label") else None for sc in self.scenes]
        self.polas = [polaroid(sc["photo"], sc["credit"], 640, (-3.0, 2.5)[sc["i"] % 2]) if sc["photo"] else None
                      for sc in self.scenes]
        self.endimg = end_layer(self.sb.get("end", {}))
        self.card = None
        esc = self.scenes[-1]
        if esc["fc"].get("card"):
            cp = os.path.join(self.work, "card.png")
            reel.end_png(esc["fc"]["card"], cp)
            self.card = Image.open(cp).convert("RGBA")
            qn = esc["fc"].get("q_words", 0)
            ws = esc["words"]
            esc["card_t"] = esc["lead"] + (ws[qn][0] if qn < len(ws) else esc["vdur"] * 0.4)
        for sc in self.scenes:
            fc = sc["fc"]
            sc["stk"] = [dict(st, t=word_time(sc, st.get("at", 0.3))) for st in fc.get("stickers", [])]
            if fc.get("stat"):
                sc["stat"] = dict(fc["stat"], t=word_time(sc, fc["stat"].get("at", 0.3)))
                sc["stat_img"] = stat_img(fc["stat"]["big"], fc["stat"].get("small", ""))
            if sc.get("intro"):           # cues in the intro wait for the arrival over the city
                for st in sc["stk"] + ([sc["stat"]] if sc.get("stat") else []):
                    st["t"] = max(st["t"], sc["fly"] + 0.2)
        self.figs = {}
        stickman.STYLE = self.sb.get("stick_style", "classic")
        stickman.POINT_AT = 132

    def cam_at(self, sc, t):
        lt = t - sc["t0"]
        if sc.get("intro"):
            a, b, c = sc["intro"]
            if lt < INTRO_HOLD:
                return a
            if lt < INTRO_HOLD + INTRO_FLY:
                return fly(a, b, (lt - INTRO_HOLD) / INTRO_FLY, self.k)
            if lt < 2 * INTRO_HOLD + INTRO_FLY + 0.2:
                return b
            return fly(b, c, (lt - 2 * INTRO_HOLD - INTRO_FLY - 0.2) / INTRO_FLY, self.k)
        prev = self.scenes[sc["i"] - 1]["cam"] if sc["i"] > 0 else self.city
        return fly(prev, sc["cam"], lt / sc["fly"], self.k)

    def fig_frame(self, sc, n_in_scene):
        i = sc["i"]
        if i not in self.figs:
            st = {"action": "teach", "x0": 0.17, "y": 0.80, "size": 300, "facing": 1}
            st.update(sc["fc"].get("stick", {}))
            n = int(sc["dur"] * FPS) + 3
            self.figs[i] = list(reel.figure_frames(st, n, patch=True))
        fr = self.figs[i]
        return fr[min(n_in_scene, len(fr) - 1)]

    def frame(self, t):
        sc = scene_at(self.scenes, t)
        lt = t - sc["t0"]
        cam = self.cam_at(sc, t)
        if sc.get("intro"):
            cf = min(1.0, max(0.0, (lt - 0.2) / 1.1))
            tf = min(1.0, max(0.0, (lt - (2 * INTRO_HOLD + INTRO_FLY + 0.2 + INTRO_FLY * 0.55)) / 1.2))
        else:
            cf, tf = 1.0, (min(1.0, t / 1.4) if sc["i"] == 0 else 1.0)
        img = draw_map(self.m, cam, self.k, city_frac=tf, country_frac=cf)
        end = sc["fc"].get("end")
        # pin + label at the target
        if sc.get("loc"):
            s = cam.scale(self.k)
            px = W / 2 + (sc["cam"].tx - cam.tx) * s
            py = cam.ay - (sc["cam"].ty - cam.ty) * s
            ta = lt - sc["fly"] + 0.1
            if ta > 0:
                drop = max(0.0, 1 - ta / 0.3) ** 2 * 260
                bounce = abs(math.sin(min(ta, 0.6) * 8)) * 18 * max(0.0, 1 - ta / 0.6)
                ring = (ta % 1.4) / 1.4
                d = ImageDraw.Draw(img)
                rr = 20 + ring * 70
                d.ellipse((px - rr, py - rr * 0.45, px + rr, py + rr * 0.45), outline=(*LINE, int(220 * (1 - ring))),
                          width=5)
                img.alpha_composite(self.pin, (int(px - self.pin.width / 2), int(py - self.pin.height - drop - bounce + 6)))
                if self.labels[sc["i"]] is not None:
                    paste_scaled(img, self.labels[sc["i"]], px, py + 62, pop_scale(ta - 0.15))
        # previous polaroid leaves, the new one pops in
        if sc["i"] > 0 and lt < 0.45 and self.polas[sc["i"] - 1] is not None:
            q = lt / 0.45
            paste_scaled(img, self.polas[sc["i"] - 1], W / 2 - q * q * 900, 640, 1.0, 1 - q)
        if self.polas[sc["i"]] is not None:
            tp = lt - sc["fly"] - 0.15
            paste_scaled(img, self.polas[sc["i"]], W / 2, 640, pop_scale(tp))
        # stickers + big number
        if sc.get("stat"):
            st = sc["stat"]
            ta = lt - st["t"]
            if ta > 0:
                im = sc["stat_img"]
                if st.get("count", True) and ta < 0.7:
                    im = stat_img(count_text(st["big"], ta / 0.7), st.get("small", ""))
                paste_scaled(img, im, W * st.get("x", 0.5), H * st.get("y", 0.31), pop_scale(ta))
        for k, st in enumerate(sc["stk"]):
            ta = lt - st["t"]
            if ta <= 0:
                continue
            im = sticker_img(st["emoji"], st.get("size", 300))
            ang = st.get("tilt", (-8, 7, -4)[k % 3]) + 5 * math.sin(2 * math.pi * 0.8 * ta + k)
            im = im.rotate(ang, Image.BICUBIC, expand=True)
            bob = 10 * math.sin(2 * math.pi * 0.6 * ta + k * 1.7)
            paste_scaled(img, im, W * st.get("x", 0.5), H * st.get("y", 0.33) + bob, pop_scale(ta))
        # stick man
        band = self.fig_frame(sc, int(lt * FPS))
        if band:
            img.alpha_composite(band[0], band[1])
        # screen shake on a knock on the glass
        for kt, kind, _ in sc.setdefault("_moves", move_sfx(sc)):
            if kind == "knock" and 0 <= lt - kt < 0.14:
                d = 9 if int((lt - kt) * 60) % 2 == 0 else -9
                m = 14
                img = img.crop((m + d, m + d * 0.5, W - m + d, H - m + d * 0.5)).resize((W, H), Image.BILINEAR)
                break
        # titles
        if end and self.card is not None and lt >= sc["card_t"]:
            k = min(1.0, (lt - sc["card_t"]) / 0.3)
            lay = self.card if k >= 1 else Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 0)), self.card, k)
            img.alpha_composite(lay)
        elif end:
            img.alpha_composite(self.titles[0])
            ta = lt - 0.6
            if ta > 0:
                lay = self.endimg if ta > 0.4 else Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 0)), self.endimg, ta / 0.4)
                img.alpha_composite(lay)
        else:
            img.alpha_composite(self.titles[sc["i"] + 1])
        return img.convert("RGB")


def move_sfx(sc):
    """Sounds for the stick man's moves (knocks, pointer taps, baton swings), scene-relative."""
    st = sc["fc"].get("stick", {})
    beats = st.get("beats") or [dict(st, t=0)]
    out = []
    for k, b in enumerate(beats):
        t0 = b.get("t", 0)
        t1 = beats[k + 1].get("t", sc["dur"]) if k + 1 < len(beats) else sc["dur"]
        act = b.get("action", "teach")
        if act == "knock":                       # once per beat
            c = t0 + stickman.KNOCK_FIRST
            out += [(c, "knock", 0.6), (c + stickman.KNOCK_GAP, "knock", 0.55)]
        elif act == "tap":
            c = t0 + 0.45
            while c < t1:
                out.append((c, "tick", 0.35))
                c += 0.9
        elif act == "swing":
            c = t0 + 0.2
            while c < t1:
                out.append((c, "whoosh", 0.07))
                c += 0.8
        elif act == "celebrate":
            out.append((t0 + 0.1, "boing", 0.2))
    return out


def render(rid, dry=False):
    rd = Renderer(rid, dry)
    work, base = rd.work, rd.base
    n = int(rd.total * FPS)
    video = os.path.join(work, "video.mp4")
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", video]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    for f in range(n):
        p.stdin.write(rd.frame(f / FPS).tobytes())
        if f % 150 == 0:
            print(f"frame {f}/{n} ({time.time() - t0:.0f} s)")
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg video failed")

    # voice track: each line starts after its scene's lead-in
    parts, subs, sfx = [], [], []
    for sc in rd.scenes:
        pw = os.path.join(work, f"vp{sc['i']}.wav")
        reel.sh("ffmpeg", "-y", "-i", sc["wav"], "-af",
                f"adelay={int(sc['lead'] * 1000)}|{int(sc['lead'] * 1000)},apad=whole_dur={sc['dur']:.3f}",
                "-ar", "44100", "-ac", "2", pw)
        parts.append(pw)
        words = reel.attach_punctuation(sc["words"], sc["fc"]["text"])
        chunks = reel.chunk_words(words, sc["t0"] + sc["lead"])
        nums = re.compile(r"\d")
        subs += [(s, e, txt, bool(nums.search(txt))) for s, e, txt in chunks]
        if sc["i"] > 0:
            sfx.append((sc["t0"], "whoosh", 0.22))
        for st in sc.get("stk", []):
            sfx.append((sc["t0"] + st["t"], st.get("sfx", "pop"), 0.35))
        if sc.get("stat"):
            st = sc["stat"]
            if st.get("drumroll", True) and st["t"] > 0.85:
                sfx.append((sc["t0"] + st["t"] - 0.8, "drumroll", 0.22))
            sfx.append((sc["t0"] + st["t"], st.get("sfx", "ding"), 0.3))
        sfx += [(sc["t0"] + tt, kind, g) for tt, kind, g in move_sfx(sc)]
        if sc.get("intro"):
            sfx.append((sc["t0"] + INTRO_HOLD, "whoosh", 0.2))
            sfx.append((sc["t0"] + 2 * INTRO_HOLD + INTRO_FLY + 0.2, "whoosh", 0.2))
        elif sc.get("loc"):
            sfx.append((sc["t0"] + sc["fly"] - 0.1, "pop", 0.28))
            sfx.append((sc["t0"] + sc["fly"] + 0.15, "pop", 0.22))
        elif sc["fc"].get("end"):
            sfx.append((sc["t0"] + 0.6, "chime", 0.3))
            if sc.get("card_t") is not None:
                sfx.append((sc["t0"] + sc["card_t"], "whoosh", 0.2))
                sfx.append((sc["t0"] + sc["card_t"] + 1.3, "coin", 0.28))
    if subs:   # no caption gaps between scenes
        for i in range(len(subs) - 1):
            s, e, txt, hi = subs[i]
            if subs[i + 1][0] - e < 0.6:
                subs[i] = (s, subs[i + 1][0], txt, hi)
    with open(os.path.join(work, "audio.txt"), "w") as f:
        f.writelines(f"file '{x}'\n" for x in parts)
    voice = os.path.join(work, "voice.wav")
    reel.sh("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "audio.txt"), voice)
    fx = os.path.join(work, "sfx.wav")
    reelfx.write_track(sfx, rd.total, fx)
    mixed = os.path.join(work, "mix.wav")
    reel.sh("ffmpeg", "-y", "-i", voice, "-i", fx, "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]", "-map", "[a]", mixed)
    subf = os.path.join(work, "subs.ass")
    ass(subs, subf)
    final = os.path.join(base, "reel.mp4")
    reel.sh("ffmpeg", "-y", "-i", video, "-i", mixed, "-filter_complex", f"[0:v]ass={subf}:fontsdir={ig.FONTS}[v]",
            "-map", "[v]", "-map", "1:a", "-t", f"{rd.total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", final)
    cover = os.path.join(base, "cover.jpg")
    cs = next(sc for sc in rd.scenes if sc.get("photo"))
    rd.frame(cs["t0"] + cs["fly"] + 1.0).save(cover, quality=90)
    cap = rd.sb.get("caption", "")
    cpath = os.path.join(base, "img", "credits.json")
    if os.path.exists(cpath):
        cr = json.load(open(cpath))
        cap = cap.replace("PHOTO_CREDITS", "; ".join(f"{v['author']} ({v['license']})" for _, v in sorted(cr.items())))
    with open(os.path.join(base, "caption.txt"), "w") as f:
        f.write(cap + "\n")
    if os.path.exists(os.path.join(base, "plan.json")):      # daily fact Reel: reel.py publish reads these
        sbp = os.path.join(base, "storyboard.json")
        sbj = json.load(open(sbp))
        sbj["caption"] = cap
        sbj.setdefault("end", {})["title"] = f"Datos de {rd.sb['city']}"
        json.dump(sbj, open(sbp, "w"), ensure_ascii=False, indent=2)
        import shutil
        shutil.copy(cover, os.path.join(base, "cover_ig.jpg"))
    print(f"Fact Reel listo: {final} ({rd.total:.1f} s)")
    return final


if __name__ == "__main__":
    cmd, rid = sys.argv[1], sys.argv[2]
    dry = "--dry" in sys.argv
    if cmd == "photos":
        photos(rid)
    elif cmd == "render":
        if not dry:
            photos(rid)
        render(rid, dry)
    elif cmd == "all":        # daily fact Reel in one go: map data (if missing) → photos → render
        b = fact_base(rid)
        sb = json.load(open(os.path.join(b, "storyboard.json")))
        if not os.path.exists(os.path.join(b, "map", "osm.json.gz")) and not sb.get("map_from"):
            import factmap_fetch
            factmap_fetch.main(rid, sb["place"], sb.get("osm_rel"))
        photos(rid)
        render(rid, dry)
    elif cmd == "frame":
        Renderer(rid, dry).frame(float(sys.argv[3])).save(sys.argv[4], quality=88)
