"""Fetch OpenStreetMap data for a fact Reel map (runs in GitHub Actions – Overpass is not reachable elsewhere).

    python scripts/factmap_fetch.py <id> "<city boundary name>" [admin_level] [centre_bbox s,w,n,e]

Writes reels/facts/<id>/map/osm.json.gz:
  {"boundary": [[ring of [lon,lat]], ...], "water": [...], "green": [...], "roads": {"major": [...], "minor": [...]},
   "rail": [...], "buildings": [...]}
Polygons are lists of rings; lines are lists of [lon,lat]. Map data © OpenStreetMap contributors (ODbL).
"""
import gzip, json, os, sys, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
UA = {"User-Agent": "ViajesPilladosBot/1.0 (https://viajespillados.com; fact reels map)"}


def q(query):
    for attempt in range(6):
        url = URLS[attempt % len(URLS)]
        try:
            r = requests.post(url, data={"data": query}, headers=UA, timeout=300)
            if r.status_code == 200:
                return r.json()["elements"]
            print("overpass", url, r.status_code, r.text[:200])
        except Exception as e:
            print("overpass", url, e)
        time.sleep(15)
    raise RuntimeError("Overpass failed")


def r5(pts):
    return [[round(p["lon"], 5), round(p["lat"], 5)] for p in pts]


def join_rings(ways):
    """Join way segments (lists of [lon,lat]) into closed rings."""
    segs = [w[:] for w in ways if len(w) > 1]
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if len(ring) > 3:
            rings.append(ring)
    return rings


def polys(elements):
    """Elements (ways with geometry, relations with member geometry) → list of polygons (outer rings + holes as
    separate lists: {"o": [...rings], "i": [...rings]})."""
    out = []
    for e in elements:
        if e["type"] == "way" and e.get("geometry"):
            g = r5(e["geometry"])
            if len(g) > 3 and g[0] == g[-1]:
                out.append({"o": [g], "i": []})
        elif e["type"] == "relation":
            outer = [r5(m["geometry"]) for m in e.get("members", []) if m.get("geometry") and m.get("role") != "inner"]
            inner = [r5(m["geometry"]) for m in e.get("members", []) if m.get("geometry") and m.get("role") == "inner"]
            o = join_rings(outer)
            if o:
                out.append({"o": o, "i": join_rings(inner)})
    return out


def lines(elements):
    return [r5(e["geometry"]) for e in elements if e["type"] == "way" and e.get("geometry")]


def main(rid, name, level="8", centre=None):
    b = q(f'[out:json][timeout:200];relation["boundary"="administrative"]["admin_level"="{level}"]["name"="{name}"];out geom;')
    if not b:
        raise SystemExit("boundary not found")
    rel = max(b, key=lambda e: len(e.get("members", [])))
    outer = join_rings([r5(m["geometry"]) for m in rel["members"] if m.get("geometry") and m.get("role") == "outer"])
    lons = [p[0] for r in outer for p in r]
    lats = [p[1] for r in outer for p in r]
    pad = 0.04
    s, w, n, e = min(lats) - pad, min(lons) - pad * 1.6, max(lats) + pad, max(lons) + pad * 1.6
    bb = f"({s},{w},{n},{e})"
    cb = f"({centre})" if centre else bb
    print("bbox", bb, "centre", cb)
    water = q(f'[out:json][timeout:250];(way["natural"="water"]{bb};relation["natural"="water"]{bb};'
              f'way["waterway"="riverbank"]{bb};relation["waterway"="riverbank"]{bb};'
              f'way["landuse"~"^(reservoir|basin)$"]{bb};relation["natural"="bay"]{bb};);out geom;')
    green = q(f'[out:json][timeout:250];(way["leisure"~"^(park|garden|golf_course|nature_reserve)$"]{bb};'
              f'relation["leisure"~"^(park|nature_reserve)$"]{bb};'
              f'way["landuse"~"^(grass|forest|meadow|recreation_ground|cemetery|allotments|village_green)$"]{bb};'
              f'relation["landuse"~"^(forest|meadow|grass)$"]{bb};way["natural"~"^(wood|grassland|scrub)$"]{bb};);out geom;')
    major = q(f'[out:json][timeout:250];way["highway"~"^(motorway|trunk|primary|secondary)$"]{bb};out geom;')
    minor = q(f'[out:json][timeout:250];way["highway"~"^(tertiary|residential|unclassified|living_street|pedestrian)$"]{cb};out geom;')
    rail = q(f'[out:json][timeout:250];way["railway"="rail"]["service"!~"."]{bb};out geom;')
    bld = q(f'[out:json][timeout:250];way["building"]{cb};out geom;')
    data = {"name": name, "bbox": [w, s, e, n], "boundary": outer, "water": polys(water), "green": polys(green),
            "roads": {"major": lines(major), "minor": lines(minor)}, "rail": lines(rail),
            "buildings": [p["o"][0] for p in polys(bld)]}
    d = os.path.join(ROOT, "reels", "facts", rid, "map")
    os.makedirs(d, exist_ok=True)
    with gzip.open(os.path.join(d, "osm.json.gz"), "wt") as f:
        json.dump(data, f, separators=(",", ":"))
    print({k: (len(v) if isinstance(v, list) else {a: len(b) for a, b in v.items()}) for k, v in data.items()
           if k not in ("name", "bbox")})


if __name__ == "__main__":
    main(*sys.argv[1:])
