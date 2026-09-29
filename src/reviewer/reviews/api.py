"""The scoped score endpoint and the CSV export -- the two routes T2 scores.

**Plain Django, not DRF, and the reason is a false pass.** ``djangorestframework``
is installed and configured, and the obvious way to write ``/api/v1/...`` is a
viewset. That would have been a bug, and a quiet one. Our authentication is
``DemoCredentialMiddleware``, which resolves ``Authorization: JJ1...`` and assigns
``request.user`` **before** the view runs. DRF does not read that attribute: it
builds its own ``Request`` and populates ``request.user`` from
``DEFAULT_AUTHENTICATION_CLASSES``, which is ``SessionAuthentication`` alone. A
header-only client has no session, so **every** request would have reached the
view as ``AnonymousUser`` and been refused -- and three of the four T2 checks
want a 403.

The failure mode is what makes it worth a paragraph. It is not a red check. The
refusals would be **correct-looking**: a participant refused, a peer refused, an
empty-body 403 with no ``Location``, the whole D-02 contract satisfied by
something that never read a score. ``judge cannot see peer scores`` and
``participant blocked`` would go green for a reason that has nothing to do with
isolation -- which is F-40 exactly, and F-40 is the finding this project
classifies as the most expensive shape of bug there is: *a false pass is
believed*.

So the two entry points are ordinary Django views reading ``request.user``, the
same way the judge console does. drf-spectacular is still installed and the
OpenAPI 3.1 document is a FEAT-07 item; when that is built it will be a schema
*over* these views rather than a replacement for them, because the D-02 refusal
contract is the part that must not change.

**Why a refusal is driven by the scope's decision and never by emptiness.** A
judge with no reviews yet is a legitimate ``200`` with an empty list and a
receipt that says ``allow-own, 0 of 126``. A participant is a ``403``. Those are
different answers and the difference is the *decision the accessor reached*, not
whether rows came back -- so the branch below reads ``qs.scope.decision`` and
never ``qs.exists()``. Writing it the other way round is the F-61 defect: an
empty collection is a valid value, so a test asserting ``found == []`` passes
forever and a feature that returns nothing is indistinguishable from one that
works.

**Why an unresolvable subject is a 400 and not a fall-through.** ``?judge=nobody``
silently returning *your own* scores would be a wrong answer produced by a
missing lookup, and a reader would have no way to tell it from a correct one.
That is F-42's shape -- a wrong default that happens to produce the right answer
survives a green run and lies in the one message a human reads.
"""

from __future__ import annotations

import csv
import io
import json

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from reviewer.accounts.models import User
from reviewer.isolation import Actor
from reviewer.isolation.refusal import REFUSED_BY_HEADER, deny
from reviewer.isolation.scope import DECISION_DENY
from reviewer.reviews.models import REVIEW_SUBMITTED, Review

#: The reason strings a refusal carries. They are ``module.function`` so a probe,
#: a log line and a test can all name the same guard, which is the whole point of
#: carrying a reason at all (F-40). ``api.`` rather than ``judge_console.`` because
#: these are not the console's refusals even where the rule behind them is shared.
REFUSED_BY_ROLE = "api.judge_scores.role"
REFUSED_BY_SUBJECT = "api.judge_scores.peer_scope"
REFUSED_BY_EXPORT = "api.export.role"
BAD_SUBJECT = "api.judge_scores.unknown_subject"


def _json(payload: dict, *, status: int = 200) -> HttpResponse:
    response = HttpResponse(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        content_type="application/json",
        status=status,
    )
    return response


def _review_label(review) -> str:
    """A stable, readable identifier for one review.

    **``Review.source_key`` is empty on loaded data, and this is why that has to
    be handled rather than printed.** D-11 puts ``source_key`` on every
    importable table so a round trip is byte-identical *including natural keys*,
    and the ``Review`` model inherits the column -- but the loader keys a review
    on ``(judge, project)`` and never writes the field, so all 126 rows carry an
    empty string.

    Printing it produced **a CSV whose first column was 126 empty cells**: a
    structurally perfect export in which one column contains nothing at all.
    That is F-61's exact shape -- a feature returning structurally valid output
    containing nothing -- and the test that caught it is the one asserting every
    exported value against the database, not the one asserting the header. The
    column was never the interesting assertion.

    So the label falls back to the natural key, which is what the loader actually
    keys on and what a reader can check. Recorded as **F-69**; the underlying
    gap (populate ``Review.source_key``) belongs to FEAT-07, which owns
    ``source_key`` and the byte-identical round trip.
    """
    if review.source_key:
        return review.source_key
    return f"{review.judge.source_key}:{review.project.source_key}"


# --------------------------------------------------------------------- subjects


