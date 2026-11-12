"""Fetch OpenStreetMap data for a fact Reel map (runs in GitHub Actions – Overpass is not reachable elsewhere).

    python scripts/factmap_fetch.py <id> "<City, Country>" [osm relation id]

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


def fact_dir(rid):
    """A daily fact Reel lives in reels/<id>/ (next to its plan.json); test/one-off ones in reels/facts/<id>/."""
    d = os.path.join(ROOT, "reels", rid)
    return d if os.path.exists(os.path.join(d, "plan.json")) else os.path.join(ROOT, "reels", "facts", rid)


def find_city(query):
    """Nominatim → point; Overpass is_in → the city-sized administrative boundary around it (admin level 8, 7 or 6)."""
    r = requests.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=60,
                     params={"q": query, "format": "json", "limit": 1})
    r.raise_for_status()
    hit = r.json()[0]
    lat, lon = float(hit["lat"]), float(hit["lon"])
    print("nominatim", query, "→", hit.get("display_name"), lat, lon, hit.get("osm_type"), hit.get("osm_id"))
    if hit.get("osm_type") == "relation" and hit.get("class") == "boundary":
        return int(hit["osm_id"]), lat, lon
    rels = q(f'[out:json][timeout:120];is_in({lat},{lon})->.a;'
             f'rel(pivot.a)["boundary"="administrative"]["admin_level"~"^(6|7|8)$"];out tags;')
    if not rels:
        raise SystemExit(f"no administrative boundary around {query}")
    rels.sort(key=lambda e: -int(e["tags"].get("admin_level", 0)))
    best = rels[0]
    print("boundary", best["id"], best["tags"].get("name"), "admin_level", best["tags"].get("admin_level"))
    return best["id"], lat, lon


def main(rid, query, rel=None):
    """query: "Cartagena, Colombia" (or old style "Amsterdam|8"); rel: optional OSM relation id to force the outline."""
    lat0 = lon0 = None
    if query.startswith("rel:"):
        rel = query[4:]
    if rel:
        rel = int(rel)
    elif "|" in query:
        name, level = (query.split("|") + ["8"])[:2]
        b = q(f'[out:json][timeout:200];relation["boundary"="administrative"]["admin_level"="{level}"]["name"="{name}"];out ids;')
        rel = b[0]["id"]
    else:
        rel, lat0, lon0 = find_city(query)
    b = q(f'[out:json][timeout:200];relation({rel});out geom;')
    relel = b[0]
    outer = join_rings([r5(m["geometry"]) for m in relel["members"] if m.get("geometry") and m.get("role") == "outer"])
    lons = [p[0] for r in outer for p in r]
    lats = [p[1] for r in outer for p in r]
    if lat0 is None:   # centre = the relation's admin_centre/label node, else the middle of the outline
        cn = [m for m in relel["members"] if m["type"] == "node" and m.get("role") in ("admin_centre", "label")]
        lat0, lon0 = (cn[0]["lat"], cn[0]["lon"]) if cn else ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
    pad = 0.04
    s, w, n, e = min(lats) - pad, min(lons) - pad * 1.6, max(lats) + pad, max(lons) + pad * 1.6
    # very big municipalities: keep the map data to ~70 km around the centre
    s, n = max(s, lat0 - 0.32), min(n, lat0 + 0.32)
    w, e = max(w, lon0 - 0.45), min(e, lon0 + 0.45)
    bb = f"({s},{w},{n},{e})"
    cb = f"({lat0 - 0.03},{lon0 - 0.045},{lat0 + 0.03},{lon0 + 0.045})"
    print("bbox", bb, "centre", cb)
    water = q(f'[out:json][timeout:250];(way["natural"="water"]{bb};relation["natural"="water"]{bb};'
              f'way["waterway"="riverbank"]{bb};relation["waterway"="riverbank"]{bb};'
              f'way["landuse"~"^(reservoir|basin)$"]{bb};);out geom;')
    coast = q(f'[out:json][timeout:250];way["natural"="coastline"]{bb};out geom;')
    green = q(f'[out:json][timeout:250];(way["leisure"~"^(park|garden|golf_course|nature_reserve)$"]{bb};'
              f'relation["leisure"~"^(park|nature_reserve)$"]{bb};'
              f'way["landuse"~"^(grass|forest|meadow|recreation_ground|cemetery|allotments|village_green)$"]{bb};'
              f'relation["landuse"~"^(forest|meadow|grass)$"]{bb};way["natural"~"^(wood|grassland|scrub|beach|sand)$"]{bb};);out geom;')
    major = q(f'[out:json][timeout:250];way["highway"~"^(motorway|trunk|primary|secondary)$"]{bb};out geom;')
    minor = q(f'[out:json][timeout:250];way["highway"~"^(tertiary|residential|unclassified|living_street|pedestrian)$"]{cb};out geom;')
    rail = q(f'[out:json][timeout:250];way["railway"="rail"]["service"!~"."]{bb};out geom;')
    bld = q(f'[out:json][timeout:250];way["building"]{cb};out geom;')
    sand = [p for p in polys([g for g in green if (g.get("tags") or {}).get("natural") in ("beach", "sand")])]
    data = {"name": relel.get("tags", {}).get("name", query), "rel": rel, "centre": [lon0, lat0], "bbox": [w, s, e, n],
            "boundary": outer, "water": polys(water), "coast": lines(coast),
            "green": polys([g for g in green if (g.get("tags") or {}).get("natural") not in ("beach", "sand")]),
            "sand": sand, "roads": {"major": lines(major), "minor": lines(minor)}, "rail": lines(rail),
            "buildings": [p["o"][0] for p in polys(bld)]}
    d = os.path.join(fact_dir(rid), "map")
    os.makedirs(d, exist_ok=True)
    with gzip.open(os.path.join(d, "osm.json.gz"), "wt") as f:
        json.dump(data, f, separators=(",", ":"))
    print({k: (len(v) if isinstance(v, list) else v) for k, v in data.items() if k not in ("bbox", "centre")
           and not isinstance(v, dict)})


if __name__ == "__main__":
    main(*sys.argv[1:])
