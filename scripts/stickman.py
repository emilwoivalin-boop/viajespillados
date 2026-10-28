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

    def stroke(self, *pts, width=None, color=WHITE, outline=DARK):
        w = (width or self.lw) * SS
        o = w + 8 * SS
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
    pen.circle(c, r, WHITE, DARK, 5)
    ex = facing * r * 0.30 + look * r * 0.1
    eyes = [(c[0] + ex - r * 0.26, c[1] - r * 0.05), (c[0] + ex + r * 0.26, c[1] - r * 0.05)]
    blink = (t % 3.4) < 0.12
    if mask:
        pen.rrect((c[0] + ex - r * 0.62, c[1] - r * 0.35, c[0] + ex + r * 0.62, c[1] + r * 0.18), r * 0.25,
                  (120, 200, 230, 200), DARK, 4)
        pen.stroke((c[0] - facing * r * 0.6, c[1] - r * 0.1), (c[0] - facing * r * 0.85, c[1] - r * 1.1),
                   width=r * 0.18, color=YELLOW)
    elif glasses:
        for e in eyes:
            pen.rrect((e[0] - r * 0.24, e[1] - r * 0.15, e[0] + r * 0.24, e[1] + r * 0.17), r * 0.1, NAVY, DARK, 2)
        pen.line((eyes[0][0] + r * 0.24, eyes[0][1]), (eyes[1][0] - r * 0.24, eyes[1][1]), DARK, 4)
    else:
        for e in eyes:
            if blink:
                pen.line((e[0] - r * 0.09, e[1]), (e[0] + r * 0.09, e[1]), DARK, 5)
            else:
                pen.ellipse((e[0] - r * 0.08, e[1] - r * 0.11, e[0] + r * 0.08, e[1] + r * 0.11), DARK)
                pen.ellipse((e[0] - r * 0.02, e[1] - r * 0.08, e[0] + r * 0.04, e[1] - r * 0.02), WHITE)
        # eyebrows
        for e in eyes:
            lift = r * 0.1 if mood == "wow" else 0
            pen.line((e[0] - r * 0.12, e[1] - r * 0.25 - lift), (e[0] + r * 0.12, e[1] - r * 0.28 - lift), DARK, 4)
    mx = c[0] + facing * r * 0.25
    if mood == "wow":
        pen.ellipse((mx - r * 0.16, c[1] + r * 0.28, mx + r * 0.16, c[1] + r * 0.62), DARK)
        pen.ellipse((mx - r * 0.09, c[1] + r * 0.45, mx + r * 0.09, c[1] + r * 0.6), CORAL)
    elif not mask:
        pen.arc((mx - r * 0.32, c[1] + r * 0.02, mx + r * 0.32, c[1] + r * 0.52), 15, 165, DARK, 5)
    # cheek
    if not mask:
        pen.ellipse((c[0] + facing * r * 0.62 - r * 0.12, c[1] + r * 0.2, c[0] + facing * r * 0.62 + r * 0.12,
                     c[1] + r * 0.36), (255, 140, 130, 120))


def cap(pen, c, r, facing):
    dome = [(c[0] - r * 1.04, c[1] - r * 0.12), (c[0] - r * 0.92, c[1] - r * 0.62), (c[0] - r * 0.5, c[1] - r * 0.98),
            (c[0], c[1] - r * 1.1), (c[0] + r * 0.5, c[1] - r * 0.98), (c[0] + r * 0.92, c[1] - r * 0.62),
            (c[0] + r * 1.04, c[1] - r * 0.12)]
    pen.poly(dome, YELLOW, DARK, 5)
    pen.line((c[0] - r * 1.0, c[1] - r * 0.2), (c[0] + r * 1.0, c[1] - r * 0.2), YELLOW_D, 5)
    brim = [(c[0] + facing * r * 0.45, c[1] - r * 0.42), (c[0] + facing * r * 1.85, c[1] - r * 0.30),
            (c[0] + facing * r * 1.80, c[1] - r * 0.02), (c[0] + facing * r * 0.5, c[1] - r * 0.06)]
    pen.poly(brim, YELLOW, DARK, 5)
    pen.circle((c[0], c[1] - r * 1.1), r * 0.1, YELLOW_D, DARK, 3)
    pen.circle((c[0] - facing * r * 0.15, c[1] - r * 0.6), r * 0.17, NAVY, None)  # logo dot


