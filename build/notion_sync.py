"""Sync the Notion editorial database into content/.

    NOTION_TOKEN=… NOTION_DATABASE_ID=… python build/notion_sync.py

Rows marked Published become content/posts/<slug>/.
Rows marked Accepted become unlisted previews at content/previews/<token>/,
and the preview link is written back onto the Notion page. Previews are never
committed — the repository is public, and an unpublished post must not be
readable there. Only a fingerprint of them is committed, in
content/.previews-state, so the workflow knows when to rebuild.

The sync only writes files when something changed, so the scheduled workflow
commits only real edits. It refuses to empty the site: if Notion returns no
published posts while content/ still has some, it stops, because that is far
more likely to be an API or permissions fault than an editorial decision.
Pass --allow-empty to override.

Without NOTION_TOKEN it exits quietly, so the site can build before Notion is
set up.
"""

import argparse
import datetime as dt
import hashlib
import hmac
import os
import re
import shutil
import sys

# Windows consoles default to a legacy code page; titles and arrows in the
# log would otherwise crash the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import manuscript  # noqa: E402
import notion as N  # noqa: E402
from content import slugify, split_front_matter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "content" / "posts"
PREVIEWS = ROOT / "content" / "previews"


def log(msg):
    print("  " + msg, flush=True)


def site_config():
    cfg = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    cfg["site_url"] = (os.environ.get("SITE_URL") or cfg["url"]).rstrip("/")
    return cfg


def resolve_category(name, cfg):
    wanted = (name or "").strip().casefold()
    for c in cfg["categories"]:
        if wanted in (c["slug"].casefold(), c["name"].casefold(), str(c.get("short", "")).casefold()):
            return c["slug"]
    return None


def preview_token(page_id):
    secret = (os.environ.get("PREVIEW_SECRET") or os.environ.get("NOTION_TOKEN") or "").encode()
    return hmac.new(secret, page_id.replace("-", "").encode(), hashlib.sha256).hexdigest()[:20]


def existing_notion_posts(folder):
    """Map notion_id → (folder, notion_edited) for posts the sync created.
    Hand-written posts (no notion_id) are never touched."""
    found = {}
    if not folder.exists():
        return found
    for d in folder.iterdir():
        index = d / "index.md"
        if not index.exists():
            continue
        try:
            meta, _ = split_front_matter(index.read_text(encoding="utf-8"), index)
        except Exception:
            continue
        if meta.get("notion_id"):
            found[meta["notion_id"]] = (d, str(meta.get("notion_edited", "")))
    return found


