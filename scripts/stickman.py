"""Animated stick man for Viajes Pillados reels.

A detailed "stick figure" mascot: white limbs with a dark outline, round hands and navy sneakers,
a face (eyes that blink, eyebrows, smile), the yellow Viajes Pillados cap, a soft ground shadow and
props (roller suitcase, backpack, sunglasses, beach towel, snorkel mask, jeep, phone).

frames(action, n, fps, **params) yields RGBA images of size (W, band_h); the reel overlays them at a
fixed y. Everything is drawn at 2x and downsampled for smooth, anti-aliased lines.

Actions: walk, suitcase, wave, celebrate, relax, swim, drive, photo, none.
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
    if mood == "wow":
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


# ---------------------------------------------------------------- main generator
def frames(action, n, fps=30, x0=0.25, x1=0.65, feet=600, size=340, facing=1, band_h=700, speed=1.0,
           glasses=None, backpack=None, style=None, feet1=None, size1=None):
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
        out = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        if action == "none":
            yield out
            continue
        # local canvas around the figure
        cw = int(size * 3.2)
        lx = int(x - cw / 2)
        py0 = max(0, int(feet - size * 1.6))
        ph = max(10, min(band_h - py0, int(size * 1.9)))
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
        if wcrop > 0:
            out.alpha_composite(local.crop((sx, 0, sx + wcrop, local.height)), (dx, py0))
        yield out
