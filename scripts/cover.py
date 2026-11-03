"""Cover image for a daily Reel (shown on the Instagram grid and as the Reel's thumbnail).

    python scripts/cover.py <id> [out.jpg]      # -> reels/<id>/cover_ig.jpg

Background: reels/<id>/img/cover.jpg (Picsart picture) or the dia1 picture. On top: "DESDE BOGOTÁ", the
destination, "<N> días · ida y vuelta", the price, the stick man celebrating (and the travel buddy on buddy
Reels) and viajespillados.com. All text is drawn here, so names and prices are always exact.
The important part sits in the middle (Instagram's grid crops the top and bottom of a 9:16 cover).
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(__file__))
import instagram as ig  # noqa: E402
import reel_plan  # noqa: E402
import stickman  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1920
YELLOW = (255, 198, 49)
DARK = (16, 24, 40)


def text_c(d, y, s, f, fill=(255, 255, 255), stroke=6, sfill=(10, 16, 30)):
    w = d.textlength(s, font=f)
    d.text(((W - w) / 2, y), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill)


def figure(img, action, x, y, size, facing=1, look="hero"):
    g = stickman.frames(action, 30, 30, x0=x, x1=x, feet=int(y * H), size=size, facing=facing, band_h=H,
                        look=look, patch=True)
    fr = None
    for i, p in enumerate(g):
        if i == 12:
            fr = p
    if fr:
        img.alpha_composite(fr[0], fr[1])


def make(rid, out=None):
    base = os.path.join(ROOT, "reels", rid)
    plan = json.load(open(os.path.join(base, "plan.json")))
    o = plan["offer"]
    src = next((os.path.join(base, "img", f"{k}.jpg") for k in ("cover", "dia1", "llegada")
                if os.path.exists(os.path.join(base, "img", f"{k}.jpg"))), None)
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    k = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    ox, oy = (im.width - W) // 2, (im.height - H) // 2
    img = im.crop((ox, oy, ox + W, oy + H)).convert("RGBA")

    # soft dark band behind the text block (keeps the picture visible above and below)
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for y in range(H):
        t = abs(y - 860) / 520
        sd.line([(0, y), (W, y)], fill=int(150 * max(0.0, 1 - t * t)))
    img.alpha_composite(Image.merge("RGBA", (Image.new("L", (W, H), 0),) * 3 + (shade.filter(ImageFilter.GaussianBlur(30)),)))

    d = ImageDraw.Draw(img)
    inf = reel_plan.info(o["ida"], o["vuelta"])
    # chip
    chip = "DESDE BOGOTÁ"
    f = ig.font("ExtraBold", 46)
    cw = d.textlength(chip, font=f) + 70
    d.rounded_rectangle(((W - cw) / 2, 470, (W + cw) / 2, 545), 38, fill=YELLOW)
    d.text(((W - cw) / 2 + 35, 478), chip, font=f, fill=DARK)
    # destination
    dest = o["destino"].upper()
    fd = ig.fit_font(d, dest, "Black", 190, 960, 90)
    text_c(d, 575, dest, fd, stroke=9)
    yb = 575 + fd.size + 30
    sub = f"{inf['dias']} DÍAS · IDA Y VUELTA"
    oc = ((plan.get("ocasion") or {}).get("nombre") or "").split("(")[0].strip()
    text_c(d, yb, sub, ig.fit_font(d, sub, "Bold", 64, 900, 40), stroke=5)
    yb += 95
    if oc:
        text_c(d, yb, oc.upper(), ig.fit_font(d, oc.upper(), "Bold", 54, 960, 26), fill=YELLOW, stroke=5)
        yb += 80
    # price pill
    price = ig.cop(int(o["precio"]))
    fp = ig.font("Black", 120)
    pw = d.textlength(price, font=fp) + 110
    py = yb + 20
    d.rounded_rectangle(((W - pw) / 2 + 8, py + 10, (W + pw) / 2 + 8, py + 170), 40, fill=(0, 0, 0, 120))
    d.rounded_rectangle(((W - pw) / 2, py, (W + pw) / 2, py + 160), 40, fill=YELLOW, outline=DARK, width=6)
    d.text(((W - pw) / 2 + 55, py + 8), price, font=fp, fill=DARK)
    # stick man (+ buddy) celebrating under the price
    if plan.get("buddy"):
        figure(img, "celebrate", 0.36, 0.93, 470, 1, "buddy")
        figure(img, "celebrate", 0.62, 0.93, 500, -1)
    else:
        figure(img, "celebrate", 0.5, 0.93, 500)
    d = ImageDraw.Draw(img)
    text_c(d, H - 120, "viajespillados.com", ig.font("Bold", 46), stroke=4)
    out = out or os.path.join(base, "cover_ig.jpg")
    img.convert("RGB").save(out, quality=90)
    print("cover:", out)
    return out


if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
