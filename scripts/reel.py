#!/usr/bin/env python3
"""
Viajes Pillados – short vertical Reels (1080x1920) from a storyboard.

  reels/<id>/storyboard.json  → reels/<id>/reel.mp4 (+ cover.jpg, caption.txt)

The script (voice-over text) and the choice of footage are written in the storyboard.
The voice is generated with Microsoft Edge neural TTS (edge-tts), subtitles are burned in,
and a banner with the deal (destination + price) stays on screen the whole time.

storyboard.json:
{
  "id": "aruba-puente-mayo",
  "voice": "es-CO-SalomeNeural",
  "banner": {"title": "Aruba", "price": "$645.976", "detail": "ida y vuelta · 29 abr – 2 may"},
  "scenes": [
     {"text": "...", "media": {"type": "video", "pexels_id": 34467289}},
     {"text": "...", "media": {"type": "photo", "url": "https://commons.../Special:FilePath/X.jpg",
                               "credit": "Autor / Wikimedia Commons, CC BY 2.0"}}
  ],
  "end": {"line1": "Vuelos desde $645.976", "line2": "ida y vuelta · link en la bio"},
  "caption": "..."
}

Usage: python scripts/reel.py render <id>      (render only)
       python scripts/reel.py publish <id>     (render if needed + publish as Reel)
"""
import asyncio, json, os, re, subprocess, sys, time

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instagram as ig  # noqa: E402  (fonts, git helpers, Instagram API helpers)
import stickman  # noqa: E402
import reelfx  # noqa: E402

W, H, FPS = 1080, 1920, 30
YELLOW = (255, 198, 49)
NAVY = (20, 34, 59)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36 ViajesPilladosBot/1.0 (+https://viajespillados.com)"}
WUA = {"User-Agent": "ViajesPilladosBot/1.0 (https://viajespillados.com; reels)"}


def sh(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ---------------------------------------------------------------- voice
async def _tts(text, voice, mp3, rate):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append((chunk["offset"] / 1e7, (chunk["offset"] + chunk["duration"]) / 1e7, chunk["text"]))
    return words


def tts(text, voice, mp3, rate="+15%"):
    text = text.replace("…", "...")
    for attempt in range(8):   # the free Edge TTS service sometimes returns no audio: retry, waiting longer each time
        try:
            return asyncio.run(_tts(text, voice, mp3, rate))
        except Exception as e:
            if attempt == 7:
                raise
            print(f"TTS reintento {attempt + 1}: {e}")
            time.sleep(10 * (attempt + 1))


def tight_voice(text, voice, mp3, rate):
    """TTS + cut the silence before the first and after the last word (no gaps between scenes).
    Full stops inside a scene become commas so the voice doesn't pause between sentences.
    Returns (wav path, duration, word timings relative to the trimmed audio)."""
    spoken = text.strip()
    if os.environ.get("REEL_MERGE_SENTENCES") == "1":   # optional: no pauses inside a scene
        spoken = re.sub(r"([.!…])\s+(?=\S)", ", ", spoken)
    words = tts(spoken, voice, mp3, rate)
    full = duration(mp3)
    if words:
        s0 = max(0.0, words[0][0] - 0.03)
        e0 = min(full, words[-1][1] + 0.07)
    else:
        s0, e0 = 0.0, full
    wav = mp3.replace(".mp3", ".wav")
    sh("ffmpeg", "-y", "-i", mp3, "-af", f"atrim={s0:.3f}:{e0:.3f},asetpts=PTS-STARTPTS", "-ar", "44100", "-ac", "2", wav)
    return wav, e0 - s0, [(a - s0, b - s0, w) for a, b, w in words]


# ---------------------------------------------------------------- footage
def pexels_file(pid, dst):
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    url = None
    if key:
        j = requests.get(f"https://api.pexels.com/videos/videos/{pid}", headers={"Authorization": key},
                         timeout=30).json()
        files = [f for f in j.get("video_files", []) if f.get("height") and f["height"] >= 1280
                 and f.get("file_type") == "video/mp4"]
        files.sort(key=lambda f: abs(f["height"] - 1920))
        if files:
            url = files[0]["link"]
    if not url:
        url = f"https://www.pexels.com/download/video/{pid}/"
    r = requests.get(url, headers=UA, timeout=180, allow_redirects=True)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("video"):
        raise RuntimeError(f"Pexels {pid}: no video ({r.headers.get('content-type')})")
    with open(dst, "wb") as f:
        f.write(r.content)
    return dst


def photo_file(url, dst):
    r = requests.get(re.sub(r"width=\d+", "width=2160", url), headers=WUA, timeout=120)
    r.raise_for_status()
    im = ImageOps.exif_transpose(Image.open(__import__("io").BytesIO(r.content))).convert("RGB")
    im.save(dst, "JPEG", quality=92)
    return dst


def ai_image(prompt, dst, seed=7, ref=None):
    """Generate a vertical illustration. Uses OpenAI (OPENAI_API_KEY) when available, otherwise the free
    Pollinations (Flux) API. The result is cached next to the storyboard so re-renders don't regenerate it."""
    import hashlib
    import urllib.parse
    key = hashlib.sha1(f"{prompt}|{seed}|{ref}".encode()).hexdigest()[:12]
    cache = dst.rsplit(".", 1)[0] + f"-{key}.jpg"
    if os.path.exists(cache):
        return cache
    for old in [f for f in os.listdir(os.path.dirname(dst)) if f.startswith(os.path.basename(dst).rsplit(".", 1)[0] + "-")]:
        os.remove(os.path.join(os.path.dirname(dst), old))
    import base64
    data = None
    ref_bytes = None
    if ref:
        rr = requests.get(ref, headers=WUA, timeout=120)
        rr.raise_for_status()
        im0 = ImageOps.exif_transpose(Image.open(__import__("io").BytesIO(rr.content))).convert("RGB")
        im0.thumbnail((1536, 1536))
        buf = __import__("io").BytesIO()
        im0.save(buf, "PNG")
        ref_bytes = buf.getvalue()
    if os.environ.get("GEMINI_API_KEY"):
        parts = [{"text": prompt + ". Vertical 9:16 image."}]
        if ref_bytes:
            parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(ref_bytes).decode()}})
        model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          params={"key": os.environ["GEMINI_API_KEY"]}, timeout=300,
                          json={"contents": [{"parts": parts}],
                                "generationConfig": {"responseModalities": ["IMAGE"],
                                                     "imageConfig": {"aspectRatio": "9:16"}}})
        r.raise_for_status()
        for part in r.json()["candidates"][0]["content"]["parts"]:
            blob = part.get("inline_data") or part.get("inlineData")
            if blob:
                data = base64.b64decode(blob["data"])
                break
        if data is None:
            raise RuntimeError(f"Gemini no devolvió imagen: {str(r.json())[:300]}")
    elif os.environ.get("OPENAI_API_KEY"):
        hdr = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
        if ref_bytes:
            r = requests.post("https://api.openai.com/v1/images/edits", headers=hdr, timeout=300,
                              files={"image": ("ref.png", ref_bytes, "image/png")},
                              data={"model": "gpt-image-1", "prompt": prompt, "size": "1024x1536", "quality": "medium"})
        else:
            r = requests.post("https://api.openai.com/v1/images/generations", headers=hdr, timeout=300,
                              json={"model": "gpt-image-1", "prompt": prompt, "size": "1024x1536", "quality": "medium"})
        r.raise_for_status()
        data = base64.b64decode(r.json()["data"][0]["b64_json"])
    else:
        # free fallback: text-to-image only (no reference photo), lower quality
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) +
               f"?width=1080&height=1920&seed={seed}&nologo=true&private=true&model=flux")
        for attempt in range(4):
            r = requests.get(url, headers=WUA, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                data = r.content
                break
            print(f"Imagen IA: HTTP {r.status_code}, reintento {attempt + 1}")
            time.sleep(20)
        if data is None:
            raise RuntimeError("No se pudo generar la imagen con IA")
        time.sleep(16)  # anonymous rate limit: one image every 15 s
    im = Image.open(__import__("io").BytesIO(data)).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, int(h * 0.95)))  # drop the bottom strip (possible watermark)
    im = ImageOps.fit(im, (1080, 1920), Image.LANCZOS)
    im.save(cache, "JPEG", quality=92)
    return cache


