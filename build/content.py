"""Loading posts and turning their Markdown into reader HTML.

A post is a folder: content/posts/<slug>/index.md (front matter + Markdown) and
any images beside it. That folder is the source of truth for the build — the
Notion sync writes it, and a local build reads only it, so the site never
depends on Notion being reachable.

Rendering does four things a plain Markdown converter does not:

1. Notes. `[^n]` references become sidenotes that sit in the right margin on
   wide screens and fold open inline on narrow ones. Pandoc writes Word
   endnotes in exactly this form, so an author's endnotes arrive intact.
2. Paragraph numbers. Top-level paragraphs get stable ids (#p7) and a margin
   number, so a post can be pinpoint-cited "at para 7".
3. Heading numerals. The submission guidelines number headings I / A / (i);
   the numeral is split out so it can be set apart typographically.
4. Figures, tables and dividers get the markup the stylesheet expects.
"""

import datetime as dt
import html
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import markdown
import yaml

MD_EXTENSIONS = ["tables", "sane_lists", "smarty", "md_in_html"]


# ── front matter ──────────────────────────────────────────────────────────

class ContentError(Exception):
    pass


def split_front_matter(text, source):
    if not text.startswith("---"):
        raise ContentError("%s: missing front matter (the file must start with ---)" % source)
    try:
        _, fm, body = text.split("---", 2)
    except ValueError:
        raise ContentError("%s: front matter is not closed with ---" % source)
    meta = yaml.safe_load(fm) or {}
    if not isinstance(meta, dict):
        raise ContentError("%s: front matter must be key: value pairs" % source)
    return meta, body.lstrip("\n")


def slugify(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-") or "section"


def smarten(text):
    """Curly quotes, apostrophes and dashes for front-matter strings, which
    never pass through the Markdown body renderer. Returned unescaped, because
    the templates escape on output."""
    if not text:
        return text
    out = markdown.markdown(str(text), extensions=["smarty"]).strip()
    out = re.sub(r"^<p>|</p>$", "", out)
    return html.unescape(re.sub(r"<[^>]+>", "", out))


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    parts = re.split(r"\s*(?:,|;|\band\b|&)\s*", str(value))
    return [p for p in (s.strip() for s in parts) if p]


# ── notes ─────────────────────────────────────────────────────────────────

NOTE_DEF = re.compile(r"^\[\^([^\]\s]+)\]:[ \t]?(.*)$")
NOTE_REF = re.compile(r"\[\^([^\]\s]+)\](?!:)")
TOKEN = "zqnote%dzq"
TOKEN_RE = re.compile(r"zqnote(\d+)zq")


def extract_notes(md_text):
    """Pull note definitions out of the Markdown, including multi-paragraph
    notes whose continuation lines are indented."""
    lines = md_text.split("\n")
    kept, notes, i = [], {}, 0
    while i < len(lines):
        m = NOTE_DEF.match(lines[i])
        if not m:
            kept.append(lines[i])
            i += 1
            continue
        key, buf = m.group(1), [m.group(2)]
        i += 1
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j][:1] in (" ", "\t") and lines[j].startswith(("    ", "\t")):
                    buf.append("")
                    i += 1
                    continue
                break
            if line.startswith("    "):
                buf.append(line[4:])
            elif line.startswith("\t"):
                buf.append(line[1:])
            else:
                break
            i += 1
        notes[key] = "\n".join(buf).strip()
    return "\n".join(kept), notes


def note_inner_html(note_md):
    """Notes live inside a <span>, so block elements become block-styled spans."""
    out = markdown.markdown(note_md, extensions=MD_EXTENSIONS).strip()
    out = re.sub(r"</?(ul|ol)>", "", out)
    out = re.sub(r"<(p|li|blockquote)>", '<span class="snp">', out)
    out = re.sub(r"</(p|li|blockquote)>", "</span>", out)
    return out


def sidenote(n, inner):
    return ('<span class="sn-wrap">'
            '<input type="checkbox" class="sn-toggle" id="sn-%(n)d" aria-label="Show note %(n)d">'
            '<label class="sn-ref" for="sn-%(n)d" data-note="%(n)d">%(n)d</label>'
            '<span class="sn" id="note-%(n)d" role="note"><span class="sn-no">%(n)d</span> %(inner)s</span>'
            '</span>') % {"n": n, "inner": inner}


# ── HTML passes ───────────────────────────────────────────────────────────

CONTAINERS = {"blockquote", "ul", "ol", "li", "table", "div", "figure", "aside", "details", "section"}
TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")


def number_paragraphs(body):
    """Give top-level paragraphs ids and a pinpoint link. The number sits at the
    end of the paragraph in source order (so it never becomes the paragraph's
    first letter) and is positioned into the left margin by CSS."""
    out, pos, depth, n = [], 0, 0, 0
    for m in TAG.finditer(body):
        closing, name, selfclose = m.group(1), m.group(2).lower(), m.group(3)
        if name in CONTAINERS and not selfclose:
            depth += -1 if closing else 1
            continue
        if name == "p" and depth == 0:
            if not closing:
                n += 1
                out.append(body[pos:m.start()])
                out.append('<p id="p%d">' % n)
                pos = m.end()
            else:
                out.append(body[pos:m.start()])
                out.append('<a class="pn" href="#p%d" aria-label="Link to paragraph %d">%d</a></p>' % (n, n, n))
                pos = m.end()
    out.append(body[pos:])
    return "".join(out), n


HEADING = re.compile(r"<h([2-4])>(.*?)</h\1>", re.S)
NUMERAL = {
    "2": re.compile(r"^([IVXLC]{1,7})[.)]\s+(.+)$", re.S),
    "3": re.compile(r"^([A-Z])[.)]\s+(.+)$", re.S),
    "4": re.compile(r"^\(([ivxlc]{1,6})\)\s+(.+)$", re.S),
}