def hand(pen, p, r):
    pen.circle(p, r, WHITE, DARK, 4)


def shoe(pen, ankle, facing, s, angle=0):
    a = rad(angle)
    tip = (ankle[0] + facing * s * 1.0 * math.cos(a), ankle[1] + s * 0.25 + s * math.sin(a) * facing * 0.0)
    pen.stroke((ankle[0] - facing * s * 0.25, ankle[1] + s * 0.18), tip, width=s * 0.55, color=NAVY)
    pen.line((ankle[0] - facing * s * 0.3, ankle[1] + s * 0.42), (tip[0] + facing * s * 0.1, tip[1] + s * 0.17),
             WHITE, 3)


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
    return h


def standing(pen, x, feet, h, facing, t, legs, arms, bob=0.0, mood="smile", glasses=False, backpack=False,
             lean=0.0, tilt=0.0):
    """legs: [(thigh angle, knee bend), (back, front)], arms: [(upper angle, elbow bend), (back, front)]."""
    leg_L, torso_L, arm_L = h * 0.44, h * 0.34, h * 0.32
    r = h * 0.115
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
    pen.stroke(hip, neck, width=lw * 1.15)
    af = leg(pen, hip, l_front[0], l_front[1], leg_L, facing)
    shoe(pen, af, facing, h * 0.07)
    hf = arm(pen, sh, a_front[0], a_front[1], arm_L, facing, h * 0.04)
    head(pen, hc, r, facing, t, mood=mood, glasses=glasses)
    cap(pen, hc, r, facing)
    return hb, hf, hc


def walk_pose(t, speed=1.0):
    ph = t * 2 * math.pi * 1.7 * speed
    s, c = math.sin(ph), math.cos(ph)
    l1 = (26 * s, 8 + 30 * max(0.0, -c))
    l2 = (-26 * s, 8 + 30 * max(0.0, c))
    a1 = (-22 * s, 18)
    a2 = (22 * s, 18)
    bob = -abs(math.sin(ph)) * 0.025
    return (l2, l1), (a1, a2), bob


# ---------------------------------------------------------------- props
def suitcase(pen, handle_hand, x, feet, h, facing):
    bw, bh = h * 0.30, h * 0.40
    cx = x - facing * h * 0.46
    top = feet - bh - h * 0.06
    pen.stroke(handle_hand, (cx + facing * bw * 0.25, top - h * 0.03), width=h * 0.018, color=(200, 205, 215, 255))
    pen.rrect((cx - bw / 2, top, cx + bw / 2, top + bh), h * 0.04, YELLOW, DARK, 5)
    for k in (0.33, 0.66):
        pen.line((cx - bw / 2 + bw * k, top + h * 0.03), (cx - bw / 2 + bw * k, top + bh - h * 0.03), YELLOW_D, 4)
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
        ph = (t * 2.2 + k / 3) % 1
        px = x - facing * (L * 0.6 + ph * L * 0.5)
        pen.circle((px, cy + wr * 0.4 - ph * L * 0.15), L * (0.05 + ph * 0.07), (230, 215, 190, int(170 * (1 - ph))),
                   None)
    body = [(x - L * 0.55, cy - L * 0.08), (x + L * 0.55, cy - L * 0.08), (x + L * 0.58, cy + L * 0.10),
            (x - L * 0.58, cy + L * 0.10)]
    hood = [(x + facing * L * 0.18, cy - L * 0.08), (x + facing * L * 0.55, cy - L * 0.08),
            (x + facing * L * 0.55, cy - L * 0.2), (x + facing * L * 0.22, cy - L * 0.22)]
    return body, hood, wr, cy


