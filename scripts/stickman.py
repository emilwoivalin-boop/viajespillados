"""Animated stick man for Viajes Pillados reels.

A detailed "stick figure" mascot: white limbs with a dark outline, round hands and navy sneakers,
a face (eyes that blink, eyebrows, smile), the yellow Viajes Pillados cap, a soft ground shadow and
props (roller suitcase, backpack, sunglasses, beach towel, snorkel mask, jeep, phone).

frames(action, n, fps, **params) yields RGBA images of size (W, band_h); the reel overlays them at a
fixed y. Everything is drawn at 2x and downsampled for smooth, anti-aliased lines.

Actions: walk, suitcase, wave, celebrate, relax, swim, drive, photo, none,
         wade (walking knee-deep in the sea), dance, lookout (shading the eyes + pointing), sip (drinks from
         a coconut), dive (jumps from x0/y into the water at x1/y1, splash, swims up), float (on his back in water),
         stand, run (speed lines), sit (on an edge at y), hammock (between x0 and x1 at y), shrug, selfie, scared,
         laugh, eat (fried fish), kayak, parachute (drops in from above, lands at y), point (= lookout).
look="buddy" draws the travel buddy (ponytail + flower); mood=laugh|love|scared|wow overrides the face.
"""
import math
import random
from PIL import Image, ImageDraw, ImageFilter

W = 1080
SS = 2  # supersampling
WHITE = (255, 255, 255, 255)
DARK = (16, 24, 40, 255)
NAVY = (20, 34, 59, 255)
YELLOW = (255, 198, 49, 255)
YELLOW_D = (226, 160, 20, 255)
CORAL = (255, 90, 78, 255)
SKIN_SHADOW = (0, 0, 0, 70)
RED = (214, 48, 49, 255)
RED_D = (168, 30, 34, 255)
SHIRT = (255, 205, 40, 255)
SHIRT_D = (222, 165, 20, 255)

# "classic": black lines, hair strands, white mitten hands (user's reference)
# "pop": Modern Pop look – red knit beanie, yellow t-shirt, black stick limbs (stickman-video-director A2)
STYLE = "classic"
LOOK = "hero"     # "hero" (hair strands) or "buddy" (ponytail + flower) – set per frame by frames()
MOOD = None       # optional face override for a whole move: laugh, love, scared, wow


def rad(a):
    return math.radians(a)


def limb(p, angle, length):
    """angle in degrees measured from straight down; positive = towards +x."""
    a = rad(angle)
    return (p[0] + math.sin(a) * length, p[1] + math.cos(a) * length)


