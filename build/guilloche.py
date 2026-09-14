"""Guilloché engravings.

Share certificates, stamp paper and banknotes carry the same fine interlaced
line-work, cut on a rose engine so it cannot be copied by hand. It is the visual
vernacular of corporate and financial instruments, so the blog uses it where
other blogs use stock photographs.

How a rose engine works, and so how this module works: one closed curve is cut,
the work is rotated by a tiny angle, and the same curve is cut again — dozens of
times. The copies interfere and weave into a lattice. Borders are made the same
way, with a wave shifted sideways instead of rotated.

That also keeps the files small. Each motif is written once into <defs> and
repeated with <use transform="…">, so a medallion of several hundred strokes
is a few kilobytes.

Every pattern is generated deterministically from a category's slug. The same
category always gets the same engraving; a new category gets a new one. The
SVGs are single-colour line art used as CSS masks, so the theme picks the ink.
"""

import hashlib
import math
import random

TAU = math.tau


def _rng(slug, salt):
    digest = hashlib.sha256(("%s/%s" % (slug, salt)).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:12], 16))


# ── motifs ────────────────────────────────────────────────────────────────
# A motif is (points, transforms). Transforms are ("rotate", deg, cx, cy) or
# ("translate", dx, dy). SVG output writes the points once and <use>s them;
# raster output (share cards) expands them.

def polar_ring(radius, amp, lobes, harmonic=0.0, pts_per_lobe=12, cx=0.0, cy=0.0):
    """r(θ) = R + a·sin(Lθ) + h·a·sin(3Lθ): a scalloped closed band."""
    n = lobes * pts_per_lobe
    pts = []
    for i in range(n + 1):
        t = TAU * i / n
        r = radius + amp * math.sin(lobes * t) + harmonic * amp * math.sin(3 * lobes * t)
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def circle(radius, cx, cy, n=180):
    return [(cx + radius * math.cos(TAU * i / n), cy + radius * math.sin(TAU * i / n))
            for i in range(n + 1)]


def woven_ring(radius, amp, lobes, copies, cx, cy, harmonic=0.0, pts_per_lobe=12):
    """The rose-engine step: rotate one ring through a single lobe's angle in
    `copies` equal increments."""
    base = polar_ring(radius, amp, lobes, harmonic, pts_per_lobe, cx, cy)
    step = 360.0 / lobes / copies
    return base, [("rotate", k * step, cx, cy) for k in range(copies)]


def woven_ribbon(y, amp, wavelength, strands, width, pts_per_wave=20):
    """A sine wave shifted sideways through one wavelength in `strands` steps.
    The base strand overhangs both ends by a wavelength so every shifted copy
    still spans the full width."""
    pts = []
    x = -wavelength
    step = wavelength / pts_per_wave
    while x <= width + wavelength:
        pts.append((x, y + amp * math.sin(TAU * x / wavelength)))
        x += step
    shift = wavelength / strands
    return pts, [("translate", -k * shift, 0) for k in range(strands)]


# ── compositions ──────────────────────────────────────────────────────────

def medallion(slug, cx, cy, size, fine=True):
    """The anatomy of a banknote medallion: an open lace border, a scalloped
    band that overlaps it, and a petalled rosette at the centre. Each category
    draws its own proportions, lobe counts and centre form, so no two match."""
    rng = _rng(slug, "medallion")
    s = size / 2
    k = 1.0 if fine else 0.5            # coarser, thicker version for small marks
    motifs = []

    # Outer lace. Few copies relative to amplitude keeps the lattice open
    # instead of filling in to a solid ring.
    outer_r = rng.uniform(0.80, 0.84)
    outer_amp = rng.uniform(0.07, 0.10)
    motifs.append(woven_ring(outer_r * s, outer_amp * s, rng.choice([24, 28, 30, 32, 36]),
                             max(5, int(rng.choice([9, 11, 12]) * k)), cx, cy))

    # Scalloped band, pushed out until it overlaps the lace.
    mid_amp = rng.uniform(0.13, 0.19)
    mid_r = outer_r - outer_amp - mid_amp * 0.55
    motifs.append(woven_ring(mid_r * s, mid_amp * s, rng.choice([9, 10, 12, 14, 16]),
                             max(5, int(rng.choice([10, 12, 14]) * k)), cx, cy,
                             harmonic=rng.uniform(0.18, 0.42), pts_per_lobe=16))

    # Centre: either a petalled rosette whose petals reach almost to the middle,
    # or a star of long narrow lobes. The choice is what separates categories
    # most at a glance.
    inner_r = mid_r - mid_amp * 0.9
    if rng.random() < 0.55:
        motifs.append(woven_ring(inner_r * 0.55 * s, inner_r * 0.42 * s, rng.choice([5, 6, 7, 8]),
                                 max(4, int(rng.choice([8, 10, 12]) * k)), cx, cy,
                                 harmonic=rng.uniform(0.0, 0.12), pts_per_lobe=30))
    else:
        motifs.append(woven_ring(inner_r * 0.5 * s, inner_r * 0.46 * s, rng.choice([9, 11, 12, 13]),
                                 max(4, int(rng.choice([6, 7, 8]) * k)), cx, cy,
                                 harmonic=-rng.uniform(0.2, 0.32), pts_per_lobe=28))

    motifs.append((circle(0.975 * s, cx, cy), []))
    motifs.append((circle(0.05 * s, cx, cy, 48), []))
    return motifs