def _demo_key_map() -> dict[str, str]:
    """``{"judge_a": "noor.haddad@example.org", ...}`` -- derived, never typed.

    ``.dogfood.toml`` names ``/api/v1/judge/scores?judge=judge_a``, and ``judge_a``
    is a **key from the acceptance file**, not anything the portal stores. The
    mapping is produced by calling the *same* ``importer.demo.choose()`` the seed
    called, so there is one rule for which person is ``judge_a`` and it lives in
    one place. A second implementation of the rule would be F-62's defect waiting
    to happen: two sources that agree until they do not.

    Cached for the process because ``fixtures.json`` is shipped in the image and
    its SHA-256 is pinned by a test, so it cannot change under us. A portal
    deployed without the file degrades to "this key names nobody", which the view
    reports as a 400 -- honest, and not a crash on the request path.
    """
    from reviewer.importer import census as census_module
    from reviewer.importer import demo as demo_module

    global _DEMO_KEYS
    if _DEMO_KEYS is None:
        try:
            fixture = census_module.load_fixture()
            chosen = demo_module.choose(census_module.census(fixture))
        except Exception:
            # Deliberately broad. This is an optional convenience form of the
            # subject parameter; nothing about isolation may depend on it, so a
            # missing fixture degrades the key form and nothing else.
            _DEMO_KEYS = {}
        else:
            _DEMO_KEYS = {identity.key: identity.email for identity in chosen}
    return _DEMO_KEYS


_DEMO_KEYS: dict[str, str] | None = None


def _resolve_subject(event, raw: str):
    """The person ``?judge=`` names, or ``None``.

    Four accepted spellings, tried in this order and all of them real: the demo
    key from ``.dogfood.toml`` (``judge_a``), the fixture's natural key
    (``jdg_01``, which is what D-11's ``source_key`` is for), an email, and a
    numeric primary key. The order matters only in that the natural key is tried
    before the email, and no spelling can be ambiguous -- an email cannot look
    like a ``jdg_NN`` key.

    Scoped to the actor's event, so a subject from another event resolves to
    ``None`` rather than to a person the caller has no relationship with.
    """
    value = raw.strip()
    if not value:
        return None

    email = _demo_key_map().get(value)
    candidates = User.objects.filter(role_bindings__event=event, is_active=True).distinct()

    if email is not None:
        return candidates.filter(email=email).first()
    return candidates.filter(source_key=value).first() or _by_pk(event, value)


def _by_pk(event, value: str):
    if not value.isdigit():
        return None
    return (
        User.objects.filter(pk=int(value), role_bindings__event=event, is_active=True)
        .distinct()
        .first()
    )


# ------------------------------------------------------------------ judge scores


def _score_rows(qs) -> list[dict]:
    """Serialize a scoped ``Review`` set, one dict per review.

    ``prefetch_related`` is what keeps this at a constant number of queries; the
    scores arrive on ``review.scores`` already fetched rather than being looked
    up per row. The earlier draft cached them on a private attribute *and*
    prefetched, which is two mechanisms for one job and would have silently
    stopped working the moment someone removed either.
    """
    return [
        {
            "review": _review_label(review),
            "project": review.project.source_key,
            "project_title": review.project.title,
            "track": review.project.track.slug,
            "judge": review.judge.source_key,
            "judge_email": review.judge.email,
            "status": review.status,
            "scores": {
                score.criterion.key: score.value
                for score in sorted(review.scores.all(), key=lambda s: s.criterion.position)
            },
        }
        for review in qs
    ]


@require_http_methods(["GET"])
def judge_scores(request, event) -> HttpResponse:
    """``/api/v1/judge/scores`` -- the caller's own scores, and nothing else.

    The three outcomes, and they are three different answers on purpose:

    * **200, allow-own** -- a judge asking for themselves. The receipt says how
      many of the event's reviews that is, so "3 of 126" is visible rather than
      asserted.
    * **403, empty body** -- a participant, a visitor, or a judge naming a peer.
      The reason travels in ``X-Refused-By`` and never in the body (D-02).
    * **400** -- ``?judge=`` named somebody this event does not contain.

    A judge with **zero** reviews gets the 200 and an empty list, because a
    decision of ``allow-own`` with nothing behind it is a working endpoint, not a
    refusal. That is the distinction F-61 is about.
    """
    actor = Actor.for_request(request, event)

    raw_subject = request.GET.get("judge", "").strip()
    subject = None
    if raw_subject:
        subject = _resolve_subject(event, raw_subject)
        if subject is None:
            return _json(
                {
                    "error": "no such judge in this event",
                    "judge": raw_subject,
                    "refused_by": BAD_SUBJECT,
                },
                status=400,
            )

    if subject is None:
        qs = Review.objects.for_actor(actor)
    else:
        qs = Review.objects.for_actor_and_subject(actor, subject)

    # The branch is on the DECISION, never on emptiness. See the module docstring.
    if qs.scope.decision == DECISION_DENY:
        return deny(REFUSED_BY_SUBJECT if subject is not None else REFUSED_BY_ROLE)

    receipt = qs.scope.with_counts(qs.count(), qs.scope_total_count())
    return _json(
        {
            "actor": {
                "email": actor.user.email if actor.user is not None else None,
                "roles": sorted(actor.roles),
                "label": actor.label,
            },
            "subject": {
                "source_key": subject.source_key,
                "email": subject.email,
            }
            if subject is not None
            else None,
            "scope": receipt.as_dict(),
            "count": receipt.visible,
            "reviews": _score_rows(qs.prefetch_related("project__track", "judge")),
        }
    )


