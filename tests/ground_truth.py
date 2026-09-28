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

FEAT-03 added four functions, and the reason each one could not have lived in
its test module is the same: a census assertion that reads the population
*through* a scoped accessor is checking the scope against itself. The loader
tests want the event-wide review count, the gallery test wants the per-project
histogram, and P4 wants "every review in the database" so it can prove the
partition. All three are the same question asked from the outside.
"""

from __future__ import annotations

from django.db.models import Count

from reviewer.reviews.models import Review

__all__ = [
    "all_review_labels",
    "all_review_pks",
    "any_review",
    "judges_with_reviews",
    "review_histogram_by_judge",
    "review_histogram_by_project",
    "reviews_by_judge",
    "reviews_in_event",
    "reviews_with_empty_comment",
    "total_reviews",
]


def total_reviews() -> int:
    """Every review in the database, in every event."""
    return Review.objects.count()


def reviews_in_event(event) -> int:
    """Every review in one event. The denominator of the receipt."""
    return Review.objects.filter(event=event).count()


def any_review():
    """One arbitrary review, judge pre-loaded.

    For the test that only needs *a* row to look at -- "does a loaded fixture row
    carry three scores" -- and not a population. A test that wanted the
    population would use ``total_reviews``.
    """
    return Review.objects.select_related("judge").first()


def reviews_by_judge(email: str) -> int:
    """How many reviews one judge has written, across the database."""
    return Review.objects.filter(judge__email=email).count()


def reviews_with_empty_comment() -> int:
    """Reviews whose comment is the empty string.

    Not "missing" -- ``bible/04`` records 51 of 126 fixture comments as empty,
    and the column is NOT NULL with a blank default precisely because an empty
    comment is data rather than an absent one.
    """
    return Review.objects.filter(overall_comment="").count()


def all_review_pks() -> set:
    """Every review's primary key, in every event.

    P4's partition is a statement about *which rows*, not how many, so it needs
    the identities rather than a count -- a count cannot tell "the right rows"
    from "the wrong number of rows".
    """
    return set(Review.objects.values_list("pk", flat=True))


def all_review_labels() -> set[tuple[str, str]]:
    """Every review as ``(project id, judge email)``.

    The same shape the scoped tests reduce to, so a comparison is a set
    equality and not a count.
    """
    return {(r.project_id, r.judge.email) for r in Review.objects.select_related("judge")}


def judges_with_reviews(event) -> set[str]:
    """The emails of every judge with at least one review in the event.

    Used to check that a judge's scope really is a subset of this set, rather
    than a subset of whatever the test happened to build.
    """
    return {r.judge.email for r in Review.objects.filter(event=event).select_related("judge")}


def _histogram(event, field: str) -> dict[int, int]:
    rows = Review.objects.filter(event=event).values(field).annotate(n=Count("id"))
    histogram: dict[int, int] = {}
    for row in rows:
        histogram[row["n"]] = histogram.get(row["n"], 0) + 1
    return dict(sorted(histogram.items()))


def review_histogram_by_project(event) -> dict[int, int]:
    """``{reviews-per-project: how many projects}``, from the stored tables.

    The database-side half of the two invariants, and the counterpart to
    ``reviewer.importer.census``'s file-side half. Two populations, two
    independent derivations, which is the only way "the two agree" means
    anything.
    """
    return _histogram(event, "project_id")


def review_histogram_by_judge(event) -> dict[int, int]:
    """``{reviews-per-judge: how many judges}``, from the stored tables."""
    return _histogram(event, "judge_id")
