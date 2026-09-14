"""Citations for a post: Bluebook text, plus RIS and BibTeX for reference
managers. Bluebook is the Centre's house style (21st ed., R. 18.2.9, blogs):

    Author, Title, BLOG NAME (Mon. Day, Year), URL.
"""

import html

BLUEBOOK_MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July",
                   "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


def _authors_bluebook(authors):
    if not authors:
        return ""
    if len(authors) <= 2:
        return " & ".join(authors)
    return "%s et al." % authors[0]


def bluebook_date(d):
    return "%s %d, %d" % (BLUEBOOK_MONTHS[d.month - 1], d.day, d.year)


def bluebook(post, blog_name, url):
    who = _authors_bluebook(post.authors)
    text = "%s%s, %s (%s), %s." % ("%s, " % who if who else "", post.title, blog_name,
                                    bluebook_date(post.date), url)
    marked = "%s<em>%s</em>, <span class=\"sc\">%s</span> (%s), %s." % (
        "%s, " % html.escape(who) if who else "", html.escape(post.title),
        html.escape(blog_name), bluebook_date(post.date), html.escape(url))
    return text, marked


def _last_first(name):
    parts = name.split()
    if len(parts) < 2:
        return name
    return "%s, %s" % (parts[-1], " ".join(parts[:-1]))


def ris(post, blog_name, publisher, url):
    lines = ["TY  - BLOG"]
    lines += ["AU  - %s" % _last_first(a) for a in post.authors]
    lines += [
        "TI  - %s" % post.title,
        "T2  - %s" % blog_name,
        "PB  - %s" % publisher,
        "DA  - %s" % post.date.strftime("%Y/%m/%d"),
        "PY  - %d" % post.date.year,
        "UR  - %s" % url,
        "AB  - %s" % post.standfirst,
        "ER  - ",
    ]
    return "\r\n".join(lines) + "\r\n"


def bibtex(post, blog_name, url):
    def esc(s):
        return s.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}") \
                .replace("&", "\\&").replace("%", "\\%").replace("$", "\\$").replace("#", "\\#")
    key = "%s%d" % ((post.authors[0].split()[-1] if post.authors else "cclgfl").lower(), post.date.year)
    key = "".join(ch for ch in key if ch.isalnum())
    return ("@online{%s,\n  author       = {%s},\n  title        = {%s},\n"
            "  organization = {%s},\n  date         = {%s},\n  url          = {%s},\n}\n") % (
        key, " and ".join(esc(a) for a in post.authors), esc(post.title), esc(blog_name),
        post.date.isoformat(), url)