def media_file(m, sb, base, work, name, i):
    """Return a local image for a photo/ai media spec."""
    if m["type"] == "file":   # image stored in the repo (e.g. illustrations made by the owner)
        return os.path.join(ROOT, m["path"])
    if m["type"] == "ai":
        os.makedirs(os.path.join(base, "ai"), exist_ok=True)
        prompt = m["prompt"] + (", " + sb["ai_style"] if sb.get("ai_style") else "")
        return ai_image(prompt, os.path.join(base, "ai", f"{name}.jpg"), seed=m.get("seed", sb.get("seed", 7)),
                        ref=m.get("ref"))
    return photo_file(m["url"], os.path.join(work, f"{name}.jpg"))


def clip_from_video(src, dur, out):
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"eq=saturation=1.08,format=yuv420p")
    sh("ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.2f}", "-vf", vf, "-an",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out)


def clip_from_photo(src, dur, out, zoom_in=True, focus=0.5):
    frames = int(dur * FPS) + 1
    z = f"min(1+0.20*on/{frames},1.20)" if zoom_in else f"max(1.20-0.20*on/{frames},1.0)"
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
          f"crop={W*2}:{H*2}:(iw-{W*2})*{focus}:(ih-{H*2})/2,"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
          f"format=yuv420p")
    sh("ffmpeg", "-y", "-loop", "1", "-i", src, "-t", f"{dur:.2f}", "-vf", vf,
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out)


def photo_scene(src, dur, out, st=None, pops=None, zoom_in=True, focus=0.5, zoom=0.10, tag=None, crowd=None):
    """Render a picture scene in Python so the stick man lives *inside* the picture: he is drawn onto the
    illustration first and the gentle camera move (eased zoom) is applied to both, so he never slides
    against the background. Icon pops are drawn afterwards, in screen space."""
    st = st or {"action": "none"}
    pops = pops or []
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    k = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    ox, oy = int((img.width - W) * focus), (img.height - H) // 2
    base = img.crop((ox, oy, ox + W, oy + H)).convert("RGBA")

    tag_img = tag_png(tag) if tag else None
    n = int(dur * FPS) + 2
    has_main = bool(st.get("beats")) or st.get("action", "none") != "none"
    gen = figure_frames(st, n, patch=True)
    extra = [figure_frames({"action": "wave", **c}, n, patch=True) for c in (crowd or [])]
    # zoom centre: keep the stick man's area in view
    sx = (st.get("x0", 0.5) + st.get("x1", st.get("x0", 0.5))) / 2 if has_main else 0.5
    sx = min(0.85, max(0.15, sx))
    cx0, cy0 = W * (0.5 + (sx - 0.5) * 0.35), H * (0.5 + (st.get("y", 0.5) - 0.5) * 0.35)
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i, band in enumerate(gen):
        q = stickman.smooth(i / max(1, n - 1))
        z = 1 + zoom * (q if zoom_in else 1 - q)
        fr = base.copy()
        for g in extra:                          # other people in the scene (drawn behind the main figure)
            pt = next(g, None)
            if pt:
                fr.alpha_composite(pt[0], pt[1])
        if has_main and band:
            fr.alpha_composite(band[0], band[1])
        bw, bh = W / z, H / z
        x0 = min(max(cx0 - bw / 2, 0), W - bw)
        y0 = min(max(cy0 - bh / 2, 0), H - bh)
        fr = fr.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))
        if pops:
            reelfx.draw_pops(fr, pops, i / FPS, W, H)
        if tag_img is not None:
            fr.alpha_composite(tag_img)
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg photo scene failed")


def add_stickman(clip, st, dur, out, pops=None):
    """Overlay the animated stick man (st = {"action", "x0", "x1", "y", "size", "facing"}) and any icon pops
    (pops = [{"icon", "t" (scene seconds), "x", "y", "size"}]) on a clip."""
    st = st or {"action": "none"}
    pops = pops or []
    band_h, feet_local = 700, 600
    feet_abs = int(st.get("y", 0.70) * H)
    by = max(0, min(H - band_h, feet_abs - feet_local))
    full = bool(pops)                      # icons can be anywhere, so use a full-frame overlay
    oh, oy = (H, 0) if full else (band_h, by)
    n = int(dur * FPS) + 3
    cmd = ["ffmpeg", "-y", "-i", clip, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{oh}",
           "-r", str(FPS), "-i", "-", "-filter_complex", f"[0:v][1:v]overlay=0:{oy},format=yuv420p",
           "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    gen = stickman.frames(st.get("action", "walk"), n, FPS, x0=st.get("x0", 0.3), x1=st.get("x1", 0.6),
                          feet=feet_local + (feet_abs - by - feet_local), size=st.get("size", 330),
                          facing=st.get("facing", 1), band_h=band_h)
    for i, fr in enumerate(gen):
        if full:
            big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            big.paste(fr, (0, by))
            reelfx.draw_pops(big, pops, i / FPS, W, H)
            fr = big
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg stickman overlay failed")


