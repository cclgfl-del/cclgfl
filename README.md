# CCLGFL Blog

The blog of the Centre for Corporate Law, Governance and Financial Laws,
National Law University Delhi.

Editors work entirely in Notion — see **[EDITORS.md](EDITORS.md)**. This file
is for whoever maintains the site.

## How it works

```
Author ─ Word file ─▶ Notion form ─▶ Notion database
                                          │
             GitHub Actions, every 30 min │ (or "Run workflow")
             ─────────────────────────────┼──────────────────────────────
             build/screen.py              │  new submissions: check against the
                                          │  guidelines, attach an anonymised copy
             build/notion_sync.py         │  Accepted → content/previews/<token>/
                                          │  Published → content/posts/<slug>/
             git commit content/          │  the repository is the archive of record
             build/build.py               │  content/ → _site/
                                          ▼
                                    GitHub Pages
```

Two decisions shape the rest:

- **`content/` is the source of truth, not Notion.** The sync writes published
  posts into the repository as Markdown and images; the build reads only
  `content/`. If Notion changes its terms, loses the workspace, or is simply
  down, the site still builds, and every post ever published is in git.
- **The site is static.** No server, no database, nothing to patch. It costs
  nothing to host and cannot be taken down by a dependency upgrade.
- **Unpublished work never enters the repository.** It is public. Previews of
  accepted posts are built inside the workflow run and deployed to unlisted,
  unguessable addresses that search engines are told to ignore; only published
  posts are committed.

## Layout

```
site.yml                  names, links, areas of law, submission figures — edit this, not code
content/pages/            the About the Blog and Submissions text, in Markdown
content/posts/            published posts, committed: the CBFL archive (see below) and whatever the sync writes
content/previews/         previews of accepted posts — built during each run, never committed
content/.previews-state   a fingerprint of the previews, so idle runs can skip the build
content/specimens/        layout specimens; built only with --specimens, never published
templates/                Jinja templates
static/                   css, js, fonts, seal and portraits
build/build.py            content/ → _site/
build/content.py          Markdown → reader HTML: margin notes, paragraph numbers, heading numerals
build/guilloche.py        generates each subject's engraving
build/cards.py            share images for WhatsApp / LinkedIn / X
build/cite.py             Bluebook citation, RIS and BibTeX
build/notion.py           Notion API client and database property names
build/notion_sync.py      Notion → content/
build/manuscript.py       Word → Markdown, Notion blocks → Markdown
build/screen.py           automatic first-round screening
build/setup_notion.py     creates the Notion database
build/selftest.py         offline checks of the whole pipeline
build/import_cbfl.py      one-off: the CBFL Blog's Wix pages → content/posts
.github/workflows/publish.yml
```

## The CBFL archive

The Centre's earlier blog, the CBFL Blog, was on Wix at cbflnludelhi.in. Its 201
posts (2022–2025) were imported into `content/posts/` by `build/import_cbfl.py`,
one folder each, in the same form as any other post. The old domain lapses on
3 October 2026; a raw copy of every page is kept outside this repository, and the
converter reads only that copy.

- **Nothing is rewritten.** Text, links and tables are exactly the authors'. Titles
  are as published, except that titles typed in capitals are set in title case, a
  stray final full stop is dropped, and four titles Wix had cut short are complete.
- **Headings.** The old guidelines told authors to mark headings by bolding or
  underlining a line, so those lines became real headings (I., A., (i)).
- **Authors and bios.** Each post's "The author is …" line is now its author note,
  with the LinkedIn links it carried and their tracking parameters removed.
- **One repeat left out.** *Huge Backlog of Cases in the Real Estate Sector* was
  posted twice on the old site with identical text (26 July and 9 August 2023); the
  earlier is kept.
- **Provenance.** Each post says where it first appeared, and is cited to the
  CBFL Blog with its original date. Front matter keeps `archive_url`.
- **Safe from the sync.** Archive posts have no `notion_id`, so the Notion sync never
  edits or removes them, and refuses to publish a Notion row over one.
- Seven posts typed their own endnotes at the end of the text; they remain as written.

## Setting it up (once)

