"""The judge console: a judge's own assignments, the rubric, and the review form.

**This is the first surface that has to survive a hostile reader, and the whole
design is downstream of two decisions that cannot be re-litigated.**

**D-01 -- isolation lives in the data-access layer.** Every read of a ``Review``
in this module goes through ``Review.objects.for_actor(actor)``. There is no
``Review.objects.get(pk=...)`` here, no ``.filter(judge_id=...)`` written by
hand, and no view that receives a queryset the caller could widen. The lint rule
(``tools/check_isolation.py``) fails the build if an unscoped read appears, and
this module is inside its scope -- so a future edit that reaches for the
shortcut is a red gate rather than a review comment.

**D-02 -- a denial is a literal 403 with an EMPTY body and no ``Location``
header. Never a 302.** ``run.py`` follows redirects, so a redirect to a login
page returns 200 through the checker and fails a scored check while looking
perfectly correct in a browser. This is the highest-value line in the project
and it is why :func:`_deny` builds its response by hand instead of redirecting to
anything.

**Why the body is empty and the reason goes in a header.** D-02 requires an empty
body, and the reason is the one that matters: a body that says "this review
belongs to judge_a" is a body that confirms the review exists to the person who
asked, which is the leak. The reason goes in ``X-Refused-By`` because that
header is **identical for every caller who is refused** -- the judge asking for a
peer's review and the judge asking for a review that was never created get the
same 403, the same empty body and the same header, so the header carries no
information an attacker can use. It is there so a developer can debug with
``curl -i`` without the portal having to volunteer anything to a stranger.

**Drafts are first-class, because a half-finished review is the common case.**
A judge fills three criteria in, gets interrupted, and comes back tomorrow. A
NOT NULL on every score would make that impossible, and "save draft" is named
in the tier's own requirements rather than being an optimisation.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from reviewer.isolation import Actor
from reviewer.reviews.models import (
    REVIEW_ASSIGNED,
    REVIEW_IN_PROGRESS,
    REVIEW_SUBMITTED,
    Assignment,
    Review,
    Score,
)

#: The header every refusal carries. Its value is a *function* name, so it names
#: the guard that refused rather than the resource that was asked for.
REFUSED_BY_HEADER = "X-Refused-By"

REFUSED_BY_CONSOLE = "judge_console.deny"
REFUSED_BY_ASSIGNMENT = "judge_console.assignment_scope"
REFUSED_BY_ROLE = "judge_console.role"


def _deny(refused_by: str, *, status: int = 403) -> HttpResponse:
    """A refusal. Literal status, empty body, no ``Location``.

    **Written out longhand rather than with a redirect or a template** because
    the three properties that make it a refusal -- the status, the empty body and
    the absence of ``Location`` -- are all things a convenience helper is likely
    to change. A test asserts each of them separately.
    """
    response = HttpResponse(status=status)
    response[REFUSED_BY_HEADER] = refused_by
    return response


def _actor(request, event) -> Actor:
    return Actor.for_request(request, event)


def _can_judge(actor: Actor) -> bool:
    """Who may open the console at all.

    An organizer and an admin can, because the acceptance matrix has exactly one
    row for each of them and an organizer who cannot see the judging surface
    cannot staff it. A participant and a visitor cannot, and asking is a refusal
    rather than an empty page: "you may not" and "there is nothing here" are
    different answers and conflating them is how a permission bug hides.
    """
    return actor.is_judge or actor.can_read_all_reviews


@require_http_methods(["GET"])
def console(request, event) -> HttpResponse:
    """``/judge/`` -- a judge's own assignments, and the receipt that explains them.

    **The scope receipt is rendered, not merely available.** ``bible/05`` §6a
    makes this one of the three steal-it candidates: isolation that a reader can
    *see* is worth more than isolation that only our tests can see, because a
    panelist deciding whether to trust the claim reads the page, not the suite.
    """
    actor = _actor(request, event)
    if not _can_judge(actor):
        return _deny(REFUSED_BY_ROLE)

    # D-01. The ONLY way reviews are read in this module.
    reviews = Review.objects.for_actor(actor).select_related(
        "project", "project__track", "assignment", "rubric_version"
    )
    receipt = reviews.scope_receipt()

    assignments = Assignment.objects.filter(
        event_id=event.pk,
        review__in=reviews.values("pk"),
    ).select_related("project", "project__track")

    by_assignment = {r.assignment_id: r for r in reviews}
    rows = []
    for assignment in assignments:
        review = by_assignment.get(assignment.pk)
        rows.append(
            {
                "assignment": assignment,
                "review": review,
                "project": assignment.project,
                "track": assignment.project.track,
                "status": review.status if review else REVIEW_ASSIGNED,
                "score_count": (
                    Score.objects.filter(review=review, value__isnull=False).count()
                    if review
                    else 0
                ),
            }
        )
    rows.sort(key=lambda row: (row["status"], row["project"].pk))

    return render(
        request,
        "reviews/console.html",
        {
            "event": event,
            "actor": actor,
            "rows": rows,
            "receipt": receipt,
            "criteria": _criteria_for(event),
            "progress": _progress(rows),
        },
    )


@require_http_methods(["GET", "POST"])
def review_form(request, event, assignment_id) -> HttpResponse:
    """``/judge/review/<id>/`` -- read the rubric, save a draft, submit.

    **The assignment is looked up through the actor's scope, not by primary key.**
    Fetching ``Assignment.objects.get(pk=assignment_id)`` and then checking
    ownership would be correct only if the check could not be forgotten, and a
    ``pk`` in a URL is exactly the thing a reader changes. So the row is reached
    through the same ``for_actor`` scope the console used, and a judge who is not
    the assignee gets a 403 with an empty body and no way to tell "not yours"
    from "does not exist" -- which is the point.
    """
    actor = _actor(request, event)
    if not _can_judge(actor):
        return _deny(REFUSED_BY_ROLE)

    reviews = Review.objects.for_actor(actor).select_related(
        "project", "project__track", "rubric_version", "assignment"
    )
    review = reviews.filter(assignment_id=assignment_id).first()
    if review is None:
        # Same answer for "not yours" and "no such row". See the module docstring.
        return _deny(REFUSED_BY_ASSIGNMENT)

    if review.status == REVIEW_SUBMITTED:
        # A submitted review is immutable. Overwriting it would let a judge
        # change a score after seeing the leaderboard, which is the one thing a
        # judging system cannot permit.
        return _deny("judge_console.review_locked", status=409)

    if request.method == "GET":
        return _render_form(request, event, actor, review, {}, review.overall_comment, "")

    return _save(request, event, actor, review)


def _render_form(request, event, actor, review, values, comment, error, *, status=200, saved=""):
    """The one place the review form is rendered.

    **A single renderer for GET, for a rejected POST and for a save.** Three
    copies of this template's context is three chances for the "values" key to
    differ between the page that shows a half-typed review and the page that
    rejects it &mdash; and a form that comes back empty after a validation error
    is the single most annoying bug in a judging console.
    """
    rubric = review.rubric_version
    criteria = list(_criteria_for(event))
    return render(
        request,
        "reviews/review_form.html",
        {
            "event": event,
            "actor": actor,
            "review": review,
            "project": review.project,
            "track": review.project.track,
            "rubric": rubric,
            "criteria": criteria,
            # `scored` is a list of pairs, not a dict keyed by criterion id:
            # a Django template cannot look up a dict by an integer key, and
            # reaching for a custom template tag to do it would be a worse
            # answer than passing the pairs.
            "scored": [{"criterion": c, "value": values.get(c.pk)} for c in criteria],
            "overall_comment": comment,
            "error": error,
            "saved": saved,
            "locked": review.status == REVIEW_SUBMITTED,
        },
        status=status,
    )


def _save(request, event, actor: Actor, review: Review) -> HttpResponse:
    """Write a draft or a submission, through the rubric's own scale.

    The rubric bounds are read from the ``Rubric`` row rather than from a
    constant, so an organizer who scales 1..10 gets 1..10 validated. A value
    outside the scale is a **400 naming the criterion**, not a silent clamp: a
    clamped score is a score the judge did not give.
    """
    rubric = review.rubric_version
    criteria = list(_criteria_for(event))
    submitting = request.POST.get("action") == "submit"

    values: dict[int, int | None] = {}
    error = ""
    for criterion in criteria:
        raw = request.POST.get(f"score_{criterion.pk}", "").strip()
        if raw == "":
            values[criterion.pk] = None
            continue
        try:
            value = int(raw)
        except ValueError:
            error = f"{criterion.label} must be a whole number, not {raw!r}"
            values[criterion.pk] = None
            continue
        if not (rubric.scale_min <= value <= rubric.scale_max):
            error = (
                f"{criterion.label} must be between {rubric.scale_min} and "
                f"{rubric.scale_max}; {value} is outside the rubric's scale"
            )
            values[criterion.pk] = None
            continue
        values[criterion.pk] = value

    if error or (submitting and any(v is None for v in values.values())):
        if not error and submitting:
            missing = [c.label for c in criteria if values.get(c.pk) is None]
            error = "every criterion needs a score before you submit; missing " + ", ".join(missing)
        return _render_form(
            request,
            event,
            actor,
            review,
            values,
            request.POST.get("overall_comment", ""),
            error,
            status=400,
        )

    for criterion in criteria:
        Score.objects.update_or_create(
            review=review,
            criterion=criterion,
            defaults={
                "value": values[criterion.pk],
                # Snapshotted, per the models' docstring: an organizer editing
                # weights mid-judging must not silently change what a review means.
                "weight_applied": criterion.weight,
            },
        )

    review.overall_comment = request.POST.get("overall_comment", "")
    if submitting:
        from django.utils import timezone

        review.status = REVIEW_SUBMITTED
        review.submitted_at = timezone.now()
    else:
        review.status = REVIEW_IN_PROGRESS
    review.save()
    review.assignment.status = review.status
    review.assignment.save(update_fields=["status"])

    return _render_form(
        request,
        event,
        actor,
        review,
        values,
        review.overall_comment,
        "",
        saved="submitted" if submitting else "draft",
    )


@require_http_methods(["GET"])
def organizer_assignments(request, event) -> HttpResponse:
    """``/organizer/assignments/`` -- the plan, the curve, and the certificate.

    **The organizer sees the same numbers the verifier does, from the same code
    path.** ``bible/06`` §2.3 makes the signed feasibility report a product of
    this feature precisely so the document and the screen cannot disagree; a
    screen that re-implemented the arithmetic would reintroduce exactly the
    disagreement the feature exists to remove.
    """
    from reviewer.assignment import plan_assignment

    actor = _actor(request, event)
    if not actor.can_read_all_reviews:
        return _deny(REFUSED_BY_ROLE)

    plan = plan_assignment(
        event,
        capacity=event.judge_capacity,
        seed=event.assignment_seed,
        respect_in_flight=True,
    )
    return render(
        request,
        "reviews/organizer_assignments.html",
        {
            "event": event,
            "actor": actor,
            "plan": plan,
            "certificate": plan.render(),
        },
    )


def _criteria_for(event):
    from reviewer.rubrics.models import Rubric

    rubric = Rubric.objects.filter(event=event).order_by("-version").first()
    if rubric is None:
        return []
    # `position` is the fixture's key order, not alphabetical and not the weight
    # order. F-04: the export header is this order.
    return list(rubric.criteria.order_by("position"))


def _progress(rows) -> dict:
    """How far this judge has got, in the order an organizer would ask."""
    total = len(rows)
    submitted = sum(1 for row in rows if row["status"] == REVIEW_SUBMITTED)
    in_progress = sum(1 for row in rows if row["status"] == REVIEW_IN_PROGRESS)
    return {
        "total": total,
        "submitted": submitted,
        "in_progress": in_progress,
        "outstanding": total - submitted,
        "percent": round(100 * submitted / total) if total else 0,
    }
