"""One-off: Natural Earth 10m countries + lakes → data/naturalearth.json.gz (for the fact Reels' continent/country zoom).
Source: https://github.com/nvkelso/natural-earth-vector (public domain)."""
import gzip, json, sys


def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [[[[round(x, 3), round(y, 3)] for x, y in r] for r in p] for p in polys]


def main(countries, lakes, out):
    c = json.load(open(countries))
    lk = json.load(open(lakes))
    data = {"countries": [], "lakes": []}
    for f in c["features"]:
        p = f["properties"]
        iso = p.get("ADM0_A3") if p.get("ISO_A3") in (None, "-99") else p["ISO_A3"]
        data["countries"].append({"iso": iso, "name": p.get("NAME"), "cont": p.get("CONTINENT"),
                                  "polys": rings(f["geometry"])})
    for f in lk["features"]:
        if f["geometry"] and (f["properties"].get("scalerank") or 0) <= 6:
            data["lakes"] += rings(f["geometry"])
    with gzip.open(out, "wt") as fh:
        json.dump(data, fh, separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:])
