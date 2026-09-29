"""The leaderboard: an aggregate over a scoped ``Review`` set, and when it is visible.

**This is the ``aggregate`` cell of the isolation matrix, and its own docstring
called it "the aggregate cell nobody tests and everybody forgets".** It was named
in `isolation_proof.py`'s STILL-NOT-PROVEN list from FEAT-02 onward, and the
reason it is easy to forget is that nothing about the *own* and *peer* columns
looks like a leaderboard. Isolation over a list you are browsing is a filter
question. Isolation over a **ranking** is a different question entirely, and it
is the one that matters during judging: a judge who can see the standings while
judging can infer what other judges are scoring, and the score they are about to
give stops being their own.

**The rule, and it needs no new dates.** ``Event.results_state`` is
``hidden`` on the shipped fixture and the loader does not move it, so:

* **organizer and admin** may read the leaderboard at any time -- an organizer
  who cannot see the standings cannot staff the panel;
* **judge, participant, visitor** are **refused while results are hidden**, and
  may read it once they are published.

That is the brief's "results hidden until the deadline" and it is also what makes
the aggregate cell print a *refusal* for four of the five matrix rows, which is
the honest answer. A `0/41` there would read as "verified, and there are no
projects", and the project's own `UNPROVEN` docstring names that as the option to
avoid.

**The composite is UNNORMALIZED, and says so.** It is the weighted mean of the
answered criteria, straight from the ``Score`` rows. No judge-severity
correction, no shrinkage, no median/MAD -- that is FEAT-08, and it is the most
judged part of this project. Shipping an unnormalized ranking and labelling it
`unnormalized` is defensible; shipping one and calling it "the score" is the
thing the whole detectability analysis exists to warn against. **The judge-severity
effect in the published fixture is not statistically detectable (p = 0.234), so
the ranking this produces is a fair reading of the data -- but that is a
measurement we publish, not a property the code has.**
"""

from __future__ import annotations

from reviewer.events.models import RESULTS_PUBLISHED
from reviewer.reviews.models import REVIEW_SUBMITTED, Score

#: What the leaderboard reports about itself. A ranking that does not say whether
#: it is corrected is a ranking a reader has to guess about.
NORMALIZATION = "unnormalized-raw-weighted-mean"


def results_visible_to(actor) -> bool:
    """Whether this actor may read a leaderboard for this event, right now.

    A single named predicate rather than a comparison at each call site, because
    the two questions -- "may this role" and "is it published" -- are separately
    interesting and a caller that inlines them will eventually apply only one.
    """
    if actor.can_read_all_reviews:
        return True
    return actor.event.results_state == RESULTS_PUBLISHED


def leaderboard(actor, *, limit: int | None = None) -> list[dict]:
    """Rank the projects this actor may rank.

    **Every project reaching the board is computed from a *scoped* ``Review``
    set.** For an organizer that is the whole event; for a judge it is their own
    reviews, which is why the refusal above exists at all -- without it, this
    function would be the aggregate column's answer for a judge and the standing
    would be inferred from a handful of rows.
    """
    from reviewer.isolation import Actor
    from reviewer.reviews.models import Review

    reviewer_actor = Actor(actor) if not isinstance(actor, Actor) else actor
    scoped = Review.objects.for_actor(reviewer_actor)

    rows: dict[str, dict] = {}
    for score in (
        Score.objects.filter(review__in=scoped)
        .select_related("criterion", "review", "review__project")
        .order_by("criterion__position")
    ):
        if score.value is None:
            continue
        review = score.review
        if review.status != REVIEW_SUBMITTED:
            continue
        project = review.project
        row = rows.setdefault(
            project.source_key,
            {
                "project": project.source_key,
                "title": project.title,
                "track": project.track.slug,
                "weighted_total": 0.0,
                "weight": 0.0,
                "reviews": set(),
            },
        )
        row["weighted_total"] += float(score.value) * float(score.weight_applied)
        row["weight"] += float(score.weight_applied)
        row["reviews"].add(review.source_key)

    board = []
    for row in rows.values():
        weight = row.pop("weight")
        reviews = row.pop("reviews")
        row["mean"] = round(row["weighted_total"] / weight, 4) if weight else None
        row["reviews_counted"] = len(reviews)
        row["normalization"] = NORMALIZATION
        board.append(row)

    board.sort(key=lambda r: (-(r["mean"] or 0.0), r["project"]))
    for position, row in enumerate(board, start=1):
        row["rank"] = position
    return board[:limit] if limit else board