def resolve_beats(st, words, dur):
    """Give each beat of a figure ({"beats": [...]}) its start time "t" (scene seconds): from the spoken word
    ("word"), seconds ("at") or a fraction of the scene ("frac"). Beats without one are spread evenly."""
    beats = (st or {}).get("beats")
    if not beats:
        return
    last = 0.0
    for k, b in enumerate(beats):
        default = dur * k / len(beats)
        if k == 0:
            t = 0.0
        elif b.get("word"):
            t = word_time(words, b["word"], default) - b.get("lead", 0.15)
        elif "at" in b:
            t = b["at"]
        elif "frac" in b:
            t = b["frac"] * dur
        else:
            t = default
        t = min(max(t, last + 0.3 if k else 0.0), max(0.0, dur - 0.3))
        b["t"] = round(t, 3)
        last = t


def figure_frames(st, n, patch=False):
    """Frames of one stick figure for a scene: a single move, or a sequence of "beats" (each with its own move
    and position; a beat starts where the previous one ended unless it says otherwise)."""
    st = st or {}
    beats = st.get("beats")
    if not beats:
        yield from stickman.frames(st.get("action", "none"), n, FPS, x0=st.get("x0", 0.3),
                                   x1=st.get("x1", st.get("x0", 0.3)), feet=int(st.get("y", 0.7) * H),
                                   feet1=int(st.get("y1", st.get("y", 0.7)) * H), size=st.get("size", 330),
                                   size1=st.get("size1"), facing=st.get("facing", 1), band_h=H,
                                   speed=st.get("speed", 1.0), look=st.get("look", "hero"), mood=st.get("mood"),
                                   patch=patch)
        return
    cx, cy, cs, cf = st.get("x0", 0.5), st.get("y", 0.8), st.get("size", 330), st.get("facing", 1)
    starts = [int(b.get("t", 0) * FPS) for b in beats] + [n]
    starts[0] = 0
    for k, b in enumerate(beats):
        seg = max(1, starts[k + 1] - starts[k])
        x0 = b.get("x0", cx)
        x1 = b.get("x1", x0)
        y0 = b.get("y", cy)
        y1 = b.get("y1", y0)
        s0 = b.get("size", cs)
        s1 = b.get("size1", s0)
        f = b.get("facing", cf)
        yield from stickman.frames(b.get("action", "stand"), seg, FPS, x0=x0, x1=x1, feet=int(y0 * H),
                                   feet1=int(y1 * H), size=s0, size1=s1 if s1 != s0 else None, facing=f, band_h=H,
                                   speed=b.get("speed", st.get("speed", 1.0)), look=b.get("look", st.get("look", "hero")),
                                   mood=b.get("mood"), patch=patch)
        cx, cy, cs, cf = x1, y1, s1, f


def word_time(words, word, default):
    """Start time (scene seconds) of the first spoken word that matches `word`."""
    key = re.sub(r"[^a-z0-9áéíóúñ]", "", word.lower())
    for w in words:
        if re.sub(r"[^a-z0-9áéíóúñ]", "", w[2].lower()).startswith(key):
            return w[0]
    return default


def scene_sfx(sc, t0, dur, pops):
    """Sound effects that match what happens on screen in a scene (times are reel seconds)."""
    ev = []
    if t0 > 0:
        ev.append((max(0, t0 - 0.12), "whoosh", 0.22))
    for pp in pops:
        ev.append((t0 + pp["t"], "pop", 0.28))
    for amb in sc.get("ambience", []):           # background sound that matches the picture
        g = {"waves": 0.10, "underwater": 0.12, "crickets": 0.06, "flyby": 0.14, "birds": 0.07,
             "steeldrum": 0.05}.get(amb, 0.1)
        ev.append((t0, amb, g, round(dur, 2)))
    for e in sc.get("sfx", []):                  # one-off sounds placed by hand: {"kind", "at" (s), "gain"}
        at = e["frac"] * dur if "frac" in e else e.get("at", 0)
        if at < dur:
            ev.append((t0 + at, e["kind"], e.get("gain", 0.25)))
    st = sc.get("stick") or {}
    beats = st.get("beats") or []
    BEAT_SFX = {"photo": [(0.3, "shutter", 0.32)], "selfie": [(0.4, "shutter", 0.32)], "celebrate": [(0.15, "boing", 0.2)],
                "scared": [(0.0, "whoosh", 0.22), (0.05, "boing", 0.18)], "run": [(0.0, "whoosh", 0.2)],
                "laugh": [(0.1, "boing", 0.14)], "sip": [(0.6, "bubbles", 0.14)], "kayak": [(0.4, "bubbles", 0.16)],
                "parachute": [(0.0, "whoosh", 0.2), ("land", "boing", 0.22)], "dive": [("dive", "splash", 0.32)]}
    for k, b in enumerate(beats):
        b0 = b.get("t", 0.0)
        b1 = beats[k + 1].get("t", dur) if k + 1 < len(beats) else dur
        for when, kind, g in BEAT_SFX.get(b.get("action", ""), []):
            off = {"land": 0.55 * (b1 - b0), "dive": 0.42 * (b1 - b0)}.get(when, when)
            ev.append((t0 + b0 + off, kind, g))
    act = st.get("action", "none") if not beats else "beats"
    if act in ("walk", "suitcase") and sc.get("steps", False):
        n = int(dur * FPS) + 2
        y0, y1 = st.get("y", 0.7) * H, st.get("y1", st.get("y", 0.7)) * H
        steps = stickman.step_times(n, FPS, st.get("x0", 0.3), st.get("x1", st.get("x0", 0.3)), st.get("size", 330),
                                    y0, y1)
        for k, s_ in enumerate(steps):
            ev.append((t0 + s_, "step", 0.16 if k % 2 else 0.13))
        if act == "suitcase" and len(steps) > 1:
            ev.append((t0 + steps[0], "rumble", 0.05, round(steps[-1] - steps[0] + 0.3, 2)))
    if act == "dive":                            # the splash always lands with him
        ev += [(t0 + dur * 0.40, "whoosh", 0.18), (t0 + dur * 0.42, "splash", 0.32)]
    if act == "wade" and sc.get("steps", False):
        ev = [e for e in ev if e[1] != "step"]
    if not sc.get("action_sfx", True):           # max one extra sound per picture (ambience wins)
        return ev
    if act == "celebrate":
        ev.append((t0 + 0.15, "boing", 0.22))
    elif act == "photo":
        k = 0
        while k * 1.6 < dur - 0.2:
            ev.append((t0 + k * 1.6, "shutter", 0.35))
            k += 1
    elif act == "swim":
        ev += [(t0 + 0.3, "bubbles", 0.22), (t0 + dur * 0.55, "bubbles", 0.18)]
    elif act == "drive":
        ev += [(t0 + 0.1, "engine", 0.16), (t0 + 1.25, "engine", 0.13), (t0 + 2.4, "engine", 0.10)]
    return ev


