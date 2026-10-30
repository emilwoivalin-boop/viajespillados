"""List of everything published on Instagram, so the owner can repost it on TikTok by hand
(page viajespillados.com/tiktok/hoy.html). Newest first, last 60 items."""
import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "tiktok", "feed.json")


def add(kind, title, files, caption, permalink=""):
    """kind: "photos" (offer images) or "video" (Reel). files: repo-relative paths."""
    try:
        feed = json.load(open(PATH))
    except Exception:
        feed = []
    now = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    feed.insert(0, {"kind": kind, "title": title, "files": files, "caption": caption,
                    "instagram": permalink, "at": now, "id": f"{kind}-{now}"})
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(feed[:60], open(PATH, "w"), ensure_ascii=False, indent=1)
    return "tiktok/feed.json"
