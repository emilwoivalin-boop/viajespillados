"""Daily performance report from metrics/history.csv (written by metrics.py).

    python scripts/report.py <out.html> [<summary.md>]

The HTML is a self-contained page (no external requests) for the "Rendimiento diario" artifact;
the summary is a few short lines in English for the owner's notification. Nothing is committed.
"""
import csv
import html
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "metrics", "history.csv")
LATEST = os.path.join(ROOT, "metrics", "latest.json")
BOG = timezone(timedelta(hours=-5))
CH = {"instagram": "Instagram", "youtube": "YouTube", "x": "X", "facebook": "Facebook", "web": "Web"}
VIEW = {"instagram": "vistas", "youtube": "vistas", "x": "vistas", "facebook": "vistas"}
DIAS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fmt(n):
    n = int(round(n))
    return f"{n:,}"


def sign(n):
    n = int(round(n))
    return f"+{fmt(n)}" if n > 0 else ("±0" if n == 0 else f"−{fmt(-n)}")


def nice_date(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def load():
    rows = list(csv.DictReader(open(HIST, newline="")))
    snaps = sorted({r["fecha"] for r in rows if r["canal"] != "web" and r["tipo"] != "cuenta" or r["metrica"] in ("seguidores", "suscriptores")})
    today = snaps[-1] if snaps else None
    prev = snaps[-2] if len(snaps) > 1 else None
    return rows, today, prev


def short_date(d):
    d = date.fromisoformat(d)
    return f"{d.day} {MESES[d.month - 1]}"


def nice_max(v):
    if v <= 0:
        return 1
    import math
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * p:
            return m * p
    return 10 * p


def trends(rows):
    """Day-by-day series: website visits/clicks, new views, followers."""
    snaps = defaultdict(dict)
    for r in rows:
        snaps[r["fecha"]][(r["canal"], r["id"], r["metrica"], r["tipo"])] = num(r["valor"])
    dates = sorted(snaps)
    web = []
    for d in dates:
        s = snaps[d]
        vis = sum(v for k, v in s.items() if k[0] == "web" and k[3] == "web" and k[2] == "visitas")
        clk = sum(v for k, v in s.items() if k[0] == "web" and k[3] == "clic_oferta")
        if any(k[0] == "web" for k in s):
            web.append((d, vis, clk))
    # drop leading days before the site had any traffic
    while web and web[0][1] == 0 and web[0][2] == 0:
        web.pop(0)

    def post_views(s):
        return {(k[0], k[1]): v for k, v in s.items()
                if k[2] == "vistas" and k[3] not in ("cuenta", "web") and k[0] != "web"}

    views = []
    for a, b in zip(dates, dates[1:]):
        pa, pb = post_views(snaps[a]), post_views(snaps[b])
        if not pb:
            continue
        by = defaultdict(float)
        for k, v in pb.items():
            if k in pa:
                by[k[0]] += max(0.0, v - pa[k])
        views.append((b, sum(by.values()), dict(by)))

    def acct(canal, metrica):
        out = []
        for d in dates:
            v = next((v for k, v in snaps[d].items() if k[0] == canal and k[2] == metrica and k[3] == "cuenta"), None)
            if v is not None:
                out.append((d, v))
        return out

    return dict(web=web, views=views, ig=acct("instagram", "seguidores"), yt=acct("youtube", "suscriptores"),
                x=acct("x", "seguidores"), fb=acct("facebook", "seguidores"))


def svg_chart(cid, label, xs, series, kind="line", note=""):
    """xs: list of ISO dates; series: [(name, css-var, values)]. Returns HTML card with an inline SVG."""
    e = html.escape
    W, H, L, R, T, B = 460, 196, 44, 12, 20, 26
    pw, ph = W - L - R, H - T - B
    n = len(xs)
    if n == 0:
        return f'<div class="chart"><div class="ct">{e(label)}</div><p class="muted">Not enough data yet.</p></div>'
    top = 4 * max(1, nice_max(max([max(v) for _, _, v in series] + [0]) / 4))
    if kind == "bar":
        step = pw / n
        xpos = [L + step * (i + .5) for i in range(n)]
    else:
        xpos = [L + (pw * i / (n - 1) if n > 1 else pw / 2) for i in range(n)]
    y = lambda v: T + ph - ph * v / top
    g = []
    for i in range(5):
        tv = top * i / 4
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(tv):.1f}" y2="{y(tv):.1f}"/>'
                 f'<text class="ax" x="{L - 6}" y="{y(tv) + 4:.1f}" text-anchor="end">{fmt(tv) if tv < 1000 else f"{tv/1000:g}k"}</text>')
    every = max(1, round(n / 6))
    for i, d in enumerate(xs):
        if i % every == 0 or i == n - 1:
            g.append(f'<text class="ax" x="{xpos[i]:.1f}" y="{H - 8}" text-anchor="{'end' if i == n - 1 and kind != 'bar' else ('start' if i == 0 and kind != 'bar' else 'middle')}">{short_date(d)}</text>')
    marks = []
    for si, (name, col, vals) in enumerate(series):
        if kind == "bar":
            bw = min(28, step * .62)
            for i, v in enumerate(vals):
                h = max(0, y(0) - y(v))
                yy = y(v)
                r = min(4, h / 2, bw / 2)
                path = (f"M{xpos[i]-bw/2:.1f},{y(0):.1f} V{yy+r:.1f} Q{xpos[i]-bw/2:.1f},{yy:.1f} {xpos[i]-bw/2+r:.1f},{yy:.1f} "
                        f"H{xpos[i]+bw/2-r:.1f} Q{xpos[i]+bw/2:.1f},{yy:.1f} {xpos[i]+bw/2:.1f},{yy+r:.1f} V{y(0):.1f} Z")
                marks.append(f'<path d="{path}" fill="var({col})"/>')
        else:
            pts = " ".join(f"{xpos[i]:.1f},{y(v):.1f}" for i, v in enumerate(vals))
            marks.append(f'<polyline points="{pts}" fill="none" stroke="var({col})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
            for i, v in enumerate(vals):
                marks.append(f'<circle cx="{xpos[i]:.1f}" cy="{y(v):.1f}" r="3.5" fill="var({col})" stroke="var(--card)" stroke-width="2"/>')
            if len(series) == 1:  # direct label on the last point (legend covers multi-series)
                marks.append(f'<text class="dl" x="{xpos[-1] - 6:.1f}" y="{y(vals[-1]) - 9:.1f}" text-anchor="end">{fmt(vals[-1])}</text>')
    hits = []
    hw = pw / n if kind == "bar" else (pw / (n - 1) if n > 1 else pw)
    for i, d in enumerate(xs):
        tip = short_date(d) + "|" + "|".join(f"{name}: {fmt(vals[i])}" for name, _, vals in series)
        hits.append(f'<rect class="hit" x="{xpos[i] - hw/2:.1f}" y="{T}" width="{hw:.1f}" height="{ph}" data-x="{xpos[i]:.1f}" data-tip="{e(tip)}"/>')
    legend = ""
    if len(series) > 1:
        legend = '<div class="lg">' + "".join(f'<span><i style="background:var({c})"></i>{e(nm)}</span>' for nm, c, _ in series) + "</div>"
    table = ("<details><summary>Table</summary><table><thead><tr><th>Date</th>" + "".join(f'<th class="n">{e(nm)}</th>' for nm, _, _ in series)
             + "</tr></thead><tbody>" + "".join("<tr><td>" + short_date(d) + "</td>" + "".join(f'<td class="n">{fmt(v[i])}</td>' for _, _, v in series) + "</tr>"
                                                for i, d in enumerate(xs)) + "</tbody></table></details>")
    return (f'<div class="chart" id="{cid}"><div class="ct">{e(label)}</div>{legend}'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(label)}">{"".join(g)}<line class="xh" x1="0" x2="0" y1="{T}" y2="{T + ph}"/>'
            f'{"".join(marks)}{"".join(hits)}</svg>'
            f'{f"<div class=sub>{e(note)}</div>" if note else ""}{table}</div>')


