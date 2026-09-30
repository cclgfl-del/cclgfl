"""One-off import of the Centre's earlier blog (the CBFL Blog, on Wix) into
content/posts, as Markdown that the site builds like any other post.

    python build/import_cbfl.py --raw <folder of *.html.gz> [--out content/posts] [--limit N]

Needs beautifulsoup4 and lxml (not in requirements.txt: nothing in the
publishing pipeline uses this). --raw is a snapshot of each post's page,
saved one file per post; the old domain lapses in October 2026, so the
snapshot is the source of record and this script only reads it.

What it keeps: title, authors and their one-line bio (with links), the
original publication date, and the body: paragraphs, headings, lists, quotes,
tables, links and images. What it changes: headings the authors made by
bolding or underlining a short line become real headings, tracking parameters
are stripped from links, and each post records where it was first published.
Everything it cannot convert with confidence is written to the report, not
guessed at.
"""

import argparse
import datetime as dt
import gzip
import html as htmllib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import requests  # noqa: E402
import yaml  # noqa: E402
from bs4 import BeautifulSoup, Comment, NavigableString, Tag  # noqa: E402

OLD_HOST = "www.cbflnludelhi.in"
ARCHIVE_NAME = "CBFL Blog"
KNOWN_SLUGS = set()          # filled from the snapshot, so links between posts can be kept
# Addresses the old site answered with another post's page (its canonical address is the value).
SLUG_ALIASES = {
    "a-comparative-study-of-antitrust-implications-in-indian-and-eu-competition-law-with-specific-focus-o-1":
        "a-comparative-study-of-antitrust-implications-in-indian-and-eu-competition-law-with-specific-focus-2",
}
BLOCK_TAGS = {"p", "div", "ul", "ol", "li", "table", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
              "figure", "pre", "hr", "img"}
TRACKING = re.compile(r"^(utm_|lipi$|trk|fbclid$|gclid$|mc_|trackingid$|originalsubdomain$|igshid$)", re.I)
UNHANDLED = {"iframe", "video", "audio", "object", "embed", "canvas", "form"}
CHROME = {"script", "style", "noscript", "button", "svg", "input"}        # page furniture, not content


# ── inline text ───────────────────────────────────────────────────────────

def clean_url(u):
    u = (u or "").strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        return u
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunparse(p._replace(query=urlencode(q)))


def esc(t):
    t = t.replace(" ", " ").replace("​", "").replace("﻿", "").replace(" ", " ")
    t = re.sub(r"[ \t\r\n]+", " ", t)
    t = re.sub(r"([\\`*_\[\]>])", r"\\\1", t)
    return t.replace("<", "&lt;")


def wrap(s, mark):
    core = s.strip(" ")
    if not core.strip():
        return s
    lead, trail = s[:len(s) - len(s.lstrip(" "))], s[len(s.rstrip(" ")):]
    parts = core.split("  \n")
    return lead + "  \n".join(mark + p.strip(" ") + mark if p.strip() else p for p in parts) + trail


def md_link(text, href):
    href = href.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    return "[%s](%s)" % (text, href)


class Ctx:
    def __init__(self):
        self.internal_links = []
        self.warnings = []
        self.images = []          # (src, alt) in order


def inline(node, ctx):
    out = []
    for c in node.children:
        if isinstance(c, Comment):
            continue
        if isinstance(c, NavigableString):
            out.append(esc(str(c)))
            continue
        n = c.name
        if n == "br":
            out.append("  \n")
        elif n in ("strong", "b"):
            out.append(wrap(inline(c, ctx), "**"))
        elif n in ("em", "i"):
            out.append(wrap(inline(c, ctx), "*"))
        elif n in ("s", "strike", "del"):
            inner = inline(c, ctx)
            out.append("<del>%s</del>" % inner if inner.strip() else inner)
        elif n in ("sup", "sub"):
            inner = inline(c, ctx)
            out.append("<%s>%s</%s>" % (n, inner, n) if inner.strip() else inner)
        elif n == "a":
            text = inline(c, ctx)
            href = clean_url(c.get("href"))
            if not href or not text.strip():
                out.append(text)
            else:
                if urlparse(href).netloc == OLD_HOST:
                    target = re.match(r"^/post/([^/?#]+)", urlparse(href).path)
                    slug = SLUG_ALIASES.get(target.group(1), target.group(1)) if target else ""
                    if slug in KNOWN_SLUGS:
                        href = "../%s/" % slug
                    else:
                        ctx.internal_links.append(href)
                lead, trail = text[:len(text) - len(text.lstrip(" "))], text[len(text.rstrip(" ")):]
                out.append(lead + md_link(text.strip(" "), href) + trail)
        elif n == "img":
            src = c.get("src") or c.get("data-src") or ""
            if src:
                ctx.images.append((src, c.get("alt") or ""))
                out.append("\x00IMG%d\x00" % (len(ctx.images) - 1))
        elif n in CHROME:
            continue
        elif n in UNHANDLED:
            ctx.warnings.append("unhandled <%s> inside text" % n)
        else:                       # span, u, font, mark, ...: keep the text
            out.append(inline(c, ctx))
    return "".join(out)