# ---------------------------------------------------------------- main generator
def frames(action, n, fps=30, x0=0.25, x1=0.65, feet=600, size=340, facing=1, band_h=700, speed=1.4,
           glasses=None, backpack=None):
    lw = max(10, size * 0.045)
    rnd = random.Random(7)
    confetti = [(rnd.uniform(-1, 1), rnd.uniform(0, 1), rnd.choice([YELLOW, CORAL, (80, 170, 220, 255), WHITE]),
                 rnd.uniform(0, 1)) for _ in range(26)]
    for i in range(n):
        t = i / fps * speed
        p = i / max(1, n - 1)
        x = W * (x0 + (x1 - x0) * p)
        out = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        if action == "none":
            yield out
            continue
        # local canvas around the figure
        cw = int(size * 3.2)
        lx = int(x - cw / 2)
        pen = Pen(lx, 0, cw, band_h, lw)

        if action in ("walk", "suitcase"):
            legs, arms, bob = walk_pose(t)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            if action == "suitcase":
                arms = ((-48, 6), arms[1])
            hb, hf, hc = standing(pen, x, feet, size, facing, t, legs, arms, bob=bob * size,
                                  backpack=bool(backpack), glasses=bool(glasses))
            if action == "suitcase":
                suitcase(pen, hb, x, feet, size, facing)
        elif action == "wave":
            w = 28 * math.sin(t * 2 * math.pi * 1.6)
            shadow(pen, x, feet + size * 0.02, size * 0.2)
            standing(pen, x, feet, size, facing, t, [(-4, 4), (4, 4)], [(-14, 20), (122 + w * 0.6, 34)],
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
            j = abs(math.sin(t * 2 * math.pi * 1.1)) * size * 0.16
            w = 10 * math.sin(t * 2 * math.pi * 2.2)
            shadow(pen, x, feet + size * 0.02, size * 0.2 * (1 - j / size))
            for cx_, cy_, col, ph in confetti:
                yy = ((cy_ + t * 0.35 + ph) % 1) * size * 1.3 + feet - size * 1.45
                xx = x + cx_ * size * 0.9 + math.sin(t * 3 + ph * 6) * size * 0.05
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
            pen.stroke(hip, neck, width=lw * 1.15)
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
            yb = feet - L * 0.3 + math.sin(t * 2 * math.pi * 0.9) * L * 0.03
            hc = (x + facing * L * 0.47, yb - L * 0.06)
            sh = (x + facing * L * 0.28, yb)
            hip = (x - facing * L * 0.18, yb + L * 0.03)
            # bubbles
            for k in range(5):
                ph = (t * 0.8 + k / 5) % 1
                bx = hc[0] - facing * L * 0.1 + math.sin(t * 4 + k) * L * 0.03
                pen.circle((bx, hc[1] - L * 0.15 - ph * L * 0.6), L * (0.012 + 0.012 * k % 3), (255, 255, 255, 170),
                           (255, 255, 255, 230), 2)
            kk = math.sin(t * 2 * math.pi * 3) * 16
            for sgn in (1, -1):
                a = -facing * (90 + sgn * kk)
                knee = limb(hip, a, L * 0.22)
                ank = limb(knee, a + facing * 6 * sgn, L * 0.22)
                pen.stroke(hip, knee, ank)
                shoe(pen, ank, -facing, L * 0.06)
            pen.stroke(sh, hip, width=lw * 1.15)
            for ph0 in (0, math.pi):
                a = t * 2 * math.pi * 0.9 + ph0
                elbow = (sh[0] + facing * math.cos(a) * L * 0.18, sh[1] - math.sin(a) * L * 0.18)
                h_ = (sh[0] + facing * math.cos(a) * L * 0.34, sh[1] - math.sin(a) * L * 0.3)
                pen.stroke(sh, elbow, h_)
                hand(pen, h_, L * 0.04)
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
            bump = math.sin(t * 2 * math.pi * 2.5) * L * 0.01
            hip = (dx, cy - L * 0.06 + bump)
            neck = (dx + facing * L * 0.02, hip[1] - L * 0.25)
            pen.stroke(hip, neck, width=lw * 1.1)
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
                a = t * 14
                pen.line((wx - math.cos(a) * wr * 0.4, cy + L * 0.1 - math.sin(a) * wr * 0.4),
                         (wx + math.cos(a) * wr * 0.4, cy + L * 0.1 + math.sin(a) * wr * 0.4), DARK, 4)

        local = pen.result()
        sx = max(0, -lx)
        dx = max(0, lx)
        wcrop = min(local.width - sx, W - dx)
        if wcrop > 0:
            out.alpha_composite(local.crop((sx, 0, sx + wcrop, local.height)), (dx, 0))
        yield out
