"""Instagram caption for the daily Reel (owner's format, Nov 2026): a destination plan, few emojis, NO flight offer
(the offer is only shown at the end of the Reel). The content comes from the Where Next Atlas data
(data/wherenext.json, English) translated to Colombian Spanish by step A, saved in plan.json as "caption_es":

  "caption_es": {
    "hook":     "¿Madrid en 3 días sin perder ni un minuto? Pilla este plan, parce.",
    "intro":    "Arte de primer nivel, almuerzos eternos y noches que no se acaban.",   # from tagline
    "pais":     "España",
    "dias":     [{"titulo": "Museo del Prado", "texto": "Velázquez, Goya y los grandes maestros, frente a frente."}, ...],
    "bonus":    "Sal de noche por Malasaña, que allá se cena tarde y se rumbea más tarde.",   # optional
    "dato":     "Madrid es la capital de España desde 1561",            # fun fact, no "¿Sabías que"
    "epoca":    "abril a junio y septiembre a octubre",                 # from months
    "para":     "te gusta el arte, la comida y trasnochar",             # from good
    "no_para":  "odias el calor del verano o quieres playa cerca",      # from skip
    "versus":   "Barcelona",                                            # a similar place (optional)
    "hashtags": ["#madrid", "#españa", "#quehacerenmadrid"]
  }

    python scripts/reel_caption.py find <destino or IATA>   # look the destination up in data/wherenext.json
    python scripts/reel_caption.py show <id>                # print the caption of reels/<id>/plan.json
"""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXED_TAGS = ["#viajes", "#viajespillados"]
SITE = "Más planes y vuelos baratos en viajespillados.com (link en el perfil)."


def _slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def find(q):
    """Where Next entries matching a name (Spanish or English, accents ignored), id or IATA code."""
    data = json.load(open(os.path.join(ROOT, "data", "wherenext.json")))
    q0 = q.strip()
    if re.fullmatch(r"[A-Z]{3}", q0):
        return [d for d in data if q0 in (d.get("iata") or [])]
    s = _slug(q0)
    exact = [d for d in data if s in (d["id"], _slug(d["name"]))]
    return exact or [d for d in data if s and (s in _slug(d["name"]) or _slug(d["name"]) in s)]


def build(plan):
    c = plan.get("caption_es") or {}
    if not c.get("dias"):
        return None
    o = plan["offer"]
    dest = o["destino"]
    parts = [c["hook"].strip()]
    place = f"{dest}, {c['pais']}" if c.get("pais") and _slug(c["pais"]) not in _slug(dest) else dest
    parts.append(f"📍 {place}. {c.get('intro', '').strip()}".strip())
    days = [f"Día {i} – {d['titulo'].strip()}: {d['texto'].strip()}" for i, d in enumerate(c["dias"], 1)]
    if c.get("bonus"):
        days.append(f"Bonus – {c['bonus'].strip()}")
    parts.append("\n".join(days))
    info = []
    if c.get("dato"):
        info.append(f"¿Sabías que {c['dato'].strip().rstrip('.?')}?")
    if c.get("epoca"):
        info.append(f"Mejor época: {c['epoca'].strip().rstrip('.')}.")
    if info:
        parts.append("\n".join(info))
    if c.get("para") or c.get("no_para"):
        s = []
        if c.get("para"):
            s.append(f"Pa' ti si {c['para'].strip().rstrip('.')}.")
        if c.get("no_para"):
            s.append(f"Mejor no si {c['no_para'].strip().rstrip('.')}.")
        parts.append(" ".join(s))
    q = f"¿{dest} o {c['versus']}? Te leo en los comentarios. " if c.get("versus") else "¿Con quién irías? Te leo en los comentarios. "
    parts.append(q + "Guárdalo pa' tu próximo viaje ✈️")
    parts.append(SITE)
    tags = [t if t.startswith("#") else "#" + t for t in c.get("hashtags") or []] + FIXED_TAGS
    parts.append(" ".join(dict.fromkeys(t.lower() for t in tags)))
    text = "\n\n".join(parts)
    assert "pesos" not in text.lower() and "$" not in text, "the caption must not show the flight offer"
    return text[:2200]


if __name__ == "__main__":
    if sys.argv[1] == "find":
        for d in find(" ".join(sys.argv[2:])):
            print(json.dumps(d, ensure_ascii=False, indent=1))
    elif sys.argv[1] == "show":
        print(build(json.load(open(os.path.join(ROOT, "reels", sys.argv[2], "plan.json")))))