def next_trip(rows, today):
    """Which destination to make the next travel-plan video about (videos not tied to an offer), from the numbers:
    how each destination's posts do compared with the average post of the same format (views, likes, saves, shares,
    comments), how often it was posted, and its offer clicks on the website. Destinations that already have a travel
    video (trips/*/plan.json) are skipped. Returns a list of (destino, score, facts) best first, or [] if data is thin."""
    import glob
    import re
    made = set()
    for pj in glob.glob(os.path.join(ROOT, "trips", "*", "plan.json")):
        try:
            made.add(json.load(open(pj)).get("destino", ""))
        except Exception:
            pass

    def names(s):
        out = []
        for d in (s or "").split(","):
            d = re.sub(r"^\s*(Plan de viaje|Portada|Reel):\s*", "", d).strip()
            if d and not re.search(r"[0-9:🌴✈]", d):
                out.append(d)
        return out

    W = {"vistas": 1, "me_gusta": 10, "comentarios": 15, "guardados": 30, "compartidos": 30}
    last = {}
    for r in rows:                                   # latest snapshot of every post
        if r["canal"] in ("instagram", "youtube", "x", "facebook") and r["tipo"] not in ("cuenta",) and r["metrica"] in W:
            k = (r["canal"], r["tipo"], r["id"])
            last.setdefault(k, {"destinos": r["destinos"], "fecha": "", "m": {}})
            if r["fecha"] >= last[k]["fecha"]:
                if r["fecha"] > last[k]["fecha"]:
                    last[k]["m"] = {}
                last[k]["fecha"] = r["fecha"]
                last[k]["m"][r["metrica"]] = num(r["valor"])
    pts = {k: sum(W[m] * v for m, v in p["m"].items()) for k, p in last.items()}
    fmt_avg = defaultdict(list)
    for k, v in pts.items():
        fmt_avg[(k[0], k[1])].append(v)
    fmt_avg = {k: (sum(v) / len(v)) or 1 for k, v in fmt_avg.items()}
    rel, views, eng, posts = defaultdict(list), defaultdict(float), defaultdict(float), defaultdict(int)
    for k, p in last.items():
        ds = names(p["destinos"])
        for d in ds:
            if k[0] in ("instagram", "youtube"):     # X/Facebook numbers are too small to compare
                rel[d].append(pts[k] / fmt_avg[(k[0], k[1])] / len(ds))
            views[d] += p["m"].get("vistas", 0) / len(ds)
            eng[d] += (p["m"].get("guardados", 0) + p["m"].get("compartidos", 0)) / len(ds)
            posts[d] += 1
    clicks = defaultdict(float)
    for r in rows:
        if r["canal"] == "web" and r["tipo"] == "clic_oferta":
            for d in names(r["destinos"]):
                clicks[d] += num(r["valor"])
    cands = []
    for d in set(rel) | set(clicks):
        if d in made:
            continue
        import math
        r_ = rel.get(d, [])
        perf = min(3.0, sum(r_) / len(r_)) if r_ else 0.0
        # real reach + how much people kept/shared it + how its posts did vs. the average + website interest
        score = (0.5 * math.log1p(views[d]) + 1.0 * math.log1p(eng[d]) + 1.0 * perf + 0.6 * math.log1p(clicks[d]) * 2)
        cands.append((d, score, {"posts": posts[d], "views": views[d], "saves_shares": eng[d], "clicks": clicks[d],
                                 "vs_avg": perf}))
    cands.sort(key=lambda c: -c[1])
    if len(cands) < 3 or sum(c[2]["posts"] for c in cands) < 5:
        return []
    return cands