def build_post(client, page, cfg, dest):
    """Write one page into `dest` (a fresh temporary folder)."""
    title = N.text(page, "title")
    if not title:
        raise ValueError("no title")
    cat = resolve_category(N.text(page, "category"), cfg)
    if not cat:
        raise ValueError("category %r is not in site.yml" % N.text(page, "category"))

    manuscripts = [f for f in N.files(page, "manuscript") if f[0].lower().endswith(".docx")]
    if manuscripts:
        name, url = manuscripts[-1]            # the last attached file is the final version
        with tempfile.TemporaryDirectory() as tmp:
            local = client.download(url, Path(tmp) / "manuscript.docx")
            body = manuscript.docx_to_markdown(local, dest, title)
        source = "word"
    else:
        def fetch_image(src, n):
            ext = Path(urlparse(src).path).suffix.lower() or ".png"
            fname = "image-%d%s" % (n, ext if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg") else ".png")
            client.download(src, dest / fname)
            return fname
        body = manuscript.blocks_to_markdown(client.children(page["id"]), client.children, fetch_image)
        source = "notion"

    header = N.files(page, "header")
    header_name = ""
    if header:
        ext = Path(urlparse(header[0][1]).path).suffix.lower() or ".jpg"
        header_name = "header" + ext
        client.download(header[0][1], dest / header_name)

    meta = {
        "title": title,
        "slug": slugify(N.text(page, "slug") or title),
        "authors": N.text(page, "authors"),
        "bios": [b.strip() for b in N.text(page, "bio").split("\n") if b.strip()],
        "category": cat,
        "standfirst": N.text(page, "abstract"),
        "date": N.date(page, "date") or dt.date.today().isoformat(),
        "featured": N.checkbox(page, "featured"),
        "notion_id": page["id"],
        "notion_edited": page.get("last_edited_time", ""),
        "source": source,
    }
    if header_name:
        meta["header_image"] = header_name
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    (dest / "index.md").write_text("---\n%s---\n\n%s" % (front, body), encoding="utf-8")
    return meta


def replace_folder(src, dest):
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def previews_fingerprint(accepted, cfg):
    """A hash of which rows are Accepted and when each was last edited. It is
    committed in place of the previews themselves, which never enter the
    public repository, so the workflow can tell when previews need rebuilding."""
    parts = sorted("%s:%s" % (p["id"], p.get("last_edited_time", "")) for p in accepted)
    return hashlib.sha256(("\n".join(parts) + "\n" + cfg["site_url"]).encode()).hexdigest()


def sync(client, db_id, cfg, allow_empty=False, dry_run=False, force_previews=False):
    pages = client.query(db_id, filter={"or": [
        {"property": N.FIELDS["status"], "select": {"equals": "Published"}},
        {"property": N.FIELDS["status"], "select": {"equals": "Accepted"}},
    ]})
    published = [p for p in pages if N.text(p, "status") == "Published"]
    accepted = [p for p in pages if N.text(p, "status") == "Accepted"]
    log("Notion: %d published, %d accepted" % (len(published), len(accepted)))

    have_posts = existing_notion_posts(POSTS)
    if not published and have_posts and not allow_empty:
        raise SystemExit("Refusing to unpublish all %d posts: Notion returned none marked Published. "
                         "Check the integration still has access to the database, or pass --allow-empty."
                         % len(have_posts))

    errors, links = [], []
    posts_changed = 0

    def write_page(page, target, kind):
        """Build one page into `target`; on failure, report it on the page."""
        title = N.text(page, "title") or page["id"]
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp) / "post"
            staging.mkdir()
            try:
                meta = build_post(client, page, cfg, staging)
            except Exception as e:                   # one bad row must not stop the rest
                errors.append("%s: %s" % (title, e))
                try:
                    client.update(page["id"], {N.FIELDS["screening"]: N.rich_text_value(
                        "Could not publish (%s): %s" % (dt.date.today().isoformat(), e))})
                except N.NotionError:
                    pass
                return None
            folder = target(meta)
            replace_folder(staging, folder)
            return meta

    # ── published posts: incremental, committed to the repository ────────
    published_ids = {p["id"] for p in published}
    for page in published:
        pid, edited = page["id"], page.get("last_edited_time", "")
        if pid in have_posts and have_posts[pid][1] == edited:
            links.append((page, "live", "%s/post/%s/" % (cfg["site_url"], have_posts[pid][0].name)))
            continue
        if dry_run:
            log("would write post: %s" % N.text(page, "title"))
            continue
        old = have_posts.get(pid, (None, None))[0]
        meta = write_page(page, lambda m: POSTS / m["slug"], "post")
        if meta:
            if old is not None and old.name != meta["slug"] and old.exists():
                shutil.rmtree(old)                   # the slug was changed in Notion
            posts_changed += 1
            links.append((page, "live", "%s/post/%s/" % (cfg["site_url"], meta["slug"])))
            log("%s post: %s" % ("updated" if old is not None else "added", meta["title"]))

    for pid, (folder, _) in have_posts.items():
        if pid not in published_ids:
            if not dry_run:
                shutil.rmtree(folder)
            posts_changed += 1
            log("removed post: %s" % folder.name)

    # ── previews: rebuilt only when needed, never committed ──────────────
    fingerprint = previews_fingerprint(accepted, cfg)
    state = POSTS.parent / ".previews-state"
    previous = state.read_text(encoding="utf-8").strip() if state.exists() else ""
    previews_changed = fingerprint != previous
    if (previews_changed or posts_changed or force_previews) and not dry_run:
        if PREVIEWS.exists():
            shutil.rmtree(PREVIEWS)
        for page in accepted:
            token = preview_token(page["id"])
            if write_page(page, lambda m, t=token: PREVIEWS / t, "preview"):
                links.append((page, "preview", "%s/preview/%s/" % (cfg["site_url"], token)))
        if previews_changed:
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(fingerprint + "\n", encoding="utf-8")
        log("%d preview(s) built" % len(accepted))

    # ── write the links back, so editors never have to leave Notion ──────
    if not dry_run:
        for page, kind, url in links:
            current = N.prop(page, kind)
            if current is not None and (current.get("url") or "") != url:
                try:
                    client.update(page["id"], {N.FIELDS[kind]: {"url": url}})
                except N.NotionError as e:
                    errors.append("%s: could not write %s link (%s)" % (N.text(page, "title"), kind, e))

    for e in errors:
        print("  ! " + e)
    changed = bool(posts_changed or previews_changed)
    log("posts changed: %d · previews changed: %s" % (posts_changed, "yes" if previews_changed else "no"))
    return changed, errors


def set_output(name, value):
    """Tell GitHub Actions whether anything changed, so an idle scheduled run
    can skip building and deploying."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s=%s\n" % (name, value))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allow-empty", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("NOTION_TOKEN") or not os.environ.get("NOTION_DATABASE_ID"):
        print("Notion sync skipped: NOTION_TOKEN / NOTION_DATABASE_ID not set.")
        set_output("changed", "false")
        return
    print("Syncing from Notion")
    # A push or a manual run always rebuilds, so previews must exist on disk.
    force = os.environ.get("BUILD_ALL") == "1"
    # Per-post failures are reported on the Notion page and in the log, but do
    # not fail the run: one malformed manuscript should not hold back the rest.
    changed, _ = sync(N.Notion(), os.environ["NOTION_DATABASE_ID"], site_config(),
                      args.allow_empty, args.dry_run, force_previews=force)
    set_output("changed", "true" if changed else "false")


if __name__ == "__main__":
    main()
