"""Turning a manuscript into post Markdown — from a Word file or a Notion page.

Kept apart from the Notion sync so both conversions can be tested without an
API token (see build/selftest.py).
"""

import re
import unicodedata
from pathlib import Path

ROMAN = re.compile(r"^(?:[IVXLC]{1,7})[.)]?\s+\S")
LETTER = re.compile(r"^[A-Z][.)]\s+\S")


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", "", s)


def _strip_marks(line):
    """Remove emphasis and underline markers, for comparing a line's text."""
    line = re.sub(r"</?u>", "", line)
    return re.sub(r"(\*\*|__|\*|_)", "", line).strip()


# ── Word ──────────────────────────────────────────────────────────────────

def docx_to_markdown(docx_path, post_dir, title=""):
    """Convert with pandoc. Word footnotes and endnotes both arrive as `[^n]`
    notes, which the renderer places in the margin. Images are extracted into
    the post's folder."""
    import pypandoc

    post_dir = Path(post_dir)
    post_dir.mkdir(parents=True, exist_ok=True)
    md = pypandoc.convert_file(
        str(docx_path), "gfm", format="docx",
        extra_args=["--wrap=none", "--extract-media=%s" % post_dir.as_posix()],
    )
    prefix = post_dir.as_posix().rstrip("/") + "/"
    md = md.replace(prefix, "")
    return tidy_word_markdown(md, title)


def tidy_word_markdown(md, title=""):
    """Undo the habits of Word manuscripts:
    - the title typed as the first line of the document (it lives in Notion);
    - headings made with bold or underline instead of heading styles, which is
      what the submission guidelines ask authors to do;
    - pandoc's empty HTML comments and stray line breaks."""
    md = md.replace("\r\n", "\n").replace("\r", "\n")   # pandoc writes CRLF on Windows
    md = re.sub(r"<!-- -->\n?", "", md)
    blocks = [b for b in re.split(r"\n{2,}", md.strip())]

    if blocks and title:
        first = _strip_marks(blocks[0].lstrip("# ").strip())
        if _norm(first) and (_norm(first) == _norm(title) or _norm(title).startswith(_norm(first))):
            blocks = blocks[1:]

    out = []
    for b in blocks:
        s = b.strip()
        is_note = s.startswith("[^")
        single = "\n" not in s
        if single and not is_note and not s.startswith(("#", "|", ">", "-", "*   ", "1.")):
            words = len(_strip_marks(s).split())
            bold = re.fullmatch(r"\*\*(.+)\*\*", s)
            under = re.fullmatch(r"<u>(.+)</u>", s) or re.fullmatch(r"\*\*<u>(.+)</u>\*\*", s)
            inner = _strip_marks(s)
            if (bold or under) and words <= 16 and not inner.endswith((".", ":", ";")) or \
               (bold or under) and ROMAN.match(inner):
                if under and not bold and not ROMAN.match(inner):
                    out.append("### " + inner)
                elif LETTER.match(inner) and not ROMAN.match(inner):
                    out.append("### " + inner)
                else:
                    out.append("## " + inner)
                continue
        # Pandoc headings from real Word heading styles: shift down one level,
        # since the post title is the page's only h1.
        m = re.match(r"^(#{1,5})\s+(.*)$", s)
        if m and single:
            out.append("#" * (len(m.group(1)) + 1) + " " + _strip_marks(m.group(2)))
            continue
        out.append(b)
    return "\n\n".join(out).strip() + "\n"


# ── Notion blocks ─────────────────────────────────────────────────────────

MD_SPECIAL = re.compile(r"([\\`*_])")


def rich_to_md(rich):
    parts = []
    for r in rich or []:
        t = r.get("plain_text", "")
        if not t:
            continue
        a = r.get("annotations", {}) or {}
        href = r.get("href")
        if a.get("code"):
            t = "`%s`" % t
        else:
            t = MD_SPECIAL.sub(r"\\\1", t)
        lead = t[: len(t) - len(t.lstrip())]
        trail = t[len(t.rstrip()):]
        core = t.strip()
        if core:
            if a.get("bold"):
                core = "**%s**" % core
            if a.get("italic"):
                core = "*%s*" % core
            if a.get("strikethrough"):
                core = "~~%s~~" % core
            if href:
                core = "[%s](%s)" % (core, href)
        parts.append(lead + core + trail)
    text = "".join(parts)
    # Editors type note markers as [^1]; escaping must not break them.
    return re.sub(r"\[\\\^(\w+)\]", r"[^\1]", text)


