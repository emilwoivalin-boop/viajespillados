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
CH = {"instagram": "Instagram", "youtube": "YouTube", "x": "X", "web": "Web"}
VIEW = {"instagram": "vistas", "youtube": "vistas", "x": "vistas"}
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
          f"X {fmt(x_f)}" + (f" ({sign(x_fd)})" if x_fd else "") if x_f is not None else None]
    s.append("👥 Followers: " + " · ".join(x for x in fl if x) + ".")
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
    ])
    maxv = max([p["vistas"] for p in posts] or [1])
    prow = "".join(
        f'<tr><td><span class="ch ch-{p["canal"]}">{CH[p["canal"]]}</span></td>'
        f'<td><span class="ch chm">{CH[p["canal"]]}</span>{"<a href=" + chr(34) + e(p["enlace"]) + chr(34) + ">" if p["enlace"] else ""}{e(p["titulo"])}{"</a>" if p["enlace"] else ""}'
        f'<div class="sub">{e({"carrusel": "carousel"}.get(p["tipo"], p["tipo"]))} · {e(p["publicado"])}</div></td>'
        f'<td class="n"><div class="bar"><i style="width:{max(2, 100 * p["vistas"] / maxv):.0f}%"></i></div>{fmt(p["vistas"])}</td>'
        f'<td class="n">{sign(p["delta"]) if p["delta"] is not None else "—"}</td>'
        f'<td class="n">{fmt(p["likes"])}</td></tr>' for p in posts[:15])
    cols = ["instagram", "youtube", "x", "web clicks"]
    drow = "".join(
        f'<tr><td>{e(k)}</td>' + "".join(f'<td class="n">{fmt(v[c]) if v.get(c) else "·"}</td>' for c in cols) + "</tr>"
        for k, v in dest_rows[:15])
    rrow = "".join(f'<tr><td>{e(n)}</td><td class="n">{fmt(v)}</td></tr>' for n, v in refs[:10]) or \
        '<tr><td colspan="2" class="muted">No visits recorded yet.</td></tr>'
    err = ('<div class="warn">No data today from: ' + e(", ".join(f"{k} ({v[:80]})" for k, v in errors.items())) + "</div>") if errors else ""
    period = "new views in 24 h" if prev else "total views"
    gen = datetime.now(BOG).strftime("%Y-%m-%d %H:%M")

    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily performance</title>
<style>
:root{{--bg:#fff8ec;--card:#fff;--ink:#14223b;--muted:#5b6678;--line:#f0e3c8;--coral:#e8483c;--yellow:#ffc631;--green:#1f8a4c;--soft:#fff1d6}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0f1726;--card:#17223a;--ink:#eef2f8;--muted:#9aa6ba;--line:#26324c;--coral:#ff7a6e;--yellow:#ffd25c;--green:#4cc07c;--soft:#1d2a45}}}}
:root[data-theme="dark"]{{--bg:#0f1726;--card:#17223a;--ink:#eef2f8;--muted:#9aa6ba;--line:#26324c;--coral:#ff7a6e;--yellow:#ffd25c;--green:#4cc07c;--soft:#1d2a45}}
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
pre{{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;font:14px/1.5 system-ui,sans-serif;margin:0}}
</style></head><body><main>
<div class="top"><h1>Daily performance · Viajes Pillados</h1><small>{e(nice_date(today))} · updated {e(gen)} (Bogotá)</small></div>
<div class="tiles">{tiles}</div>{err}
<h2>Summary</h2><pre>{e(summary)}</pre>
<h2>Posts</h2>
<div class="card"><table class="pt"><thead><tr><th>Channel</th><th>Post</th><th class="n">Views</th><th class="n">24 h</th><th class="n">Likes</th></tr></thead>
<tbody>{prow or '<tr><td colspan="5" class="muted">No data.</td></tr>'}</tbody></table></div>
<div class="two">
<div><h2>Destinations <span class="muted" style="font-weight:400;font-size:13px">({period}; website clicks from yesterday)</span></h2>
<div class="card"><table><thead><tr><th>Destination</th><th class="n">Instagram</th><th class="n">YouTube</th><th class="n">X</th><th class="n">Web clicks</th></tr></thead>
<tbody>{drow or '<tr><td colspan="5" class="muted">No data.</td></tr>'}</tbody></table></div></div>
<div><h2>Website visits by source (yesterday)</h2>
<div class="card"><table><tbody>{rrow}</tbody></table></div></div>
</div>
<p class="muted" style="font-size:12.5px;margin-top:22px">Views: Instagram (views), YouTube (Short views), X (impressions of posts from the last 3 days). TikTok has no free statistics API. Website data: GoatCounter, no cookies.</p>
</main></body></html>"""
    return page, summary


if __name__ == "__main__":
    page, summary = build()
    open(sys.argv[1] if len(sys.argv) > 1 else "report.html", "w").write(page)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(summary)
    print(summary)
