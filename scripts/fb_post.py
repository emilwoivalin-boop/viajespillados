"""Post the same content as Instagram on the Facebook Page "Viajes Pillados", automatically.

Called right after an Instagram post / Reel is published (share_latest), using the newest item of
tiktok/feed.json (photos -> one post with all photos; Reel -> Page video). Text = the destination text of the
feed item (it ends with viajespillados.com, which Facebook turns into a link). Never raises. Log: fb/published.json.

Secrets: FB_PAGE_ID, FB_PAGE_TOKEN (a Page token that does not expire).
One-time setup (mode "auth"): FB_APP_ID + FB_APP_SECRET + FB_USER_TOKEN (short-lived user token from the
Graph API Explorer with pages_manage_posts, pages_read_engagement, pages_show_list, read_insights) are exchanged
for a long-lived user token and then the Page token, which is saved to the secrets with GH_ADMIN_TOKEN.
Nothing secret is printed.

CLI:  python scripts/fb_post.py auth | check | preview | latest
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tiktok_feed  # noqa: E402

G = "https://graph.facebook.com/v26.0"
GV = "https://graph-video.facebook.com/v26.0"
SITE = "https://viajespillados.com/"
REPO = "emilwoivalin-boop/viajespillados"
LOG = os.path.join(ROOT, "fb", "published.json")
ERR = os.path.join(ROOT, "fb", "last_error.txt")
PAGE_NAME = "Viajes Pillados"


def _now():
    return datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")


def _check(r, what):
    try:
        j = r.json()
    except Exception:
        j = {}
    if r.status_code >= 300 or "error" in j:
        err = j.get("error", {})
        raise RuntimeError(f"{what}: HTTP {r.status_code} {err.get('message', r.text[:300])} (code {err.get('code')})")
    return j


def _save_secret(name, value):
    env = dict(os.environ, GH_TOKEN=os.environ["GH_ADMIN_TOKEN"])
    subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value.encode(), env=env, check=True,
                   stdout=subprocess.DEVNULL)


def auth():
    app_id, secret, short = (os.environ.get(k, "") for k in ("FB_APP_ID", "FB_APP_SECRET", "FB_USER_TOKEN"))
    if not (app_id and secret and short):
        sys.exit("Faltan los secretos FB_APP_ID, FB_APP_SECRET o FB_USER_TOKEN.")
    long_user = _check(requests.get(f"{G}/oauth/access_token", timeout=30, params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
        "fb_exchange_token": short}), "exchange")["access_token"]
    print(f"::add-mask::{long_user}")
    pages = _check(requests.get(f"{G}/me/accounts", timeout=30, params={
        "fields": "id,name,access_token,tasks", "access_token": long_user}), "me/accounts").get("data", [])
    if not pages:
        sys.exit("El usuario no administra ninguna página (o no se dio acceso a la página al autorizar).")
    page = next((p for p in pages if p["name"].strip().lower() == PAGE_NAME.lower()), pages[0])
    print(f"::add-mask::{page['access_token']}")
    _save_secret("FB_PAGE_TOKEN", page["access_token"])
    _save_secret("FB_PAGE_ID", page["id"])
    print(f"Página conectada: {page['name']} ({page['id']}) – permisos: {', '.join(page.get('tasks', []))}")
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    json.dump({"page": page["name"], "page_id": page["id"], "at": _now()},
              open(os.path.join(ROOT, "fb", "connected.json"), "w"), ensure_ascii=False, indent=1)


def _creds():
    pid, tok = os.environ.get("FB_PAGE_ID", ""), os.environ.get("FB_PAGE_TOKEN", "")
    return (pid, tok) if pid and tok else (None, None)


def text_for(item):
    return (item.get("caption") or item.get("title", "")).strip()[:5000]


def post_item(item, pid, tok):
    text = text_for(item)
    urls = [SITE + p for p in item["files"]]
    if item["kind"] == "video":
        j = _check(requests.post(f"{GV}/{pid}/videos", timeout=300, data={
            "file_url": urls[0], "description": text, "title": item.get("yt_title") or item["title"],
            "access_token": tok}), "video")
        post_id = j["id"]
        url = f"https://www.facebook.com/{pid}/videos/{post_id}"
    else:
        ids = []
        for u in urls[:10]:
            ids.append(_check(requests.post(f"{G}/{pid}/photos", timeout=120, data={
                "url": u, "published": "false", "access_token": tok}), "photo")["id"])
        j = _check(requests.post(f"{G}/{pid}/feed", timeout=120, data={
            "message": text, "attached_media": json.dumps([{"media_fbid": i} for i in ids]),
            "access_token": tok}), "feed")
        post_id = j["id"]
        url = f"https://www.facebook.com/{post_id}"
    try:
        log = json.load(open(LOG))
    except Exception:
        log = []
    log.insert(0, {"feed_id": item["id"], "title": item["title"], "post_id": post_id, "kind": item["kind"],
                   "url": url, "at": _now()})
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    json.dump(log[:200], open(LOG, "w"), ensure_ascii=False, indent=1)
    return url


def share_latest():
    """Post the newest feed item on the Facebook Page. Returns repo paths to commit."""
    pid, tok = _creds()
    if not pid:
        print("Facebook: sin claves, no se publica.")
        return []
    try:
        item = json.load(open(tiktok_feed.PATH))[0]
        try:
            done = {e.get("feed_id") for e in json.load(open(LOG))}
        except Exception:
            done = set()
        if item["id"] in done:
            print("Facebook: ya estaba publicado.")
            return []
        url = post_item(item, pid, tok)
        print("Facebook: publicado", url)
        try:
            import instagram
            instagram.summary(f"📘 Publicado en Facebook: {url}")
        except Exception:
            pass
        return ["fb/published.json"]
    except Exception as e:
        print("Facebook: error –", e)
        os.makedirs(os.path.dirname(ERR), exist_ok=True)
        with open(ERR, "w") as f:
            f.write(f"{_now()} – {type(e).__name__}: {e}\n")
        return ["fb/last_error.txt"]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if mode == "auth":
        auth()
    elif mode == "check":
        pid, tok = _creds()
        if not pid:
            sys.exit("Faltan FB_PAGE_ID / FB_PAGE_TOKEN (ejecuta primero el modo auth).")
        p = _check(requests.get(f"{G}/{pid}", timeout=30, params={"fields": "name,followers_count,link",
                                                                    "access_token": tok}), "page")
        dbg = _check(requests.get(f"{G}/debug_token", timeout=30, params={"input_token": tok, "access_token": tok}),
                     "debug_token").get("data", {})
        exp = dbg.get("expires_at", 0)
        print(f"Página: {p.get('name')} · seguidores {p.get('followers_count')} · token "
              f"{'sin vencimiento' if not exp else 'vence ' + datetime.fromtimestamp(exp).isoformat()}")
    elif mode == "preview":
        item = json.load(open(tiktok_feed.PATH))[0]
        print(item["title"], item["files"], "\n\n" + text_for(item))
    elif mode == "latest":
        paths = share_latest()
        if paths == ["fb/last_error.txt"]:
            print(open(ERR).read())
            sys.exit(1)
