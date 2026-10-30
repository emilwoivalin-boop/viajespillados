"""Post the same content as Instagram on X (@viajespillados), automatically.

Called right after an Instagram post / Reel is published (share_latest), using the newest item of
tiktok/feed.json. Never raises: X problems must not break Instagram. Log: x/published.json.

The text is about the DESTINATION and has no link (X charges much more for posts with a URL);
the website is in the X profile.

Auth: OAuth 1.0a user context – GitHub secrets X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
(app "Read and write", tokens generated for @viajespillados).

CLI:  python scripts/x_post.py check      -> verify the keys (GET /2/users/me)
      python scripts/x_post.py preview    -> print the text for the newest item, no posting
      python scripts/x_post.py latest     -> post the newest feed item (if not posted yet)
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tiktok_feed  # noqa: E402

API = "https://api.x.com/2"
LOG = os.path.join(ROOT, "x", "published.json")
ERR = os.path.join(ROOT, "x", "last_error.txt")
MAX_IMAGES = 4                      # X allows max 4 images per post
CHUNK = 4 * 1024 * 1024
TAIL = "Vuelos baratos desde Bogotá: link en el perfil ✈️"


def _auth():
    keys = [os.environ.get(k, "") for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
    if not all(keys):
        return None
    from requests_oauthlib import OAuth1
    return OAuth1(*keys)


def _now():
    return datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")


def weighted_len(text):
    """X counts most emoji / CJK as 2 characters."""
    n = 0
    for ch in unicodedata.normalize("NFC", text):
        o = ord(ch)
        if 0xFE00 <= o <= 0xFE0F or o == 0x200D:   # variation selectors / joiners
            continue
        n += 1 if (o <= 0x10FF or 0x2000 <= o <= 0x200D or 0x2010 <= o <= 0x201F or 0x2032 <= o <= 0x2037) else 2
    return n


def _tags(destinos):
    out = []
    for d in destinos:
        out.append("#" + tiktok_feed._slug(re.sub(r"\s*\(.*?\)", "", d)).replace("-", ""))
    return out


def build_text(item):
    destinos = item.get("destinos") or []
    tips = tiktok_feed._tips() if destinos else {}
    if item["kind"] == "video" and len(destinos) == 1:
        d = destinos[0]
        que, _, _, pais = tips.get(tiktok_feed._slug(d)) or ("", "", "", "")
        place = tiktok_feed._place(d, pais)
        tags = " ".join(_tags([d]) + ["#viajes"])
        for body in ([f"📍 {place}", que, f"¿Con quién irías? 👇\n{TAIL}", tags],
                     [f"📍 {place}", que, TAIL, tags],
                     [f"📍 {place}", que, tags],
                     [f"📍 {place}", f"Qué hacer en {place} 👇", TAIL, tags]):
            text = "\n\n".join(x for x in body if x)
            if weighted_len(text) <= 280:
                return text
    if destinos:
        ds = destinos[:MAX_IMAGES]
        head = f"{len(ds)} destinos que tienes que conocer 🌎" if len(ds) > 1 else "Destino para tu próximo viaje 🌎"
        lines = "\n".join(f"📍 {re.sub(r'\s*\(.*?\)', '', d)}" for d in ds)
        for body in ([head, lines, f"¿Cuál eliges? 👇\n{TAIL}", " ".join(["#viajes"] + _tags(ds)[:2])],
                     [head, lines, TAIL],
                     [head, lines]):
            text = "\n\n".join(body)
            if weighted_len(text) <= 280:
                return text
    text = item.get("caption", "").split("\n\n")[0]
    return text[:200] + "\n\n" + TAIL


def _check(r, what):
    if r.status_code >= 300:
        raise RuntimeError(f"{what}: HTTP {r.status_code} {r.text[:400]}")
    return r.json() if r.text else {}


def upload(path, auth):
    size = os.path.getsize(path)
    video = path.lower().endswith(".mp4")
    mtype = "video/mp4" if video else ("image/png" if path.lower().endswith(".png") else "image/jpeg")
    init = _check(requests.post(f"{API}/media/upload/initialize", auth=auth, timeout=60,
                                json={"media_type": mtype, "total_bytes": size,
                                      "media_category": "tweet_video" if video else "tweet_image"}), "initialize")
    mid = init["data"]["id"]
    with open(path, "rb") as f:
        i = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            _check(requests.post(f"{API}/media/upload/{mid}/append", auth=auth, timeout=120,
                                 data={"segment_index": str(i)}, files={"media": ("chunk", chunk, mtype)}), "append")
            i += 1
    fin = _check(requests.post(f"{API}/media/upload/{mid}/finalize", auth=auth, timeout=60), "finalize")
    info = (fin.get("data") or {}).get("processing_info")
    for _ in range(60):
        if not info or info.get("state") == "succeeded":
            return mid
        if info.get("state") == "failed":
            raise RuntimeError(f"X no pudo procesar {os.path.basename(path)}: {info}")
        time.sleep(max(2, int(info.get("check_after_secs", 5))))
        st = _check(requests.get(f"{API}/media/upload", auth=auth, timeout=60,
                                 params={"command": "STATUS", "media_id": mid}), "status")
        info = (st.get("data") or {}).get("processing_info")
    raise RuntimeError("X tardó demasiado procesando el video")


def _log():
    try:
        return json.load(open(LOG))
    except Exception:
        return []


def post_item(item, auth):
    files = [os.path.join(ROOT, p) for p in item["files"]][: (1 if item["kind"] == "video" else MAX_IMAGES)]
    media_ids = [upload(p, auth) for p in files]
    text = build_text(item)
    res = _check(requests.post(f"{API}/tweets", auth=auth, timeout=60,
                               json={"text": text, "media": {"media_ids": media_ids}}), "post")
    tid = res["data"]["id"]
    log = _log()
    log.insert(0, {"feed_id": item["id"], "title": item["title"], "tweet_id": tid,
                   "url": f"https://x.com/viajespillados/status/{tid}", "at": _now()})
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    json.dump(log[:200], open(LOG, "w"), ensure_ascii=False, indent=1)
    return log[0]["url"]


def share_latest():
    """Post the newest feed item on X. Returns repo paths to commit (empty if nothing happened)."""
    auth = _auth()
    if not auth:
        print("X: sin claves, no se publica en X.")
        return []
    try:
        item = json.load(open(tiktok_feed.PATH))[0]
        if any(e.get("feed_id") == item["id"] for e in _log()):
            print("X: ya estaba publicado.")
            return []
        url = post_item(item, auth)
        print("X: publicado", url)
        try:
            import instagram
            instagram.summary(f"𝕏 Publicado en X: {url}")
        except Exception:
            pass
        return ["x/published.json"]
    except Exception as e:
        print("X: error –", e)
        os.makedirs(os.path.dirname(ERR), exist_ok=True)
        with open(ERR, "w") as f:
            f.write(f"{_now()} – {type(e).__name__}: {e}\n")
        return ["x/last_error.txt"]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if mode == "check":
        auth = _auth()
        if not auth:
            sys.exit("Faltan los secretos X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET.")
        me = _check(requests.get(f"{API}/users/me", auth=auth, timeout=30), "users/me")
        print("Conectado como @" + me["data"]["username"])
    elif mode == "preview":
        item = json.load(open(tiktok_feed.PATH))[0]
        t = build_text(item)
        print(item["title"], item["files"], f"({weighted_len(t)}/280)\n\n" + t)
    elif mode == "latest":
        paths = share_latest()
        if paths and os.path.exists(ERR) and paths == ["x/last_error.txt"]:
            print(open(ERR).read())
            sys.exit(1)