def plate(slug, width=1600, height=440):
    """Post header: a woven ribbon across the full width, finer ribbons along
    both edges, double frame rules, and a medallion placed per category."""
    rng = _rng(slug, "plate")
    ribbons, medal = [], []

    wl = width / rng.choice([9, 10, 11, 12])
    ribbons.append(woven_ribbon(height / 2, height * 0.15, wl, rng.choice([22, 26, 30]), width))
    wl2 = wl * rng.choice([0.5, 0.6667, 1.5])
    ribbons.append(woven_ribbon(height / 2, height * 0.11, wl2, 16, width))
    for y in (height * 0.155, height * 0.845):
        ribbons.append(woven_ribbon(y, height * 0.022, width / 44, 5, width, pts_per_wave=14))

    mx = width * rng.uniform(0.66, 0.8)
    medal.extend(medallion(slug, mx, height / 2, height * 0.92))
    return ribbons, medal


# ── SVG output ────────────────────────────────────────────────────────────

def _num(v, precision=1):
    s = ("%%.%df" % precision) % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def path_data(points):
    """Relative line commands — about half the bytes of absolute ones."""
    x0, y0 = round(points[0][0], 1), round(points[0][1], 1)
    parts, px, py = [], x0, y0
    for x, y in points[1:]:
        x, y = round(x, 1), round(y, 1)
        if x == px and y == py:
            continue
        parts.append("%s %s" % (_num(x - px), _num(y - py)))
        px, py = x, y
    return "M%s %sl%s" % (_num(x0), _num(y0), " ".join(parts))


def _transform(t):
    if t[0] == "rotate":
        return "rotate(%s %s %s)" % (_num(t[1], 3), _num(t[2]), _num(t[3]))
    return "translate(%s %s)" % (_num(t[1], 2), _num(t[2], 2))


def svg(width, height, motifs, stroke):
    defs, body = [], []
    for i, (pts, transforms) in enumerate(motifs):
        if transforms:
            defs.append('<path id="m%d" d="%s"/>' % (i, path_data(pts)))
            body.extend('<use href="#m%d" transform="%s"/>' % (i, _transform(t)) for t in transforms)
        else:
            body.append('<path d="%s"/>' % path_data(pts))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'preserveAspectRatio="xMidYMid slice" fill="none" stroke="#000" '
            'stroke-width="%s" stroke-linecap="round" stroke-linejoin="round">'
            '<defs>%s</defs>%s</svg>' % (width, height, stroke, "".join(defs), "".join(body)))


# ── raster expansion (for Pillow) ─────────────────────────────────────────

def expand(motifs):
    """Apply each transform to its motif's points, yielding plain polylines."""
    for pts, transforms in motifs:
        if not transforms:
            yield pts
            continue
        for t in transforms:
            if t[0] == "rotate":
                a = math.radians(t[1])
                ca, sa, cx, cy = math.cos(a), math.sin(a), t[2], t[3]
                yield [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca)
                       for x, y in pts]
            else:
                yield [(x + t[1], y + t[2]) for x, y in pts]


# ── files ─────────────────────────────────────────────────────────────────

def rule_svg(width=720, height=30):
    """The engraved divider used for section breaks inside posts."""
    return svg(width, height, [woven_ribbon(height / 2, height * 0.3, width / 12, 7, width, 24)], 0.9)


def write_category_patterns(slug, out_dir):
    import os
    os.makedirs(out_dir, exist_ok=True)
    ribbons, medal = plate(slug)
    files = {
        "%s-ribbons.svg" % slug: svg(1600, 440, ribbons, 0.9),
        "%s-medal.svg" % slug: svg(1600, 440, medal, 0.85),
        "%s-rosette.svg" % slug: svg(400, 400, medallion(slug, 200, 200, 392), 0.7),
        "%s-mark.svg" % slug: svg(400, 400, medallion(slug, 200, 200, 392, fine=False), 2.2),
    }
    for name, data in files.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(data)
    return files