def next_trip_text(c):
    d, _, f = c
    bits = []
    if f["posts"]:
        bits.append(f"{f['posts']} posts, {fmt(f['views'])} views ({f['vs_avg']:.1f}× the average post)")
    if f["saves_shares"]:
        bits.append(f"{fmt(f['saves_shares'])} saves/shares")
    if f["clicks"]:
        bits.append(f"{fmt(f['clicks'])} offer clicks on the website")
    return f"{d} – " + ", ".join(bits)


def insights(rows, tr, today):
    """Data-based conclusions and recommendations. Returns list of (conclusion, recommendation)."""
    out = []
    cur = [r for r in rows if r["fecha"] == today and r["metrica"] == "vistas" and r["tipo"] not in ("cuenta", "web")]
    fmt_name = {"reel": "reel", "reels": "reel", "carrusel": "carousel", "post": "post", "short": "Short"}
    # 1. format
    agg = defaultdict(list)
    for r in cur:
        agg[(r["canal"], fmt_name.get(r["tipo"], r["tipo"]))].append(num(r["valor"]))
    ig_reel, ig_car = agg.get(("instagram", "reel"), []), agg.get(("instagram", "carousel"), [])
    yt = agg.get(("youtube", "Short"), [])
    if ig_reel and ig_car:
        ar, ac = sum(ig_reel) / len(ig_reel), sum(ig_car) / len(ig_car)
        yt_txt = f", YouTube Shorts {fmt(sum(yt) / len(yt))}" if yt else ""
        out.append((f"Instagram reels average {fmt(ar)} views each vs {fmt(ac)} for carousels ({ar / max(ac, 1):.0f}×){yt_txt}.",
                    "Make reels the main format; keep carousels for offers but don't expect reach from them."))
    # 2. destination
    dest = defaultdict(float)
    for r in cur:
        if r["canal"] in ("instagram", "youtube") and r["destinos"] and "," not in r["destinos"] and fmt_name.get(r["tipo"]) in ("reel", "Short"):
            dest[r["destinos"]] += num(r["valor"])
    dest.pop("reels", None)
    if len(dest) >= 3:
        top = sorted(dest.items(), key=lambda kv: -kv[1])
        tot = sum(dest.values())
        out.append((f"Top destinations by reel/Short views: " + ", ".join(f"{k} {fmt(v)}" for k, v in top[:3])
                    + f" – the top one alone is {100 * top[0][1] / tot:.0f}% of all reel/Short views.",
                    f"Do a follow-up on {top[0][0]} (budget tips, best month, a cheaper alternative) and test similar destinations."))
    # 3. views trend
    v = tr["views"]
    if len(v) >= 3:
        last, prev = v[-1][1], v[-2][1]
        peak = max(v, key=lambda t: t[1])
        ch = (last - prev) / prev * 100 if prev else 0
        if peak[0] != v[-1][0] and last < peak[1]:
            out.append((f"New views per day peaked on {short_date(peak[0])} ({fmt(peak[1])}) and were {fmt(last)} today ({ch:+.0f}% vs the day before).",
                        "Reach comes in spikes from single reels – post a new reel every day so there is always a fresh one to take off."))
        else:
            out.append((f"New views per day are rising: {fmt(last)} today ({ch:+.0f}% vs the day before).",
                        "Keep the daily reel rhythm while it's working."))
    # 4. website conversion
    w = tr["web"]
    if w:
        vis, clk = sum(x[1] for x in w), sum(x[2] for x in w)
        pk = max(w, key=lambda t: t[1])
        src = defaultdict(float)
        for r in rows:
            if r["canal"] == "web" and r["tipo"] == "origen":
                name = (r["titulo"] or r["id"]).lower()
                src["Instagram" if ("ig" == name or "instagram" in name) else ("Google" if "google" in name else "other")] += num(r["valor"])
        st = sum(src.values()) or 1
        out.append((f"Website: {fmt(vis)} visits and {fmt(clk)} offer clicks since tracking started ({100 * clk / max(vis, 1):.0f}% click an offer); "
                    f"best day {short_date(pk[0])} with {fmt(pk[1])} visits. Instagram brings {100 * src['Instagram'] / st:.0f}% of visits, Google {100 * src['Google'] / st:.0f}%.",
                    "Put the website link (with the destination's offer) in every reel caption and story – site traffic follows Instagram spikes."))
    # 5. followers
    ig = tr["ig"]
    if len(ig) >= 3:
        gain = ig[-1][1] - ig[0][1]
        days = (date.fromisoformat(ig[-1][0]) - date.fromisoformat(ig[0][0])).days or 1
        out.append((f"Instagram went from {fmt(ig[0][1])} to {fmt(ig[-1][1])} followers in {days} days (about {fmt(gain / days)}/day).",
                    "Add a clear 'follow for a new cheap trip every day' call to action at the end of reels."))
    # 6. dead channels
    dead = []
    for canal in ("x", "facebook"):
        vals = [num(r["valor"]) for r in cur if r["canal"] == canal]
        if len(vals) >= 5 and sum(vals) <= 5:
            dead.append((CH[canal], len(vals)))
    if dead:
        out.append(("Almost no views on " + " and ".join(f"{c} ({n} posts)" for c, n in dead) + ".",
                    "Don't spend extra effort there for now; keep auto-posting and focus time on Instagram reels and YouTube Shorts."))
    return out


