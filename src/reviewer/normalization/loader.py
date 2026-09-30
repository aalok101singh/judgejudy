"""Turn the database into what the estimator and the proof need.

**One composite per REVIEW, not per criterion, and that is load-bearing.** The
variance decomposition runs over the composites and the published figure is
``N = 126`` — the number of reviews. Taking a row per criterion would give 378
inputs, change every published number, and look like nothing had changed. The
`--composites` count is asserted in `tests/test_normalization.py` for exactly
this reason.

**The composite is the review's weighted mean of its ANSWERED criteria**, the
same value `results.leaderboard` computes, so the leaderboard and the proof cannot
disagree about what a score was before normalization touched it.
"""

from __future__ import annotations

from reviewer.reviews.models import Review, Score


def composites(event=None) -> list[tuple[str, str, float]]:
    """``(judge_key, project_key, weighted_mean)`` for every submitted review."""
    event = event or _current_event()
    qs = (
        Review.objects.for_cross_judge_analysis(event.pk)
        .filter(status="submitted")
        .exclude(rubric_version=None)
        .select_related("judge", "project")
    )
    out: list[tuple[str, str, float]] = []
    for review in qs:
        weighted_total = 0.0
        weight = 0.0
        for score in Score.objects.filter(review=review):
            if score.value is None:
                continue
            weighted_total += float(score.value) * float(score.weight_applied)
            weight += float(score.weight_applied)
        if weight:
            out.append(
                (review.judge.source_key, review.project.source_key, weighted_total / weight)
            )
    return out


def by_judge(event=None) -> dict[str, list[float]]:
    """The same composites, grouped by judge, for the variance decomposition."""
    groups: dict[str, list[float]] = {}
    for judge, _project, value in composites(event):
        groups.setdefault(judge, []).append(value)
    return groups


def _current_event():
    from reviewer.events.models import Event

    event = Event.objects.order_by("pk").first()
    if event is None:
        raise RuntimeError("no event; run the loader first")
    return event
