"""A small Notion API client, and the property names the editorial database uses.

Plain `requests` rather than an SDK: the calls the pipeline needs are few, and
one readable file is easier for a successor to debug than a dependency.
"""

import os
import time
from pathlib import Path

import requests

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"

# Property names in the Notion database. If an editor renames a column in
# Notion, change it here too — nothing else in the pipeline refers to them.
FIELDS = {
    "title": "Title",
    "status": "Status",
    "authors": "Authors",
    "author_email": "Author email",
    "bio": "Author bio",
    "abstract": "Abstract",
    "manuscript": "Manuscript",
    "anonymised": "Anonymised copy",
    "header": "Header image",
    "date": "Publish date",
    "slug": "Slug",
    "featured": "Featured",
    "screening": "Screening",
    "preview": "Preview link",
    "live": "Live link",
}

STATUSES = ["Submitted", "Screened", "In review", "Accepted", "Published", "Rejected"]


class NotionError(Exception):
    pass


class Notion:
    def __init__(self, token=None):
        token = token or os.environ.get("NOTION_TOKEN")
        if not token:
            raise NotionError("NOTION_TOKEN is not set")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer %s" % token,
            "Notion-Version": VERSION,
        })

    def request(self, method, path, **kw):
        url = path if path.startswith("http") else API + path
        for attempt in range(6):
            r = self.session.request(method, url, timeout=60, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 30))
                continue
            if r.status_code >= 400:
                raise NotionError("%s %s → %d: %s" % (method, path, r.status_code, r.text[:400]))
            return r.json() if r.content else {}
        raise NotionError("%s %s: gave up after repeated rate limiting" % (method, path))

    def query(self, database_id, filter=None, sorts=None):
        body, results = {"page_size": 100}, []
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        while True:
            data = self.request("POST", "/databases/%s/query" % database_id, json=body)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            body["start_cursor"] = data["next_cursor"]

    def children(self, block_id):
        results, cursor = [], None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self.request("GET", "/blocks/%s/children" % block_id, params=params)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            cursor = data["next_cursor"]

    def update(self, page_id, properties):
        return self.request("PATCH", "/pages/%s" % page_id, json={"properties": properties})

    def download(self, url, dest):
        """Notion file links are signed and expire within the hour, so files are
        always fetched at build time and stored in the repository."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        return dest

    def upload_file(self, path, content_type):
        """Upload a local file so it can be attached to a page property."""
        path = Path(path)
        created = self.request("POST", "/file_uploads", json={
            "mode": "single_part", "filename": path.name, "content_type": content_type})
        with open(path, "rb") as f:
            r = self.session.post(created["upload_url"], files={"file": (path.name, f, content_type)}, timeout=120)
        if r.status_code >= 400:
            raise NotionError("file upload failed → %d: %s" % (r.status_code, r.text[:300]))
        return created["id"]


# ── reading properties ────────────────────────────────────────────────────

def plain(rich):
    return "".join(r.get("plain_text", "") for r in rich or [])


def prop(page, key):
    return page.get("properties", {}).get(FIELDS[key])


def text(page, key):
    p = prop(page, key)
    if not p:
        return ""
    kind = p.get("type")
    if kind in ("title", "rich_text"):
        return plain(p[kind]).strip()
    if kind == "select":
        return (p["select"] or {}).get("name", "")
    if kind == "status":
        return (p["status"] or {}).get("name", "")
    if kind in ("url", "email", "phone_number"):
        return p[kind] or ""
    if kind == "number":
        return "" if p["number"] is None else str(p["number"])
    return ""


def date(page, key):
    p = prop(page, key)
    if p and p.get("type") == "date" and p["date"]:
        return p["date"]["start"][:10]
    return ""


def checkbox(page, key):
    p = prop(page, key)
    return bool(p and p.get("type") == "checkbox" and p["checkbox"])


def files(page, key):
    p = prop(page, key)
    out = []
    if p and p.get("type") == "files":
        for f in p["files"]:
            url = (f.get("file") or f.get("external") or {}).get("url")
            if url:
                out.append((f.get("name") or url.rsplit("/", 1)[-1].split("?")[0], url))
    return out


def rich_text_value(s):
    """A rich_text property value, split to respect Notion's 2,000-char runs."""
    s = s or ""
    return {"rich_text": [{"type": "text", "text": {"content": s[i:i + 1900]}}
                          for i in range(0, max(len(s), 1), 1900)] if s else []}
