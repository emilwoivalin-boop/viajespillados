"""Icons that pop in on key words, and procedural sound effects for reels (all original, no licences needed)."""
import math
import random
import struct
import wave

from PIL import Image, ImageDraw

DARK = (16, 24, 40, 255)
WHITE = (255, 255, 255, 255)
YELLOW = (255, 198, 49, 255)
CORAL = (255, 90, 78, 255)
BLUE = (80, 170, 220, 255)
SS = 2


# ---------------------------------------------------------------- icons
def _icon(kind, s):
    """Draw one icon of size s (px) on a transparent square image."""
    im = Image.new("RGBA", (s * SS, s * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c, r = s * SS / 2, s * SS * 0.30
    ow = max(3, int(s * SS * 0.035))
    if kind == "sun":
        for k in range(10):
            a = k * math.pi / 5
            d.line([(c + math.cos(a) * r * 1.25, c + math.sin(a) * r * 1.25),
                    (c + math.cos(a) * r * 1.6, c + math.sin(a) * r * 1.6)], fill=DARK, width=ow * 3)
            d.line([(c + math.cos(a) * r * 1.25, c + math.sin(a) * r * 1.25),
                    (c + math.cos(a) * r * 1.6, c + math.sin(a) * r * 1.6)], fill=YELLOW, width=ow * 2)
        d.ellipse([c - r, c - r, c + r, c + r], fill=YELLOW, outline=DARK, width=ow)
    elif kind == "heart":
        pts = [(c + 16 * math.sin(t) ** 3 * r / 16, c - (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t)
                - math.cos(4 * t)) * r / 16) for t in [k * 2 * math.pi / 60 for k in range(60)]]
        d.polygon(pts, fill=CORAL, outline=DARK, width=ow)
    elif kind == "sparkle":
        for (dx, dy, k) in [(0, 0, 1.0), (r * 0.9, -r * 0.8, 0.45), (-r * 0.9, r * 0.7, 0.35)]:
            rr = r * k * 1.3
            pts = []
            for j in range(8):
                a = j * math.pi / 4
                rad = rr if j % 2 == 0 else rr * 0.32
                pts.append((c + dx + math.cos(a) * rad, c + dy + math.sin(a) * rad))
            d.polygon(pts, fill=YELLOW, outline=DARK, width=ow)
    elif kind == "pin":
        d.polygon([(c - r * 0.8, c - r * 0.3), (c, c + r * 1.4), (c + r * 0.8, c - r * 0.3)], fill=CORAL, outline=DARK,
                  width=ow)
        d.ellipse([c - r * 0.85, c - r * 1.2, c + r * 0.85, c + r * 0.45], fill=CORAL, outline=DARK, width=ow)
        d.ellipse([c - r * 0.35, c - r * 0.75, c + r * 0.35, c - r * 0.05], fill=WHITE, outline=DARK, width=ow)
    elif kind == "plane":
        body = [(c - r * 1.4, c), (c + r * 1.2, c - r * 0.12), (c + r * 1.5, c), (c + r * 1.2, c + r * 0.12)]
        d.polygon(body, fill=WHITE, outline=DARK, width=ow)
        d.polygon([(c - r * 0.1, c - r * 0.05), (c - r * 0.6, c - r * 1.1), (c - r * 0.25, c - r * 1.1),
                   (c + r * 0.5, c - r * 0.05)], fill=BLUE, outline=DARK, width=ow)
        d.polygon([(c - r * 0.1, c + r * 0.05), (c - r * 0.6, c + r * 1.1), (c - r * 0.25, c + r * 1.1),
                   (c + r * 0.5, c + r * 0.05)], fill=BLUE, outline=DARK, width=ow)
        d.polygon([(c - r * 1.35, c), (c - r * 1.6, c - r * 0.55), (c - r * 1.3, c - r * 0.55), (c - r * 1.0, c)],
                  fill=BLUE, outline=DARK, width=ow)
    elif kind == "fish":
        d.ellipse([c - r * 1.1, c - r * 0.6, c + r * 0.8, c + r * 0.6], fill=YELLOW, outline=DARK, width=ow)
        d.polygon([(c + r * 0.6, c), (c + r * 1.4, c - r * 0.6), (c + r * 1.4, c + r * 0.6)], fill=YELLOW, outline=DARK,
                  width=ow)
        d.ellipse([c - r * 0.75, c - r * 0.2, c - r * 0.5, c + r * 0.05], fill=DARK)
    elif kind == "suitcase":
        d.rounded_rectangle([c - r, c - r * 0.55, c + r, c + r * 0.9], radius=int(r * 0.2), fill=YELLOW, outline=DARK,
                            width=ow)
        d.rounded_rectangle([c - r * 0.4, c - r * 0.95, c + r * 0.4, c - r * 0.5], radius=int(r * 0.15), outline=DARK,
                            width=ow)
    elif kind == "clock":
        d.ellipse([c - r * 1.2, c - r * 1.2, c + r * 1.2, c + r * 1.2], fill=WHITE, outline=DARK, width=ow * 2)
        for k in range(12):
            a = k * math.pi / 6
            d.line([(c + math.cos(a) * r * 0.95, c + math.sin(a) * r * 0.95),
                    (c + math.cos(a) * r * 1.08, c + math.sin(a) * r * 1.08)], fill=DARK, width=ow)
        d.line([(c, c), (c, c - r * 0.8)], fill=DARK, width=ow * 2)                 # 12
        d.line([(c, c), (c + r * 0.55, c + r * 0.32)], fill=CORAL, width=ow * 2)
        d.ellipse([c - ow * 1.5, c - ow * 1.5, c + ow * 1.5, c + ow * 1.5], fill=DARK)
    elif kind == "camera":
        d.rounded_rectangle([c - r * 1.3, c - r * 0.7, c + r * 1.3, c + r * 0.95], radius=int(r * 0.25), fill=BLUE,
                            outline=DARK, width=ow)
        d.rounded_rectangle([c - r * 0.5, c - r * 1.0, c + r * 0.3, c - r * 0.65], radius=int(r * 0.1), fill=BLUE,
                            outline=DARK, width=ow)
        d.ellipse([c - r * 0.6, c - r * 0.45, c + r * 0.6, c + r * 0.75], fill=WHITE, outline=DARK, width=ow)
        d.ellipse([c - r * 0.3, c - r * 0.15, c + r * 0.3, c + r * 0.45], fill=DARK)
        d.ellipse([c + r * 0.8, c - r * 0.5, c + r * 1.1, c - r * 0.25], fill=YELLOW, outline=DARK, width=ow)
    return im.resize((s, s), Image.LANCZOS)


_cache = {}


def icon_frame(kind, size, age):
    """Icon at a given age (seconds since it popped): scale 0 → 1.15 → 1, then a gentle bob."""
    if age < 0:
        return None, 0
    if age < 0.18:
        k = age / 0.18 * 1.15
    elif age < 0.3:
        k = 1.15 - (age - 0.18) / 0.12 * 0.15
    else:
        k = 1.0
    s = max(4, int(size * k))
    key = (kind, s)
    if key not in _cache:
        _cache[key] = _icon(kind, s)
    bob = math.sin(age * 2 * math.pi * 0.8) * size * 0.04 if age > 0.3 else 0
    return _cache[key], bob


def draw_pops(frame, pops, t, W, H):
    for pp in pops:
        im, bob = icon_frame(pp["icon"], int(pp.get("size", 150)), t - pp["t"])
        if im is None:
            continue
        x = int(pp.get("x", 0.8) * W - im.width / 2)
        y = int(pp.get("y", 0.4) * H - im.height / 2 + bob)
        frame.alpha_composite(im, (max(0, min(W - im.width, x)), max(0, min(H - im.height, y))))


# ---------------------------------------------------------------- sound effects
RATE = 44100


def _env(t, a, d):
    return min(1.0, t / a) * math.exp(-t * d) if a > 0 else math.exp(-t * d)


def _noise_lp(n, rnd, k):
    lp, out = 0.0, []
    for _ in range(n):
        lp += k * (rnd.uniform(-1, 1) - lp)
        out.append(lp)
    return out


def synth(kind, dur=None):
    rnd = random.Random(3)
    out = []
    if kind == "step":                      # soft footstep on pavement
        n = int(RATE * 0.09)
        lp = _noise_lp(n, rnd, 0.25)
        return [lp[i] * math.exp(-i / RATE * 60) * 2.5 + math.sin(2 * math.pi * 90 * i / RATE) * math.exp(-i / RATE * 50) * 0.5
                for i in range(n)]
    if kind == "rumble":                    # suitcase wheels rolling
        n = int(RATE * (dur or 2))
        lp = _noise_lp(n, rnd, 0.04)
        return [lp[i] * 3 * (0.75 + 0.25 * math.sin(2 * math.pi * 7 * i / RATE)) * min(1, i / RATE * 4, (n - i) / RATE * 4)
                for i in range(n)]
    if kind == "flyby":                     # jet passing high above
        n = int(RATE * (dur or 3))
        lp = _noise_lp(n, rnd, 0.06)
        return [lp[i] * 2.2 * math.sin(math.pi * i / n) ** 2 for i in range(n)]
    if kind == "waves":                     # gentle sea, slow swells
        n = int(RATE * (dur or 4))
        lp = _noise_lp(n, rnd, 0.05)
        return [lp[i] * 2.0 * (0.35 + 0.65 * math.sin(math.pi * ((i / RATE) % 3.2) / 3.2) ** 2)
                * min(1, i / RATE * 2, (n - i) / RATE * 2) for i in range(n)]
    if kind == "underwater":                # muffled deep ambience
        n = int(RATE * (dur or 4))
        lp = _noise_lp(n, rnd, 0.008)
        return [lp[i] * 8 * min(1, i / RATE * 2, (n - i) / RATE * 2) for i in range(n)]
    if kind == "crickets":                  # warm Caribbean night
        n = int(RATE * (dur or 4))
        for i in range(n):
            t = i / RATE
            g = 1.0 if (t * 3.1) % 1 < 0.35 and (t * 47) % 1 < 0.5 else 0.0
            out.append(math.sin(2 * math.pi * 4300 * t) * g * 0.25 * min(1, t * 2, (n - i) / RATE * 2))
        return out
    if kind == "coin":                      # cash-register ka-ching for the price
        n = int(RATE * 0.7)
        for i in range(n):
            t = i / RATE
            v = math.sin(2 * math.pi * 1975 * t) * math.exp(-t * 9)
            if t > 0.08:
                v += math.sin(2 * math.pi * 2637 * (t - 0.08)) * math.exp(-(t - 0.08) * 7)
            out.append(v * 0.5)
        return out
    if kind == "sparkle":                   # twinkle for a sticker
        n = int(RATE * 0.45)
        for i in range(n):
            t = i / RATE
            v = 0.0
            for f, st in ((2093, 0), (2637, 0.06), (3136, 0.12)):
                if t >= st:
                    v += math.sin(2 * math.pi * f * (t - st)) * math.exp(-(t - st) * 14) * 0.35
            out.append(v)
        return out
    if kind == "pop":
        n = int(RATE * 0.14)
        for i in range(n):
            t = i / RATE
            out.append(math.sin(2 * math.pi * (420 + 1400 * t) * t) * math.exp(-t * 32))
    elif kind == "whoosh":
        n = int(RATE * 0.38)
        lp = 0.0
        for i in range(n):
            t = i / RATE
            a = 0.02 + 0.25 * math.sin(math.pi * t / 0.38)
            lp += a * (rnd.uniform(-1, 1) - lp)
            out.append(lp * math.sin(math.pi * t / 0.38) * 2.2)
    elif kind == "chime":
        n = int(RATE * 1.1)
        for i in range(n):
            t = i / RATE
            v = 0.0
            for f, st in ((1046.5, 0), (1318.5, 0.09), (1568, 0.18)):
                if t >= st:
                    v += math.sin(2 * math.pi * f * (t - st)) * math.exp(-(t - st) * 4.5) * 0.45
            out.append(v)
    elif kind == "shutter":
        n = int(RATE * 0.12)
        for i in range(n):
            t = i / RATE
            v = rnd.uniform(-1, 1) * (math.exp(-t * 90) + (math.exp(-(t - 0.06) * 110) if t > 0.06 else 0))
            out.append(v * 0.8)
    elif kind == "bubbles":
        n = int(RATE * 0.6)
        out = [0.0] * n
        for b in range(5):
            st = b * 0.11 + rnd.uniform(0, 0.03)
            f0 = rnd.uniform(500, 900)
            for i in range(int(RATE * 0.08)):
                t = i / RATE
                j = int((st + t) * RATE)
                if j < n:
                    out[j] += math.sin(2 * math.pi * (f0 + 3000 * t) * t) * math.exp(-t * 45) * 0.6
    elif kind == "boing":
        n = int(RATE * 0.35)
        for i in range(n):
            t = i / RATE
            out.append(math.sin(2 * math.pi * (180 + 260 * math.sin(t * 18) * math.exp(-t * 6)) * t) * math.exp(-t * 7))
    elif kind == "engine":
        n = int(RATE * 1.2)
        for i in range(n):
            t = i / RATE
            out.append((math.sin(2 * math.pi * 55 * t) + 0.5 * math.sin(2 * math.pi * 110 * t)) *
                       (0.6 + 0.4 * math.sin(2 * math.pi * 9 * t)) * 0.35 * min(1, t * 8) * min(1, (1.2 - t) * 6))
    return out


def write_track(events, total, path):
    """events: list of (time, kind, gain). Writes a stereo 16-bit WAV of length total seconds."""
    n = int(total * RATE) + 1
    buf = [0.0] * n
    cache = {}
    for ev in events:
        t0, kind, gain = ev[:3]
        dur = ev[3] if len(ev) > 3 else None
        key = (kind, dur)
        if key not in cache:
            cache[key] = synth(kind, dur)
        s = cache[key]
        j0 = int(t0 * RATE)
        for i, v in enumerate(s):
            j = j0 + i
            if 0 <= j < n:
                buf[j] += v * gain
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        frames = bytearray()
        for v in buf:
            v = max(-1.0, min(1.0, v))
            iv = int(v * 32000)
            frames += struct.pack("<hh", iv, iv)
        w.writeframes(bytes(frames))
