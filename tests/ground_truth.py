"""Ground truth: the event-wide totals the scoping tests check themselves against.

**This is the one test module on the isolation lint's allowlist, and the reason
is the receipt's arithmetic.** ``for_actor().scope_receipt()`` claims "3 of 126".
That is evidence only if the 126 was computed independently of the filter that
produced the 3 -- if the denominator came from the same queryset, the receipt
would be quoting its own filter back at the reader as independent evidence, and a
scope that dropped 95% of the rows for a reason unrelated to authorization would
render a confidently wrong number.

So the unscoped read lives HERE, in one named place, and every other test module
reaches the totals through it. One allowlist entry with a reason beats five
tests each quietly holding their own unscoped handle.

**Nothing here is scoped, and nothing here should be.** If a function here ever
needed an actor it would be a ground-truth function that is not ground truth.
"""

from __future__ import annotations

from reviewer.reviews.models import Review

__all__ = [
    "all_review_labels",
    "judges_with_reviews",
    "reviews_in_event",
    "total_reviews",
]


def total_reviews() -> int:
    """Every review in the database, in every event."""
    return Review.objects.count()


def reviews_in_event(event) -> int:
    """Every review in one event. The denominator of the receipt."""
    return Review.objects.filter(event=event).count()


def all_review_labels() -> set[tuple[str, str]]:
    """Every review as ``(project id, judge email)``.

    The same shape the scoped tests reduce to, so a comparison is a set
    equality and not a count -- a count cannot tell "the right rows" from "the
    wrong number of rows", which is the distinction that matters.
    """
    return {(r.project_id, r.judge.email) for r in Review.objects.select_related("judge")}


def judges_with_reviews(event) -> set[str]:
    """The emails of every judge with at least one review in the event.

    Used to check that a judge's scope really is a subset of this set, rather
    than a subset of whatever the test happened to build.
    """
    return {r.judge.email for r in Review.objects.filter(event=event).select_related("judge")}