def build():
    rows, today, prev = load()
    try:
        errors = json.load(open(LATEST)).get("errores", {})
    except Exception:
        errors = {}
    snap = defaultdict(dict)                # fecha -> (canal,id,metrica) -> valor
    info = {}                               # (canal,id) -> row (titulo, enlace, destinos, tipo, publicado)
    for r in rows:
        snap[r["fecha"]][(r["canal"], r["id"], r["metrica"])] = num(r["valor"])
        if r["tipo"] not in ("cuenta", "web", "pagina", "evento", "origen", "clic_oferta"):
            info[(r["canal"], r["id"])] = r
    cur, old = snap.get(today, {}), snap.get(prev, {}) if prev else {}
    web_day = (date.fromisoformat(today) - timedelta(days=1)).isoformat() if today else None
    wd = [r for r in rows if r["canal"] == "web" and r["fecha"] == web_day]

    def acct(canal, metrica):
        k = next((k for k in cur if k[0] == canal and k[2] == metrica), None)
        if not k:
            return None, None
        return cur[k], (cur[k] - old[k]) if k in old else None

    # posts with cumulative views + 24h change
    posts = []
    for (canal, pid), r in info.items():
        m = VIEW.get(canal)
        k = (canal, pid, m)
        if k not in cur:
            continue
        v = cur[k]
        d = v - old[k] if k in old else None
        likes = cur.get((canal, pid, "me_gusta"), 0)
        posts.append(dict(canal=canal, tipo=r["tipo"], titulo=r["destinos"] or r["titulo"], enlace=r["enlace"],
                          publicado=r["publicado"][:10], vistas=v, delta=d, likes=likes,
                          alcance=cur.get((canal, pid, "alcance"))))
    posts.sort(key=lambda p: (-(p["delta"] if p["delta"] is not None else p["vistas"]), -p["vistas"]))
    views_24h = sum(p["delta"] for p in posts if p["delta"] is not None) if prev else None
    views_total = sum(p["vistas"] for p in posts)

    # views by destination (single-destination posts only: Reels/Shorts and single offers)
    dest = defaultdict(lambda: defaultdict(float))
    for p in posts:
        if "," in p["titulo"] or not p["titulo"]:
            continue
        dest[p["titulo"]][p["canal"]] += p["delta"] if (prev and p["delta"] is not None) else p["vistas"]
    clicks = defaultdict(float)
    for r in wd:
        if r["tipo"] == "clic_oferta":
            clicks[r["destinos"] or r["id"]] += num(r["valor"])
    for k, v in clicks.items():
        dest[k]["web clicks"] += v
    dest_rows = sorted(dest.items(), key=lambda kv: -sum(v for c, v in kv[1].items() if c != "web clicks") - 50 * kv[1].get("web clicks", 0))

    web_visits = sum(num(r["valor"]) for r in wd if r["tipo"] == "web" and r["metrica"] == "visitas")
    web_clicks = sum(clicks.values())
    refs = sorted(((r["titulo"] or r["id"], num(r["valor"])) for r in wd if r["tipo"] == "origen"), key=lambda x: -x[1])

    ig_f, ig_fd = acct("instagram", "seguidores")
    yt_f, yt_fd = acct("youtube", "suscriptores")
    x_f, x_fd = acct("x", "seguidores")
    fb_f, fb_fd = acct("facebook", "seguidores")
    ig_day = {m: cur.get(k) for k in cur for m in ["alcance_dia", "visitas_perfil", "clics_web"] if k[0] == "instagram" and k[2] == m}

    # ---------------------------------------------------------------- summary text
    s = [f"📊 Performance {nice_date(today)}"]
    if views_24h is not None:
        s.append(f"👀 {fmt(views_24h)} new views in 24 h (total {fmt(views_total)}).")
    else:
        s.append(f"👀 {fmt(views_total)} views in total (first day: the 24 h change starts tomorrow).")
    if posts:
        b = posts[0]
        s.append(f"🏆 Top: {b['titulo']} on {CH[b['canal']]} – {fmt(b['vistas'])} views"
                 + (f" ({sign(b['delta'])} today)." if b["delta"] is not None else "."))
    s.append(f"🌐 Website yesterday: {fmt(web_visits)} visits, {fmt(web_clicks)} offer clicks"
             + (f"; top: {max(clicks, key=clicks.get)}." if clicks else "."))
    fl = [f"IG {fmt(ig_f)}" + (f" ({sign(ig_fd)})" if ig_fd else "") if ig_f is not None else None,
          f"YouTube {fmt(yt_f)}" + (f" ({sign(yt_fd)})" if yt_fd else "") if yt_f is not None else None,
          f"X {fmt(x_f)}" + (f" ({sign(x_fd)})" if x_fd else "") if x_f is not None else None,
          f"Facebook {fmt(fb_f)}" + (f" ({sign(fb_fd)})" if fb_fd else "") if fb_f is not None else None]
    s.append("👥 Followers: " + " · ".join(x for x in fl if x) + ".")
    nt = next_trip(rows, today)
    if nt:
        s.append("🎬 Next travel video: " + next_trip_text(nt[0]) + ". Then: " + ", ".join(c[0] for c in nt[1:3]) + ".")
    if errors:
        s.append("⚠️ No data from: " + ", ".join(errors) + ".")
    summary = "\n".join(s)

    # ---------------------------------------------------------------- HTML
    e = html.escape

    def tile(label, value, delta=None, note=""):
        d = f'<span class="d {"up" if delta and delta > 0 else ""}">{sign(delta)}</span>' if delta is not None else ""
        return f'<div class="tile"><div class="tl">{e(label)}</div><div class="tv">{value}{d}</div><div class="tn">{e(note)}</div></div>'

    tiles = "".join([
        tile("Views in 24 h", fmt(views_24h) if views_24h is not None else "—", None,
             f"{fmt(views_total)} in total" if views_24h is not None else f"{fmt(views_total)} in total · change from tomorrow"),
        tile("Website visits (yesterday)", fmt(web_visits), None, f"{fmt(web_clicks)} offer clicks"),
        tile("Instagram followers", fmt(ig_f) if ig_f is not None else "—", ig_fd,
             f"reach yesterday {fmt(ig_day['alcance_dia'])}" if ig_day.get("alcance_dia") is not None else ""),
        tile("YouTube subscribers", fmt(yt_f) if yt_f is not None else "—", yt_fd),
        tile("X followers", fmt(x_f) if x_f is not None else "—", x_fd),
        tile("Facebook followers", fmt(fb_f) if fb_f is not None else "—", fb_fd),
    ])
    maxv = max([p["vistas"] for p in posts] or [1])
    prow = "".join(
        f'<tr><td><span class="ch ch-{p["canal"]}">{CH[p["canal"]]}</span></td>'
        f'<td><span class="ch chm">{CH[p["canal"]]}</span>{"<a href=" + chr(34) + e(p["enlace"]) + chr(34) + ">" if p["enlace"] else ""}{e(p["titulo"])}{"</a>" if p["enlace"] else ""}'
        f'<div class="sub">{e({"carrusel": "carousel"}.get(p["tipo"], p["tipo"]))} · {e(p["publicado"])}</div></td>'
        f'<td class="n"><div class="bar"><i style="width:{max(2, 100 * p["vistas"] / maxv):.0f}%"></i></div>{fmt(p["vistas"])}</td>'
        f'<td class="n">{sign(p["delta"]) if p["delta"] is not None else "—"}</td>'
        f'<td class="n">{fmt(p["likes"])}</td></tr>' for p in posts[:15])
    cols = ["instagram", "youtube", "x", "facebook", "web clicks"]
    drow = "".join(
        f'<tr><td>{e(k)}</td>' + "".join(f'<td class="n">{fmt(v[c]) if v.get(c) else "·"}</td>' for c in cols) + "</tr>"
        for k, v in dest_rows[:15])
    rrow = "".join(f'<tr><td>{e(n)}</td><td class="n">{fmt(v)}</td></tr>' for n, v in refs[:10]) or \
        '<tr><td colspan="2" class="muted">No visits recorded yet.</td></tr>'
    err = ('<div class="warn">No data today from: ' + e(", ".join(f"{k} ({v[:80]})" for k, v in errors.items())) + "</div>") if errors else ""
    period = "new views in 24 h" if prev else "total views"
    gen = datetime.now(BOG).strftime("%Y-%m-%d %H:%M")
    tr = trends(rows)
    charts = "".join([
        svg_chart("c-web", "Website visits & offer clicks (per day)", [d for d, _, _ in tr["web"]],
                  [("Visits", "--s1", [v for _, v, _ in tr["web"]]), ("Offer clicks", "--s2", [c for _, _, c in tr["web"]])]),
        svg_chart("c-views", "New views per day (all channels)", [d for d, _, _ in tr["views"]],
                  [("New views", "--s1", [v for _, v, _ in tr["views"]])], kind="bar",
                  note="Only posts tracked on both days count; Instagram tracked from 1 Nov."),
        svg_chart("c-ig", "Instagram followers", [d for d, _ in tr["ig"]], [("Followers", "--s1", [v for _, v in tr["ig"]])]),
        svg_chart("c-yt", "YouTube subscribers", [d for d, _ in tr["yt"]], [("Subscribers", "--s1", [v for _, v in tr["yt"]])],
                  note=("X and Facebook: " + " · ".join(f"{n} {fmt(t[-1][1])}" for n, t in (("X", tr["x"]), ("Facebook", tr["fb"])) if t)) if tr["x"] or tr["fb"] else ""),
    ])
    ins = insights(rows, tr, today)
    if nt:
        top3 = "; ".join(next_trip_text(c) for c in nt[:3])
        ins.insert(0, (f"Best destinations for the next travel-plan video (no travel video yet, ranked by how their posts did "
                       f"vs. the average post of the same format + website offer clicks): {top3}.",
                       f"Make the next travel video about {nt[0][0]}."))
    insrow = "".join(f'<li><b>{e(c)}</b><br><span class="rec">→ {e(r)}</span></li>' for c, r in ins) or '<li class="muted">Not enough data yet.</li>'

    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily performance</title>