class Pen:
    """Draws on a local, supersampled canvas; takes band coordinates."""

    def __init__(self, x0, y0, w, h, lw):
        self.x0, self.y0 = x0, y0
        self.img = Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.lw = lw

    def P(self, p):
        return ((p[0] - self.x0) * SS, (p[1] - self.y0) * SS)

    def stroke(self, *pts, width=None, color=DARK, outline=WHITE):
        """Classic stick-figure line: black, with a thin white halo so it reads on any background."""
        w = (width or self.lw) * SS
        o = w + 6 * SS
        q = [self.P(p) for p in pts]
        if outline:
            self.d.line(q, fill=outline, width=int(o), joint="curve")
            for p in q:
                self.d.ellipse([p[0] - o / 2, p[1] - o / 2, p[0] + o / 2, p[1] + o / 2], fill=outline)
        self.d.line(q, fill=color, width=int(w), joint="curve")
        for p in q:
            self.d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)

    def circle(self, c, r, fill=WHITE, outline=DARK, ow=4):
        p = self.P(c)
        r2, o = r * SS, ow * SS
        if outline:
            self.d.ellipse([p[0] - r2 - o, p[1] - r2 - o, p[0] + r2 + o, p[1] + r2 + o], fill=outline)
        self.d.ellipse([p[0] - r2, p[1] - r2, p[0] + r2, p[1] + r2], fill=fill)

    def ellipse(self, box, fill, outline=None, ow=4):
        a, b = self.P(box[:2]), self.P(box[2:])
        if outline:
            o = ow * SS
            self.d.ellipse([a[0] - o, a[1] - o, b[0] + o, b[1] + o], fill=outline)
        self.d.ellipse([a[0], a[1], b[0], b[1]], fill=fill)

    def poly(self, pts, fill, outline=DARK, ow=4):
        self.d.polygon([self.P(p) for p in pts], fill=fill, outline=outline, width=int(ow * SS) if outline else 0)

    def rrect(self, box, r, fill, outline=DARK, ow=4):
        a, b = self.P(box[:2]), self.P(box[2:])
        self.d.rounded_rectangle([a[0], a[1], b[0], b[1]], radius=r * SS, fill=fill,
                                 outline=outline, width=int(ow * SS) if outline else 0)

    def arc(self, box, start, end, color=DARK, width=4):
        a, b = self.P(box[:2]), self.P(box[2:])
        self.d.arc([a[0], a[1], b[0], b[1]], start, end, fill=color, width=int(width * SS))

    def line(self, a, b, color=DARK, width=4):
        self.d.line([self.P(a), self.P(b)], fill=color, width=int(width * SS))

    def result(self):
        return self.img.resize((self.img.width // SS, self.img.height // SS), Image.LANCZOS)


# ---------------------------------------------------------------- body parts
def head(pen, c, r, facing, t, mood="smile", glasses=False, mask=False, look=0.0):
    """Round white head, thick black outline, oval eyes, arched eyebrows, big smile (reference style)."""
    ow = max(3, r * 0.075)
    pen.circle(c, r + 3, WHITE, None)               # halo
    pen.circle(c, r, WHITE, DARK, ow)
    ex = facing * r * 0.12 + look * r * 0.1
    pop = STYLE == "pop"
    ey = c[1] + r * 0.12 if pop else c[1] - r * 0.12
    eyes = [(c[0] + ex - r * 0.25, ey), (c[0] + ex + r * 0.25, ey)]
    blink = (t % 3.4) < 0.12
    if mask:
        pen.rrect((c[0] + ex - r * 0.66, c[1] - r * 0.42, c[0] + ex + r * 0.66, c[1] + r * 0.14), r * 0.25,
                  (120, 200, 230, 210), DARK, ow * 0.8)
        pen.stroke((c[0] - facing * r * 0.7, c[1] - r * 0.1), (c[0] - facing * r * 0.9, c[1] - r * 1.15),
                   width=r * 0.14, color=YELLOW, outline=DARK)
    elif glasses:
        for e in eyes:
            pen.rrect((e[0] - r * 0.25, e[1] - r * 0.14, e[0] + r * 0.25, e[1] + r * 0.18), r * 0.1, DARK, DARK, 2)
            pen.ellipse((e[0] - r * 0.16, e[1] - r * 0.08, e[0] - r * 0.04, e[1] - r * 0.01), (255, 255, 255, 140))
        pen.line((eyes[0][0] + r * 0.25, eyes[0][1]), (eyes[1][0] - r * 0.25, eyes[1][1]), DARK, ow * 0.8)
    elif (MOOD if MOOD and mood == "smile" else mood) in ("laugh", "love"):
        md = MOOD if MOOD and mood == "smile" else mood
        for e in eyes:
            if md == "laugh":                       # happy squint ^ ^
                pen.arc((e[0] - r * 0.13, e[1] - r * 0.08, e[0] + r * 0.13, e[1] + r * 0.2), 200, 340, DARK, ow)
            else:                                   # heart eyes
                hr = r * 0.11
                pen.circle((e[0] - hr * 0.55, e[1] - hr * 0.3), hr * 0.62, CORAL, None)
                pen.circle((e[0] + hr * 0.55, e[1] - hr * 0.3), hr * 0.62, CORAL, None)
                pen.poly([(e[0] - hr * 1.1, e[1] - hr * 0.1), (e[0] + hr * 1.1, e[1] - hr * 0.1), (e[0], e[1] + hr * 1.1)],
                         CORAL, None)
    else:
        for e in eyes:
            if blink:
                pen.line((e[0] - r * 0.1, e[1]), (e[0] + r * 0.1, e[1]), DARK, ow)
            elif pop:
                pen.ellipse((e[0] - r * 0.07, e[1] - r * 0.11, e[0] + r * 0.07, e[1] + r * 0.11), DARK)
            else:
                pen.ellipse((e[0] - r * 0.085, e[1] - r * 0.15, e[0] + r * 0.085, e[1] + r * 0.15), DARK)
        lift = r * 0.08 if mood == "wow" else 0
        for e in ([] if pop else eyes):  # arched eyebrows
            pen.arc((e[0] - r * 0.15, e[1] - r * 0.42 - lift, e[0] + r * 0.15, e[1] - r * 0.2 - lift), 200, 340,
                    DARK, ow * 0.75)
    mx = c[0] + facing * r * 0.08
    if MOOD and mood == "smile":
        mood = MOOD
    if mood == "laugh" and not mask:
        pen.poly([(mx - r * 0.42, c[1] + r * 0.18), (mx + r * 0.42, c[1] + r * 0.18), (mx + r * 0.3, c[1] + r * 0.5),
                  (mx, c[1] + r * 0.66), (mx - r * 0.3, c[1] + r * 0.5)], DARK, None)
        pen.ellipse((mx - r * 0.16, c[1] + r * 0.42, mx + r * 0.16, c[1] + r * 0.6), CORAL)
    elif mood == "scared" and not mask:
        pts = [(mx - r * 0.3 + k * r * 0.12, c[1] + r * (0.42 if k % 2 else 0.34)) for k in range(6)]
        pen.stroke(*pts, width=ow * 0.8, outline=None)
    elif mood == "wow":
        pen.ellipse((mx - r * 0.2, c[1] + r * 0.2, mx + r * 0.2, c[1] + r * 0.62), DARK)
        pen.ellipse((mx - r * 0.12, c[1] + r * 0.42, mx + r * 0.12, c[1] + r * 0.58), CORAL)
    elif pop and not mask:
        pen.arc((mx - r * 0.3, c[1] + r * 0.12, mx + r * 0.3, c[1] + r * 0.62), 25, 155, DARK, ow * 0.9)
    elif not mask:
        pen.arc((mx - r * 0.5, c[1] - r * 0.25, mx + r * 0.5, c[1] + r * 0.62), 25, 155, DARK, ow)


def beanie(pen, c, r, facing):
    """Smooth red knit beanie (no pom-pom) with a ribbed folded cuff, sitting low on the forehead."""
    ow = max(3, r * 0.075)
    top = c[1] - r * 1.45
    pen.ellipse((c[0] - r * 0.97, top, c[0] + r * 1.0, c[1] - r * 0.25), RED, DARK, ow)
    pen.arc((c[0] - r * 0.7, top + r * 0.18, c[0] + r * 0.2, top + r * 0.9), 200, 250, (240, 110, 105, 255),
            max(2, r * 0.07))                                               # soft highlight
    y0, y1 = c[1] - r * 0.5, c[1] - r * 0.16
    pen.rrect((c[0] - r * 1.07, y0, c[0] + r * 1.07, y1), r * 0.14, RED, DARK, ow)
    k = -0.82
    while k < 0.9:                                                          # knit ribs
        pen.line((c[0] + k * r, y0 + r * 0.07), (c[0] + k * r, y1 - r * 0.07), RED_D, max(2, r * 0.05))
        k += 0.2


def cap(pen, c, r, facing):
    """Three hair strands on top of the head (classic) or the red beanie (pop)."""
    if STYLE == "pop":
        return beanie(pen, c, r, facing)
    if LOOK == "buddy":                             # travel buddy: ponytail with a coral tie + a flower
        b = (c[0] - facing * r * 0.85, c[1] - r * 0.55)
        pen.stroke(b, (b[0] - facing * r * 0.45, b[1] + r * 0.25), (b[0] - facing * r * 0.35, b[1] + r * 0.85),
                   width=max(4, r * 0.16))
        pen.circle(b, r * 0.13, CORAL, DARK, 2)
        f = (c[0] + facing * r * 0.55, c[1] - r * 0.8)
        for a in range(5):
            pen.circle((f[0] + math.cos(a * 1.257) * r * 0.13, f[1] + math.sin(a * 1.257) * r * 0.13), r * 0.1,
                       (255, 120, 170, 255), DARK, 2)
        pen.circle(f, r * 0.08, YELLOW, DARK, 2)
        return
    for k, (dx, h, bend) in enumerate([(-0.26, 0.42, -0.16), (0.0, 0.5, 0.02), (0.24, 0.42, 0.18)]):
        base = (c[0] + dx * r, c[1] - r * 0.96 + abs(dx) * r * 0.25)
        mid = (base[0] + (dx * 0.3 + bend * 0.5) * r, base[1] - h * r * 0.55)
        tip = (base[0] + (dx * 0.5 + bend) * r, base[1] - h * r)
        pen.stroke(base, mid, tip, width=max(3, r * 0.065))


def hand(pen, p, r):
    """Small white mitten with a thumb (classic) or a small black fist (pop)."""
    if STYLE == "pop":
        pen.circle(p, r * 0.8, DARK, WHITE, 1.5)
        return
    pen.circle((p[0] + r * 0.55, p[1] - r * 0.55), r * 0.42, WHITE, DARK, max(2, r * 0.18))
    pen.circle(p, r, WHITE, DARK, max(2, r * 0.18))


def shoe(pen, ankle, facing, s, angle=0):
    """Black oval foot."""
    cx = ankle[0] + facing * s * 0.35
    cy = ankle[1] + s * 0.12
    pen.ellipse((cx - s * 0.75, cy - s * 0.3, cx + s * 0.75, cy + s * 0.3), DARK, WHITE, 2)


def torso(pen, neck, hip, h, lw):
    """Body line (classic) or a yellow t-shirt with rounded shoulders (pop)."""
    if STYLE != "pop":
        pen.stroke(hip, neck, width=lw * 1.15)
        return
    dx, dy = hip[0] - neck[0], hip[1] - neck[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    px, py = -uy, ux

    def at(u, v):  # u along the body (down), v sideways
        return (neck[0] + ux * u + px * v, neck[1] + uy * u + py * v)
    sw, hw, hem = h * 0.095, h * 0.098, L + h * 0.02
    pts = [at(h * 0.005, -h * 0.045), at(h * 0.012, -sw * 0.8), at(h * 0.035, -sw), at(h * 0.08, -sw * 0.97),
           at(hem - h * 0.01, -hw), at(hem, -hw * 0.9), at(hem, hw * 0.9), at(hem - h * 0.01, hw),
           at(h * 0.08, sw * 0.97), at(h * 0.035, sw), at(h * 0.012, sw * 0.8), at(h * 0.005, h * 0.045)]
    pen.poly(pts, SHIRT, DARK, max(2.5, lw * 0.45))
    pen.arc((neck[0] - h * 0.045, neck[1] - h * 0.035, neck[0] + h * 0.045, neck[1] + h * 0.03), 20, 160, SHIRT_D,
            max(2, lw * 0.4))                                                # collar


def sleeve(pen, sh, elbow, h, lw):
    """Short flared t-shirt sleeve over the upper arm (pop only)."""
    if STYLE != "pop":
        return
    dx, dy = elbow[0] - sh[0], elbow[1] - sh[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    b, e = h * 0.045, h * 0.048
    s0 = (sh[0] - ux * h * 0.02, sh[1] - uy * h * 0.02)
    s1 = (sh[0] + dx * 0.6, sh[1] + dy * 0.6)
    pts = [(s0[0] + px * b, s0[1] + py * b), (s1[0] + px * e, s1[1] + py * e),
           (s1[0] - px * e, s1[1] - py * e), (s0[0] - px * b, s0[1] - py * b)]
    pen.poly(pts, SHIRT, None)
    ow = max(2.5, lw * 0.45)
    pen.stroke(pts[0], pts[1], width=ow, color=DARK, outline=None)
    pen.stroke(pts[1], pts[2], width=ow, color=DARK, outline=None)
    pen.stroke(pts[2], pts[3], width=ow, color=DARK, outline=None)


def shadow(pen, x, y, w):
    pen.ellipse((x - w, y - w * 0.12, x + w, y + w * 0.12), SKIN_SHADOW)


def leg(pen, hip, thigh_a, knee_bend, L, facing):
    knee = limb(hip, facing * thigh_a, L * 0.5)
    ankle = limb(knee, facing * (thigh_a - knee_bend), L * 0.5)
    pen.stroke(hip, knee, ankle)
    return ankle


def arm(pen, sh, upper_a, elbow_bend, L, facing, hand_r):
    elbow = limb(sh, facing * upper_a, L * 0.5)
    h = limb(elbow, facing * (upper_a + elbow_bend), L * 0.5)
    pen.stroke(sh, elbow, h)
    hand(pen, h, hand_r)
    sleeve(pen, sh, elbow, L / 0.32, pen.lw)
    return h


def standing(pen, x, feet, h, facing, t, legs, arms, bob=0.0, mood="smile", glasses=False, backpack=False,
             lean=0.0, tilt=0.0):
    """legs: [(thigh angle, knee bend), (back, front)], arms: [(upper angle, elbow bend), (back, front)]."""
    leg_L, torso_L, arm_L = (h * 0.48, h * 0.30, h * 0.31) if STYLE == "pop" else (h * 0.44, h * 0.34, h * 0.32)
    r = h * 0.15
    hip = (x, feet - leg_L + bob)
    neck = (x + facing * lean * h, hip[1] - torso_L)
    sh = (neck[0], neck[1] + h * 0.06)
    hc = (neck[0] + facing * tilt * r, neck[1] - r * 1.12)
    lw = pen.lw
    # back arm and leg first (depth), slightly darker
    a_back, a_front = arms
    l_back, l_front = legs
    pen.lw = lw * 0.92
    ab = leg(pen, hip, l_back[0], l_back[1], leg_L, facing)
    shoe(pen, ab, facing, h * 0.07)
    hb = arm(pen, sh, a_back[0], a_back[1], arm_L, facing, h * 0.04)
    pen.lw = lw
    if backpack:
        bx = neck[0] - facing * h * 0.1
        pen.rrect((bx - h * 0.09, sh[1] + h * 0.01, bx + h * 0.09, sh[1] + h * 0.26), h * 0.04, CORAL, DARK, 4)
        pen.line((bx - h * 0.06, sh[1] + h * 0.15), (bx + h * 0.06, sh[1] + h * 0.15), DARK, 3)
    af = leg(pen, hip, l_front[0], l_front[1], leg_L, facing)
    shoe(pen, af, facing, h * 0.07)
    torso(pen, neck, hip, h, lw)
    hf = arm(pen, sh, a_front[0], a_front[1], arm_L, facing, h * 0.04)
    head(pen, hc, r, facing, t, mood=mood, glasses=glasses)
    cap(pen, hc, r, facing)
    return hb, hf, hc


def walk_pose(ph, amp=1.0):
    """Walk cycle at phase ph (radians). amp 0..1 scales the stride so he can ease into and out of a stop."""
    s, c = math.sin(ph), math.cos(ph)
    l1 = (22 * amp * s, 6 + 22 * amp * max(0.0, -c))
    l2 = (-22 * amp * s, 6 + 22 * amp * max(0.0, c))
    a1 = (-16 * amp * s, 16)
    a2 = (16 * amp * s, 16)
    bob = -abs(math.sin(ph)) * 0.014 * amp
    return (l2, l1), (a1, a2), bob


def smooth(p):
    """Ease-in-out (smootherstep) for 0..1."""
    p = max(0.0, min(1.0, p))
    return p * p * p * (p * (p * 6 - 15) + 10)


# ---------------------------------------------------------------- props
def suitcase(pen, handle_hand, x, feet, h, facing):
    bw, bh = h * 0.30, h * 0.40
    cx = x - facing * h * 0.46
    top = feet - bh - h * 0.06
    pen.stroke(handle_hand, (cx + facing * bw * 0.25, top - h * 0.03), width=h * 0.018, color=(200, 205, 215, 255))
    body, rib = ((70, 160, 220, 255), (45, 120, 180, 255)) if STYLE == "pop" else (YELLOW, YELLOW_D)
    pen.rrect((cx - bw / 2, top, cx + bw / 2, top + bh), h * 0.04, body, DARK, 5)
    for k in (0.33, 0.66):
        pen.line((cx - bw / 2 + bw * k, top + h * 0.03), (cx - bw / 2 + bw * k, top + bh - h * 0.03), rib, 4)
    pen.rrect((cx - bw * 0.3, top + bh * 0.25, cx + bw * 0.05, top + bh * 0.45), h * 0.01, CORAL, None)
    for wx in (cx - bw * 0.32, cx + bw * 0.32):
        pen.circle((wx, feet - h * 0.03), h * 0.03, NAVY, DARK, 3)


def towel(pen, x0, x1, y, h):
    pen.rrect((x0, y - h * 0.03, x1, y + h * 0.05), h * 0.02, (255, 255, 255, 235), DARK, 4)
    k, stripe = x0 + h * 0.06, 0
    while k < x1 - h * 0.05:
        pen.rrect((k, y - h * 0.025, k + h * 0.05, y + h * 0.045), 0, CORAL if stripe % 2 == 0 else (80, 170, 220, 255),
                  None)
        k += h * 0.12
        stripe += 1


def jeep(pen, x, ground, L, facing, t):
    wr = L * 0.12
    cy = ground - wr
    # dust puffs behind
    for k in range(3):
        ph = (t * 1.2 + k / 3) % 1
        px = x - facing * (L * 0.6 + ph * L * 0.5)
        pen.circle((px, cy + wr * 0.4 - ph * L * 0.15), L * (0.05 + ph * 0.07), (230, 215, 190, int(170 * (1 - ph))),
                   None)
    body = [(x - L * 0.55, cy - L * 0.08), (x + L * 0.55, cy - L * 0.08), (x + L * 0.58, cy + L * 0.10),
            (x - L * 0.58, cy + L * 0.10)]
    hood = [(x + facing * L * 0.18, cy - L * 0.08), (x + facing * L * 0.55, cy - L * 0.08),
            (x + facing * L * 0.55, cy - L * 0.2), (x + facing * L * 0.22, cy - L * 0.22)]
    return body, hood, wr, cy


WATER = (110, 205, 215, 175)


def water_over(pen, x, wl, half_w, L, t):
    """Translucent sea surface that hides the figure below the water line wl, with moving ripples."""
    pen.ellipse((x - half_w, wl - L * 0.035, x + half_w, wl + L * 0.33), WATER)
    for k in range(2):
        ph = (t * 0.6 + k * 0.5) % 1
        rw = half_w * (0.55 + ph * 0.6)
        pen.arc((x - rw, wl - L * 0.035, x + rw, wl + L * 0.05), 0, 180, (255, 255, 255, int(230 * (1 - ph))),
                max(2, int(L * 0.012)))


def note(pen, x, y, s, a=255):
    pen.ellipse((x - s * 0.5, y - s * 0.35, x + s * 0.5, y + s * 0.35), (16, 24, 40, a), (255, 255, 255, a), 2)
    pen.line((x + s * 0.45, y), (x + s * 0.45, y - s * 1.6), (16, 24, 40, a), max(2, int(s * 0.18)))
    pen.line((x + s * 0.45, y - s * 1.6), (x + s * 1.0, y - s * 1.2), (16, 24, 40, a), max(2, int(s * 0.18)))


def coconut(pen, c, s):
    pen.line((c[0] + s * 0.1, c[1] - s * 0.3), (c[0] + s * 0.45, c[1] - s * 1.05), (250, 250, 250, 255), max(2, int(s * 0.12)))
    pen.circle(c, s * 0.5, (140, 90, 45, 255), DARK, 3)
    pen.ellipse((c[0] - s * 0.4, c[1] - s * 0.38, c[0] + s * 0.4, c[1] - s * 0.18), (245, 240, 225, 255), None)


def splash(pen, x, y, L, age):
    """Water splash at (x, y), age in seconds since entry."""
    if age < 0:
        return
    a = max(0.0, 1 - age / 0.9)
    rnd = random.Random(11)
    for k in range(12):
        ang = rnd.uniform(-70, 70)
        v = rnd.uniform(0.5, 1.0) * L * 0.9
        px = x + math.sin(math.radians(ang)) * v * age
        py = y - math.cos(math.radians(ang)) * v * age + 2.2 * L * age * age
        if a > 0 and py < y + L * 0.05:
            pen.circle((px, py), L * 0.025, (255, 255, 255, int(235 * a)), (120, 200, 230, int(255 * a)), 2)
    for k in range(3):
        ph = (age * 0.7 + k / 3) % 1 if age > 0.2 else age * 2
        rw = L * (0.12 + ph * 0.45)
        pen.ellipse((x - rw, y - rw * 0.16, x + rw, y + rw * 0.16), None, (255, 255, 255, int(220 * (1 - ph))), 4)


def step_times(n, fps, x0, x1, size, feet0=0, feet1=0, speed=1.0):
    """Seconds at which a foot touches the ground (same walk maths as frames())."""
    xs = [W * (x0 + (x1 - x0) * smooth(i / max(1, n - 1))) for i in range(n + 1)]
    leg_L, phase, out, last = size * 0.44, 0.0, [], 0
    for i in range(n):
        p = i / max(1, n - 1)
        e = smooth(p)
        sz = size
        v = math.hypot(xs[i + 1] - xs[i], (feet1 - feet0) * (smooth((i + 1) / max(1, n - 1)) - e)) * fps
        f = max(0.7, min(1.1, v / (0.5 * sz))) if v > 1 else 0.7
        amp = min(1.0, math.degrees(math.asin(min(0.45, v / f / 4 / leg_L))) / 22) if v > 1 else 0.0
        phase += 2 * math.pi * f / fps * (1 if amp > 0.02 else 0)
        k = int(phase // math.pi)
        if k > last:
            last = k
            if amp > 0.15:
                out.append(i / fps)
    return out


# ---------------------------------------------------------------- main generator
KNOCK_FIRST, KNOCK_PERIOD, KNOCK_GAP = 0.5, 2.6, 0.24   # knock: timing (s) – factreel adds the sound
POINT_AT = 118     # teach: pointer angle from straight down (degrees, towards facing)


def frames(action, n, fps=30, x0=0.25, x1=0.65, feet=600, size=340, facing=1, band_h=700, speed=1.0,
           glasses=None, backpack=None, style=None, feet1=None, size1=None, look="hero", mood=None, patch=False):
    """patch=True yields (small RGBA image, (x, y)) or None instead of full-width frames (much faster to composite)."""
    """feet1/size1 (optional): end position/size, so he can walk into or out of the picture with perspective."""
    global STYLE
    feet0, size0 = feet, size
    feet1 = feet0 if feet1 is None else feet1
    size1 = size0 if size1 is None else size1
    if style:
        STYLE = style
    lw = max(6, size * 0.024)
    rnd = random.Random(7)
    confetti = [(rnd.uniform(-1, 1), rnd.uniform(0, 1), rnd.choice([YELLOW, CORAL, (80, 170, 220, 255), WHITE]),
                 rnd.uniform(0, 1)) for _ in range(26)]
    # eased path: he starts and stops gently; the walk cycle is driven by how far he actually moves,
    # so the feet don't slide over the ground
    xs = [W * (x0 + (x1 - x0) * smooth(i / max(1, n - 1))) for i in range(n + 1)]
    leg_L = size * 0.44
    phase = 0.0
    for i in range(n):
        t = i / fps * speed
        p = i / max(1, n - 1)
        x = xs[i]
        e = smooth(p)
        feet, size = feet0 + (feet1 - feet0) * e, size0 + (size1 - size0) * e
        lw = max(4, size * 0.024)
        v = math.hypot(xs[i + 1] - xs[i], (feet1 - feet0) * (smooth((i + 1) / max(1, n - 1)) - e)) * fps                      # px per second right now
        f = max(0.7, min(1.1, v / (0.5 * size))) if v > 1 else 0.7
        amp = min(1.0, math.degrees(math.asin(min(0.45, v / f / 4 / leg_L))) / 22) if v > 1 else 0.0
        amp = max(amp, 0.0)
        phase += 2 * math.pi * f / fps * (1 if amp > 0.02 else 0)
        global LOOK, MOOD
        LOOK, MOOD = look, mood
        if action == "point":
            action = "lookout"
        out = None if patch else Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        if action == "none":
            yield out
            continue
        if action == "dive":                 # own path: stand, jump in an arc, splash, swim up
            pd0, pd1 = 0.22, 0.42
            u = min(1.0, max(0.0, (p - pd0) / (pd1 - pd0)))
            x = W * (x0 + (x1 - x0) * u)
            feet = feet0 + (feet1 - feet0) * u - math.sin(math.pi * u) * size0 * 0.55 * (1 if u < 1 else 0)
            size = size0
        # local canvas around the figure
        cw = int(size * 3.2) if action != "hammock" else int(abs(x1 - x0) * W + size * 1.2)
        if action == "hammock":
            x = W * (x0 + x1) / 2
        lx = int(x - cw / 2)
        up = {"dive": 2.2, "parachute": 2.6}.get(action, 1.6)
        if action == "parachute":            # floats down from above the picture, lands at feet
            pl = min(1.0, p / 0.55)
            land_y = feet
            feet = land_y - (1 - smooth(pl)) * size * 3.2
            x = W * (x0 + (x1 - x0) * smooth(pl)) + math.sin(t * 2.2) * size * 0.08 * (1 - pl)
        if action == "hammock":
            cw_h = abs(x1 - x0) * W + size
        py0 = max(0, int(feet - size * up))
        ph = max(10, min(band_h - py0, int(size * (up + 0.4))))
        pen = Pen(lx, py0, cw, ph, lw)

        if action in ("walk", "suitcase"):
            legs, arms, bob = walk_pose(phase, amp)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            if action == "suitcase":
                arms = ((-48, 6), arms[1])
            hb, hf, hc = standing(pen, x, feet, size, facing, t, legs, arms, bob=bob * size,
                                  backpack=bool(backpack), glasses=bool(glasses))
            if action == "suitcase":
                suitcase(pen, hb, x, feet, size, facing)
        elif action == "wave":
            w = 22 * math.sin(t * 2 * math.pi * 0.8)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, [(-4, 4), (4, 4)], [(-14, 20), (98 + w * 0.6, 45)],
                     glasses=bool(glasses), backpack=bool(backpack))
        elif action == "photo":
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-6, 4), (6, 4)], [(70, 70), (95, 30)],
                                  glasses=bool(glasses), backpack=bool(backpack), tilt=-0.1)
            ph = (hf[0] + facing * size * 0.02, hf[1] - size * 0.06)
            pen.rrect((ph[0] - size * 0.045, ph[1] - size * 0.08, ph[0] + size * 0.045, ph[1] + size * 0.08),
                      size * 0.015, NAVY, DARK, 4)
            if (t % 1.6) < 0.12:  # camera flash
                pen.circle((ph[0] + facing * size * 0.05, ph[1] - size * 0.05), size * 0.07, (255, 255, 230, 220), None)
        elif action == "celebrate":
            j = math.sin(t * math.pi * 0.9) ** 2 * size * 0.07      # soft little hops
            w = 8 * math.sin(t * 2 * math.pi * 0.7)
            shadow(pen, x, feet + size * 0.02, size * 0.2 * (1 - j / size))
            for cx_, cy_, col, ph in confetti:
                yy = ((cy_ + t * 0.18 + ph) % 1) * size * 1.3 + feet - size * 1.45
                xx = x + cx_ * size * 0.9 + math.sin(t * 1.6 + ph * 6) * size * 0.04
                pen.rrect((xx, yy, xx + size * 0.025, yy + size * 0.045), 2, col, None)
            standing(pen, x, feet - j, size, facing, t, [(-14, 20), (14, 20)], [(160 + w, -15), (-160 - w, 15)],
                     mood="wow", backpack=bool(backpack))
        elif action == "relax":
            L = size
            gy = feet - L * 0.03
            b = math.sin(t * 2 * math.pi * 0.4) * L * 0.012
            towel(pen, x - L * 0.75, x + L * 0.7, gy + L * 0.02, L)
            hx = x - L * 0.5
            hc = (hx, gy - L * 0.12)
            neck = (hx + L * 0.14, gy - L * 0.07 - b)
            hip = (hx + L * 0.55, gy - L * 0.05)
            # arms folded behind the head
            pen.stroke(neck, (hx + L * 0.02, gy - L * 0.32), (hx - L * 0.12, gy - L * 0.2))
            torso(pen, neck, hip, L, lw)
            knee = (hip[0] + L * 0.22, gy - L * 0.3)
            pen.stroke(hip, knee, (hip[0] + L * 0.42, gy - L * 0.05))
            shoe(pen, (hip[0] + L * 0.42, gy - L * 0.08), 1, L * 0.07)
            pen.stroke(hip, (hip[0] + L * 0.48, gy - L * 0.05))
            shoe(pen, (hip[0] + L * 0.48, gy - L * 0.08), 1, L * 0.07)
            head(pen, hc, L * 0.115, 1, t, glasses=True)
            cap(pen, hc, L * 0.115, 1)
            # "z" when relaxing
            zt = (t * 0.5) % 1
            zx, zy = hc[0] + L * 0.15 + zt * L * 0.2, hc[1] - L * 0.25 - zt * L * 0.3
            fz = int(L * 0.09)
            pen.line((zx, zy), (zx + fz, zy), WHITE, 5)
            pen.line((zx + fz, zy), (zx, zy + fz), WHITE, 5)
            pen.line((zx, zy + fz), (zx + fz, zy + fz), WHITE, 5)
        elif action == "swim":
            L = size
            yb = feet - L * 0.3 + math.sin(t * 2 * math.pi * 0.35) * L * 0.025
            hc = (x + facing * L * 0.47, yb - L * 0.06)
            sh = (x + facing * L * 0.28, yb)
            hip = (x - facing * L * 0.18, yb + L * 0.03)
            # bubbles
            for k in range(5):
                ph = (t * 0.5 + k / 5) % 1
                bx = hc[0] - facing * L * 0.1 + math.sin(t * 4 + k) * L * 0.03
                pen.circle((bx, hc[1] - L * 0.15 - ph * L * 0.6), L * (0.012 + 0.012 * k % 3), (255, 255, 255, 170),
                           (255, 255, 255, 230), 2)
            kk = math.sin(t * 2 * math.pi * 1.4) * 12
            for sgn in (1, -1):
                a = -facing * (90 + sgn * kk)
                knee = limb(hip, a, L * 0.22)
                ank = limb(knee, a + facing * 6 * sgn, L * 0.22)
                pen.stroke(hip, knee, ank)
                shoe(pen, ank, -facing, L * 0.06)
            torso(pen, sh, hip, L, lw)
            for ph0 in (0, math.pi):
                a = t * 2 * math.pi * 0.5 + ph0
                elbow = (sh[0] + facing * math.cos(a) * L * 0.18, sh[1] - math.sin(a) * L * 0.18)
                h_ = (sh[0] + facing * math.cos(a) * L * 0.34, sh[1] - math.sin(a) * L * 0.3)
                pen.stroke(sh, elbow, h_)
                hand(pen, h_, L * 0.04)
                sleeve(pen, sh, elbow, L, lw)
            head(pen, hc, L * 0.115, facing, t, mask=True)
            cap(pen, hc, L * 0.115, facing)
        elif action == "wade":
            legs, arms, bob = walk_pose(phase, amp * 0.7)
            arms = ((-65, -20), (65 + 10 * math.sin(t * 2), 25))      # arms out for balance
            standing(pen, x, feet, size, facing, t, legs, arms, bob=bob * size, glasses=bool(glasses))
            water_over(pen, x, feet - size * 0.24, size * 0.42, size, t)
        elif action == "dance":
            sw = math.sin(t * 2 * math.pi * 1.1)
            up = abs(math.sin(t * 2 * math.pi * 1.1))
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x + sw * size * 0.03, feet, size, facing, t,
                     [(-12 + 10 * sw, 8 + 22 * max(0, sw)), (12 + 10 * sw, 8 + 22 * max(0, -sw))],
                     [(-(130 - 30 * sw), -45), (130 + 30 * sw, 45)], bob=-up * size * 0.03, lean=0.03 * sw, tilt=0.15 * sw)
            for k in range(3):
                ph_ = (t * 0.45 + k / 3) % 1
                note(pen, x + facing * size * (0.35 + 0.15 * k) + math.sin(t * 3 + k) * size * 0.03,
                     feet - size * (1.0 + ph_ * 0.45), size * 0.05, int(255 * (1 - ph_)))
        elif action == "teach_walk":
            # walks with the pointer resting on his shoulder
            legs, arms, bob = walk_pose(phase, amp)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, legs, (arms[0], (150, -40)), bob=bob * size)
            a = rad(200)
            tip = (hf[0] + facing * math.sin(a) * size * 0.5, hf[1] + math.cos(a) * size * 0.5)
            pen.stroke(hf, tip, width=size * 0.022, color=(132, 86, 44, 255), outline=DARK)
            pen.circle(tip, size * 0.022, CORAL, DARK, 2)
        elif action == "swing":
            # twirls the pointer like a baton over his head, facing the viewer
            spin = t * 360 * 1.25
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-8, 3), (8, 3)], [(-30, 40), (150, 10)])
            for sgn in (1, -1):
                a = rad(spin + (0 if sgn == 1 else 180))
                end = (hf[0] + math.sin(a) * size * 0.28, hf[1] + math.cos(a) * size * 0.28)
                pen.stroke(hf, end, width=size * 0.022, color=(132, 86, 44, 255), outline=DARK)
                if sgn == 1:
                    pen.circle(end, size * 0.022, CORAL, DARK, 2)
            head(pen, hc, size * 0.15, 0, t, mood="laugh")
        elif action == "knock":
            # knocks on the screen glass: fist comes towards the viewer, two knocks every KNOCK_PERIOD
            cyc = (t - KNOCK_FIRST) % KNOCK_PERIOD if t >= KNOCK_FIRST - 0.3 else -1
            near = 0.0
            for k0 in (0.0, KNOCK_GAP):
                dt = cyc - k0
                if -0.18 < dt < 0.14:
                    near = max(near, 1 - abs(dt) / (0.18 if dt < 0 else 0.14))
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-8, 3), (8, 3)],
                                  [(-30, 40), (118 - 18 * near, 95 - 40 * near)], tilt=0.0)
            fr = size * (0.06 + 0.09 * near)
            fc = (hf[0] + facing * size * 0.04 * near, hf[1] - size * 0.03 * near)
            pen.circle(fc, fr, WHITE, DARK, max(3, size * 0.02))
            if near > 0.85:
                for ang in range(0, 360, 45):
                    a = rad(ang)
                    r0, r1 = fr * 1.35, fr * 1.9
                    pen.line((fc[0] + math.sin(a) * r0, fc[1] + math.cos(a) * r0),
                             (fc[0] + math.sin(a) * r1, fc[1] + math.cos(a) * r1), DARK, max(3, size * 0.014))
            head(pen, hc, size * 0.15, 0, t, mood="wow" if near > 0.3 else "smile")
        elif action == "tap":
            # taps the pointer on the map in front of him
            cyc = (t % 0.9) / 0.9
            down = math.exp(-((cyc - 0.5) / 0.12) ** 2)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-8, 3), (8, 3)],
                                  [(-38, 70), (48 + 18 * (1 - down), -12)])
            a = rad(28 + 26 * (1 - down))
            tip = (hf[0] + facing * math.sin(a) * size * 0.5, hf[1] + math.cos(a) * size * 0.5)
            pen.stroke(hf, tip, width=size * 0.022, color=(132, 86, 44, 255), outline=DARK)
            pen.circle(tip, size * 0.022, CORAL, DARK, 2)
            if down > 0.8:
                pen.arc((tip[0] - size * 0.09, tip[1] - size * 0.025, tip[0] + size * 0.09, tip[1] + size * 0.035),
                        0, 360, (255, 90, 78, 200), max(3, size * 0.012))
            head(pen, hc, size * 0.15, 0, t, mood="smile")
        elif action == "teach":
            # lecturer facing the viewer: glasses, pointer stick in the front hand aimed at the map,
            # the other hand explaining, mouth moving while he talks
            g = math.sin(t * 2 * math.pi * 0.9)
            tap = 3.5 * math.sin(t * 2 * math.pi * 1.6)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-8, 3), (8, 3)],
                                  [(-38 - 10 * g, 75 + 25 * g), (POINT_AT + 8 + tap, -12)])
            a = rad(POINT_AT + tap)
            tip = (hf[0] + facing * math.sin(a) * size * 0.5, hf[1] + math.cos(a) * size * 0.5)
            pen.stroke(hf, tip, width=size * 0.022, color=(132, 86, 44, 255), outline=DARK)
            pen.circle(tip, size * 0.022, CORAL, DARK, 2)
            talk = (math.sin(t * 2 * math.pi * 3.1) + 0.4 * math.sin(t * 2 * math.pi * 4.7)) > 0.25
            head(pen, hc, size * 0.15, 0, t, mood="wow" if talk else "smile")
        elif action == "lookout":
            pt = 4 * math.sin(t * 2 * math.pi * 0.3)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, [(-6, 4), (6, 4)], [(-30, -95), (92 + pt, 6)],
                     tilt=0.08, glasses=bool(glasses), backpack=bool(backpack))
        elif action == "sip":
            cyc = (t % 3.0) / 3.0
            lift = smooth(min(1, cyc / 0.25)) * (1 - smooth(max(0, (cyc - 0.6) / 0.25)))
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-4, 4), (4, 4)],
                                  [(-10, 15), (40 + 105 * lift, 70 + 40 * lift)], tilt=-0.12 * lift)
            coconut(pen, (hf[0] + facing * size * 0.03, hf[1] - size * 0.02), size * 0.09)
            if lift > 0.9:
                for k in range(3):   # little bubbles = slurp
                    pen.circle((hc[0] + facing * size * (0.16 + 0.05 * k), hc[1] - size * (0.05 + 0.04 * k)),
                               size * 0.012, (255, 255, 255, 200), None)
        elif action == "float":
            L = size
            gy = feet - L * 0.03 + math.sin(t * 2 * math.pi * 0.3) * L * 0.015
            hx = x - L * 0.5
            hc = (hx, gy - L * 0.1)
            neck = (hx + L * 0.14, gy - L * 0.05)
            hip = (hx + L * 0.55, gy - L * 0.03)
            pen.stroke(neck, (hx + L * 0.25, gy - L * 0.28), (hx + L * 0.05, gy - L * 0.4))   # arm waving
            torso(pen, neck, hip, L, lw)
            pen.stroke(hip, (hip[0] + L * 0.45, gy - L * 0.02))
            pen.stroke(hip, (hip[0] + L * 0.42, gy - L * 0.08))
            head(pen, hc, L * 0.115, 1, t, glasses=True)
            cap(pen, hc, L * 0.115, 1)
            water_over(pen, x, gy - L * 0.01, L * 0.85, L * 0.6, t)
        elif action == "dive":
            pd0, pd1 = 0.22, 0.42
            if p < pd0:                      # crouch, arms swing back
                c = smooth(p / pd0)
                shadow(pen, x, feet + size * 0.02, size * 0.2)
                standing(pen, x, feet, size, facing, t, [(35 * c, 75 * c), (45 * c, 85 * c)],
                         [(-50 * c, 10), (-35 * c, 10)], bob=size * 0.1 * c, mood="wow")
            elif p < pd1:                    # flying, arms over the head
                standing(pen, x, feet, size, facing, t, [(-6, 0), (6, 0)], [(-155, 0), (155, 0)], mood="wow")
            else:                            # splash, then he pops up and waves
                age = (p - pd1) * n / fps
                wx, wy = W * x1, feet1
                splash(pen, wx, wy, size, age)
                if age > 0.7:
                    bobv = math.sin(t * 2 * math.pi * 0.4) * size * 0.015
                    hc = (wx, wy - size * 0.1 + bobv)
                    w_ = 25 * math.sin(t * 2 * math.pi * 0.9)
                    pen.stroke((wx + size * 0.08, wy), limb((wx + size * 0.08, wy), 160 + w_, size * 0.28))
                    hand(pen, limb((wx + size * 0.08, wy), 160 + w_, size * 0.28), size * 0.04)
                    head(pen, hc, size * 0.12, facing, t, mood="smile")
                    cap(pen, hc, size * 0.12, facing)
                    water_over(pen, wx, wy, size * 0.35, size * 0.5, t)
        elif action == "stand":
            br = math.sin(t * 2 * math.pi * 0.35)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, [(-5, 4), (5, 4)], [(-12 - 2 * br, 18), (12 + 2 * br, 18)],
                     bob=br * size * 0.006, glasses=bool(glasses), backpack=bool(backpack))
        elif action == "run":
            legs, arms, bob = walk_pose(phase * 1.0, amp)
            legs = tuple((a * 1.7, b * 1.8 + 10) for a, b in legs)
            arms = tuple((a * 2.4, 75) for a, b in arms)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, legs, arms, bob=bob * size * 1.6, lean=0.07 * min(1, amp * 2),
                     glasses=bool(glasses), backpack=bool(backpack))
            if amp > 0.2:                     # speed lines + dust
                for k in range(3):
                    yy = feet - size * (0.45 + 0.22 * k)
                    xx = x - facing * size * (0.35 + 0.08 * k)
                    pen.line((xx, yy), (xx - facing * size * (0.25 + 0.1 * (k % 2)), yy), (255, 255, 255, 210), 5)
                for k in range(2):
                    ph_ = (t * 2.5 + k * 0.5) % 1
                    pen.circle((x - facing * size * (0.2 + ph_ * 0.3), feet - size * 0.03 - ph_ * size * 0.08),
                               size * (0.03 + ph_ * 0.05), (235, 225, 205, int(190 * (1 - ph_))), None)
        elif action == "sit":                 # sitting on an edge (dock, wall, rock) – y = the edge surface
            sw = 14 * math.sin(t * 2 * math.pi * 0.6)
            leg_L = size * 0.44
            standing(pen, x, feet + leg_L, size, facing, t, [(88, 95 + sw), (88, 95 - sw)], [(-25, 0), (30, 20)],
                     glasses=bool(glasses), backpack=bool(backpack))
        elif action == "hammock":             # lies in a hammock hung between x0 and x1 at height y
            ax0, ax1 = W * x0, W * x1
            sway = math.sin(t * 2 * math.pi * 0.25) * size * 0.04
            sag = size * 0.32
            pts_top, pts_bot = [], []
            for k in range(21):
                u = k / 20
                xx = ax0 + (ax1 - ax0) * (0.12 + 0.76 * u) + sway
                yy = feet + sag * math.sin(math.pi * u) ** 1.3
                pts_top.append((xx, yy - size * 0.02))
                pts_bot.append((xx, yy + size * 0.07 + size * 0.04 * math.sin(math.pi * u)))
            pen.stroke((ax0, feet - size * 0.05), pts_top[0], width=lw * 0.6)
            pen.stroke((ax1, feet - size * 0.05), pts_top[-1], width=lw * 0.6)
            mid = pts_top[10]
            hc = (pts_top[4][0], pts_top[4][1] - size * 0.11)
            hip = (pts_top[12][0], pts_top[12][1] - size * 0.02)
            neck = (pts_top[6][0], pts_top[6][1] - size * 0.04)
            torso(pen, neck, hip, size, lw)
            pen.stroke(neck, (hc[0] - size * 0.02, hc[1] - size * 0.2), (hc[0] - size * 0.14, hc[1] - size * 0.06))
            knee = (pts_top[15][0], pts_top[15][1] - size * 0.2)
            pen.stroke(hip, knee, (pts_top[18][0], pts_top[18][1] - size * 0.05))
            pen.stroke(hip, (pts_top[18][0] + size * 0.04, pts_top[18][1] - size * 0.1))
            head(pen, hc, size * 0.11, 1, t, glasses=True)
            cap(pen, hc, size * 0.11, 1)
            pen.poly(pts_top + pts_bot[::-1], (255, 140, 90, 235), DARK, 4)
            for k in (5, 10, 15):
                pen.line(pts_top[k], pts_bot[k], (255, 210, 80, 255), 5)
            zt = (t * 0.5) % 1
            zx, zy = hc[0] + size * 0.15 + zt * size * 0.2, hc[1] - size * 0.25 - zt * size * 0.3
            fz = int(size * 0.08)
            pen.line((zx, zy), (zx + fz, zy), WHITE, 5)
            pen.line((zx + fz, zy), (zx, zy + fz), WHITE, 5)
            pen.line((zx, zy + fz), (zx + fz, zy + fz), WHITE, 5)
        elif action == "shrug":
            u = smooth(abs(math.sin(t * 2 * math.pi * 0.45)))
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, [(-5, 4), (5, 4)], [(-60 - 20 * u, -95), (60 + 20 * u, 95)],
                     bob=-u * size * 0.015, tilt=0.15 * u, mood="smile")
        elif action == "selfie":
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-6, 4), (8, 10)], [(-150, -40), (128, -15)],
                                  tilt=0.12, glasses=bool(glasses))
            pen.rrect((hf[0] - size * 0.04, hf[1] - size * 0.075, hf[0] + size * 0.04, hf[1] + size * 0.075),
                      size * 0.015, NAVY, DARK, 4)
            for k in (-1, 1):                 # peace sign
                pen.stroke(hb, (hb[0] + k * size * 0.03, hb[1] - size * 0.07), width=lw * 0.6)
            if (t % 1.8) < 0.12:
                pen.circle((hf[0], hf[1]), size * 0.08, (255, 255, 230, 220), None)
        elif action == "scared":              # jumps back, shakes, sweat drops and "!"
            jb = math.sin(min(1, t / 0.45) * math.pi) * size * 0.18 if t < 0.45 else 0
            back = -facing * size * 0.15 * smooth(min(1, t / 0.45))
            sh_ = math.sin(t * 2 * math.pi * 9) * size * 0.008 if t > 0.45 else 0
            xx = x + back + sh_
            shadow(pen, xx, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, xx, feet - jb, size, facing, t, [(-14, 18), (16, 22)],
                                  [(-150, -40), (150, 40)], mood="wow", lean=-0.04)
            for k in range(2):
                ph_ = (t * 1.2 + k * 0.5) % 1
                dx_ = hc[0] - facing * size * (0.16 + 0.06 * k)
                dy_ = hc[1] - size * 0.08 + ph_ * size * 0.12
                pen.poly([(dx_, dy_ - size * 0.04), (dx_ - size * 0.022, dy_), (dx_ + size * 0.022, dy_)],
                         (130, 200, 255, int(255 * (1 - ph_))), None)
                pen.circle((dx_, dy_), size * 0.022, (130, 200, 255, int(255 * (1 - ph_))), None)
            ex_ = (hc[0] + facing * size * 0.05, hc[1] - size * 0.42 - abs(math.sin(t * 6)) * size * 0.03)
            pen.rrect((ex_[0] - size * 0.025, ex_[1] - size * 0.12, ex_[0] + size * 0.025, ex_[1]), size * 0.01,
                      YELLOW, DARK, 3)
            pen.circle((ex_[0], ex_[1] + size * 0.045), size * 0.025, YELLOW, DARK, 3)
        elif action == "laugh":
            b_ = abs(math.sin(t * 2 * math.pi * 1.6))
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, [(-6, 6), (6, 6)], [(-35, -60), (35, 60)],
                     bob=b_ * size * 0.02, lean=-0.03, tilt=-0.15, mood="laugh")
        elif action == "eat":
            cyc = (t % 2.4) / 2.4
            lift = smooth(min(1, cyc / 0.3)) * (1 - smooth(max(0, (cyc - 0.55) / 0.3)))
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            hb, hf, hc = standing(pen, x, feet, size, facing, t, [(-4, 4), (4, 4)],
                                  [(55, 60), (45 + 100 * lift, 75 + 30 * lift)], tilt=-0.08 * lift)
            pc = (hb[0] + facing * size * 0.06, hb[1])         # plate with a fried fish + patacón
            pen.ellipse((pc[0] - size * 0.15, pc[1] - size * 0.035, pc[0] + size * 0.15, pc[1] + size * 0.035),
                        (250, 250, 250, 255), DARK, 3)
            pen.ellipse((pc[0] - size * 0.1, pc[1] - size * 0.06, pc[0] + size * 0.05, pc[1] - size * 0.005),
                        (230, 140, 50, 255), DARK, 3)
            pen.poly([(pc[0] + size * 0.04, pc[1] - size * 0.033), (pc[0] + size * 0.1, pc[1] - size * 0.07),
                      (pc[0] + size * 0.1, pc[1] + size * 0.0)], (230, 140, 50, 255), DARK, 3)
            pen.circle((pc[0] + size * 0.09, pc[1] - size * 0.01), size * 0.03, (240, 200, 90, 255), DARK, 2)
            pen.line(hf, (hf[0] + facing * size * 0.06, hf[1] - size * 0.06), (200, 205, 215, 255), 4)  # fork
        elif action == "kayak":
            L = size
            pr = t * 2 * math.pi * 0.9
            hull_y = feet
            pen.ellipse((x - L * 0.75, hull_y - L * 0.08, x + L * 0.75, hull_y + L * 0.08), YELLOW, DARK, 6)
            pen.ellipse((x - L * 0.18, hull_y - L * 0.05, x + L * 0.18, hull_y + L * 0.02), (60, 60, 70, 255), None)
            hip = (x, hull_y - L * 0.03)
            neck = (x + facing * L * 0.04, hip[1] - L * 0.3)
            torso(pen, neck, hip, L, lw)
            hcx = (neck[0] + facing * L * 0.01, neck[1] - L * 0.11)
            dxp, dyp = math.cos(pr) * L * 0.45, math.sin(pr) * L * 0.12
            c_ = (neck[0] + facing * L * 0.12, neck[1] + L * 0.12)
            pa, pb = (c_[0] - dxp, c_[1] - dyp), (c_[0] + dxp, c_[1] + dyp)
            pen.stroke(pa, pb, width=lw * 0.6, color=(120, 80, 40, 255))
            for pp_ in (pa, pb):
                pen.ellipse((pp_[0] - L * 0.05, pp_[1] - L * 0.03, pp_[0] + L * 0.05, pp_[1] + L * 0.03), CORAL, DARK, 3)
            for k in (-0.18, 0.18):
                hpt = (c_[0] + (pa[0] - c_[0]) * 0.4 * (1 if k < 0 else -1) * -1, c_[1] + (pa[1] - c_[1]) * 0.4 * (1 if k < 0 else -1) * -1)
                pen.stroke((neck[0], neck[1] + L * 0.05), hpt)
                hand(pen, hpt, L * 0.035)
            head(pen, hcx, L * 0.11, facing, t, glasses=True)
            cap(pen, hcx, L * 0.11, facing)
            water_over(pen, x, hull_y + L * 0.03, L * 0.85, L * 0.35, t)
        elif action == "parachute":
            pl = min(1.0, p / 0.55)
            landed = pl >= 1
            if not landed:
                cy_ = feet - size * 1.45
                pen.poly([(x - size * 0.55 + k * size * 0.11, cy_ - math.sin(math.pi * k / 10) * size * 0.32)
                          for k in range(11)] + [(x + size * 0.55, cy_ + size * 0.04), (x - size * 0.55, cy_ + size * 0.04)],
                         CORAL, DARK, 5)
                for k in (3, 7):
                    xs_ = x - size * 0.55 + k * size * 0.11
                    pen.line((xs_, cy_ - math.sin(math.pi * k / 10) * size * 0.32), (xs_, cy_ + size * 0.04), YELLOW, 6)
                for sx_ in (-0.5, -0.2, 0.2, 0.5):
                    pen.line((x + sx_ * size, cy_ + size * 0.04), (x, feet - size * 0.7), (240, 240, 240, 255), 3)
                standing(pen, x, feet, size, facing, t, [(-10, 15), (10, 15)], [(-165, 0), (165, 0)], mood="wow")
            else:
                age = (p - 0.55) * n / fps
                sq = math.exp(-age * 6) * math.sin(age * 18) * size * 0.03
                if age < 0.6:
                    for k in range(4):        # landing dust
                        ph_ = min(1, age / 0.6)
                        pen.circle((x + (k - 1.5) * size * 0.12 * (1 + ph_), feet - ph_ * size * 0.05), size * 0.04 * (1 + ph_),
                                   (235, 225, 205, int(200 * (1 - ph_))), None)
                shadow(pen, x, feet + size * 0.02, size * 0.2)
                w_ = 22 * math.sin(t * 2 * math.pi * 0.8)
                standing(pen, x, feet, size, facing, t, [(-4, 4), (4, 4)], [(-14, 20), (98 + w_ * 0.6, 45)], bob=sq)
        elif action == "drive":
            L = size
            body, hood, wr, cy = jeep(pen, x, feet, L, facing, t)
            # roll bar + seat behind driver
            rb = x - facing * L * 0.28
            pen.stroke((rb, cy - L * 0.08), (rb, cy - L * 0.42), (rb + facing * L * 0.12, cy - L * 0.42),
                       width=lw * 0.8, color=(210, 215, 225, 255))
            # driver (upper body only; the car hides the legs)
            dx = x - facing * L * 0.08
            bump = math.sin(t * 2 * math.pi * 1.6) * L * 0.006
            hip = (dx, cy - L * 0.06 + bump)
            neck = (dx + facing * L * 0.02, hip[1] - L * 0.25)
            torso(pen, neck, hip, L, lw)
            hcx = (neck[0] + facing * L * 0.01, neck[1] - L * 0.1)
            head(pen, hcx, L * 0.1, facing, t, glasses=True)
            cap(pen, hcx, L * 0.1, facing)
            wheel = (x + facing * L * 0.16, cy - L * 0.2)
            sh = (neck[0], neck[1] + L * 0.05)
            pen.stroke(sh, ((sh[0] + wheel[0]) / 2 + facing * L * 0.02, sh[1] + L * 0.1), wheel)
            hand(pen, wheel, L * 0.035)
            # car body over the legs
            pen.poly(body, YELLOW, DARK, 6)
            pen.poly(hood, YELLOW, DARK, 6)
            pen.line((x - facing * L * 0.02, cy - L * 0.06), (x - facing * L * 0.02, cy + L * 0.09), YELLOW_D, 5)
            ws_x = x + facing * L * 0.2
            pen.stroke((ws_x, cy - L * 0.21), (ws_x - facing * L * 0.05, cy - L * 0.42), width=lw * 0.6,
                       color=(200, 230, 245, 255))
            pen.circle((x + facing * L * 0.56, cy - L * 0.02), L * 0.03, (255, 250, 210, 255), DARK, 3)  # headlight
            for wx in (x - L * 0.34, x + L * 0.34):
                pen.circle((wx, cy + L * 0.1), wr, (40, 40, 45, 255), DARK, 5)
                pen.circle((wx, cy + L * 0.1), wr * 0.45, (200, 205, 215, 255), DARK, 3)
                a = (x - xs[0]) / wr
                pen.line((wx - math.cos(a) * wr * 0.4, cy + L * 0.1 - math.sin(a) * wr * 0.4),
                         (wx + math.cos(a) * wr * 0.4, cy + L * 0.1 + math.sin(a) * wr * 0.4), DARK, 4)

        local = pen.result()
        sx = max(0, -lx)
        dx = max(0, lx)
        wcrop = min(local.width - sx, W - dx)
        hcrop = min(local.height, band_h - py0)
        if patch:
            yield (local.crop((sx, 0, sx + wcrop, hcrop)), (dx, py0)) if wcrop > 0 and hcrop > 0 else None
            continue
        if wcrop > 0:
            out.alpha_composite(local.crop((sx, 0, sx + wcrop, local.height)), (dx, py0))
        yield out
