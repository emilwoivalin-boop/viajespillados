"""Nightly performance snapshot for the website and the social channels.

Writes (one block of rows per run date, Bogotá):
  metrics/history.csv  – fecha,canal,tipo,id,publicado,destinos,titulo,enlace,metrica,valor
                         (cumulative values per post as of that night; account totals with tipo=cuenta;
                          website rows for the previous full day with tipo=web)
  metrics/latest.json  – the same rows of the last run, plus errors per channel

Every channel is optional: missing keys or API errors are recorded in latest.json["errores"] and the rest goes on.
Secrets: GOATCOUNTER_TOKEN, IG_ACCESS_TOKEN (+IG_USER_ID), YOUTUBE_API_KEY, X_* (see x_post.py).
X charges per read, so only X posts from the last 3 days are read (+ the account once).
"""
import csv
import glob
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "metrics")
BOG = timezone(timedelta(hours=-5))
TODAY = datetime.now(BOG).date()
YDAY = TODAY - timedelta(days=1)
FIELDS = ["fecha", "canal", "tipo", "id", "publicado", "destinos", "titulo", "enlace", "metrica", "valor"]
YT_CHANNEL = "UCUaIRv98Akt5tvHvsmPd1kQ"
GC_SITE = "https://viajespillados.goatcounter.com"

rows, errors = [], {}


def add(canal, tipo, id_, metrica, valor, publicado="", destinos="", titulo="", enlace="", fecha=None):
    if valor is None:
        return
    rows.append({"fecha": str(fecha or TODAY), "canal": canal, "tipo": tipo, "id": str(id_),
                 "publicado": publicado, "destinos": destinos, "titulo": (titulo or "")[:120].replace("\n", " "),
                 "enlace": enlace, "metrica": metrica, "valor": valor})


def section(name):
    def deco(fn):
        def run():
            try:
                fn()
            except Exception as e:
                errors[name] = f"{type(e).__name__}: {str(e)[:300]}"
                print(f"[{name}] ERROR {errors[name]}")
        run.__name__ = name
        return run
    return deco


def _get(url, **kw):
    r = requests.get(url, timeout=60, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} {url.split('?')[0]}: {r.text[:200]}")
    return r.json()


# ---------------------------------------------------------------- website (GoatCounter, yesterday)
@section("web")
def web():
    tok = os.environ.get("GOATCOUNTER_TOKEN")
    if not tok:
        raise RuntimeError("falta GOATCOUNTER_TOKEN")
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    p = {"start": f"{YDAY}T05:00:00Z", "end": f"{TODAY}T05:00:00Z"}   # Bogotá midnight = 05:00 UTC
    tot = _get(f"{GC_SITE}/api/v0/stats/total", headers=h, params=p)
    add("web", "web", "total", "visitas", tot.get("total", tot.get("total_utc")), fecha=YDAY)
    if "total_events" in tot:
        add("web", "web", "total", "eventos", tot["total_events"], fecha=YDAY)
    hits = _get(f"{GC_SITE}/api/v0/stats/hits", headers=h, params={**p, "limit": 200}).get("hits", [])
    for x in hits:
        path, n = x.get("path", ""), x.get("count", 0)
        if not n:
            continue
        if path.startswith("oferta/"):
            dest = x.get("title", "").replace("Clic oferta: ", "")
            add("web", "clic_oferta", path, "clics", n, destinos=dest, titulo=x.get("title", ""), fecha=YDAY)
        elif x.get("event"):
            add("web", "evento", path, "clics", n, titulo=x.get("title", ""), fecha=YDAY)
        else:
            add("web", "pagina", path, "visitas", n, titulo=x.get("title", ""), fecha=YDAY)
    try:
        refs = _get(f"{GC_SITE}/api/v0/stats/toprefs", headers=h, params={**p, "limit": 50}).get("stats", [])
        for x in refs:
            name = x.get("name") or "(directo)"
            add("web", "origen", name, "visitas", x.get("count", 0), titulo=name, fecha=YDAY)
    except Exception as e:
        errors["web_origen"] = str(e)[:200]


# ---------------------------------------------------------------- Instagram
def _ig_index():
    """media_id -> (destinos, tipo) from our own publishing logs."""
    idx = {}
    try:
        for p in json.load(open(os.path.join(ROOT, "instagram", "published.json")))["posts"]:
            d = idx.setdefault(p["media_id"], [[], "carrusel" if p.get("carousel") else "post"])
            d[0].append(p["destino"])
    except Exception:
        pass
    for f in glob.glob(os.path.join(ROOT, "reels", "*", "published.json")):
        try:
            mid = json.load(open(f))["media_id"]
            dest = json.load(open(os.path.join(os.path.dirname(f), "plan.json")))["offer"]["destino"]
            idx[mid] = [[dest], "reel"]
        except Exception:
            pass
    return idx