def tidy_inline(s):
    s = re.sub(r"\*\*( *)\*\*", r"\1", s)          # adjacent bold runs become one
    s = re.sub(r"(?: {2}\n)+$", "", s)
    s = re.sub(r"^(?: {2}\n)+", "", s)
    s = re.sub(r"[ ]{2,}(?!\n)", " ", s)
    return s.strip()


def guard_block_start(s):
    s = re.sub(r"^(\d+)([.)])(\s|$)", r"\1\\\2\3", s)
    return re.sub(r"^([-+#])(\s|#|$)", r"\\\1\2", s)


# ── blocks ────────────────────────────────────────────────────────────────

def text_nodes(node):
    for t in node.find_all(string=True):
        if isinstance(t, Comment):
            continue
        if str(t).replace(" ", " ").replace("​", "").strip():
            yield t


def all_within(node, names, skip_links=False):
    seen = False
    for t in text_nodes(node):
        seen = True
        ok = False
        for p in t.parents:
            if p is node:
                break
            if p.name in names:
                ok = True
                break
        if not ok:
            return False
        if skip_links and any(p.name == "a" for p in t.parents):
            return False
    return seen


def is_leaf_div(el):
    """A div that holds only inline content is a paragraph in all but name."""
    return el.name == "div" and not el.find(list(BLOCK_TAGS))


def para_block(el, ctx):
    md = tidy_inline(inline(el, ctx))
    plain = re.sub(r"\s+", " ", el.get_text(" ", strip=True).replace(" ", " ").replace("​", ""))
    return {"k": "p", "md": md, "plain": plain,
            "bold": all_within(el, {"strong", "b"}),
            "under": all_within(el, {"u"}, skip_links=True) and not all_within(el, {"strong", "b"})}


def render_list(el, ctx, depth=0):
    lines = []
    ordered = el.name == "ol"
    for i, li in enumerate(el.find_all("li", recursive=False), 1):
        parts, nested = [], []
        for c in li.children:
            if isinstance(c, Tag) and c.name in ("ul", "ol"):
                nested.append(render_list(c, ctx, depth + 1))
            elif isinstance(c, Tag) and (c.name in ("p", "div") or c.name.startswith("h")):
                inner = tidy_inline(inline(c, ctx))
                if inner:
                    parts.append(inner)
            elif isinstance(c, NavigableString):
                inner = tidy_inline(esc(str(c)))
                if inner:
                    parts.append(inner)
            elif isinstance(c, Tag):
                inner = tidy_inline(inline(c, ctx))
                if inner:
                    parts.append(inner)
        text = " ".join(parts)
        marker = ("%d. " % i) if ordered else "- "
        lines.append("    " * depth + marker + text)
        lines.extend(nested)
    return "\n".join(lines)


def render_table(el, ctx):
    rows = []
    for tr in el.find_all("tr"):
        cells = []
        for td in tr.find_all(["td", "th"], recursive=False):
            paras = [tidy_inline(inline(p, ctx)) for p in (td.find_all(["p", "div"]) if td.find(["p", "div"]) else [td])
                     if not p.find(["p", "div"])]
            cell = "<br>".join(p for p in paras if p).replace("|", "\\|")
            cells.append(cell or " ")
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [" "] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join([" --- "] * width) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def walk(node, out, ctx):
    for c in node.children:
        if not isinstance(c, Tag):
            continue
        n = c.name
        if n in CHROME:
            continue
        if n in ("h1", "h2", "h3", "h4", "h5", "h6"):
            md = tidy_inline(inline(c, ctx))
            if md:
                out.append({"k": "h", "lvl": int(n[1]), "md": md, "plain": c.get_text(" ", strip=True)})
        elif n == "p" or is_leaf_div(c):
            b = para_block(c, ctx)
            if b["md"]:
                out.append(b)
        elif n in ("ul", "ol"):
            out.append({"k": "list", "md": render_list(c, ctx)})
        elif n == "blockquote":
            inner = []
            walk(c, inner, ctx)
            text = "\n\n".join(b["md"] for b in inner if b.get("md"))
            if text:
                out.append({"k": "quote", "md": "\n".join("> " + l if l else ">" for l in text.split("\n"))})
        elif n == "table":
            md = render_table(c, ctx)
            if md:
                out.append({"k": "table", "md": md})
        elif n == "hr":
            out.append({"k": "hr", "md": "---"})
        elif n == "img":
            ctx.images.append((c.get("src") or "", c.get("alt") or ""))
            out.append({"k": "p", "md": "\x00IMG%d\x00" % (len(ctx.images) - 1), "plain": "", "bold": False, "under": False})
        elif n in UNHANDLED:
            ctx.warnings.append("unhandled <%s>" % n)
        else:
            walk(c, out, ctx)


