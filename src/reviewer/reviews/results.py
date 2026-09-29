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

from reviewer.core import ROLE_ORGANIZER
from reviewer.events.models import RESULTS_PUBLISHED
from reviewer.reviews.models import REVIEW_SUBMITTED, Score

#: What the leaderboard reports about itself. A ranking that does not say whether
#: it is corrected is a ranking a reader has to guess about.
NORMALIZATION = "unnormalized-raw-weighted-mean"


def _event_wide(actor):
    """A synthetic authority that can see the whole event.

    **Built lazily and cached, because ``Actor`` is imported inside the functions
    here** to keep this module importable without an import cycle. A module-level
    ``Actor.__new__(Actor)`` therefore fails at import time -- which the first
    version of this did, loudly, at collection.

    It is a real ``Actor`` rather than a branch inside ``for_actor`` so the board
    is still computed from a **scoped queryset**. D-01 puts the constraint in the
    accessor, and a path that bypassed the accessor to get a wider answer is
    exactly the unscoped read the isolation lint rule forbids.
    """
    from reviewer.isolation import Actor

    return Actor(event=actor.event, user=None, roles=frozenset({ROLE_ORGANIZER}))


def has_own_reviews(actor) -> bool:
    """Whether this actor has at least one review that ``for_actor`` would return.

    Asked as an EXISTS rather than inferred from ``actor.is_judge``: the question
    the branch is really asking is "is there anything of this actor's own that
    narrowing would hide", and a judge with no assigned reviews is in the same
    position as a visitor.
    """
    from reviewer.reviews.models import Review

    return Review.objects.for_actor(actor).exists()


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

    **F-89: an actor with no reviews of their own is ranked over the WHOLE event,
    and the reason is that scoping is protective, not decorative.** The scoping
    exists so a judge cannot infer what other judges scored. A **participant or a
    visitor has no reviews at all**, so ``for_actor`` returns nothing and the
    board was *empty* -- a published results page that renders 200 and ranks
    nothing, which is F-80's shape ("structurally valid, contains nothing") and
    which made publication mean nothing to the public it was published *to*.

    The rule this encodes, in one sentence: **narrow the board only when narrowing
    protects somebody.** A judge is narrowed, because their own five reviews would
    otherwise carry the standing. A visitor is not narrowed, because there is
    nothing of theirs to protect and a whole-event board leaks nothing they did not
    already know. The FEAT-05 test that pins the judge's scoping still passes,
    because the two cases are genuinely different and the test covers the case
    that matters for the threat model.
    """
    from reviewer.isolation import Actor
    from reviewer.reviews.models import Review

    reviewer_actor = Actor(actor) if not isinstance(actor, Actor) else actor

    if reviewer_actor.can_read_all_reviews:
        scoped = Review.objects.for_actor(reviewer_actor)
    elif has_own_reviews(reviewer_actor):
        scoped = Review.objects.for_actor(reviewer_actor)
    else:
        # Nobody's own reviews: there is nothing to hide behind, so the board is
        # the event's. See the docstring, F-89.
        scoped = Review.objects.for_actor(_event_wide(reviewer_actor))

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