def mark_headings(body):
    seen, sections = {}, []

    def repl(m):
        level, inner = m.group(1), m.group(2).strip()
        plain = html.unescape(re.sub(r"<[^>]+>", "", inner))
        numeral, text = "", inner
        nm = NUMERAL[level].match(plain)
        if nm:
            numeral = nm.group(1)
            text = re.sub(r"^\s*\(?%s[.)]?\s+" % re.escape(numeral), "", inner, count=1)
        base = slugify(re.sub(r"<[^>]+>", "", text))
        seen[base] = seen.get(base, 0) + 1
        hid = base if seen[base] == 1 else "%s-%d" % (base, seen[base])
        if level == "2":
            sections.append({"id": hid, "numeral": numeral, "title": html.unescape(re.sub(r"<[^>]+>", "", text))})
        num_html = '<span class="h-no">%s</span>' % numeral if numeral else ""
        return '<h%s id="%s">%s<span class="h-t">%s</span></h%s>' % (level, hid, num_html, text, level)

    return HEADING.sub(repl, body), sections


def dress_blocks(body):
    body = re.sub(r"<p>\s*(<img\b[^>]*?alt=\"([^\"]*)\"[^>]*>)\s*</p>",
                  lambda m: '<figure>%s%s</figure>' % (
                      m.group(1).replace("<img ", '<img loading="lazy" decoding="async" '),
                      '<figcaption>%s</figcaption>' % m.group(2) if m.group(2).strip() else ""),
                  body)
    body = re.sub(r"<table>", '<div class="table-wrap"><table>', body)
    body = body.replace("</table>", "</table></div>")
    body = re.sub(r"<hr\s*/?>", '<div class="ornament" role="separator"></div>', body)
    return body


def words_in(fragment):
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return len(re.findall(r"[\w’'-]+", text))


def render(md_text):
    md_text = md_text.replace("\r\n", "\n").replace("\r", "\n")
    body_md, note_defs = extract_notes(md_text)

    order = {}

    def ref(m):
        key = m.group(1)
        if key not in note_defs:
            return m.group(0)
        if key not in order:
            order[key] = len(order) + 1
        return TOKEN % order[key]

    body_md = NOTE_REF.sub(ref, body_md)
    body = markdown.markdown(body_md, extensions=MD_EXTENSIONS)
    body = dress_blocks(body)
    words = words_in(TOKEN_RE.sub("", body))
    body, paragraphs = number_paragraphs(body)
    body, sections = mark_headings(body)

    rendered = {n: note_inner_html(note_defs[k]) for k, n in order.items()}
    body = TOKEN_RE.sub(lambda m: sidenote(int(m.group(1)), rendered[int(m.group(1))]), body)
    return {
        "html": body,
        "words": words,
        "notes": len(order),
        "paragraphs": paragraphs,
        "sections": sections,
    }


# ── posts ─────────────────────────────────────────────────────────────────

@dataclass
class Post:
    slug: str
    title: str
    authors: list
    date: dt.date
    category: dict
    standfirst: str
    bios: list
    html: str
    words: int
    notes: int
    paragraphs: int
    sections: list
    source_dir: Path
    featured: bool = False
    specimen: bool = False
    preview_token: str = ""
    header_image: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def minutes(self):
        return max(1, round(self.words / 230))

    @property
    def byline(self):
        a = self.authors
        if not a:
            return ""
        return a[0] if len(a) == 1 else "%s and %s" % (", ".join(a[:-1]), a[-1])


def load_post(folder, categories, preview_token=""):
    index = folder / "index.md"
    meta, body = split_front_matter(index.read_text(encoding="utf-8"), index)

    missing = [k for k in ("title", "date", "category") if not meta.get(k)]
    if missing:
        raise ContentError("%s: missing %s" % (index, ", ".join(missing)))
    cat = categories.get(str(meta["category"]).strip())
    if not cat:
        by_name = {c["name"].lower(): c for c in categories.values()}
        cat = by_name.get(str(meta["category"]).strip().lower())
    if not cat:
        raise ContentError("%s: unknown category %r — add it to site.yml or fix the post"
                           % (index, meta["category"]))

    date = meta["date"]
    if isinstance(date, str):
        date = dt.date.fromisoformat(date[:10])
    elif isinstance(date, dt.datetime):
        date = date.date()

    r = render(body)
    standfirst = str(meta.get("standfirst") or "").strip()
    if not standfirst:
        first = re.search(r"<p id=\"p1\">(.*?)<a class=\"pn\"", r["html"], re.S)
        plain = html.unescape(re.sub(r"<[^>]+>", "", first.group(1))) if first else ""
        plain = re.sub(r"\s+", " ", plain).strip()
        standfirst = " ".join(plain.split()[:32]) + ("…" if len(plain.split()) > 32 else "")

    bios = meta.get("bios") or meta.get("bio") or []
    if isinstance(bios, str):
        bios = [b.strip() for b in bios.split("\n") if b.strip()]

    return Post(
        slug=str(meta.get("slug") or folder.name),
        title=smarten(str(meta["title"]).strip()),
        authors=as_list(meta.get("authors")),
        date=date,
        category=cat,
        standfirst=smarten(standfirst),
        bios=[smarten(b) for b in bios],
        html=r["html"],
        words=r["words"],
        notes=r["notes"],
        paragraphs=r["paragraphs"],
        sections=r["sections"],
        source_dir=folder,
        featured=bool(meta.get("featured")),
        specimen=bool(meta.get("specimen")),
        preview_token=preview_token,
        header_image=str(meta.get("header_image") or ""),
    )
