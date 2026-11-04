"""Layover check for flight deals. Owner's rule: layovers under 4 h are fine; 4–6 h is forbidden (too short to
leave the airport, too long to wait); longer layovers (also overnight) are fine ONLY if the traveller gets daytime to
explore the layover city – the alerts don't show clock times, so those go to the owner for a manual check.

Google Flights alerts only give the total travel time, the number of stops and the end airports
("COPA · 1 stop · BOG–CNF · 11 hrs"). This script estimates the pure flying time through the airline's hub(s)
and returns the time left for layovers:

    python scripts/layover.py BOG CNF "COPA" 1 11
    -> {"verdict": "ok", "layover_h": 3.0, "flying_h": 8.0, "via": "PTY", ...}

verdict: "ok"       est. layover < 3.5 h (2+ stops: < 3.5 h per stop on average)  -> post
         "review"   1 stop, 3.5 h or more (borderline, 4–6 h, or long/overnight); 2+ stops with longer
                    layovers; or travel time/airport unknown                            -> owner checks it
Non-stop flights are always "ok". The estimate is about ±1 h (Google rounds the travel time to whole hours).
"""
import csv
import itertools
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# main connection airports per airline (lowercase name fragments)
HUBS = {
    "avianca": ["BOG", "SAL", "MDE", "LIM"], "copa": ["PTY"], "arajet": ["SDQ"], "wingo": ["PTY", "BOG"],
    "latam": ["LIM", "GRU", "SCL", "BOG", "UIO"], "jetsmart": ["LIM", "SCL", "MDE", "BOG"],
    "viva": ["MEX", "MTY", "CUN", "GDL"], "volaris": ["MEX", "GDL", "TIJ"], "aeromexico": ["MEX"],
    "air canada": ["YYZ", "YUL", "YVR"], "american": ["MIA", "DFW", "CLT", "JFK"], "united": ["IAH", "EWR", "ORD", "SFO"],
    "delta": ["ATL", "JFK", "MSP", "DTW"], "jetblue": ["FLL", "JFK"], "spirit": ["FLL"], "frontier": ["MIA", "MCO", "DEN"],
    "iberia": ["MAD"], "air europa": ["MAD"], "plus ultra": ["MAD"], "air france": ["CDG"], "klm": ["AMS"],
    "lufthansa": ["FRA", "MUC"], "discover": ["FRA", "MUC"], "swiss": ["ZRH"], "edelweiss": ["ZRH"], "austrian": ["VIE"],
    "brussels": ["BRU"], "tap": ["LIS"], "british": ["LHR"], "turkish": ["IST"], "pegasus": ["SAW"], "condor": ["FRA"],
    "qatar": ["DOH"], "emirates": ["DXB"], "etihad": ["AUH"], "air new zealand": ["AKL"], "virgin australia": ["BNE", "SYD"],
    "qantas": ["SYD"], "eva": ["TPE"], "aerolineas": ["EZE", "AEP"], "gol": ["GRU", "BSB", "GIG"], "azul": ["VCP"],
    "sky": ["SCL", "LIM"], "conviasa": ["CCS"], "interjet": ["MEX"], "icelandair": ["KEF"], "ita": ["FCO"],
    "aer lingus": ["DUB"], "air transat": ["YUL", "YYZ"], "westjet": ["YYC", "YYZ"], "sas": ["CPH", "ARN"],
    "finnair": ["HEL"], "ethiopian": ["ADD"], "royal air maroc": ["CMN"], "korean": ["ICN"], "asiana": ["ICN"],
    "ana": ["NRT", "HND"], "japan airlines": ["NRT", "HND"], "singapore": ["SIN"], "cathay": ["HKG"], "air china": ["PEK"],
    "china eastern": ["PVG"], "china southern": ["CAN"], "boa": ["VVI"], "paranair": ["ASU"], "satena": ["BOG"],
}
# common hubs used when the airline is unknown ("varias aerolíneas", Kiwi)
GENERIC = ["PTY", "BOG", "LIM", "MIA", "MEX", "SAL", "SDQ", "MAD", "IST", "DOH", "GRU", "SCL", "IAH", "ATL", "FRA", "CDG"]

_AP = None


