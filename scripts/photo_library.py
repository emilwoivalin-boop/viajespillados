"""Destination photo library (Wikimedia Commons).

search: for every destination in photos/destinos_in.json find up to 4 good, reusable Commons photos
        (CC BY / CC BY-SA / CC0 / public domain, ≥1600 px, not maps/flags/logos/collages) and write
        photos/candidates.json plus labelled contact sheets photos/sheets/*.jpg for a human/AI to pick from.
The chosen photo per destination goes to the sheet tab "Fotos" (Destino | Foto (URL) | Crédito foto | Link crédito),
which the website, the Instagram posts and the daily price check use when an offer row has no photo.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "ViajesPilladosBot/1.0 (https://viajespillados.com; photo library)"}
API = "https://commons.wikimedia.org/w/api.php"
BAD = re.compile(r"map|flag|logo|coat of arms|collage|montage|location|locator|diagram|plan|seal|escudo|bandera|"
                 r"mapa|interior|airport|aeropuerto|satellite|night_sky", re.I)
OK_LIC = re.compile(r"^(cc[- ]by(-sa)?[- ]?\d|cc0|public domain|pd)", re.I)


def search(q, quality):
    s = f'{q} filetype:bitmap' + (' incategory:"Quality images"' if quality else "")
    r = requests.get(API, params={"action": "query", "format": "json", "generator": "search", "gsrsearch": s,
                                  "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo",
                                  "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 480}, headers=UA, timeout=60)
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        lic = (md.get("LicenseShortName") or {}).get("value", "")
        title = p["title"][5:]
        if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 1600 or BAD.search(title):
            continue
        if not OK_LIC.match(lic.strip()) or re.search(r"\bnc\b|nd\b", lic, re.I):
            continue
        w, h = ii["width"], ii["height"]
        if w / h > 2.0 or h / w > 2.0:
            continue
        artist = re.sub(r"<[^>]+>", "", (md.get("Artist") or {}).get("value", "")).strip() or "desconocido"
        artist = re.sub(r"\s+", " ", artist)[:60]
        fname = title.replace(" ", "_")
        out.append({"file": fname, "thumb": ii.get("thumburl"), "w": w, "h": h, "license": lic, "artist": artist,
                    "foto": "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(fname) + "?width=1080",
                    "credito": f"{artist} / Wikimedia Commons, {lic}",
                    "credito_link": "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(fname, safe="(),_-.")})
    return out


def run_search():
    dest = json.load(open(os.path.join(ROOT, "photos", "destinos_in.json")))
    res = {}
    for d in dest:
        c = []
        for quality in (True, False):
            try:
                c += [x for x in search(d["q"], quality) if x["file"] not in {y["file"] for y in c}]
            except Exception as e:
                print(d["destino"], e)
            if len(c) >= 4:
                break
            time.sleep(0.5)
        res[d["destino"]] = c[:4]
        print(d["destino"], len(res[d["destino"]]))
        time.sleep(0.5)
    json.dump(res, open(os.path.join(ROOT, "photos", "candidates.json"), "w"), ensure_ascii=False, indent=1)
    sheets(res)


def sheets(res):
    os.makedirs(os.path.join(ROOT, "photos", "sheets"), exist_ok=True)
    try:
        font = ImageFont.truetype(os.path.join(ROOT, "instagram", "fonts", sorted(os.listdir(os.path.join(ROOT, "instagram", "fonts")))[0]), 22)
    except Exception:
        font = ImageFont.load_default()
    names = list(res)
    per = 12
    for s in range(0, len(names), per):
        rows = names[s:s + per]
        tw, th = 240, 170
        sheet = Image.new("RGB", (tw * 4 + 200, th * len(rows)), "white")
        d = ImageDraw.Draw(sheet)
        for r, name in enumerate(rows):
            d.text((8, r * th + 70), name[:18], fill="black", font=font)
            for i, c in enumerate(res[name]):
                try:
                    im = Image.open(io.BytesIO(requests.get(c["thumb"], headers=UA, timeout=60).content)).convert("RGB")
                    im = ImageOps.fit(im, (tw - 6, th - 6))
                    sheet.paste(im, (200 + i * tw, r * th))
                    d.rectangle([200 + i * tw, r * th, 230 + i * tw, r * th + 28], fill="yellow")
                    d.text((206 + i * tw, r * th + 2), str(i), fill="black", font=font)
                except Exception as e:
                    print("thumb", name, i, e)
                time.sleep(0.2)
        sheet.save(os.path.join(ROOT, "photos", "sheets", f"sheet_{s // per:02d}.jpg"), quality=80)


if __name__ == "__main__":
    if sys.argv[1] == "search":
        run_search()
