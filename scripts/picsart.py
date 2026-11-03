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
REELS_ORDER = ["vuelo", "llegada", "dia1", "dia2", "dia3", "cover"]


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


def login():
    """Device sign-in. The link + code are pushed to branch picsart-login (file login.txt) so the assistant can
    send them to the owner; the owner approves on the phone and this waits until done (max ~15 min)."""
    p = subprocess.Popen(["gen-ai", "login", "--device", "--plain", "--no-color"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    info, sent = {}, False
    for line in p.stdout:
        print(line, end="")
        m = re.search(r"open:\s*(https?://\S+)", line)
        if m and "directly" not in line:
            info["url"] = m.group(1)
        m = re.search(r"code:\s*([A-Z0-9-]{4,})", line)
        if m:
            info["code"] = m.group(1)
        m = re.search(r"directly:\s*(https?://\S+)", line)
        if m:
            info["direct"] = m.group(1)
        if not sent and "code" in info and "url" in info:
            time.sleep(1)
            text = (f"open: {info.get('direct') or info['url']}\ncode: {info['code']}\n"
                    f"time: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\nstatus: waiting\n")
            push_branch("picsart-login", {"login.txt": text}, "Picsart sign-in code")
            sent = True
    rc = p.wait()
    who = subprocess.run(["gen-ai", "whoami", "--plain"], capture_output=True, text=True)
    cred = subprocess.run(["gen-ai", "credits", "--plain"], capture_output=True, text=True)
    status = "ok" if rc == 0 and who.returncode == 0 else f"failed (exit {rc})"
    push_branch("picsart-login", {"login.txt": f"status: {status}\n{who.stdout}\n{cred.stdout}\n"},
                "Picsart sign-in result")
    summary(f"Picsart sign-in: {status}\n\n{who.stdout}\n{cred.stdout}")
    if status != "ok":
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
