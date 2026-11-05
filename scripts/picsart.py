"""Picsart (gen-ai CLI) for the daily Reels and travel videos – runs in .github/workflows/picsart.yml.

    python scripts/picsart.py login                       # device sign-in: the code is pushed to branch picsart-login
    python scripts/picsart.py pictures reels <id> [keys]   # plan.json "prompts" -> reels/<id>/img/<key>.jpg
    python scripts/picsart.py pictures trips <id> [keys]   # trips/<id>/prompts.json {key: prompt} -> trips/<id>/img/
    python scripts/picsart.py credits

The sign-in lives in ~/.gen-ai (the workflow keeps it encrypted in the Actions cache between runs).
keys = comma-separated subset (to redo only some pictures), default all.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(__file__))
import instagram as ig  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.environ.get("PICSART_MODEL", "gemini-3.1-flash-image")       # Nano Banana 2
FALLBACK = os.environ.get("PICSART_FALLBACK", "gemini-3-pro-image")     # Nano Banana Pro
REELS_ORDER = ["vuelo", "llegada", "dia1", "dia2", "dia3", "dia4", "dia5", "cover"]


def summary(text):
    print(text)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as f:
            f.write(text + "\n\n")


def push_branch(branch, files, message):
    """Write small text files to a side branch (not main, so the website is untouched)."""
    wt = "/tmp/side-" + branch
    subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=ROOT, capture_output=True)
    exists = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], cwd=ROOT,
                            capture_output=True).returncode == 0
    if exists:
        subprocess.run(["git", "fetch", "-q", "origin", branch], cwd=ROOT, check=True)
        subprocess.run(["git", "worktree", "add", "-q", wt, "FETCH_HEAD"], cwd=ROOT, check=True)
    else:
        subprocess.run(["git", "worktree", "add", "-q", "--detach", wt], cwd=ROOT, check=True)
        subprocess.run(["git", "checkout", "-q", "--orphan", branch], cwd=wt, check=True)
        subprocess.run(["git", "rm", "-rfq", "."], cwd=wt, capture_output=True)
    for name, text in files.items():
        with open(os.path.join(wt, name), "w") as f:
            f.write(text)
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=wt, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], cwd=wt, check=True)


AUTH = "https://auth.picsart.com/api"          # same endpoints and client as `gen-ai login --device`
CLIENT = "auth-service-Gen-AI-CLI"


def login():
    """Device sign-in (like `gen-ai login --device`, but patient with rate limits). The link + code are pushed to
    branch picsart-login (file login.txt) so the assistant can send them to the owner; the owner approves on the
    phone and this waits until done. Writes ~/.gen-ai/credentials.json in the CLI's format."""
    import requests
    from datetime import datetime, timedelta, timezone
    r = requests.post(f"{AUTH}/oauth2/device_authorization", data={"client_id": CLIENT, "scope": "user-global"},
                      headers={"Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    dev = r.json()
    url = dev.get("verification_uri_complete") or dev["verification_uri"]
    push_branch("picsart-login", {"login.txt": f"open: {dev['verification_uri']}\ncode: {dev['user_code']}\n"
                                               f"direct: {url}\nstatus: waiting\n"}, "Picsart sign-in code")
    print("code pushed:", dev["user_code"])
    interval, end, tok = int(dev.get("interval", 5)), time.time() + int(dev.get("expires_in", 900)), None
    while time.time() < end:
        time.sleep(interval)
        try:
            t = requests.post(f"{AUTH}/oauth2/token", headers={"Accept": "application/json"}, timeout=30,
                              data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                    "device_code": dev["device_code"], "client_id": CLIENT})
        except requests.RequestException as e:
            print("retry:", e)
            continue
        if t.status_code == 429:
            interval = min(60, interval + int(t.headers.get("Retry-After", 10)))
            print("rate limited, waiting", interval, "s")
            continue
        body = t.json() if t.content else {}
        if t.ok and body.get("access_token"):
            tok = body
            break
        err = body.get("error")
        if err == "slow_down":
            interval += 5
        elif err != "authorization_pending":
            print("sign-in error:", t.status_code, body)
            break
    if not tok:
        push_branch("picsart-login", {"login.txt": "status: failed (not approved in time)\n"}, "Picsart sign-in result")
        sys.exit(1)
    me = requests.get("https://api.picsart.com/gw-v2/users/show/me.json", timeout=30,
                      headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
    me = me.get("response", me)
    now = datetime.now(timezone.utc)
    iso = lambda s: (now + timedelta(seconds=int(s))).isoformat().replace("+00:00", "Z")  # noqa: E731
    cred = {"token": tok["access_token"], "refreshToken": tok["refresh_token"], "uid": str(me.get("id", "")),
            "email": str(me.get("email") or me.get("username") or ""), "expiresAt": iso(tok["expires_in"]),
            "apiUrl": "https://api.picsart.com", "authSource": "device"}
    if tok.get("refresh_token_expires_in"):
        cred["refreshExpiresAt"] = iso(tok["refresh_token_expires_in"])
    d = os.path.expanduser("~/.gen-ai")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "credentials.json")
    with open(path, "w") as f:
        json.dump(cred, f, indent=2)
    os.chmod(path, 0o600)
    who = subprocess.run(["gen-ai", "whoami", "--plain"], capture_output=True, text=True)
    cr = subprocess.run(["gen-ai", "credits", "--plain"], capture_output=True, text=True)
    ok = who.returncode == 0
    push_branch("picsart-login", {"login.txt": f"status: {'ok' if ok else 'failed'}\n{who.stdout}{who.stderr}\n"
                                               f"{cr.stdout}{cr.stderr}\n"}, "Picsart sign-in result")
    summary(f"Picsart sign-in: {'ok' if ok else 'failed'}\n\n{who.stdout}\n{cr.stdout}")
    if not ok:
        sys.exit(1)


def generate(prompt, out_dir, model):
    os.makedirs(out_dir, exist_ok=True)
    before = set(glob.glob(os.path.join(out_dir, "*")))
    cmd = ["gen-ai", "image", "-s", "--no-color", "-m", model, "-p", prompt, "--aspect-ratio", "9:16",
           "--download", out_dir, "--max-cost", "12", "--no-open"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    print(r.stdout[-1500:], r.stderr[-1500:])
    new = sorted(set(glob.glob(os.path.join(out_dir, "*"))) - before, key=os.path.getmtime)
    new = [f for f in new if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    if r.returncode != 0 or not new:
        raise RuntimeError(f"{model}: no picture ({r.returncode}) {r.stderr[-300:]}")
    return new[-1]


def pictures(kind, rid, keys=None):
    base = os.path.join(ROOT, kind, rid)
    if kind == "reels":
        prompts = json.load(open(os.path.join(base, "plan.json")))["prompts"]
        order = [k for k in REELS_ORDER if k in prompts] + [k for k in prompts if k not in REELS_ORDER]
    else:
        prompts = json.load(open(os.path.join(base, "prompts.json")))
        order = list(prompts)
    if keys:
        order = [k for k in order if k in keys.split(",")]
    os.makedirs(os.path.join(base, "img"), exist_ok=True)
    done, failed = [], []
    for k in order:
        src = None
        for model in (MODEL, FALLBACK):
            try:
                src = generate(prompts[k], f"/tmp/picsart/{rid}/{k}", model)
                break
            except Exception as e:
                print(f"{k}: {e}")
        if not src:
            failed.append(k)
            continue
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        if im.width > 1080:
            im = im.resize((1080, round(im.height * 1080 / im.width)), Image.LANCZOS)
        im.save(os.path.join(base, "img", f"{k}.jpg"), quality=92)
        done.append(f"{k} {im.size[0]}x{im.size[1]}")
    with open(os.path.join(base, "img", "picsart.json"), "w") as f:
        json.dump({"done": done, "failed": failed, "model": MODEL,
                   "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}, f, indent=1)
    ig.commit_push([f"{kind}/{rid}/img"], f"Picsart: pictures {rid}")
    cred = subprocess.run(["gen-ai", "credits", "--plain"], capture_output=True, text=True).stdout
    summary(f"Pictures for {rid}: {len(done)} ok, failed: {failed or 'none'}\n\n{cred}")
    if failed and not done:
        sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "login":
        login()
    elif cmd == "pictures":
        pictures(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None)
    elif cmd == "credits":
        summary(subprocess.run(["gen-ai", "credits", "--plain"], capture_output=True, text=True).stdout)