### 1. The repository

Create `cclgfl` (public) on the Centre's GitHub account, `cclgfl-del`, and push this folder.
The Journal lives separately, at `cclgfl-nlud/jcfl`.

In **Settings → Pages**, set **Source** to **GitHub Actions**. (Not "Deploy
from a branch" — this site is built by the workflow.)

### 2. Notion

1. At <https://www.notion.so/profile/integrations>, create an **internal
   integration** on the Centre's workspace. Give it read content, update
   content and insert content. Copy its token.
2. Create a page to hold the database, and share that page with the
   integration (**•••  → Connections**).
3. Create the database:

   ```bash
   NOTION_TOKEN=secret_xxx python build/setup_notion.py --parent <page link>
   ```

   It prints `NOTION_DATABASE_ID=…`.
4. Add the form — see *Setting up the form* in EDITORS.md.

The workspace should belong to the Centre's institutional account, not a
student's, for the same reason the GitHub account does.

### 3. Secrets and variables

**Settings → Secrets and variables → Actions:**

| Name | Kind | Value |
|---|---|---|
| `NOTION_TOKEN` | secret | the integration token |
| `NOTION_DATABASE_ID` | secret | from step 2 |
| `PREVIEW_SECRET` | secret | any long random string — makes preview links unguessable |
| `SITE_URL` | variable | optional — leave unset to use `https://cclgfl-del.github.io/cclgfl` |

Then **Actions → Publish → Run workflow**.

### 4. The domain, when IT has made the CNAME

1. IT creates `cclgfl` as a **CNAME** to `cclgfl-del.github.io`, **DNS only**.
   (Not `cclgfl-nlud.github.io` — that account holds the Journal, and a CNAME
   must point at the account that owns this repository.)
2. Set variables `SITE_URL` = `https://cclgfl.nludelhi.ac.in` and `CUSTOM_DOMAIN` = `cclgfl.nludelhi.ac.in`.
3. Run the workflow, then tick **Enforce HTTPS** in Settings → Pages once the certificate is issued.

## Working locally

```bash
pip install -r build/requirements.txt
python build/build.py --specimens      # --specimens adds the layout specimens
python -m http.server 4174 --directory _site
```

Open <http://localhost:4174>. With `SITE_URL` unset, links point at the
production domain; set `SITE_URL=http://localhost:4174` for local builds.

`python build/selftest.py` checks Word conversion, screening, anonymisation,
Notion-block conversion and rendering without needing a Notion token. The
workflow runs it before every build.

## Things that need confirming

- **The submission form.** Submissions come through the Centre's Google Form
  (`submission_form_url` in `site.yml`), but the pipeline above reads a Notion
  database. Until the form's responses are connected to Notion, an editor copies
  each one across (see EDITORS.md). The form must also be open to anyone with
  the link, or authors outside the University cannot use it.
- **Contact email.** Currently `blog.cclgfl@nludelhi.ac.in`.
- **Submission form link.** Empty until the Notion form exists; the Submit page
  says the form is being set up.

## Design

- **Identity:** the journal's — maroon `#5F1D25`, gold `#9E6B22`, warm paper,
  Cormorant Garamond for display, the Centre's seal. The blog and the journal
  read as one family.
- **Text:** Source Serif 4, with optical sizing, so body text and margin notes
  are each drawn for their size. Hanken Grotesk only for small labels. All fonts
  self-hosted.
- **The engravings** are guilloché — the line-work of share certificates and
  banknotes, the visual vernacular of financial instruments. `guilloche.py`
  generates each subject's from its slug, the way a rose engine cuts one curve
  and rotates it: same subject, same engraving; new subject, new engraving. They
  are CSS masks, so each theme chooses the ink.
- **The reader:** endnotes in the right margin on wide screens, folding into the
  text on narrow ones (CSS only). Numbered paragraphs for pinpoint citation.
  Reading settings for light / sepia / dark, text size, and notes in margin or
  text.
- **Accessibility:** every text colour clears WCAG AA in all three themes on
  every page type; keyboard focus is visible; reduced motion is respected; the
  site reads without JavaScript.
