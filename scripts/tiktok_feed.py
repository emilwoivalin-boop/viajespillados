"""List of everything published on Instagram, so the owner can repost it on TikTok / YouTube Shorts by hand
(page viajespillados.com/tiktok/hoy.html). Newest first, last 60 items.

The TikTok/YouTube text is about the DESTINATION (what to do there + a practical tip), not the flight:
the picture/video already shows price and dates. Text comes from the sheet tab "Qué hacer (captions)"."""
import json
import os
import re
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "tiktok", "feed.json")
SITE_LINE = "Vuelos baratos desde Bogotá en viajespillados.com ✈️"
_TIPS = None


def _tips():
    """slug(destino) -> (que_hacer, ojo, caption_listo, pais), from the sheet (cached)."""
    global _TIPS
    if _TIPS is None:
        try:
            import instagram
            _TIPS = instagram.load_tips()
        except Exception as e:
            print("Sin textos de destinos:", e)
            _TIPS = {}
    return _TIPS


def _slug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _tag(s):
    return "#" + _slug(s).replace("-", "")


def _place(destino, pais):
    name = re.sub(r"\s*\(.*?\)", "", destino).strip()          # "Granada (isla)" -> "Granada"
    return name if not pais or _slug(pais) == _slug(name) else f"{name}, {pais}"


def _cap(s):
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


def destination_text(destinos, tips=None):
    """Returns (caption, youtube_title) about the destinations, or (None, None) if none is in the sheet."""
    tips = tips if tips is not None else _tips()
    rows = []
    for d in destinos:
        que, ojo, _, pais = (tips.get(_slug(d)) or ("", "", "", ""))
        if que:
            rows.append((d, pais, que, ojo))
    if not rows:
        return None, None

    tags = []
    if len(rows) == 1:
        d, pais, que, ojo = rows[0]
        place = _place(d, pais)
        parts = [f"📍 {place}", que]
        if ojo:
            parts.append(f"💡 Dato: {_cap(ojo)}")
        parts.append(f"¿Con quién irías? 👇\n{SITE_LINE}")
        tags = [_tag(re.sub(r"\s*\(.*?\)", "", d))]
        if pais and _slug(pais) != _slug(d):
            tags.append(_tag(pais))
        tags += ["#viajes", "#quehacer", "#viajespillados"]
        title = f"Qué hacer en {place} ✈️"
    else:
        n = len(rows)
        parts = [f"{n} destinos que tienes que conocer 🌎"]
        for d, pais, que, _ in rows:
            parts.append(f"📍 {_place(d, pais)}\n{que}")
        parts.append(f"¿Cuál eliges? 👇\n{SITE_LINE}")
        tags = ["#viajes"] + [_tag(re.sub(r"\s*\(.*?\)", "", d)) for d, *_ in rows][:4] + ["#viajespillados"]
        title = f"{n} destinos que tienes que conocer 🌎"
    text = "\n\n".join(parts) + "\n\n" + " ".join(dict.fromkeys(tags))
    return text[:2200], title[:100]


def add(kind, title, files, caption, permalink="", destinos=None):
    """kind: "photos" (offer images) or "video" (Reel). files: repo-relative paths.
    destinos: destination names – used to write the TikTok/YouTube text (falls back to `caption`)."""
    try:
        feed = json.load(open(PATH))
    except Exception:
        feed = []
    yt_title = ""
    if destinos:
        text, yt = destination_text(destinos)
        if text:
            caption, yt_title = text, yt
    now = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    feed.insert(0, {"kind": kind, "title": title, "files": files, "caption": caption, "yt_title": yt_title,
                    "instagram": permalink, "at": now, "id": f"{kind}-{now}",
                    "destinos": list(destinos or [])})
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(feed[:60], open(PATH, "w"), ensure_ascii=False, indent=1)
    return "tiktok/feed.json"