NOTES_HEADINGS = {"notes", "endnotes", "footnotes", "references"}


def blocks_to_markdown(blocks, fetch_children, fetch_image):
    """Convert a Notion page's blocks. `fetch_children(block_id)` returns child
    blocks; `fetch_image(url, index)` stores an image and returns its filename.

    Notes convention for posts written in Notion: type [^1] in the text, and put
    a heading called "Notes" at the end followed by a numbered list — item 1 is
    note 1, and so on."""
    lines = []
    state = {"notes": False, "note_n": 0, "image_n": 0}

    def walk(items, depth=0):
        numbered = 0
        for b in items:
            kind = b.get("type")
            data = b.get(kind, {}) or {}
            rich = data.get("rich_text", [])
            text = rich_to_md(rich)
            indent = "    " * depth

            if kind != "numbered_list_item":
                numbered = 0
            is_list = kind in ("bulleted_list_item", "numbered_list_item", "to_do") and not state["notes"]
            if not is_list and depth == 0 and lines and lines[-1] != "":
                lines.append("")     # a list must end before the next block starts

            if kind in ("heading_1", "heading_2", "heading_3"):
                plain = "".join(r.get("plain_text", "") for r in rich).strip()
                if plain.casefold().rstrip(":") in NOTES_HEADINGS:
                    state["notes"] = True
                    continue
                level = {"heading_1": 2, "heading_2": 3, "heading_3": 4}[kind]
                lines.append("#" * level + " " + text)
            elif kind == "paragraph":
                lines.append(indent + text if text else "")
            elif kind == "numbered_list_item" and state["notes"] and depth == 0:
                state["note_n"] += 1
                lines.append("[^%d]: %s" % (state["note_n"], text))
            elif kind in ("bulleted_list_item", "numbered_list_item", "to_do"):
                numbered += 1
                marker = "%d." % numbered if kind == "numbered_list_item" else "-"
                lines.append("%s%s %s" % (indent, marker, text))
                if b.get("has_children"):
                    walk(fetch_children(b["id"]), depth + 1)
                continue
            elif kind == "quote":
                lines.append("> " + text)
            elif kind == "callout":
                lines.append("> " + text)
            elif kind == "divider":
                lines.append("---")
            elif kind == "code":
                lang = data.get("language", "")
                lines.append("```%s\n%s\n```" % ("" if lang == "plain text" else lang,
                                                 "".join(r.get("plain_text", "") for r in rich)))
            elif kind == "image":
                src = (data.get("file") or data.get("external") or {}).get("url")
                if src:
                    state["image_n"] += 1
                    name = fetch_image(src, state["image_n"])
                    caption = "".join(r.get("plain_text", "") for r in data.get("caption", []))
                    lines.append("![%s](%s)" % (caption.replace("]", ""), name))
            elif kind == "table":
                rows = fetch_children(b["id"])
                cells = [[rich_to_md(c).replace("|", "\\|") for c in r.get("table_row", {}).get("cells", [])]
                         for r in rows]
                if cells:
                    width = max(len(r) for r in cells)
                    cells = [r + [""] * (width - len(r)) for r in cells]
                    lines.append("| " + " | ".join(cells[0]) + " |")
                    lines.append("|" + "---|" * width)
                    lines.extend("| " + " | ".join(r) + " |" for r in cells[1:])
            elif kind == "toggle":
                lines.append(text)
            # Anything else (embeds, databases, synced blocks) is skipped deliberately.

            if b.get("has_children") and kind not in ("table", "bulleted_list_item", "numbered_list_item", "to_do"):
                walk(fetch_children(b["id"]), depth + (1 if kind == "toggle" else 0))

            lines.append("")

    walk(blocks)
    md = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
