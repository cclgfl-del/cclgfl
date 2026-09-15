"""Build the CCLGFL Blog into a static site.

    python build/build.py                 # production build into _site/
    python build/build.py --specimens     # include the specimen posts, for review
    python build/build.py --no-search     # skip the Pagefind index (faster)

Reads only site.yml, content/, templates/ and static/. Notion is never touched
here — build/notion_sync.py writes content/, and this reads it.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

# Windows consoles default to a legacy code page; titles and arrows in the
# log would otherwise crash the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape as xml_escape

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

sys.path.insert(0, str(Path(__file__).parent))
import cards  # noqa: E402
import cite  # noqa: E402
import guilloche  # noqa: E402
from content import ContentError, load_post  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
CACHE = ROOT / ".cache"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# The engraving used where no single post is in view: the call for blogs, the
# empty home page, the 404.
HOUSE_ENGRAVING = "cclgfl"


def log(msg):
    print("  " + msg)


# ── config ────────────────────────────────────────────────────────────────

def load_config():
    cfg = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    site_url = (os.environ.get("SITE_URL") or cfg["url"]).rstrip("/")
    cfg["site_url"] = site_url
    cfg["base"] = urlparse(site_url).path.rstrip("/")
    return cfg


# ── content ───────────────────────────────────────────────────────────────

def load_folder(path, **kw):
    posts = []
    if not path.exists():
        return posts
    for folder in sorted(p for p in path.iterdir() if p.is_dir() and (p / "index.md").exists()):
        posts.append(load_post(folder, **kw))
    return posts


def load_all(cfg, with_specimens):
    posts = load_folder(ROOT / "content" / "posts")
    if with_specimens:
        posts += load_folder(ROOT / "content" / "specimens")
    previews = []
    pdir = ROOT / "content" / "previews"
    if pdir.exists():
        for folder in sorted(p for p in pdir.iterdir() if p.is_dir() and (p / "index.md").exists()):
            previews.append(load_post(folder, preview_token=folder.name))

    slugs = {}
    for p in posts:
        if p.slug in slugs:
            raise ContentError("Two posts share the slug %r: %s and %s" % (p.slug, slugs[p.slug], p.source_dir))
        slugs[p.slug] = p.source_dir
    posts.sort(key=lambda p: (p.date, p.title), reverse=True)
    return posts, previews


def load_page(name):
    """A page of editorial text from content/pages, as a list of sections
    split on its "## " headings: [{"heading": ..., "html": ...}]. Text before
    the first heading becomes a section with no heading."""
    text = (ROOT / "content" / "pages" / ("%s.md" % name)).read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).replace("\r\n", "\n")
    parts = re.split(r"^## +(.+)$", text, flags=re.M)
    sections = []
    if parts[0].strip():
        sections.append({"heading": "", "html": md_block(parts[0])})
    for heading, body in zip(parts[1::2], parts[2::2]):
        sections.append({"heading": heading.strip(), "html": md_block(body)})
    return sections


def md_block(text):
    return markdown.markdown(text.strip(), extensions=["smarty", "sane_lists"])


# ── templating ────────────────────────────────────────────────────────────

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def make_env(cfg, posts, specimens_build):
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    hashes = {}

    def url(path="/"):
        return cfg["base"] + path

    def abs_url(path="/"):
        return cfg["site_url"] + path

    def asset(path):
        full = ROOT / "static" / path
        if path not in hashes:
            hashes[path] = file_hash(full) if full.exists() else "0"
        return "%s/static/%s?v=%s" % (cfg["base"], path, hashes[path])

    def pattern(slug, kind):
        return "%s/static/patterns/%s-%s.svg" % (cfg["base"], slug, kind)

    env.globals.update(
        cfg=cfg, url=url, abs_url=abs_url, asset=asset, pattern=pattern, house=HOUSE_ENGRAVING,
        specimens_build=specimens_build, now=dt.date.today(), quote=quote,
    )
    env.filters["longdate"] = lambda d: "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)
    env.filters["shortdate"] = lambda d: "%d %s %d" % (d.day, MONTHS_SHORT[d.month - 1], d.year)
    env.filters["daymonth"] = lambda d: "%d %s" % (d.day, MONTHS_SHORT[d.month - 1])
    env.filters["iso"] = lambda d: d.isoformat()
    env.filters["tojson_attr"] = lambda v: json.dumps(v, ensure_ascii=False)
    return env


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── pages ─────────────────────────────────────────────────────────────────

def read_next(post, posts, n=3):
    """The posts published just before this one, then the newest: the Blog
    runs by date, so "next" means the neighbouring entries in its timeline."""
    others = [p for p in posts if p is not post]
    older = [p for p in others if (p.date, p.title) < (post.date, post.title)]
    return (older + [p for p in others if p not in older])[:n]


def post_context(cfg, post, posts, preview=False):
    path = "/preview/%s/" % post.preview_token if preview else "/post/%s/" % post.slug
    canonical = cfg["site_url"] + path
    cite_text, cite_html = cite.bluebook(post, cfg["blog_name"], canonical)
    return {
        "post": post,
        "path": path,
        "canonical": canonical,
        "preview": preview,
        "read_next": [] if preview else read_next(post, posts),
        "cite_text": cite_text,
        "cite_html": cite_html,
        "card": cfg["site_url"] + "/cards/%s.png" % post.slug,
    }


def build_pages(env, cfg, posts, previews):
    render = lambda name, **ctx: env.get_template(name).render(**ctx)  # noqa: E731

    lead = next((p for p in posts if p.featured), posts[0] if posts else None)
    others = [p for p in posts if p is not lead]
    write(OUT / "index.html", render("home.html", page="home", path="/", lead=lead,
                                     secondary=others[:2], recent=others[2:10], total=len(posts)))

    for post in posts:
        ctx = post_context(cfg, post, posts)
        base = OUT / "post" / post.slug
        write(base / "index.html", render("post.html", page="post", **ctx))
        publisher = "%s, %s" % (cfg["centre"], cfg["university"])
        write(base / "cite.ris", cite.ris(post, cfg["blog_name"], publisher, ctx["canonical"]))
        write(base / "cite.bib", cite.bibtex(post, cfg["blog_name"], ctx["canonical"]))
        copy_media(post.source_dir, base)

    for post in previews:
        ctx = post_context(cfg, post, posts, preview=True)
        base = OUT / "preview" / post.preview_token
        write(base / "index.html", render("post.html", page="post", **ctx))
        copy_media(post.source_dir, base)

    # The timeline: years, and within each year its months, newest first.
    years = OrderedDict()
    for p in posts:
        months = years.setdefault(p.date.year, OrderedDict())
        months.setdefault(MONTHS[p.date.month - 1], []).append(p)
    write(OUT / "blogs" / "index.html",
          render("blogs.html", page="blogs", path="/blogs/", years=years, total=len(posts)))

    write(OUT / "about" / "index.html",
          render("about.html", page="about", path="/about/", about_blog=load_page("about-blog")))
    write(OUT / "submissions" / "index.html",
          render("submissions.html", page="submissions", path="/submissions/",
                 sections=load_page("submissions")))
    write(OUT / "contact" / "index.html", render("contact.html", page="contact", path="/contact/"))
    write(OUT / "404.html", render("404.html", page="404", path="/404.html", latest=posts[:3]))

    # Addresses from the first review build, which was shared before the pages
    # were renamed.
    for old, new in (("posts", "/blogs/"), ("submit", "/submissions/"), ("search", "/blogs/")):
        write(OUT / old / "index.html", redirect_page(cfg["base"] + new))


def redirect_page(target):
    return ('<!DOCTYPE html><html lang="en-IN"><head><meta charset="utf-8">'
            '<meta name="robots" content="noindex"><link rel="canonical" href="{0}">'
            '<meta http-equiv="refresh" content="0; url={0}"><title>Moved</title></head>'
            '<body><p><a href="{0}">This page has moved.</a></p></body></html>\n').format(target)


def copy_media(src, dest):
    for item in src.iterdir():
        if item.name == "index.md":
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


# ── feeds, sitemap, cards, patterns ───────────────────────────────────────

def rfc822(d):
    return dt.datetime(d.year, d.month, d.day, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))) \
             .strftime("%a, %d %b %Y %H:%M:%S %z")


def build_feed(cfg, posts):
    items = []
    for p in posts[:30]:
        link = "%s/post/%s/" % (cfg["site_url"], p.slug)
        items.append(
            "<item><title>%s</title><link>%s</link><guid isPermaLink=\"true\">%s</guid>"
            "<pubDate>%s</pubDate>%s<description>%s</description></item>" % (
                xml_escape(p.title), link, link, rfc822(p.date),
                "".join("<dc:creator>%s</dc:creator>" % xml_escape(a) for a in p.authors),
                xml_escape(p.standfirst)))
    feed = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<channel><title>%s</title><link>%s/</link><description>%s</description><language>en-in</language>'
            '<atom:link href="%s/feed.xml" rel="self" type="application/rss+xml"/>%s</channel></rss>\n') % (
        xml_escape(cfg["blog_name"]), cfg["site_url"], xml_escape(cfg["description"].strip()),
        cfg["site_url"], "".join(items))
    write(OUT / "feed.xml", feed)


def build_sitemap(cfg, posts):
    paths = ["/", "/about/", "/blogs/", "/submissions/", "/contact/"]
    entries = ["<url><loc>%s%s</loc></url>" % (cfg["site_url"], p) for p in paths]
    entries += ["<url><loc>%s/post/%s/</loc><lastmod>%s</lastmod></url>" % (cfg["site_url"], p.slug, p.date.isoformat())
                for p in posts]
    write(OUT / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % "".join(entries))
    if cfg.get("review"):
        write(OUT / "robots.txt", "User-agent: *\nDisallow: /\n")
    else:
        write(OUT / "robots.txt", "User-agent: *\nDisallow: %s/preview/\nSitemap: %s/sitemap.xml\n"
              % (cfg["base"], cfg["site_url"]))


def build_patterns(posts):
    out = OUT / "static" / "patterns"
    for key in sorted({HOUSE_ENGRAVING} | {p.engraving for p in posts}):
        guilloche.write_patterns(key, out)
    write(out / "rule.svg", guilloche.rule_svg())


def build_cards(cfg, posts):
    seal = ROOT / "static" / "img" / "seal.png"
    for p in posts:
        cards.build_card(p, cfg, seal, OUT / "cards" / ("%s.png" % p.slug), CACHE / "cards")


def run_pagefind():
    result = subprocess.run([sys.executable, "-m", "pagefind", "--site", str(OUT)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-2000:], result.stderr[-2000:])
        raise SystemExit("Pagefind failed")
    pages = [l.strip() for l in result.stdout.splitlines() if l.strip().startswith("Indexed") and "page" in l]
    log("search index: %s" % (pages[0].lower() if pages else "built"))


def clean_output():
    """Empty _site without deleting the folder itself. On Windows a local
    preview server or OneDrive can hold a directory open; its files can still
    be removed, and a leftover empty folder does no harm."""
    OUT.mkdir(exist_ok=True)
    for item in OUT.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError:
            for f in sorted(item.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                try:
                    f.unlink() if f.is_file() else f.rmdir()
                except OSError:
                    pass


# ── main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specimens", action="store_true", help="include content/specimens for review")
    ap.add_argument("--no-search", action="store_true", help="skip the Pagefind search index")
    args = ap.parse_args()

    cfg = load_config()
    args.specimens = args.specimens or bool(cfg.get("review"))
    print("Building %s → %s%s" % (cfg["blog_name"], cfg["site_url"], "  [review mode]" if cfg.get("review") else ""))
    try:
        posts, previews = load_all(cfg, args.specimens)
    except ContentError as e:
        raise SystemExit("Content error: %s" % e)
    log("%d post(s), %d preview(s)%s" % (len(posts), len(previews), " incl. specimens" if args.specimens else ""))

    clean_output()
    shutil.copytree(ROOT / "static", OUT / "static", dirs_exist_ok=True)

    env = make_env(cfg, posts, args.specimens)
    build_patterns(posts + previews)
    build_pages(env, cfg, posts, previews)
    build_cards(cfg, posts)
    build_feed(cfg, posts)
    build_sitemap(cfg, posts)
    shutil.copy2(ROOT / "static" / "favicon.ico", OUT / "favicon.ico")
    write(OUT / ".nojekyll", "")
    if os.environ.get("CUSTOM_DOMAIN"):
        write(OUT / "CNAME", os.environ["CUSTOM_DOMAIN"].strip() + "\n")
    log("pages, cards, feed and sitemap written")

    if not args.no_search:
        run_pagefind()
    print("Done.")


if __name__ == "__main__":
    main()