@section("instagram")
def instagram():
    tok, uid = os.environ.get("IG_ACCESS_TOKEN"), os.environ.get("IG_USER_ID")
    if not tok or not uid:
        raise RuntimeError("faltan IG_ACCESS_TOKEN / IG_USER_ID")
    G = "https://graph.instagram.com"
    me = _get(f"{G}/{uid}", params={"fields": "followers_count,media_count", "access_token": tok})
    add("instagram", "cuenta", uid, "seguidores", me.get("followers_count"))
    add("instagram", "cuenta", uid, "publicaciones", me.get("media_count"))
    idx = _ig_index()
    media = _get(f"{G}/{uid}/media", params={"fields": "id,media_type,media_product_type,timestamp,permalink,like_count,comments_count",
                                              "limit": 50, "access_token": tok}).get("data", [])
    insight_err = None
    for m in media:
        dests, tipo = idx.get(m["id"], [[], (m.get("media_product_type") or m.get("media_type", "")).lower()])
        base = dict(publicado=m.get("timestamp", "")[:16].replace("T", " "), destinos=", ".join(dests),
                    titulo=", ".join(dests) or tipo, enlace=m.get("permalink", ""))
        add("instagram", tipo, m["id"], "me_gusta", m.get("like_count"), **base)
        add("instagram", tipo, m["id"], "comentarios", m.get("comments_count"), **base)
        metrics = "reach,views,saved,shares,total_interactions"
        try:
            ins = _get(f"{G}/{m['id']}/insights", params={"metric": metrics, "access_token": tok}).get("data", [])
            for x in ins:
                v = (x.get("values") or [{}])[0].get("value", x.get("total_value", {}).get("value"))
                name = {"reach": "alcance", "views": "vistas", "saved": "guardados", "shares": "compartidos",
                        "total_interactions": "interacciones"}.get(x["name"], x["name"])
                add("instagram", tipo, m["id"], name, v, **base)
        except Exception as e:
            insight_err = str(e)[:300]
    if insight_err:
        errors["instagram_insights"] = insight_err
    try:
        acc = _get(f"{G}/{uid}/insights", params={"metric": "reach,profile_views,website_clicks,accounts_engaged",
                                                   "period": "day", "metric_type": "total_value",
                                                   "since": int(datetime(YDAY.year, YDAY.month, YDAY.day, tzinfo=BOG).timestamp()),
                                                   "until": int(datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=BOG).timestamp()),
                                                   "access_token": tok}).get("data", [])
        for x in acc:
            name = {"reach": "alcance_dia", "profile_views": "visitas_perfil", "website_clicks": "clics_web",
                    "accounts_engaged": "cuentas_interactuaron"}.get(x["name"], x["name"])
            add("instagram", "cuenta", uid, name, (x.get("total_value") or {}).get("value"), fecha=YDAY)
    except Exception as e:
        errors["instagram_cuenta"] = str(e)[:300]


# ---------------------------------------------------------------- YouTube
@section("youtube")
def youtube():
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("falta YOUTUBE_API_KEY")
    Y = "https://www.googleapis.com/youtube/v3"
    ch = _get(f"{Y}/channels", params={"part": "statistics", "id": YT_CHANNEL, "key": key})["items"][0]["statistics"]
    add("youtube", "cuenta", YT_CHANNEL, "suscriptores", int(ch.get("subscriberCount", 0)))
    add("youtube", "cuenta", YT_CHANNEL, "vistas_total", int(ch.get("viewCount", 0)))
    add("youtube", "cuenta", YT_CHANNEL, "videos", int(ch.get("videoCount", 0)))
    pl = _get(f"{Y}/playlistItems", params={"part": "contentDetails", "playlistId": "UU" + YT_CHANNEL[2:],
                                            "maxResults": 50, "key": key}).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in pl]
    if not ids:
        return
    vids = _get(f"{Y}/videos", params={"part": "statistics,snippet", "id": ",".join(ids), "key": key}).get("items", [])
    for v in vids:
        sn, st = v["snippet"], v["statistics"]
        title = sn.get("title", "")
        m = re.search(r"(?:en|a)\s+([^,✈️#|]+?)(?:,|\s+desde|\s*✈|$)", title)
        base = dict(publicado=sn.get("publishedAt", "")[:16].replace("T", " "), destinos=(m.group(1).strip() if m else ""),
                    titulo=title, enlace=f"https://youtube.com/shorts/{v['id']}")
        for k, name in (("viewCount", "vistas"), ("likeCount", "me_gusta"), ("commentCount", "comentarios")):
            if k in st:
                add("youtube", "short", v["id"], name, int(st[k]), **base)


