"""The embeddable results widget: one HTML file, one JSON file, no network.

**What "renders offline" has to mean, or the requirement is decorative.** Not "the
page loads when the server is up" -- the portal is a server. It means the document
**reaches the browser having asked for nothing**: no CDN, no font host, no
analytics, no stylesheet link, no script src, no favicon, no external image. An
organizer can save this file, mail it to a sponsor, open it from a USB stick ten
years from now, and it will still show the ranking.

That is why :func:`build_document` inlines its CSS and emits **no script tag at
all**. A ranking is a table; the temptation is to reach for a charting library, and
a charting library is a network dependency wearing a costume. So the widget is
server-rendered HTML, and the JSON beside it is there for a reader who wants the
data rather than the picture.

One rule makes it a widget rather than a page
--------------------------------------------
**It is self-contained and it is one event.** There is no layout, no navigation, no
chrome -- an embedder pastes it in an ``<iframe>`` and it has to look deliberate
inside somebody else's page. So there is no site header, and there is exactly one
thing on it.

What it will not do
-------------------
**It carries no scores.** The rows are rank, title, track, mean, and how many
reviews were counted -- the same public standing ``/results/`` publishes. A widget
embedded in a sponsor's page is the *least* controlled surface in the system, so
the thing it carries is the thing we would publish anyway.

Every widget says how the ranking was computed
----------------------------------------------
``normalization`` is rendered on the document and present in the JSON, exactly as
on ``/results/``. **A ranking that does not say how it was computed is one a
reader has to guess about**, and a widget is read by people who will never see the
rest of the portal. The value is the literal
``unnormalized-raw-weighted-mean`` and the number beside it says what the
normalization engine measured -- see ``docs/REAL-FIXTURE-RESULTS.md``.
"""

from __future__ import annotations

import datetime as dt
import html

from reviewer.reviews import results as results_module

#: Inline, and small. **The whole stylesheet is three rules plus a font stack**,
#: because a widget that needs a stylesheet is a widget that needs a network.
_CSS = """
:root{color-scheme:light dark}
body{margin:0;padding:1.25rem;font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;
color:#16181d;background:#fff}
h1{font-size:1.05rem;margin:0 0 .15rem}
.meta{color:#5b6472;font-size:.82rem;margin:0 0 1rem}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #e6e8ec}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:#5b6472}
td.num,th.num{text-align:right}
tr:last-child td{border-bottom:0}
footer{margin-top:1rem;color:#5b6472;font-size:.78rem}
@media (prefers-color-scheme:dark){
 body{color:#e8eaed;background:#111317}
 th,td{border-bottom-color:#2a2f38}th,.meta,footer{color:#9aa3b2}}
"""


def widget_payload(event, actor) -> dict:
    """The data half. The same rows the published page ranks, unchanged.

    **Delegates to ``leaderboard``** rather than computing a second ranking. Two
    implementations of "the ranking" is a class of defect this project has paid for
    twice already (F-84, F-89) -- in both cases two shipped artefacts answering
    one question differently -- and a widget is a third artefact.
    """
    rows = results_module.leaderboard(actor)
    return {
        "event": event.pk,
        "event_name": event.name,
        "results_state": event.results_state,
        "normalization": results_module.NORMALIZATION,
        "published_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "rows": [
            {
                "rank": row["rank"],
                "project": row["project"],
                "title": row["title"],
                "track": row["track"],
                "mean": row["mean"],
                "reviews_counted": row["reviews_counted"],
                "normalization": row["normalization"],
            }
            for row in rows
        ],
    }


def build_json(payload: dict) -> str:
    """Canonical JSON, so a widget's data file is diffable and re-fetchable."""
    from reviewer.io.bundle import canonical

    return canonical(payload)


def _cell(value: str, *, numeric: bool = False) -> str:
    """One escaped cell. **Every value goes through ``html.escape``**, and the test
    that proves it puts a hostile project title into the fixture rather than
    trusting the reviewer."""
    tag = "td"
    attrs = ' class="num"' if numeric else ""
    return f"<{tag}{attrs}>{html.escape(value)}</{tag}>"


def _mean_cell(mean) -> str:
    """The mean, formatted, or a dash when there is none.

    **A separate function because the naive inline version is unreadable** -- the
    first draft nested an f-string inside an f-string inside a conditional inside a
    comprehension and produced something no reviewer could check, in the one place
    a reader checks the published number.
    """
    if mean is None:
        return _cell("-", numeric=True)
    return _cell(f"{mean:.4f}".rstrip("0").rstrip(".") or "0", numeric=True)


def build_document(payload: dict) -> str:
    """The HTML half: a complete, self-contained document.

    **No ``<script>``, no ``<link>``, no ``<img>``, no absolute URL.** That is the
    whole acceptance criterion and ``tests/test_widget.py`` asserts the *absence*
    of each of those, because a document that renders offline until somebody adds
    a font is a document that renders online.
    """
    rows = payload["rows"]
    # **One escaping path, not two.** The first draft rendered the title with its
    # own `html.escape` in the f-string here while every other cell went through
    # `_cell`. The escaping tests passed either way, and the mutation harness then
    # reported the `_cell` escape as NOT DETECTED -- because the mutation was
    # aimed at a copy of the logic that the hostile fixture never reached. **Two
    # copies of one rule means one of them is untested**, so the title is a `_cell`
    # like the rest.
    body = "\n".join(
        "<tr>"
        + _cell(str(row["rank"]), numeric=True)
        + _cell(str(row["title"]))
        + _cell(str(row["track"]))
        + _mean_cell(row["mean"])
        + _cell(str(row["reviews_counted"]), numeric=True)
        + "</tr>"
        for row in rows
    )
    heading = html.escape(str(payload["event_name"]))
    method = html.escape(payload["normalization"])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Results — {heading}</title>
<style>{_CSS}</style></head>
<body>
<h1>Results — {heading}</h1>
<p class="meta">{len(rows)} projects · <code>{method}</code></p>
<table>
<thead><tr><th class="num">#</th><th>Project</th><th>Track</th>
<th class="num">Mean</th><th class="num">Judges</th></tr></thead>
<tbody>
{body}
</tbody></table>
<footer>Ranking: <code>{method}</code>.
Escaped from a signed, hashed publication — see the portal's results page.</footer>
</body></html>
"""
