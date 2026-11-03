"""Download openly licensed photos from Wikimedia Commons with their author + license (for the travel atlas).

    python scripts/commons_fetch.py '<json>'     # {"key": "File:Name.jpg" | "search:query words", ...}

Writes <key>.jpg (1400 px wide) and credits.json to the side branch atlas-photos (not main, so the website is untouched).
"""
import io
import json
import os
import re
import sys

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from picsart import push_branch  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "WhereNextAtlas/1.0 (https://viajespillados.com; photo credits bot)"}
OK = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? [0-9.]+)", re.I)


def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def info(params):
    p = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
         "iiurlwidth": 1400, **params}
    return requests.get(API, params=p, headers=UA, timeout=60).json().get("query", {}).get("pages", {})


def pick(spec):
    pages = info({"titles": spec}) if spec.startswith("File:") else \
        info({"generator": "search", "gsrsearch": spec[7:] + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 15})
    cands = sorted(pages.values(), key=lambda p: p.get("index", 0))
    for p in cands:
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = clean(md.get("LicenseShortName", {}).get("value"))
        if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 1200 or not OK.match(lic):
            continue
        if not spec.startswith("File:") and ii["width"] < ii["height"]:
            continue
        return {"title": p["title"], "thumb": ii["thumburl"], "page": ii["descriptionurl"],
                "author": clean(md.get("Artist", {}).get("value")) or "Unknown", "license": lic,
                "width": ii["width"], "height": ii["height"]}
    return None


def main(spec_json):
    specs = json.loads(spec_json)
    out, files = {}, {}
    for key, spec in specs.items():
        m = pick(spec)
        if not m:
            print(key, "-> nothing usable for", spec)
            continue
        r = requests.get(m["thumb"], headers=UA, timeout=120)
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        if im.width > 1400:
            im = im.resize((1400, round(im.height * 1400 / im.width)), Image.LANCZOS)
        path = f"/tmp/atlas/{key}.jpg"
        os.makedirs("/tmp/atlas", exist_ok=True)
        im.save(path, quality=86)
        out[key] = m
        print(key, "->", m["title"], "|", m["author"], "|", m["license"])
    # push binary files with the side-branch helper (it writes text, so copy files in afterwards)
    import shutil
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    push_branch("atlas-photos", {"credits.json": json.dumps(out, ensure_ascii=False, indent=1)}, "Atlas photos: credits")
    wt = "/tmp/side-atlas-photos"
    for key in out:
        shutil.copy(f"/tmp/atlas/{key}.jpg", os.path.join(wt, f"{key}.jpg"))
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-qm", "Atlas photos"], cwd=wt, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:refs/heads/atlas-photos"], cwd=wt, check=True)


if __name__ == "__main__":
    main(sys.argv[1])