# ------------------------------------------------------------------- csv export


@require_http_methods(["GET"])
def csv_export(request, event) -> HttpResponse:
    """``/api/v1/export.csv`` -- every score in the event, for an organizer.

    **The header is the fixture's KEY order and nothing else.** ``functionality,
    quality, innovation`` -- which is neither alphabetical nor the order the
    values appear in any row of the fixture. It comes from ``Criterion.position``,
    which the loader set from ``census.CRITERIA_KEYS``, and
    ``tests/test_api.py::test_the_export_header_is_the_fixtures_key_order``
    compares it against the order derived from ``fixtures.json`` itself.

    This is F-04 and it is worth stating what goes wrong if it is wrong: **two
    columns transpose in every row of every export, and no acceptance check, no
    test and no reader notices**, because a CSV with the right number of columns
    in the wrong order is a perfectly well-formed CSV. The one thing that catches
    it is an assertion against a value derived from the fixture rather than typed
    here -- which is the rule this project has been paying for since F-28.

    The rows are the organizer's whole event, reached through
    ``for_actor(actor)`` like every other read, so the export cannot become a
    second, unscoped path to every score in the portal.
    """
    actor = Actor.for_request(request, event)
    if not actor.can_read_all_reviews:
        return deny(REFUSED_BY_EXPORT)

    qs = Review.objects.for_actor(actor).select_related(
        "project", "project__track", "judge", "rubric_version"
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    criteria = _criteria_in_key_order(event)
    writer.writerow(
        [
            "review",
            "project",
            "project_title",
            "track",
            "judge",
            "judge_email",
            "status",
            "scores_recorded",
            "weighted_total",
            *(criterion.key for criterion in criteria),
        ]
    )
    for row in _export_rows(qs, criteria):
        writer.writerow(row)

    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="judges-scores.csv"'
    return response


def _criteria_in_key_order(event):
    """The rubric's criteria, in the fixture's key order.

    Read off ``position`` rather than off a constant so that an organizer who
    changes the rubric's *order* changes the export, and so that a test can
    compare this list against the order derived from ``fixtures.json`` and fail
    when the two disagree. The **newest** version, because ``Rubric.Meta``
    orders by ``-version`` and an organizer who re-publishes a rubric is
    exporting the one scores were written against.
    """
    from reviewer.rubrics.models import Rubric

    rubric = Rubric.objects.filter(event=event).order_by("-version").first()
    if rubric is None:
        return []
    return list(rubric.criteria.order_by("position"))


def _export_rows(qs, criteria) -> list[list]:
    """One list per review, in the header's column order.

    The per-row criterion values are looked up **by criterion key**, never by
    position in this loop. A row is a dict of ``key -> value``; the header is a
    list of keys. Pairing them positionally is the other half of F-04 and it is
    just as silent.

    ``criteria`` is passed in rather than re-read per row. The first draft called
    ``_criteria_in_key_order(review.event)`` inside the loop, which is one query
    per review -- 126 queries to produce a file -- and it is the kind of defect
    that only shows up on the export nobody runs during development.
    """
    rows = []
    for review in qs.prefetch_related("scores__criterion"):
        scores = list(review.scores.all())
        by_key = {score.criterion.key: score.value for score in scores}
        answered = [s for s in scores if s.value is not None]
        weighted = sum(float(s.value) * float(s.weight_applied) for s in answered)
        rows.append(
            [
                _review_label(review),
                review.project.source_key,
                review.project.title,
                review.project.track.slug,
                review.judge.source_key,
                review.judge.email,
                "submitted" if review.status == REVIEW_SUBMITTED else review.status,
                len(answered),
                f"{weighted:.4f}" if answered else "",
                *(by_key.get(criterion.key, "") for criterion in criteria),
            ]
        )
    return rows


# Re-exported so a caller does not have to know which module owns the header name.
__all__ = [
    "REFUSED_BY_EXPORT",
    "REFUSED_BY_HEADER",
    "REFUSED_BY_ROLE",
    "REFUSED_BY_SUBJECT",
    "csv_export",
    "judge_scores",
]
