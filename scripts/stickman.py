"""Simple animated stick man (Viajes Pillados style: white lines, dark outline, yellow cap).

frames(action, n, fps, **params) yields RGBA PIL images of size (W, BAND_H) that are laid over the
video at y = BAND_Y. Actions: walk, suitcase, wave, celebrate, relax, swim, drive, none.
"""
import math
from PIL import Image, ImageDraw

W = 1080
WHITE, DARK, YELLOW = (255, 255, 255, 255), (16, 24, 40, 235), (255, 198, 49, 255)


def _limb(p, angle_deg, length):
    a = math.radians(angle_deg)
    return (p[0] + math.sin(a) * length, p[1] + math.cos(a) * length)


class Pen:
    def __init__(self, img, lw):
        self.d = ImageDraw.Draw(img)
        self.lw = lw
        self.segs, self.circles, self.polys = [], [], []

    def line(self, *pts):
        self.segs.append(pts)

    def circle(self, c, r, fill=None):
        self.circles.append((c, r, fill))

    def poly(self, pts, fill, over=False):
        self.polys.append((pts, fill, over))

    def flush(self):
        o = self.lw + 9
        for pts, fill, over in self.polys:
            if not over:
                self.d.polygon(pts, fill=fill, outline=DARK, width=6)
        for pts in self.segs:  # outline pass
            self.d.line(pts, fill=DARK, width=o, joint="curve")
            for p in pts:
                self.d.ellipse([p[0] - o / 2, p[1] - o / 2, p[0] + o / 2, p[1] + o / 2], fill=DARK)
        for c, r, fill in self.circles:
            self.d.ellipse([c[0] - r - 5, c[1] - r - 5, c[0] + r + 5, c[1] + r + 5], fill=DARK)
        for pts in self.segs:
            self.d.line(pts, fill=WHITE, width=self.lw, joint="curve")
            for p in pts:
                self.d.ellipse([p[0] - self.lw / 2, p[1] - self.lw / 2, p[0] + self.lw / 2, p[1] + self.lw / 2],
                               fill=WHITE)
        for c, r, fill in self.circles:
            self.d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=fill or WHITE)
        for pts, fill, over in self.polys:
            if over:
                self.d.polygon(pts, fill=fill, outline=DARK, width=6)
        for c, r, fill in getattr(self, "top_circles", []):
            self.d.ellipse([c[0] - r - 5, c[1] - r - 5, c[0] + r + 5, c[1] + r + 5], fill=DARK)
            self.d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=fill)
        for pts in getattr(self, "top_segs", []):
            self.d.line(pts, fill=WHITE, width=max(4, self.lw // 2))


def _head(pen, c, r, facing):
    pen.circle(c, r)
    # yellow cap with visor
    cap = [(c[0] - r * 1.02, c[1] - r * 0.15), (c[0] - r * 0.8, c[1] - r * 0.85), (c[0], c[1] - r * 1.08),
           (c[0] + r * 0.8, c[1] - r * 0.85), (c[0] + r * 1.02, c[1] - r * 0.15)]
    visor = [(c[0] + facing * r * 0.6, c[1] - r * 0.35), (c[0] + facing * r * 1.65, c[1] - r * 0.2),
             (c[0] + facing * r * 1.0, c[1] - r * 0.05)]
    pen.poly(cap, YELLOW, over=True)
    pen.poly(visor, YELLOW, over=True)


def standing_figure(pen, x, feet_y, h, facing=1, legs=(0, 0), arms=(20, -20), bob=0.0, arm_r=None):
    """Upright figure. legs/arms: angles in degrees from straight down (positive = forward)."""
    leg, torso, arm = h * 0.42, h * 0.36, h * 0.30
    r = h * 0.11
    hip = (x, feet_y - leg + bob)
    neck = (x, hip[1] - torso)
    head = (x, neck[1] - r * 1.15)
    shoulder = (x, neck[1] + h * 0.07)
    for a in legs:
        knee = _limb(hip, facing * a * 0.6, leg * 0.5)
        foot = _limb(knee, facing * a * 1.1, leg * 0.5)
        pen.line(hip, knee, foot)
    hands = []
    for a in arms:
        elbow = _limb(shoulder, facing * a, arm * 0.5)
        bend = 15 if a >= 0 else -15
        hand = _limb(elbow, facing * (a + bend), arm * 0.5)
        pen.line(shoulder, elbow, hand)
        hands.append(hand)
    pen.line(hip, neck)
    _head(pen, head, r, facing)
    return hands


def frames(action, n, fps=30, x0=0.25, x1=0.65, feet=600, size=340, facing=1, band_h=700):
    lw = max(10, int(size * 0.045))
    for i in range(n):
        t = i / fps
        p = i / max(1, n - 1)
        img = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        pen = Pen(img, lw)
        x = W * (x0 + (x1 - x0) * p)
        s = math.sin(t * 2 * math.pi * 1.8)
        if action in ("walk", "suitcase"):
            hands = standing_figure(pen, x, feet, size, facing, legs=(28 * s, -28 * s),
                                    arms=(-24 * s, 24 * s) if action == "walk" else (24 * s, -40),
                                    bob=-abs(s) * size * 0.02)
            if action == "suitcase":
                hx, hy = hands[1]
                bw, bh = size * 0.30, size * 0.38
                cx = x - facing * size * 0.42
                top = feet - bh - size * 0.05
                pen.line((hx, hy), (cx, top - size * 0.02))
                pen.poly([(cx - bw / 2, top), (cx + bw / 2, top), (cx + bw / 2, top + bh), (cx - bw / 2, top + bh)],
                         YELLOW)
                pen.circle((cx - bw * 0.3, feet - 8), size * 0.03)
                pen.circle((cx + bw * 0.3, feet - 8), size * 0.03)
        elif action == "wave":
            w = 25 * math.sin(t * 2 * math.pi * 1.6)
            standing_figure(pen, x, feet, size, facing, legs=(6, -6), arms=(-12, 112 + w))
        elif action == "celebrate":
            j = abs(math.sin(t * 2 * math.pi * 1.1)) * size * 0.18
            w = 12 * math.sin(t * 2 * math.pi * 2.2)
            standing_figure(pen, x, feet - j, size, facing, legs=(14, -14), arms=(130 + w, -130 - w))
        elif action == "relax":
            # lying on the sand, hands behind the head, one knee up, slow breathing
            b = math.sin(t * 2 * math.pi * 0.4) * size * 0.01
            gy = feet - size * 0.05
            L = size
            hx = x - L * 0.45
            head = (hx, gy - L * 0.13)
            neck = (hx + L * 0.13, gy - L * 0.06 - b)
            hip = (hx + L * 0.50, gy - L * 0.04)
            pen.line(neck, hip)
            pen.line(hip, (hip[0] + L * 0.2, gy - L * 0.28), (hip[0] + L * 0.42, gy - L * 0.02))
            pen.line(hip, (hip[0] + L * 0.45, gy - L * 0.03))
            pen.line(neck, (hx + L * 0.25, gy - L * 0.16), (hx + L * 0.42, gy - L * 0.10))
            _head(pen, head, L * 0.11, -1)
        elif action == "swim":
            yb = feet - size * 0.25 + math.sin(t * 2 * math.pi * 0.9) * size * 0.03
            L = size
            head = (x + facing * L * 0.40, yb - L * 0.05)
            sh = (x + facing * L * 0.22, yb)
            hip = (x - facing * L * 0.20, yb + L * 0.03)
            pen.line(sh, hip)
            k = math.sin(t * 2 * math.pi * 3) * 14
            pen.line(hip, _limb(hip, -facing * (90 + k), L * 0.42))
            pen.line(hip, _limb(hip, -facing * (90 - k), L * 0.42))
            for ph in (0, math.pi):
                a = (t * 2 * math.pi * 0.9 + ph)
                hand = (sh[0] + facing * math.cos(a) * L * 0.32, sh[1] - math.sin(a) * L * 0.25)
                pen.line(sh, hand)
            _head(pen, head, L * 0.11, facing)
        elif action == "drive":
            L = size
            cy = feet - L * 0.18
            wr = L * 0.11
            body = [(x - L * 0.45, cy - L * 0.20), (x + L * 0.45, cy - L * 0.20), (x + L * 0.50, cy + L * 0.06),
                    (x - L * 0.50, cy + L * 0.06)]
            standing_figure(pen, x - facing * L * 0.08, cy + L * 0.02, L * 0.62, facing, legs=(0, 0),
                            arms=(75, 65), bob=0)
            pen.poly(body, YELLOW, over=True)
            pen.top_segs = [((x + facing * L * 0.28, cy - L * 0.20), (x + facing * L * 0.20, cy - L * 0.40))]
            pen.top_circles = []
            for wx in (x - L * 0.30, x + L * 0.30):
                pen.top_circles.append(((wx, cy + L * 0.08), wr, (40, 40, 40, 255)))
                a = t * 12
                pen.top_segs.append(((wx - math.cos(a) * wr * 0.6, cy + L * 0.08 - math.sin(a) * wr * 0.6),
                                     (wx + math.cos(a) * wr * 0.6, cy + L * 0.08 + math.sin(a) * wr * 0.6)))
        pen.flush()
        yield img