# ── one post ──────────────────────────────────────────────────────────────

BIO_WORDS = re.compile(r"\b(?:students?|advocates?|lawyers?|associates?|professor|researchers?|research|partner|graduates?|"
                       r"intern|counsel|alumn\w*|pursuing|works?|working|lecturer|scholar|founder)\b", re.I)

INTRO = re.compile(r"^\s*(?:the\s+)?(?:author|authors|writer|writers|contributor|contributors)\b", re.I)
NUMERAL = re.compile(r"^(?:[IVXLC]+|[A-Z]|\d+)[.)]\s*\S")


ACRONYMS = {"SEBI", "CCI", "ESG", "RERA", "MCA", "CDS", "IBC", "RBI", "NCLT", "NCLAT", "GST", "FDI", "AI", "US", "UK", "EU"}
SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to",
         "with", "within", "vs", "v", "via"}
ROMANS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII"}
# where the rule cannot know (a company name, a plural acronym)
TITLE_FIXES = {
    "CORPORATE GUARANTEE: AN INTERNATIONAL TRANSACTION?CRAYON GROUP AS V. ACIT":
        "Corporate Guarantee: An International Transaction? Crayon Group AS v. ACIT",
    "SEBI MASTER CIRCULAR: A CRITICAL DISSECTION OF AIFS' CDS REGULATIONS":
        "SEBI Master Circular: A Critical Dissection of AIFs’ CDS Regulations",
}


def clean_title(t):
    """A title typed in capitals is set in title case; a stray full stop after
    the last word goes. Titles are otherwise exactly as published."""
    t = TITLE_FIXES.get(t, t)
    if t.upper() == t and len(re.findall(r"[A-Z]", t)) > 6:
        out, start = [], True
        for w in t.split(" "):
            def fix(m, start=start):
                tok = m.group(0)
                base = re.match(r"[A-Za-z]+", tok).group(0)
                suffix = tok[len(base):].lower()
                if base in ACRONYMS or base in ROMANS:
                    return base + suffix
                if base.lower() in SMALL and not start:
                    return base.lower() + suffix
                return base.capitalize() + suffix
            out.append(re.sub(r"[A-Za-z]+(?:['’][A-Za-z]+)?", fix, w))
            start = w.endswith((":", "?", "!")) or w in ("-", "–")
        t = " ".join(out)
        t = re.sub(r"(\w)- (Part\b)", r"\1 – \2", t)
    if t.endswith(".") and not re.search(r"\b(?:Ltd|Pvt|Inc|Corp|Co|No|v|vs)\.$", t):
        t = t[:-1]
    return t