<style>
:root{{--s1:#2a78d6;--s2:#eb6834;--bg:#fff8ec;--card:#fff;--ink:#14223b;--muted:#5b6678;--line:#f0e3c8;--coral:#e8483c;--yellow:#ffc631;--green:#1f8a4c;--soft:#fff1d6}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--s1:#3987e5;--s2:#d95926;--bg:#0f1726;--card:#17223a;--ink:#eef2f8;--muted:#9aa6ba;--line:#26324c;--coral:#ff7a6e;--yellow:#ffd25c;--green:#4cc07c;--soft:#1d2a45}}}}
:root[data-theme="dark"]{{--s1:#3987e5;--s2:#d95926;--bg:#0f1726;--card:#17223a;--ink:#eef2f8;--muted:#9aa6ba;--line:#26324c;--coral:#ff7a6e;--yellow:#ffd25c;--green:#4cc07c;--soft:#1d2a45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:22px 16px 48px}}h1{{font-size:24px;margin:0}}h2{{font-size:16px;margin:26px 0 10px}}
.top{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}}.muted,.top small{{color:var(--muted)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:16px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}}.tl{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.tv{{font-size:26px;font-weight:800;margin-top:2px;font-variant-numeric:tabular-nums}}.tn{{font-size:12.5px;color:var(--muted)}}
.d{{font-size:13px;font-weight:700;margin-left:8px;color:var(--muted)}}.d.up{{color:var(--green)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:4px 0;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:0}}th{{font-size:12px;color:var(--muted);font-weight:600}}td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.sub{{font-size:12px;color:var(--muted)}}a{{color:inherit}}.bar{{display:inline-block;width:60px;height:6px;background:var(--soft);border-radius:3px;margin-right:8px;vertical-align:middle}}
.bar i{{display:block;height:100%;background:var(--coral);border-radius:3px}}
.ch{{font-size:12px;font-weight:700;padding:2px 8px;border-radius:999px;background:var(--soft);white-space:nowrap}}
.two{{display:grid;grid-template-columns:2fr 1fr;gap:14px}}@media (max-width:720px){{.two{{grid-template-columns:1fr}}}}
.chm{{display:none}}@media (max-width:560px){{.bar{{display:none}}.pt td:first-child,.pt th:first-child{{display:none}}.chm{{display:inline-block;margin:0 6px 4px 0}}th,td{{padding:8px 10px}}}}
.warn{{margin-top:14px;background:var(--soft);border-radius:12px;padding:10px 14px;font-size:13.5px}}
.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:12px}}
.chart{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}}.ct{{font-weight:700;font-size:14px;margin-bottom:4px}}
.chart svg{{width:100%;height:auto;display:block}}.grid{{stroke:var(--line);stroke-width:1}}.ax{{fill:var(--muted);font-size:11px}}.dl{{fill:var(--ink);font-size:11.5px;font-weight:700}}
.xh{{stroke:var(--muted);stroke-width:1;opacity:0}}.hit{{fill:transparent;cursor:crosshair}}
.lg{{display:flex;gap:14px;font-size:12.5px;color:var(--muted);margin-bottom:2px}}.lg i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
.chart details{{margin-top:6px;font-size:12.5px;color:var(--muted)}}.chart details table{{font-size:12.5px}}.chart summary{{cursor:pointer}}
.tip{{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);border-radius:8px;padding:6px 9px;font-size:12.5px;line-height:1.4;z-index:9;white-space:nowrap}}
.ins{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px 12px 34px;margin:0}}.ins li{{margin:6px 0 10px}}.rec{{color:var(--muted)}}
pre{{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;font:14px/1.5 system-ui,sans-serif;margin:0}}
</style></head><body><main>
<div class="top"><h1>Daily performance · Viajes Pillados</h1><small>{e(nice_date(today))} · updated {e(gen)} (Bogotá)</small></div>
<div class="tiles">{tiles}</div>{err}
<h2>Summary</h2><pre>{e(summary)}</pre>
<h2>Trends</h2><div class="charts">{charts}</div><div id="tip" class="tip" hidden></div>
<h2>Conclusions &amp; recommendations</h2><ol class="ins">{insrow}</ol>
<h2>Posts</h2>
<div class="card"><table class="pt"><thead><tr><th>Channel</th><th>Post</th><th class="n">Views</th><th class="n">24 h</th><th class="n">Likes</th></tr></thead>
<tbody>{prow or '<tr><td colspan="5" class="muted">No data.</td></tr>'}</tbody></table></div>
<div class="two">
<div><h2>Destinations <span class="muted" style="font-weight:400;font-size:13px">({period}; website clicks from yesterday)</span></h2>
<div class="card"><table><thead><tr><th>Destination</th><th class="n">Instagram</th><th class="n">YouTube</th><th class="n">X</th><th class="n">Facebook</th><th class="n">Web clicks</th></tr></thead>
<tbody>{drow or '<tr><td colspan="6" class="muted">No data.</td></tr>'}</tbody></table></div></div>
<div><h2>Website visits by source (yesterday)</h2>
<div class="card"><table><tbody>{rrow}</tbody></table></div></div>
</div>
<p class="muted" style="font-size:12.5px;margin-top:22px">Views: Instagram (views), YouTube (Short views), X (impressions of posts from the last 3 days). TikTok has no free statistics API. Website data: GoatCounter, no cookies.</p>
</main><script>
(function(){{var tip=document.getElementById('tip');
document.querySelectorAll('.chart svg').forEach(function(svg){{var xh=svg.querySelector('.xh');
svg.querySelectorAll('.hit').forEach(function(h){{
h.addEventListener('pointerenter',function(){{xh.setAttribute('x1',h.dataset.x);xh.setAttribute('x2',h.dataset.x);xh.style.opacity=.6;
var p=h.dataset.tip.split('|');tip.innerHTML='<b>'+p[0]+'</b><br>'+p.slice(1).join('<br>');tip.hidden=false;}});
h.addEventListener('pointermove',function(ev){{var x=ev.clientX+12;if(x+160>innerWidth)x=ev.clientX-170;tip.style.left=x+'px';tip.style.top=(ev.clientY+12)+'px';}});
h.addEventListener('pointerleave',function(){{xh.style.opacity=0;tip.hidden=true;}});}});}});}})();
</script></body></html>"""
    return page, summary


if __name__ == "__main__":
    page, summary = build()
    open(sys.argv[1] if len(sys.argv) > 1 else "report.html", "w").write(page)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(summary)
    print(summary)
