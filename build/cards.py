"""Share cards: the image WhatsApp, LinkedIn and X show when a post is shared.

1200 × 630, drawn with the same engraving as the post header so a shared link
is recognisably the Centre's. Cards are cached by a hash of what they show, so
an unchanged post is not redrawn on every build.
"""

import hashlib
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import guilloche

W, H = 1200, 630
SS = 2  # supersampling for the hairlines

PAPER = (251, 249, 245)
INK = (28, 24, 22)
INK_2 = (74, 66, 61)
MAROON = (95, 29, 37)
MAROON_DEEP = (61, 18, 24)
GOLD = (158, 107, 34)
GOLD_INK = (135, 90, 31)

FONTS = Path(__file__).parent / "fonts"


MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def _engrave(img, motifs, color, alpha, width, dx=0.0, dy=0.0, scale=1.0):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for pts in guilloche.expand(motifs):
        d.line([((x * scale + dx) * SS, (y * scale + dy) * SS) for x, y in pts],
               fill=color + (alpha,), width=max(1, round(width * SS)))
    img.alpha_composite(layer)


def _fit_title(draw, title, font_name, max_width, max_lines, sizes):
    for size in sizes:
        font = _font(font_name, size * SS)
        avg = font.getlength("abcdefghijklmnopqrstuvwxyz") / 26
        cols = max(8, int(max_width * SS / avg))
        lines = textwrap.wrap(title, width=cols)
        # tighten the wrap until every line actually fits
        while lines and max(font.getlength(l) for l in lines) > max_width * SS and cols > 8:
            cols -= 1
            lines = textwrap.wrap(title, width=cols)
        if len(lines) <= max_lines:
            return font, lines, size
    font = _font(font_name, sizes[-1] * SS)
    lines = textwrap.wrap(title, width=cols)[:max_lines]
    lines[-1] = lines[-1].rstrip(" ,;:") + "…"
    return font, lines, sizes[-1]


def draw_card(post, cfg, seal_path):
    img = Image.new("RGBA", (W * SS, H * SS), PAPER + (255,))

    # Engraving: medallion bleeding off the right edge, ribbon along the foot.
    _engrave(img, guilloche.medallion(post.engraving, 280, 330, 620), MAROON, 92, 1.0, dx=760, dy=-10)
    ribbon = [guilloche.woven_ribbon(H - 34, 9, W / 30, 7, W, 18)]
    _engrave(img, ribbon, GOLD, 120, 0.9)

    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W * SS, 10 * SS], fill=MAROON_DEEP + (255,))

    x = 72
    seal = Image.open(seal_path).convert("RGBA").resize((64 * SS, 64 * SS), Image.LANCZOS)
    img.alpha_composite(seal, (x * SS, 58 * SS))
    label = _font("HankenGrotesk-SemiBold.ttf", 19 * SS)
    d.text(((x + 84) * SS, 70 * SS), cfg["blog_name"].upper(), font=label, fill=INK, spacing=0)
    small = _font("HankenGrotesk-Medium.ttf", 15 * SS)
    d.text(((x + 84) * SS, 98 * SS), cfg["university"], font=small, fill=INK_2)

    date_font = _font("HankenGrotesk-SemiBold.ttf", 17 * SS)
    when = "%d %s %d" % (post.date.day, MONTHS[post.date.month - 1], post.date.year)
    d.text((x * SS, 186 * SS), when.upper(), font=date_font, fill=GOLD_INK)

    font, lines, size = _fit_title(d, post.title, "CormorantGaramond-SemiBold.ttf", 690, 4, [66, 58, 50, 44])
    y = 222
    lh = int(size * 1.06)
    for line in lines:
        d.text((x * SS, y * SS), line, font=font, fill=INK)
        y += lh

    if post.byline:
        by = _font("SourceSerif4-Italic.ttf", 27 * SS)
        d.text((x * SS, (y + 22) * SS), post.byline, font=by, fill=INK_2)

    return img.resize((W, H), Image.LANCZOS).convert("RGB")


def build_card(post, cfg, seal_path, out_path, cache_dir):
    key = hashlib.sha256(json.dumps([
        post.title, post.byline, post.engraving, post.date.isoformat(), cfg["blog_name"], cfg["university"], 4,
    ]).encode("utf-8")).hexdigest()[:20]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / ("%s.png" % key)
    if not cached.exists():
        draw_card(post, cfg, seal_path).save(cached, optimize=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(cached.read_bytes())