# ---------------------------------------------------------------- overlays
def banner_png(b, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # top shade for readability
    shade = Image.new("L", (1, 420))
    for y in range(420):
        shade.putpixel((0, y), int(170 * (1 - y / 420) ** 1.6))
    img.paste(Image.new("RGBA", (W, 420), (10, 18, 34, 255)), (0, 0), shade.resize((W, 420)))
    # bottom shade for subtitles
    shade2 = Image.new("L", (1, 700))
    for y in range(700):
        shade2.putpixel((0, y), int(185 * (y / 700) ** 1.4))
    img.paste(Image.new("RGBA", (W, 700), (10, 18, 34, 255)), (0, H - 700), shade2.resize((W, 700)))
    d = ImageDraw.Draw(img)
    if b.get("logo", True):
        logo = Image.open(os.path.join(ROOT, "logo-icon.png")).convert("RGBA").resize((76, 76), Image.LANCZOS)
        img.alpha_composite(logo, (60, 150))
        d.text((152, 188), "viajespillados", font=ig.font("ExtraBold", 38), fill="white", anchor="lm")
    if b.get("title"):
        d.text((W // 2, 300), b["title"], font=ig.font("Black", 92), fill="white", anchor="mm")
    y = 380
    if b.get("price"):  # optional: price can be kept for the end card only
        fp = ig.font("Black", 64)
        tw = d.textlength(b["price"], font=fp)
        d.rounded_rectangle([W // 2 - tw / 2 - 34, 360, W // 2 + tw / 2 + 34, 448], radius=44, fill=YELLOW)
        d.text((W // 2, 404), b["price"], font=fp, fill=NAVY, anchor="mm")
        y = 492
    if b.get("detail"):
        d.text((W // 2, y), b["detail"], font=ig.font("Bold", 40), fill="white", anchor="mm")
    img.save(path)


def intro_png(it, path):
    """Opening tag with the departure date and time (shown during the first seconds)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fk, fl, fs = ig.font("Bold", 38), ig.font("Black", 68), ig.font("SemiBold", 40)
    tw = max(d.textlength(it.get("line", ""), font=fl), d.textlength(it.get("sub", ""), font=fs)) + 120
    x0, x1, y0 = W // 2 - tw / 2 - 40, W // 2 + tw / 2 + 40, 330
    d.rounded_rectangle([x0, y0, x1, y0 + 250], radius=44, fill=(10, 18, 34, 225), outline=YELLOW, width=5)
    plane = reelfx._icon("plane", 104)
    img.alpha_composite(plane, (int(x0 + 26), y0 + 14))
    d.text((x0 + 140, y0 + 66), it.get("kicker", "DEPARTURE").upper(), font=fk, fill=YELLOW, anchor="lm")
    d.text((W // 2 + 30, y0 + 140), it.get("line", ""), font=fl, fill="white", anchor="mm")
    if it.get("sub"):
        d.text((W // 2 + 30, y0 + 208), it["sub"], font=fs, fill=(220, 228, 240), anchor="mm")
    img.save(path)


def end_png(e, path):
    """End card: the reveal (trip, airline, price, flight times) and the call to action."""
    img = Image.new("RGBA", (W, H), (10, 18, 34, 225))
    d = ImageDraw.Draw(img)
    logo = Image.open(os.path.join(ROOT, "logo-icon.png")).convert("RGBA").resize((150, 150), Image.LANCZOS)
    img.alpha_composite(logo, (W // 2 - 75, 300))
    y = 560
    if e.get("title"):
        fs = 100                                  # shrink long titles ("7 días en Santiago de Chile") to fit the frame
        while fs > 56 and d.textlength(e["title"], font=ig.font("Black", fs)) > W - 90:
            fs -= 4
        d.text((W // 2, y), e["title"], font=ig.font("Black", fs), fill="white", anchor="mm"); y += 110
    if e.get("kicker"):
        d.text((W // 2, y), e["kicker"], font=ig.font("Bold", 50), fill="white", anchor="mm"); y += 90
    if e.get("airline"):
        fs = 58                                  # shrink long lines (e.g. "escala larga en …") to fit the frame
        while fs > 34 and d.textlength(e["airline"], font=ig.font("Bold", fs)) > W - 100:
            fs -= 2
        d.text((W // 2, y), e["airline"], font=ig.font("Bold", fs), fill=(220, 228, 240), anchor="mm"); y += 160
    if e.get("price"):
        fp = ig.font("Black", 120)
        tw = d.textlength(e["price"], font=fp)
        d.rounded_rectangle([W // 2 - tw / 2 - 50, y - 85, W // 2 + tw / 2 + 50, y + 85], radius=85, fill=YELLOW)
        d.text((W // 2, y), e["price"], font=fp, fill=NAVY, anchor="mm"); y += 140
    if e.get("detail"):
        d.text((W // 2, y), e["detail"], font=ig.font("Bold", 46), fill="white", anchor="mm"); y += 90
    for label, val in e.get("times", []):
        fl, fv = ig.font("Bold", 44), ig.font("SemiBold", 44)
        lw_, vw = d.textlength(label + "  ", font=fl), d.textlength(val, font=fv)
        x = W // 2 - (lw_ + vw) / 2
        d.text((x, y), label + "  ", font=fl, fill=YELLOW, anchor="lm")
        d.text((x + lw_, y), val, font=fv, fill="white", anchor="lm"); y += 68
    y += 90
    cta = e.get("cta", "viajespillados.com")
    if cta:                                   # fact Reels: no website pill (owner's rule)
        fc = ig.font("Black", 56)
        tw = d.textlength(cta, font=fc)
        d.rounded_rectangle([W // 2 - tw / 2 - 46, y - 58, W // 2 + tw / 2 + 46, y + 58], radius=58, fill="white")
        d.text((W // 2, y), cta, font=fc, fill=NAVY, anchor="mm"); y += 110
    if e.get("small"):
        d.text((W // 2, y), e["small"], font=ig.font("SemiBold", 42), fill="white", anchor="mm")
    img.save(path)


def tag_png(text, y=250):
    """Small yellow chip at the top (e.g. "DÍA 1"), above the captions."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ig.font("Black", 50)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([W / 2 - tw / 2 - 34, y - 42, W / 2 + tw / 2 + 34, y + 42], radius=42, fill=YELLOW)
    d.text((W // 2, y), text, font=f, fill=NAVY, anchor="mm")
    return img


def outro_png(o, path):
    """Low-key sign-off: small logo + site name near the bottom (Spanish travel plans only)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ig.font("Bold", 38)
    text = o.get("text", "viajespillados.com")
    tw = d.textlength(text, font=f)
    x = W // 2 - (64 + 14 + tw) / 2
    y = H - o.get("bottom", 170)
    d.rounded_rectangle([x - 22, y - 46, x + 64 + 14 + tw + 22, y + 46], radius=46, fill=(10, 18, 34, 150))
    logo = Image.open(os.path.join(ROOT, "logo-icon.png")).convert("RGBA").resize((64, 64), Image.LANCZOS)
    img.alpha_composite(logo, (int(x), int(y - 32)))
    d.text((x + 64 + 14, y), text, font=f, fill="white", anchor="lm")
    img.save(path)


def ass_time(t):
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def subtitles(chunks, path, margin_v=300, align=2):
    """chunks: list of (start, end, text). Big bold captions, lower third."""
    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Sub,Inter Display Black,74,&H00FFFFFF,&H00FFFFFF,&H00221410,&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"5,2,{align},80,80,{margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n")
    with open(path, "w") as f:
        f.write(head)
        for s, e, t in chunks:
            t = t.replace("{", "(").replace("}", ")")
            f.write(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Sub,,0,0,0,,{t}\n")


def attach_punctuation(words, text):
    """edge-tts word boundaries drop punctuation; take the display form from the original text."""
    toks = text.split()
    out, j = [], 0
    norm = lambda w: re.sub(r"[^\wáéíóúüñ]", "", w.lower())
    for s, e, w in words:
        k = j
        while k < len(toks) and norm(toks[k]) != norm(w) and not norm(toks[k]).startswith(norm(w)):
            k += 1
        if k < len(toks):
            n = max(1, len(w.split()))          # a boundary can cover several words ("April 29")
            out.append((s, e, " ".join(toks[k:k + n])))
            j = k + n
        else:
            out.append((s, e, w))
    return out


STOP = {"a", "an", "the", "to", "of", "in", "on", "at", "and", "for", "with", "your", "our", "over", "under",
        "de", "la", "el", "en", "y", "con", "por", "para", "los", "las", "un", "una", "tu"}


def chunk_words(words, offset, max_words=3, max_chars=18):
    """Group spoken words into short captions; never leave a chunk hanging on 'the', 'to', 'and'…"""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        text = " ".join(x[2] for x in cur)
        last = re.sub(r"[^a-záéíóúñ]", "", w[2].lower())
        punct = re.search(r"[.,:;!?]$", w[2])
        full = len(cur) >= max_words or len(text) >= max_chars
        if punct or (full and (last not in STOP or len(cur) >= max_words + 1) and i + 1 < len(words)):
            out.append((offset + cur[0][0], offset + cur[-1][1] + 0.08, text))
            cur = []
    if cur:
        out.append((offset + cur[0][0], offset + cur[-1][1] + 0.08, " ".join(x[2] for x in cur)))
    # make chunks continuous so captions don't flicker
    for i in range(len(out) - 1):          # each caption ends exactly when the next one starts
        s, e, t = out[i]
        out[i] = (s, out[i + 1][0], t)
    return out


# ---------------------------------------------------------------- render
def render(rid, folder="reels", sb_file="storyboard.json", out_file="reel.mp4"):
    base = os.path.join(ROOT, folder, rid)
    sb = json.load(open(os.path.join(base, sb_file)))
    work = os.path.join("/tmp", "reel-" + rid + "-" + sb_file.replace(".json", ""))
    os.makedirs(work, exist_ok=True)
    voice = sb.get("voice", "es-CO-SalomeNeural")
    rate = sb.get("rate", "+28%")
    pad = sb.get("pad", 0.0)
    stickman.STYLE = sb.get("stick_style", "classic")   # "classic" or "pop" (red beanie, yellow t-shirt)

    clips, audios, subs, sfx, t = [], [], [], [], 0.0
    for i, sc in enumerate(sb["scenes"]):
        mp3 = os.path.join(work, f"v{i}.mp3")
        wav, vdur, words = tight_voice(sc["text"], voice, mp3, rate)
        dur = vdur + pad + sc.get("hold", 0.0)   # "hold": extra seconds on the picture after the line
        subs += chunk_words(attach_punctuation(words, sc["text"]), t)
        pops = []
        for k, pp in enumerate(sc.get("pops", [])):
            pt = word_time(words, pp["word"], dur * (k + 1) / 3) if pp.get("word") else pp.get("at", 0.5) * dur
            pops.append({**pp, "t": pt})
        for fig in [sc.get("stick")] + list(sc.get("crowd") or []):
            resolve_beats(fig, words, dur)
        sfx += scene_sfx(sc, t, dur, pops)
        audios.append((wav, dur))
        m = sc["media"]
        out = os.path.join(work, f"c{i}.mp4")
        in_photo = False
        try:
            if m["type"] == "video":
                clip_from_video(pexels_file(m["pexels_id"], os.path.join(work, f"s{i}.mp4")), dur, out)
            else:
                photo_scene(media_file(m, sb, base, work, f"scene{i}", i), dur, out, sc.get("stick"), pops,
                            i % 2 == 0, m.get("focus", 0.5), sb.get("zoom", 0.10), sc.get("tag"),
                            crowd=sc.get("crowd"))
                in_photo = True
        except Exception as e:
            fb = m.get("fallback_photo") or sb.get("fallback_photo")
            print(f"Escena {i}: {e} – uso la foto de respaldo")
            clip_from_photo(photo_file(fb, os.path.join(work, f"s{i}.jpg")), dur, out, i % 2 == 0)
        if not in_photo and (pops or (sc.get("stick") and sc["stick"].get("action", "none") != "none")):
            out2 = os.path.join(work, f"c{i}s.mp4")
            add_stickman(out, sc.get("stick"), dur, out2, pops)
            out = out2
        clips.append(out)
        t += dur

    # end card: reveal + call to action, optionally with its own voice line (travel plans have none)
    end = sb.get("end") or {}
    has_end = bool(end)
    end_audio = None
    if not has_end:
        end_dur = 0.0
    elif end.get("text"):
        end_audio = os.path.join(work, "vend.mp3")
        end_audio, edur, end_words = tight_voice(end["text"], voice, end_audio, rate)
        end["coin_at"] = word_time(end_words, "645", 1.4)
        end_dur = edur + 0.35                  # owner: stop right after "viajespillados punto com"
    else:
        end_dur = 3.0
    if has_end:
        end_bg = os.path.join(work, "end_bg.mp4")
        end_media = end.get("media") or {"type": "photo", "url": sb.get("fallback_photo")}
        end_media.setdefault("type", "photo")
        try:
            clip_from_photo(media_file(end_media, sb, base, work, "end", -1), end_dur, end_bg, True,
                            end_media.get("focus", 0.5))
        except Exception:
            sh("ffmpeg", "-y", "-sseof", "-0.1", "-i", clips[-1], "-vf",
               f"tpad=stop_mode=clone:stop_duration={end_dur}", "-t", f"{end_dur}", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", end_bg)
        clips.append(end_bg)

    with open(os.path.join(work, "clips.txt"), "w") as f:
        f.writelines(f"file '{c}'\n" for c in clips)
    video = os.path.join(work, "video.mp4")
    sh("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "clips.txt"), "-c", "copy", video)

    # voice track with silence padding per scene + end
    parts = []
    for wav, dur in audios:
        p = wav.replace(".wav", "_p.wav")
        sh("ffmpeg", "-y", "-i", wav, "-af", f"apad=whole_dur={dur:.3f}", "-ar", "44100", "-ac", "2", p)
        parts.append(p)
    silence = os.path.join(work, "end.wav")
    if end_audio:
        sh("ffmpeg", "-y", "-i", end_audio, "-af", f"apad=whole_dur={end_dur:.3f}", "-ar", "44100",
           "-ac", "2", silence)
        parts.append(silence)
    elif has_end:
        sh("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{end_dur}", silence)
        parts.append(silence)
    with open(os.path.join(work, "audio.txt"), "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    audio = os.path.join(work, "voice.wav")
    sh("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "audio.txt"), audio)
    if sb.get("sfx", True):
        if has_end:
            sfx += [(max(0, t - 0.1), "whoosh", 0.22), (t + 0.05, "chime", 0.30)]
        if end.get("coin"):
            sfx.append((t + sb["end"].get("coin_at", 1.4), "coin", 0.28))
        fx = os.path.join(work, "sfx.wav")
        reelfx.write_track(sfx, t + end_dur, fx)
        mixed = os.path.join(work, "voice_sfx.wav")
        sh("ffmpeg", "-y", "-i", audio, "-i", fx, "-filter_complex",
           "[0:a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]", "-map", "[a]", mixed)
        audio = mixed

    banner = os.path.join(work, "banner.png")
    banner_png(sb["banner"], banner)
    endcard = os.path.join(work, "endcard.png")
    if has_end:
        end_png(end, endcard)
    ass = os.path.join(work, "subs.ass")
    subtitles(subs, ass, sb.get("caption_margin", 300), sb.get("caption_align", 2))   # higher margin = captions further up

    final = os.path.join(base, out_file)
    fonts = ig.FONTS
    ins = ["-i", video, "-i", audio, "-loop", "1", "-i", banner]
    flt = f"[0:v][2:v]overlay=0:0:enable='lt(t,{t:.2f})'[s0];"
    cur, n_in = "s0", 3
    if has_end:
        ins += ["-loop", "1", "-i", endcard]
        flt += (f"[{n_in}:v]format=rgba,fade=in:st={t:.2f}:d=0.3:alpha=1[e];"
                f"[{cur}][e]overlay=0:0:enable='gte(t,{t:.2f})'[s1];")
        cur, n_in = "s1", n_in + 1
    if sb.get("intro"):
        intro = os.path.join(work, "intro.png")
        intro_png(sb["intro"], intro)
        idur = sb["intro"].get("dur", 3.5)
        ins += ["-loop", "1", "-i", intro]
        flt += (f"[{n_in}:v]format=rgba,fade=in:st=0.15:d=0.35:alpha=1,fade=out:st={idur - 0.4:.2f}:d=0.4:alpha=1[i];"
                f"[{cur}][i]overlay=0:0:enable='lt(t,{idur:.2f})'[s2];")
        cur, n_in = "s2", n_in + 1
    if sb.get("outro"):
        outro = os.path.join(work, "outro.png")
        outro_png(sb["outro"], outro)
        od = sb["outro"].get("dur", 3.0)
        st0 = max(0.0, t + end_dur - od)
        ins += ["-loop", "1", "-i", outro]
        flt += (f"[{n_in}:v]format=rgba,fade=in:st={st0:.2f}:d=0.5:alpha=1[o];"
                f"[{cur}][o]overlay=0:0:enable='gte(t,{st0:.2f})'[s3];")
        cur, n_in = "s3", n_in + 1
    flt += f"[{cur}]ass={ass}:fontsdir={fonts}[v]"
    sh("ffmpeg", "-y", *ins,
       "-filter_complex", flt, "-map", "[v]", "-map", "1:a", "-t", f"{t + end_dur:.2f}",
       "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-profile:v", "high", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", final)

    cover = os.path.join(base, out_file.replace(".mp4", "") + "_cover.jpg" if out_file != "reel.mp4" else "cover.jpg")
    sh("ffmpeg", "-y", "-ss", "1.0", "-i", final, "-frames:v", "1", "-q:v", "3", cover)
    with open(os.path.join(base, "caption.txt" if out_file == "reel.mp4" else out_file.replace(".mp4", "_caption.txt")), "w") as f:
        f.write(sb.get("caption", "") + "\n")
    print(f"Reel listo: {final} ({t + end_dur:.1f} s)")
    return final


# ---------------------------------------------------------------- publish
def write_reels_csv(daily):
    """reels/reels_por_destino.csv: every destination with a published daily Reel + its newest link.
    The "Reels por destino" tab of the Price log reads it with IMPORTDATA (no Claude needed)."""
    import csv
    last = {}
    for day in sorted(daily):
        d = daily[day]
        if d.get("status") == "published" and d.get("destino"):
            last[d["destino"]] = d.get("permalink") or last.get(d["destino"], "")
    with open(os.path.join(ROOT, "reels", "reels_por_destino.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["destino", "link"])
        for k in sorted(last):
            w.writerow([k, last[k]])


def daily_post():
    """Step C of the daily Reel, run by the schedule in reel.yml at 08:14 Bogotá (backups 09:44, 11:14) (no Claude needed):
    publish today's Reel if it is rendered, mark it published in reels/daily.json and update
    reels/reels_por_destino.csv (read by the "Reels por destino" tab of the Price log with IMPORTDATA)."""
    from datetime import datetime, timedelta, timezone
    today = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d")
    path = os.path.join(ROOT, "reels", "daily.json")
    daily = json.load(open(path))
    e = daily.get(today)
    if not e:
        raise RuntimeError(f"No hay Reel para hoy ({today}) en reels/daily.json: el paso A no corrió.")
    if e.get("status") == "published":
        ig.summary(f"Reel de {e.get('destino')} ya estaba publicado: {e.get('permalink')}")
        return
    if e.get("status") != "rendered":
        raise RuntimeError(f"El Reel de hoy ({e.get('destino')}) no está listo: estado '{e.get('status')}'. No se publicó.")
    publish(e["id"])
    pub = json.load(open(os.path.join(ROOT, "reels", e["id"], "published.json")))
    daily = json.load(open(path))              # publish() pulled: reload before changing
    daily[today].update(status="published", permalink=pub.get("permalink", ""))
    json.dump(daily, open(path, "w"), ensure_ascii=False, indent=1)
    write_reels_csv(daily)
    ig.commit_push(["reels/daily.json", "reels/reels_por_destino.csv"], f"Reel diario publicado: {e['id']}")
    ig.summary(f"✅ Reel de {e.get('destino')} publicado: {pub.get('permalink')}\n"
               f"📲 Para TikTok y YouTube: https://viajespillados.com/tiktok/hoy.html")


def publish(rid):
    base = os.path.join(ROOT, "reels", rid)
    if os.path.exists(os.path.join(base, "published.json")):     # never post the same Reel twice
        ig.summary(f"Reel {rid} ya estaba publicado: {open(os.path.join(base, 'published.json')).read()}")
        return
    rel = f"reels/{rid}/reel.mp4"
    if not os.path.exists(os.path.join(ROOT, rel)):
        render(rid)
        ig.commit_push([f"reels/{rid}"], f"Reel: {rid}")
    url = ig.public_image_url(rel)   # works for any file: waits for viajespillados.com, else raw GitHub
    sb = json.load(open(os.path.join(base, "storyboard.json")))
    try:                     # owner's rule: the caption is about the destination, not the flight
        plan = json.load(open(os.path.join(base, "plan.json")))
        if plan.get("kind") == "facts":        # fact Reel (every other day): caption written with the facts
            sb["yt_title"] = sb.get("yt_title") or f"Datos curiosos de {plan['offer']['destino']} 📍"
            json.dump(sb, open(os.path.join(base, "storyboard.json"), "w"), ensure_ascii=False, indent=1)
            raise StopIteration
        import reel_caption           # owner's format: plan from Where Next, few emojis, no flight offer
        full = reel_caption.build(plan)
        text = None if full else ig.destination_caption([plan["offer"]["destino"]])
        if full:
            sb["caption"] = full
            sb["yt_title"] = f"Qué hacer en {plan['offer']['destino']} ✈️"
            json.dump(sb, open(os.path.join(base, "storyboard.json"), "w"), ensure_ascii=False, indent=1)
        if text:
            oc = (plan.get("ocasion") or {}).get("nombre")
            oc = (oc or "").split("(")[0].strip()
            sb["caption"] = (f"{oc} en {plan['offer']['destino']} ✨\n\n" if oc else "") + text
            json.dump(sb, open(os.path.join(base, "storyboard.json"), "w"), ensure_ascii=False, indent=1)
    except StopIteration:
        pass
    except Exception as e:
        print("caption:", e)
    uid = os.environ["IG_USER_ID"]
    extra = {}
    if os.path.exists(os.path.join(base, "cover_ig.jpg")):       # designed cover (destination + price)
        extra["cover_url"] = ig.public_image_url(f"reels/{rid}/cover_ig.jpg")
    def container(**cover):
        c = ig.api("POST", f"{uid}/media", media_type="REELS", video_url=url, caption=sb.get("caption", ""),
                   share_to_feed="false", **cover)["id"]   # owner: Reels stay off the profile grid (Reels tab only)
        for _ in range(60):
            st = ig.api("GET", c, fields="status_code,status")
            if st.get("status_code") == "FINISHED":
                return c
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram no pudo procesar el video: {st}")
            time.sleep(10)
        raise RuntimeError("Instagram tardó demasiado en procesar el video")
    try:
        c = container(**extra)
    except RuntimeError as e:
        if not extra:
            raise
        print("Con portada falló, se intenta sin portada:", e)   # the designed cover can make Instagram reject the Reel
        c = container()
    media_id, permalink = ig.finish(c)
    with open(os.path.join(base, "published.json"), "w") as f:
        json.dump({"media_id": media_id, "permalink": permalink}, f)
    import tiktok_feed   # same Reel, ready to repost on TikTok by hand
    try:
        destino = [json.load(open(os.path.join(base, "plan.json")))["offer"]["destino"]]
    except Exception:
        destino = None
    files = [rel] + ([f"reels/{rid}/cover_ig.jpg"] if os.path.exists(os.path.join(base, "cover_ig.jpg")) else [])
    feed = tiktok_feed.add("video", "Reel: " + sb.get("end", {}).get("title", rid), files, sb.get("caption", ""),
                           permalink, destinos=destino, yt_title=sb.get("yt_title", ""))   # yt_title set = keep the full caption
    import x_post        # same Reel on X (skipped if the X keys are not set)
    xp = x_post.share_latest()
    import fb_post       # and on the Facebook Page (skipped if not connected)
    xp += fb_post.share_latest()
    ig.commit_push([f"reels/{rid}/published.json", feed] + xp, f"Reel publicado: {rid}")
    ig.summary(f"✅ Reel publicado: {permalink}")


def publish_trip(tid, lang="es"):
    """Post a finished travel-plan video (branch trip-videos) as an Instagram Reel – only when the owner asks.
    The video is copied to main (trips/<id>/video_<lang>.mp4) so the website can serve it to Instagram/X/Facebook."""
    base = os.path.join(ROOT, "trips", tid)
    done = os.path.join(base, f"published_{lang}.json")
    if os.path.exists(done):
        ig.summary(f"{tid} ({lang}) ya estaba publicado: {open(done).read()}")
        return
    rel = f"trips/{tid}/video_{lang}.mp4"
    with open(os.path.join(ROOT, rel), "wb") as f:
        f.write(subprocess.run(["git", "show", f"origin/trip-videos:{tid}/video_{lang}.mp4"], cwd=ROOT,
                               check=True, capture_output=True).stdout)
    crel = f"trips/{tid}/cover_{lang}.jpg"
    got = subprocess.run(["git", "show", f"origin/trip-videos:{tid}/cover_{lang}.jpg"], cwd=ROOT, capture_output=True)
    if got.returncode == 0:
        open(os.path.join(ROOT, crel), "wb").write(got.stdout)
    elif not os.path.exists(os.path.join(ROOT, crel)):
        import cover
        cover.make_trip(tid, lang)
    ig.commit_push([rel, crel], f"Travel video for Instagram: {tid} ({lang})")
    url = ig.public_image_url(rel)
    plan = json.load(open(os.path.join(base, "plan.json")))
    caption = (plan.get("publish_caption") or {}).get(lang) or (plan.get("caption") or {}).get(lang, "")
    uid = os.environ["IG_USER_ID"]
    c = ig.api("POST", f"{uid}/media", media_type="REELS", video_url=url, caption=caption, share_to_feed="false",
               cover_url=ig.public_image_url(crel))["id"]
    for _ in range(90):
        st = ig.api("GET", c, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram no pudo procesar el video: {st}")
        time.sleep(10)
    media_id, permalink = ig.finish(c)
    with open(done, "w") as f:
        json.dump({"media_id": media_id, "permalink": permalink}, f)
    import tiktok_feed
    feed = tiktok_feed.add("video", f"Plan de viaje: {plan.get('destino', tid)}", [rel, crel], caption, permalink,
                           yt_title=(plan.get("yt_title") or f"{plan.get('destino', tid)} en {plan.get('dias', 3)} días: "
                                     "plan completo"))
    import x_post
    xp = x_post.share_latest()
    import fb_post
    xp += fb_post.share_latest()
    ig.commit_push([done, feed] + xp, f"Travel video publicado: {tid} ({lang})")
    ig.summary(f"✅ Travel video publicado: {permalink}")


if __name__ == "__main__":
    import traceback
    mode, rid = sys.argv[1], sys.argv[2]
    try:
        if mode == "images":   # only (re)generate the AI images, for review
            base = os.path.join(ROOT, "reels", rid)
            sb = json.load(open(os.path.join(base, "storyboard.json")))
            for i, sc in enumerate(sb["scenes"]):
                if sc["media"]["type"] == "ai":
                    try:
                        media_file(sc["media"], sb, base, "/tmp", f"scene{i}", i)
                    except Exception as e:
                        print(f"scene{i}: {e}")
            ig.commit_push([f"reels/{rid}"], f"Reel: imágenes IA {rid}")
        elif mode == "fetch":   # daily Reel: download the pictures the owner uploaded to Google Drive
            base = os.path.join(ROOT, "reels", rid)
            plan = json.load(open(os.path.join(base, "plan.json")))
            os.makedirs(os.path.join(base, "img"), exist_ok=True)
            for key, fid in plan["drive_files"].items():
                r = requests.get("https://drive.google.com/uc", params={"export": "download", "id": fid},
                                 headers=WUA, timeout=60)
                r.raise_for_status()
                if not r.headers.get("content-type", "").startswith("image/"):
                    raise RuntimeError(f"{key}: Drive no devolvió una imagen (¿carpeta compartida con enlace?) "
                                       f"{r.headers.get('content-type')}")
                from io import BytesIO
                im = ImageOps.exif_transpose(Image.open(BytesIO(r.content))).convert("RGB")
                if im.width > 1080:
                    im = im.resize((1080, round(im.height * 1080 / im.width)), Image.LANCZOS)
                im.save(os.path.join(base, "img", f"{key}.jpg"), quality=92)
                print(key, im.size)
            ig.commit_push([f"reels/{rid}/img"], f"Reel: imágenes de Drive {rid}")
        elif mode == "trip":   # travel plan videos: trips/<id>/storyboard_es.json + storyboard_en.json
            import cover
            for lang in os.environ.get("LANGS", "es en").split():
                if os.path.exists(os.path.join(ROOT, "trips", rid, f"storyboard_{lang}.json")):
                    render(rid, "trips", f"storyboard_{lang}.json", f"video_{lang}.mp4")
                    try:
                        cover.make_trip(rid, lang)          # designed cover: trips/<id>/cover_<lang>.jpg
                    except Exception as e:
                        print("cover:", e)
        elif mode == "render":
            render(rid)
            if os.path.exists(os.path.join(ROOT, "reels", rid, "plan.json")):   # daily Reel: grid cover
                try:
                    import cover
                    cover.make(rid)
                except Exception as e:
                    print("cover:", e)
            ig.commit_push([f"reels/{rid}"], f"Reel (vista previa): {rid}")
        elif mode == "publish":
            publish(rid)
        elif mode == "daily-post":   # scheduled step C (reel.yml cron)
            daily_post()
        elif mode == "trip-publish":   # travel-plan video, Spanish, on the owner's request only
            subprocess.run(["git", "fetch", "-q", "origin", "trip-videos:refs/remotes/origin/trip-videos"], cwd=ROOT,
                           check=True)
            publish_trip(rid, "es")
    except Exception as e:
        err = traceback.format_exc()
        if isinstance(e, subprocess.CalledProcessError) and e.stderr:
            err += "\n--- ffmpeg ---\n" + e.stderr.decode(errors="ignore")[-3000:]
        path = os.path.join(ROOT, "trips" if mode.startswith("trip") else "reels", rid, "error.txt")
        if mode == "daily-post":
            path = os.path.join(ROOT, "reels", "daily_error.txt")
        with open(path, "w") as f:
            f.write(err)
        ig.commit_push([path], f"Reel: error {rid}")
        raise