def norm_title(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def looks_like_heading(plain):
    """A whole paragraph set in bold or underline, short, and not a sentence."""
    words = plain.split()
    if not words or len(words) > 30:
        return False
    if plain.rstrip().endswith((";", ",")):
        return False
    if plain.rstrip().endswith(".") and not (NUMERAL.match(plain) and len(words) <= 12):
        return False
    return True


ROMAN_UP = re.compile(r"^([IVXLC]{1,7})[.)]\s*(?=\S)")
ALPHA_UP = re.compile(r"^([A-Z])[.)]\s+")
ROMAN_LO = re.compile(r"^\(?([ivxlc]{1,6})[.)]\s+")


def heading_levels(items):
    """items: [(style_level, plain_text)] in document order -> final levels.
    Numbering decides where it can (I. is a section, A. a subsection, i. sits
    beneath whatever precedes it); otherwise the author's bold / underline
    does. No level skips a step, and the shallowest is always 2."""
    levels, parent, last_alpha = [], None, None
    for style, plain in items:
        one = re.match(r"^([A-Z])[.)]", plain)
        # C, L, I, V and X are letters as well as numerals: a letter that
        # follows the previous letter (B, then C) is the lettered series.
        if one and last_alpha and ord(one.group(1)) == ord(last_alpha) + 1:
            lvl, last_alpha = 3, one.group(1)
        elif ROMAN_UP.match(plain):
            lvl = 2
        elif ALPHA_UP.match(plain):
            lvl, last_alpha = 3, one.group(1)
        elif ROMAN_LO.match(plain):
            lvl = (parent + 1) if parent else style
        else:
            lvl = style
        if not ROMAN_LO.match(plain):
            parent = lvl
        levels.append(lvl)
    shallow = min(levels) if levels else 2
    levels = [l - shallow + 2 for l in levels]
    prev = 1
    for i, l in enumerate(levels):
        levels[i] = min(l, prev + 1, 4)
        prev = levels[i]
    return levels


DOUBLE_LETTER = re.compile(r"^[A-Z][.)]\s*(?=[A-Z][.)]\s)")


def heading_text(md, plain):
    text = re.sub(r"(?<!\\)\*+", "", md)
    text = re.sub(r"^(?:([IVXLC]{1,7}|[A-Z])([.)]))(?=[A-Z])", r"\1\2 ", text)     # "III.Conflicts"
    text = re.sub(r"^(\d{1,2}[.)])(?=[A-Za-z])", r"\1 ", text)                       # "1.Defining"
    text = re.sub(r"(?<![.\s])\.$", "", text) if len(plain.split()) > 12 else text  # a stray full stop after a long heading
    m = ROMAN_LO.match(plain)
    if m and not ROMAN_UP.match(plain):
        text = re.sub(r"^\(?%s[.)]\s+" % m.group(1), "(%s) " % m.group(1), text)
    return text


NAME_END = re.compile(
    r",\s+(?=(?:both\s+)?(?:an?\s|the\s|students?\b|final\b|penultimate\b|pre-final\b|recent\b|alumn|advocate|associate|lawyer|"
    r"research|assistant|junior|senior|counsel|partner|\w+(?:-|\s)(?:and\s+\w+\s+)?year\b|\d))", re.I)


DESCRIPTORS = {"advocate", "adv", "advocates", "associate", "partner", "counsel", "lawyer", "esq", "dr", "prof",
               "student", "students", "founder", "professor"}


def split_names(text):
    parts = re.split(r"\s*(?:,|&|\band\b)\s*", text)
    return [p.strip(" .") for p in parts if p.strip(" .") and p.strip(" .").casefold() not in DESCRIPTORS]


def squash(text):
    """Text as bare letters with link addresses removed, to ask whether a name
    appears even when a link or a stray space happens to split it."""
    text = re.sub(r"\]\([^)]*\)", "", text)
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def parse_intro(plain, md):
    """(authors, bio_markdown) from the 'The author is …' line, else ([], '')."""
    m = re.match(r"^\s*(?:the\s+)?(?:author|authors|writer|writers|contributor|contributors)\s+(?:is|are|was|were)\s+(.*)$", plain, re.I | re.S)
    names = []
    if m:
        rest = m.group(1)
        cut = NAME_END.search(rest)
        head = rest[:cut.start()] if cut else rest.split(",")[0]
        names = split_names(head)
    return names


def bio_from(el_md):
    # the intro line as plain text plus links, no bold/italic markers
    s = re.sub(r"\*+", "", el_md)
    s = re.sub(r"\\([\\`*_\[\]>.\-+#()])", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)([A-Za-z]+)", r"[\1\3](\2)", s)   # a link that stops a letter short of the name
    return re.sub(r"\s+", " ", s).strip()


def download_image(src, dest_dir, n, session):
    m = re.match(r"https://static\.wixstatic\.com/media/([^/]+?)(?:/v1/.*)?$", src)
    if m:
        media = m.group(1)
        ext = Path(media.split("~")[0]).suffix.lower() or ".jpg"
        url = "https://static.wixstatic.com/media/%s/v1/fit/w_1400,h_2000,q_88/file%s" % (media, ext)
    else:
        url = src
        ext = Path(urlparse(src).path).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    name = "image-%d%s" % (n, ext)
    r = session.get(url, timeout=60)
    r.raise_for_status()
    (dest_dir / name).write_bytes(r.content)
    return name


def convert(html, want_images, out_dir, session):
    soup = BeautifulSoup(html, "lxml")
    ld = None
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "BlogPosting":
            ld = data
            break
    ld = ld or {}                       # a few pages carry empty structured data
    canonical = soup.find("link", rel="canonical")
    url = ld["mainEntityOfPage"]["url"] if isinstance(ld.get("mainEntityOfPage"), dict) else ld.get("url")
    url = url or (canonical.get("href") if canonical else "")
    if not url:
        raise ValueError("no address for the post")
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    # The page's own title, not the metadata copy: Wix cuts that off at about 110 characters.
    heading = soup.select_one('[data-hook="post-title"]')
    shown = heading.get_text() if heading else ""
    title = re.sub(r"\s+", " ", htmllib.unescape(shown or ld.get("headline") or "")).strip()
    if not title:
        raise ValueError("no title")
    title = clean_title(title)
    if not ld.get("author"):
        who = soup.select_one('[data-hook="user-name"]')
        ld["author"] = {"name": who.get_text(strip=True) if who else ""}
    if not ld.get("datePublished"):
        ld["datePublished"] = "1970-01-01"

    shown = soup.select_one('[data-hook="time-ago"]')
    date = None
    if shown:
        try:
            date = dt.datetime.strptime(shown.get_text(strip=True), "%b %d, %Y").date()
        except ValueError:
            date = None
    if date is None:
        date = dt.date.fromisoformat(ld["datePublished"][:10])

    body = soup.select_one('[data-hook="post-description"]')
    if body is None:
        raise ValueError("no post body")
    ctx = Ctx()
    blocks = []
    walk(body, blocks, ctx)

    # drop empties and the repeat of the title
    blocks = [b for b in blocks if b.get("md", "").strip()]
    while blocks and blocks[0]["k"] in ("p", "h") and norm_title(blocks[0].get("plain", "")) == norm_title(title):
        blocks.pop(0)

    notes = list(ctx.warnings)
    authors, bios = [], []
    wix_author = htmllib.unescape((ld.get("author") or {}).get("name", "")).strip()
    wix_names = split_names(wix_author)

    def names_author(b):
        text = b["plain"].casefold()
        return (b["k"] == "p" and len(b["plain"].split()) <= 60 and not b["bold"]
                and any(n.casefold() in text for n in wix_names) and BIO_WORDS.search(b["plain"])
                and re.search(r"\b(?:is|are|was|were)\b", b["plain"]))

    if blocks and blocks[0]["k"] == "p" and (INTRO.match(blocks[0]["plain"]) or names_author(blocks[0])):
        intro = blocks.pop(0)
        authors = parse_intro(intro["plain"], intro["md"])
        bios = [bio_from(intro["md"])]
        if not authors and not wix_names:
            notes.append("could not read author names from: %s" % intro["plain"][:100])
    else:
        notes.append("no author line")
    intro_text = squash(bios[0]) if bios else ""
    if wix_names and intro_text and all(squash(n) in intro_text for n in wix_names) and len(wix_names) >= len(authors):
        authors = wix_names
    elif not authors and wix_names:
        authors = wix_names
        notes.append("author taken from the Wix account: %s" % ", ".join(wix_names))
    elif wix_names and authors and [a.casefold() for a in authors] != [w.casefold() for w in wix_names]:
        notes.append("authors differ: intro %s / Wix %s" % (authors, wix_names))

    # headings: real ones if the author used them, otherwise bold / underlined short lines
    real = sorted({b["lvl"] for b in blocks if b["k"] == "h"})
    for b in blocks:
        b["head"] = None
        if b["k"] == "h":
            b["head"] = 1 + real.index(b["lvl"])
        elif b["k"] == "p" and looks_like_heading(b["plain"]):
            b["head"] = 1 if b["bold"] else 2 if b["under"] else None
    if sum(1 for b in blocks if b["head"]) >= 2:      # this author sets headings in bold: a bold line that ends in a full stop is one too
        for b in blocks:
            if (not b["head"] and b["k"] == "p" and b["bold"] and len(b["plain"].split()) <= 30
                    and not b["plain"].rstrip().endswith((";", ","))):
                b["head"] = 1
    for b in blocks:                          # "C. A. Persons…", left over from renumbering: keep the later letter
        if b["head"]:
            b["md"] = DOUBLE_LETTER.sub("", re.sub(r"(?<!\\)\*+", "", b["md"]))
            b["plain"] = DOUBLE_LETTER.sub("", b["plain"])
    marked = [b for b in blocks if b["head"]]
    for b, lvl in zip(marked, heading_levels([(b["head"] + 1, b["plain"]) for b in marked])):
        b["head"] = lvl
    if real and any(b["k"] == "p" and b["head"] for b in blocks):
        notes.append("mixes real headings with bold lines: check the levels")
    lines = []
    for b in blocks:
        if b["head"]:
            lines.append("#" * b["head"] + " " + heading_text(b["md"], b["plain"]))
        elif b["k"] == "p":
            lines.append(guard_block_start(b["md"]))
        else:
            lines.append(b["md"])
    md = "\n\n".join(lines)

    # images
    def put_image(m):
        idx = int(m.group(1))
        src, alt = ctx.images[idx]
        if not want_images:
            return "![%s](%s)" % (alt, src)
        try:
            name = download_image(src, out_dir, idx + 1, session)
        except Exception as e:  # noqa: BLE001
            notes.append("image not downloaded (%s): %s" % (e, src))
            return "![%s](%s)" % (alt, src)
        return "![%s](%s)" % (alt.replace("]", ""), name)
    md = re.sub(r"\x00IMG(\d+)\x00", put_image, md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"

    words = len(re.findall(r"[\w’'-]+", re.sub(r"\(https?://[^)]*\)", "", re.sub(r"[*#>\\`\[\]]", " ", md))))
    return {
        "slug": slug, "url": url, "title": title, "authors": authors, "bios": bios, "date": date,
        "md": md, "words": words, "notes": notes, "internal_links": ctx.internal_links,
        "images": len(ctx.images), "wix_author": wix_author,
        "orig_words": len(re.findall(r"[\w’'-]+", body.get_text(" "))),
        "orig_links": len(body.find_all("a", href=True)),
        "md_links": len(re.findall(r"\]\(https?://|\]\(\.\./|\]\(mailto:", md)),
    }


def write_post(rec, out_root):
    folder = out_root / rec["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "title": rec["title"], "slug": rec["slug"],
        "authors": rec["authors"], "date": rec["date"].isoformat(),
    }
    if rec["bios"]:
        meta["bios"] = rec["bios"]
    meta["archive"] = ARCHIVE_NAME
    meta["archive_url"] = rec["url"]
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=10000)
    (folder / "index.md").write_text("---\n%s---\n\n%s" % (front, rec["md"]), encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "content" / "posts"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    files = sorted(Path(args.raw).glob("*.html.gz"))
    KNOWN_SLUGS.update(f.name[:-len(".html.gz")] for f in files)
    if args.limit:
        files = files[:args.limit]
    out_root = Path(args.out)
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
    records, failed = [], []
    for f in files:
        try:
            html = gzip.decompress(f.read_bytes()).decode("utf-8")
            # the post's own folder exists before its images are downloaded
            slug_guess = f.name.replace(".html.gz", "")
            target = out_root / slug_guess
            target.mkdir(parents=True, exist_ok=True)
            rec = convert(html, not args.no_images, target, session)
            if rec["slug"] != slug_guess:
                target.rmdir() if not any(target.iterdir()) else None
                (out_root / rec["slug"]).mkdir(parents=True, exist_ok=True)
                for extra in target.iterdir():
                    extra.rename(out_root / rec["slug"] / extra.name)
                target.rmdir()
            write_post(rec, out_root)
            records.append(rec)
        except Exception as e:  # noqa: BLE001
            failed.append((f.name, repr(e)))
            leftover = out_root / f.name[:-len(".html.gz")]
            if leftover.is_dir() and not any(leftover.iterdir()):
                leftover.rmdir()
    # A repeat is dropped when a reader would see the same words: the old site's
    # second copy of "Huge Backlog…" differs only in one link being split in two.
    seen, kept = {}, []
    for rec in sorted(records, key=lambda r: r["date"]):
        words = re.sub(r"\]\([^)]*\)", "]", rec["md"])
        key = (norm_title(rec["title"]), re.sub(r"[\W_]+", "", words.lower()))
        if key in seen:
            print("  duplicate of %s: dropped %s" % (seen[key], rec["slug"]))
            shutil.rmtree(out_root / rec["slug"], ignore_errors=True)
            continue
        seen[key] = rec["slug"]
        kept.append(rec)
    records = kept
    print("converted %d, failed %d" % (len(records), len(failed)))
    for name, e in failed:
        print("  FAILED", name, e)
    if args.report:
        slim = [{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in r.items() if k != "md"} for r in records]
        Path(args.report).write_text(json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
