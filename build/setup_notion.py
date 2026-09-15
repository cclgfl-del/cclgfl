"""Create the editorial database in Notion, with every property the pipeline
expects, in one step.

    NOTION_TOKEN=… python build/setup_notion.py --parent <page id or URL>

The parent is any Notion page the integration has been shared with. Prints the
new database's id — store it as the NOTION_DATABASE_ID repository secret.

Notion's API cannot create forms; the submission form is made by hand from the
database afterwards (see EDITORS.md, "Setting up the form").
"""

import argparse
import re
import sys

# Windows consoles default to a legacy code page; titles and arrows in the
# log would otherwise crash the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import notion as N  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATUS_COLOURS = {"Submitted": "gray", "Screened": "blue", "In review": "yellow",
                  "Accepted": "orange", "Published": "green", "Rejected": "red"}


def page_id(value):
    m = re.search(r"([0-9a-f]{32})", value.replace("-", ""))
    if not m:
        raise SystemExit("Could not find a Notion page id in %r" % value)
    return m.group(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parent", required=True, help="parent page id or URL")
    ap.add_argument("--title", default="CCLGFL Blog — Submissions")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    F = N.FIELDS
    properties = {
        F["title"]: {"title": {}},
        F["status"]: {"select": {"options": [{"name": s, "color": STATUS_COLOURS[s]} for s in N.STATUSES]}},
        F["authors"]: {"rich_text": {}},
        F["author_email"]: {"email": {}},
        F["bio"]: {"rich_text": {}},
        F["abstract"]: {"rich_text": {}},
        F["manuscript"]: {"files": {}},
        F["anonymised"]: {"files": {}},
        F["header"]: {"files": {}},
        F["date"]: {"date": {}},
        F["slug"]: {"rich_text": {}},
        F["featured"]: {"checkbox": {}},
        F["screening"]: {"rich_text": {}},
        F["preview"]: {"url": {}},
        F["live"]: {"url": {}},
    }
    db = N.Notion().request("POST", "/databases", json={
        "parent": {"type": "page_id", "page_id": page_id(args.parent)},
        "title": [{"type": "text", "text": {"content": args.title}}],
        "properties": properties,
    })
    print("Created database: %s" % db.get("url", ""))
    print("NOTION_DATABASE_ID=%s" % db["id"].replace("-", ""))


if __name__ == "__main__":
    main()
