# The CCLGFL Blog — guide for editors

Everything you need to publish lives in one Notion database. You never touch
code, GitHub or the website directly.

## How a post moves

| Status | What it means | Who moves it |
|---|---|---|
| **Submitted** (or empty) | An author sent it through the form | The form |
| **Screened** | Checked automatically against the guidelines; an anonymised copy is attached | The system, within half an hour |
| **In review** | The Editorial Board is reading the anonymised copy | You |
| **Accepted** | Approved and being edited. A **Preview link** appears on the page | You |
| **Published** | Live on the blog. A **Live link** appears on the page | You |
| **Rejected** | Declined. Nothing is published | You |

The site checks Notion every 30 minutes. To publish sooner, ask whoever manages
the GitHub repository to press **Run workflow** under *Actions → Publish*.

## Screening

When a submission arrives, the system reads the Word file and writes a report
into the **Screening** field. Lines marked ⚠ need attention; lines marked ✓ are
fine. It checks:

- length (1,000–1,500 words, not counting notes)
- title (10 words at most)
- number of authors (two at most)
- footnotes and endnotes — the guidelines require references as hyperlinks
- the file name
- the author's name appearing in the text, headers or footers

It then attaches **Anonymised copy** — the same document with the author's name
stripped from its hidden file properties, comments and tracked changes. **Send
reviewers the anonymised copy, never the original.**

If the author's name appears in the *text itself*, the report says so but does
not remove it. Deciding how to anonymise someone's prose is an editorial call.

Screening does **not** check plagiarism or AI-generated content. Do that by hand.

## Before you mark a post Accepted

Fill in, on the Notion page:

- **Title** — as it should appear on the site
- **Authors** — separated by commas or "and"
- **Author bio** — one line per author, e.g. *Jane Doe is a fourth-year student at National Law University Delhi.*
- **Abstract** — a one- or two-sentence summary, shown under the title and when the post is shared. Optional: left empty, the opening words of the post are used.
- **Manuscript** — the **final, edited** Word file. If there are several files, the last one is used.
- **Publish date** — optional; defaults to the day it is published

Optional:

- **Slug** — the web address, e.g. `section-29a-eligibility`. Left empty, it is made from the title. **Don't change it after publishing** — it breaks every link to the post.
- **Header image** — normally leave empty; each subject has its own engraving.
- **Featured** — puts the post at the top of the home page, even if it isn't the newest.

## Checking the preview

Once a post is **Accepted**, a **Preview link** appears within half an hour.
It shows the post exactly as it will look when published, including notes in
the margin. The link is unlisted and hidden from search engines, but anyone
who has it can open it — share it with the author, not publicly.

If something looks wrong, fix the Word file, re-attach it, and the preview
updates on the next check.

If the preview doesn't appear and the **Screening** field says *Could not
publish*, the reason is written there.

## Publishing, and taking a post down

- **To publish:** change Status to **Published**. The Live link appears on the next check.
- **To edit a published post:** change the Word file or the fields. The live post updates on the next check.
- **To take a post down:** change Status away from Published. It disappears from the site on the next check.

## Notes and citations

The guidelines require every reference to be a **hyperlink** in the text, and
screening flags any footnotes or endnotes. If the Editorial Board relaxes that
for a post, Word notes still come across automatically and appear in the margin
beside the paragraph they belong to.

### Writing a post directly in Notion instead of Word

For short pieces — announcements, event notes — you can write straight into
the Notion page and leave **Manuscript** empty.

- Use Notion headings for section headings. *I. Introduction* style numbering is picked up automatically.
- Paste links as normal.
- For a note, type `[^1]` where the marker goes. Then add a heading called **Notes** at the very end, followed by a numbered list: item 1 is note 1, item 2 is note 2.

## Setting up the form (once)

1. In the database, add a **Form** view.
2. Add these questions, each linked to the property of the same name: **Title**, **Authors**, **Author email**, **Author bio**, **Manuscript**. Leave Status out — a response with no Status is treated as a new submission.
3. Allow anyone with the link to respond.
4. Copy the form's link and give it to whoever maintains the site, so it can go in `site.yml` as `submission_form_url`. The *Write for the blog* page then links to it.

Notion's free plan limits uploads to 5 MB per file, which is well above a
normal Word manuscript.