def airports():
    global _AP
    if _AP is None:
        _AP = {}
        with open(os.path.join(ROOT, "data", "airports_iata.csv"), newline="") as f:
            for r in csv.DictReader(f):
                _AP[r["iata"]] = (float(r["lat"]), float(r["lon"]))
    return _AP


def km(a, b):
    (la1, lo1), (la2, lo2) = airports()[a], airports()[b]
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 6371 * math.acos(max(-1, min(1, c)))


def leg_h(a, b):
    """Block time of one flight: cruise ~800 km/h + 25 min for taxi/climb/descent."""
    return km(a, b) / 800 + 0.42


def hubs_for(airline):
    a = (airline or "").lower()
    hubs = []
    for k, v in HUBS.items():
        if k in a:
            hubs += v
    return list(dict.fromkeys(hubs)) or GENERIC


def check(orig, dest, airline, stops, total_h):
    orig, dest = orig.upper(), dest.upper()
    stops = int(stops or 0)
    if stops == 0:
        return {"verdict": "ok", "layover_h": 0.0, "why": "non-stop"}
    if not total_h or orig not in airports() or dest not in airports():
        return {"verdict": "review", "layover_h": None, "why": "travel time unknown – check the layovers" if not total_h else "unknown airport – check the layovers"}
    total_h = float(total_h)
    hubs = [h for h in hubs_for(airline) if h in airports() and h not in (orig, dest)]
    need = min(stops, 2)
    if len(hubs) < need:   # e.g. "COPA, Air New Zealand" with 2 stops: PTY + one more connection
        hubs += [h for h in GENERIC if h not in hubs and h not in (orig, dest)]
    best = None
    for combo in itertools.permutations(hubs, need):
        path = [orig, *combo, dest]
        fly = sum(leg_h(a, b) for a, b in zip(path, path[1:]))
        if stops > 2:                       # rare: add one short extra leg
            fly += 1.5
        if best is None or fly < best[0]:
            best = (fly, "–".join(combo))
    fly, via = best
    lay = max(0.0, total_h - fly)
    if stops == 1:
        if lay < 3.5:
            verdict, why = "ok", f"~{lay:.0f} h layover via {via}"
        elif lay < 4.5:
            verdict, why = "review", f"~{lay:.1f} h layover via {via} – borderline (limit 4 h)"
        elif lay < 6.5:
            verdict, why = "review", f"~{lay:.0f} h layover via {via} – 4–6 h: check if it works"
        else:
            verdict, why = "review", f"~{lay:.0f} h layover via {via} – long: check if there is daytime to explore"
    else:
        if lay / stops < 3.5:
            verdict, why = "ok", f"~{lay:.0f} h of layovers in total ({stops} stops)"
        else:
            verdict, why = "review", f"~{lay:.0f} h of layovers in total ({stops} stops) – check them"
    return {"verdict": verdict, "layover_h": round(lay, 1), "flying_h": round(fly, 1),
            "via": via, "stops": stops, "total_h": total_h,
            "why": why}


def parse_alert_line(line):
    """'COPA · 1 stop · BOG–CNF · 11 hrs' -> dict for check()."""
    parts = [p.strip() for p in re.split(r"\s*·\s*", line)]
    out = {"airline": parts[0] if parts else ""}
    m = re.search(r"(\d+)\s+stops?", line)
    out["stops"] = 0 if re.search(r"non-?stop", line, re.I) else int(m.group(1)) if m else None
    m = re.search(r"\b([A-Z]{3})\s*[–-]\s*([A-Z]{3})\b", line)
    out["orig"], out["dest"] = (m.group(1), m.group(2)) if m else ("BOG", None)
    m = re.search(r"(\d+(?:\.\d+)?)\s*hrs?\b", line)
    out["total_h"] = float(m.group(1)) if m else None
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 1:      # one alert line
        p = parse_alert_line(a[0])
        print(json.dumps(check(p["orig"], p["dest"] or "", p["airline"], p["stops"], p["total_h"]), ensure_ascii=False))
    else:
        orig, dest, airline, stops, total = a + [None] * (5 - len(a))
        print(json.dumps(check(orig, dest, airline, stops, total), ensure_ascii=False))