# ---------------------------------------------------------------- X
@section("x")
def x():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import x_post
    auth = x_post._auth()
    if not auth:
        raise RuntimeError("faltan las claves de X")
    me = _get("https://api.x.com/2/users/me", auth=auth, params={"user.fields": "public_metrics"})["data"]
    pm = me.get("public_metrics", {})
    add("x", "cuenta", me["id"], "seguidores", pm.get("followers_count"))
    add("x", "cuenta", me["id"], "posts", pm.get("tweet_count"))
    try:
        log = json.load(open(os.path.join(ROOT, "x", "published.json")))
    except Exception:
        log = []
    recent = [e for e in log if e.get("at", "")[:10] >= str(TODAY - timedelta(days=3))]
    if not recent:
        return
    data = _get("https://api.x.com/2/tweets", auth=auth,
                params={"ids": ",".join(e["tweet_id"] for e in recent[:20]), "tweet.fields": "public_metrics,created_at"}).get("data", [])
    by = {e["tweet_id"]: e for e in recent}
    for t in data:
        e, pm = by.get(t["id"], {}), t.get("public_metrics", {})
        title = e.get("title", "")
        dests = title.split(": ", 1)[1] if title.startswith("Ofertas: ") else re.sub(r"^Reel: \d+ días en ", "", title)
        base = dict(publicado=e.get("at", ""), destinos=dests, titulo=title, enlace=e.get("url", ""))
        tipo = "reel" if title.startswith("Reel") else "carrusel"
        for k, name in (("impression_count", "vistas"), ("like_count", "me_gusta"), ("retweet_count", "reposts"),
                        ("reply_count", "respuestas"), ("bookmark_count", "guardados")):
            if k in pm:
                add("x", tipo, t["id"], name, pm[k], **base)


# ---------------------------------------------------------------- Facebook Page
@section("facebook")
def facebook():
    pid, tok = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
    if not pid or not tok:
        raise RuntimeError("Facebook no conectado")
    F = "https://graph.facebook.com/v26.0"
    pg = _get(f"{F}/{pid}", params={"fields": "followers_count,fan_count", "access_token": tok})
    add("facebook", "cuenta", pid, "seguidores", pg.get("followers_count", pg.get("fan_count")))
    try:
        log = json.load(open(os.path.join(ROOT, "fb", "published.json")))
    except Exception:
        log = []
    for e in log[:30]:
        title = e.get("title", "")
        dests = title.split(": ", 1)[1] if title.startswith("Ofertas: ") else re.sub(r"^Reel: \d+ días en ", "", title)
        tipo = "reel" if e.get("kind") == "video" else "carrusel"
        base = dict(publicado=e.get("at", ""), destinos=dests, titulo=title, enlace=e.get("url", ""))
        try:
            if e.get("kind") == "video":
                v = _get(f"{F}/{e['post_id']}/video_insights", params={"metric": "total_video_views", "access_token": tok}).get("data", [])
                add("facebook", tipo, e["post_id"], "vistas", (v[0]["values"][0]["value"] if v else None), **base)
            else:
                v = _get(f"{F}/{e['post_id']}/insights", params={"metric": "post_impressions", "access_token": tok}).get("data", [])
                add("facebook", tipo, e["post_id"], "vistas", (v[0]["values"][0]["value"] if v else None), **base)
        except Exception as ex:
            errors["facebook_posts"] = str(ex)[:200]


def save():
    os.makedirs(OUT, exist_ok=True)
    hist = os.path.join(OUT, "history.csv")
    old = []
    if os.path.exists(hist):
        with open(hist, newline="") as f:
            old = [r for r in csv.DictReader(f)
                   # re-running the same night replaces that night's rows
                   if not (r["fecha"] in (str(TODAY), str(YDAY)) and (r["canal"], r["fecha"]) in
                           {(n["canal"], n["fecha"]) for n in rows})]
    with open(hist, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(old + rows)
    json.dump({"generado": datetime.now(BOG).strftime("%Y-%m-%d %H:%M"), "errores": errors, "filas": rows},
              open(os.path.join(OUT, "latest.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(rows)} filas · errores: {errors or 'ninguno'}")


if __name__ == "__main__":
    for fn in (web, instagram, youtube, x, facebook):
        fn()
    save()
