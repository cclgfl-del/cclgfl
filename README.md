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
site.yml                  names, links, categories, submission rules — edit this, not code
content/posts/            published posts (written by the sync, committed)
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
.github/workflows/publish.yml
```

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

- **Blog guidelines.** `site.yml → guidelines` and the Submit page are taken
  from the predecessor CBFL blog's published guidelines, with the name changed:
  1,000–1,500 words, 50-word abstract, 10-word title, two authors, hyperlinks
  with endnotes only where needed, no footnotes, decision in 20 days, literary
  rights vesting in the Centre. Confirm these still stand.
- **Categories.** Nine subjects in `site.yml`, drawn from CCLGFL's mandate and
  CBFL's old categories. The slug becomes the URL, so settle them before the
  first post.
- **Contact email.** Currently `nlud.bflr@nludelhi.ac.in`.
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
