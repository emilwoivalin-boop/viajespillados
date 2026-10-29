"""TikTok: send the daily Reel to the owner's TikTok inbox as a draft (Content Posting API, "upload" mode).

The owner then opens TikTok, adds a sound/caption if they like, and taps Post.

    python scripts/tiktok.py auth <code>   # one time: exchange the OAuth code, save the refresh token as a GitHub secret
    python scripts/tiktok.py upload <id>   # upload reels/<id>/reel.mp4 to the TikTok inbox

Secrets: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN (written by "auth"),
GH_ADMIN_TOKEN (fine-grained GitHub token with "Secrets: read and write" on this repo, used to save/rotate the
refresh token). Tokens are never printed.
"""
import json
import os
import subprocess
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://open.tiktokapis.com"
REDIRECT = "https://viajespillados.com/tiktok/callback.html"
REPO = os.environ.get("GITHUB_REPOSITORY", "emilwoivalin-boop/viajespillados")


def summary(md):
    print(md)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as f:
            f.write(md + "\n")


def save_secret(name, value):
    """Store a value as a GitHub Actions secret without ever printing it."""
    env = dict(os.environ, GH_TOKEN=os.environ["GH_ADMIN_TOKEN"])
    subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value.encode(), env=env, check=True,
                   stdout=subprocess.DEVNULL)


def token(**data):
    data.update(client_key=os.environ["TIKTOK_CLIENT_KEY"], client_secret=os.environ["TIKTOK_CLIENT_SECRET"])
    r = requests.post(f"{API}/v2/oauth/token/", data=data, timeout=30,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError(f"TikTok no entregó token: {j.get('error')} {j.get('error_description')}")
    return j


def auth(code):
    j = token(code=code.strip(), grant_type="authorization_code", redirect_uri=REDIRECT)
    save_secret("TIKTOK_REFRESH_TOKEN", j["refresh_token"])
    me = requests.get(f"{API}/v2/user/info/", params={"fields": "display_name"}, timeout=30,
                      headers={"Authorization": f"Bearer {j['access_token']}"}).json()
    name = ((me.get("data") or {}).get("user") or {}).get("display_name", "?")
    with open(os.path.join(ROOT, "tiktok", "connected.json"), "w") as f:   # flag for the daily task (no secrets)
        json.dump({"account": name, "scope": j.get("scope"), "at": time.strftime("%Y-%m-%d %H:%M")}, f)
    summary(f"✅ TikTok conectado: cuenta **{name}**, permisos: {j.get('scope')}. "
            f"El token se renueva solo (válido 365 días).")


def access_token():
    j = token(grant_type="refresh_token", refresh_token=os.environ["TIKTOK_REFRESH_TOKEN"])
    if j.get("refresh_token") and j["refresh_token"] != os.environ["TIKTOK_REFRESH_TOKEN"] and os.environ.get("GH_ADMIN_TOKEN"):
        save_secret("TIKTOK_REFRESH_TOKEN", j["refresh_token"])   # keep the newest refresh token
    return j["access_token"]


def upload(rid):
    path = os.path.join(ROOT, "reels", rid, "reel.mp4")
    size = os.path.getsize(path)
    at = access_token()
    h = {"Authorization": f"Bearer {at}", "Content-Type": "application/json; charset=UTF-8"}
    # videos under 64 MB can go in one chunk
    chunk = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    n = 1 if chunk == size else size // chunk
    r = requests.post(f"{API}/v2/post/publish/inbox/video/init/", headers=h, timeout=30,
                      json={"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                            "chunk_size": chunk, "total_chunk_count": n}}).json()
    if (r.get("error") or {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init: {r['error']}")
    url, pid = r["data"]["upload_url"], r["data"]["publish_id"]
    with open(path, "rb") as f:
        for i in range(n):
            start = i * chunk
            end = size - 1 if i == n - 1 else start + chunk - 1
            f.seek(start)
            body = f.read(end - start + 1)
            u = requests.put(url, data=body, timeout=300,
                             headers={"Content-Type": "video/mp4", "Content-Length": str(len(body)),
                                      "Content-Range": f"bytes {start}-{end}/{size}"})
            if u.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok upload chunk {i}: HTTP {u.status_code} {u.text[:200]}")
    status = "?"
    for _ in range(40):
        s = requests.post(f"{API}/v2/post/publish/status/fetch/", headers=h, json={"publish_id": pid},
                          timeout=30).json()
        status = (s.get("data") or {}).get("status", "?")
        if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok rechazó el video: {(s.get('data') or {}).get('fail_reason')}")
        time.sleep(6)
    base = os.path.join(ROOT, "reels", rid)
    with open(os.path.join(base, "tiktok.json"), "w") as f:
        json.dump({"publish_id": pid, "status": status, "at": time.strftime("%Y-%m-%d %H:%M")}, f)
    sb = json.load(open(os.path.join(base, "storyboard.json")))
    summary(f"📥 Reel {rid} enviado a tus borradores de TikTok (estado: {status}).\n\nCaption sugerido:\n\n"
            f"{sb.get('caption', '')}")


if __name__ == "__main__":
    mode, arg = sys.argv[1], sys.argv[2]
    try:
        auth(arg) if mode == "auth" else upload(arg)
    except Exception as e:
        if mode == "upload":
            with open(os.path.join(ROOT, "reels", arg, "tiktok_error.txt"), "w") as f:
                f.write(str(e))
        raise
