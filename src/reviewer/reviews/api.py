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
import hashlib
import io
import json
import logging

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from reviewer.accounts.models import User
from reviewer.audit import chain as audit_chain
from reviewer.ballots import influence as influence_module
from reviewer.isolation import Actor
from reviewer.isolation.refusal import REFUSED_BY_HEADER, deny
from reviewer.isolation.scope import DECISION_DENY
from reviewer.reviews import results as results_module
from reviewer.reviews.models import REVIEW_SUBMITTED, Review

logger = logging.getLogger(__name__)

#: The reason strings a refusal carries. They are ``module.function`` so a probe,
#: a log line and a test can all name the same guard, which is the whole point of
#: carrying a reason at all (F-40). ``api.`` rather than ``judge_console.`` because
#: these are not the console's refusals even where the rule behind them is shared.
REFUSED_BY_ROLE = "api.judge_scores.role"
REFUSED_BY_SUBJECT = "api.judge_scores.peer_scope"
REFUSED_BY_EXPORT = "api.export.role"
REFUSED_BY_RESULTS = "api.results.hidden"
REFUSED_BY_AUDIT = "api.audit.role"
REFUSED_BY_INFLUENCE = "api.influence.role"
BAD_SUBJECT = "api.judge_scores.unknown_subject"


def _json(payload: dict, *, status: int = 200) -> HttpResponse:
    response = HttpResponse(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        content_type="application/json",
        status=status,
    )
    return response


def _log_denial(event, actor, request, object_id: str, guard: str) -> None:
    """Record a refusal in the chain.

    **Denials are logged because "who tried" is a first-class question.** A run of
    refused peer-score requests is exactly the signal a security-minded organizer
    wants, and the model's own docstring says so. The IP is stored **hashed**, never
    raw, so the entry can correlate a burst without becoming a location log -- the
    same trade ``reviewer.ballots`` makes.

    **A failure to log must not turn a refusal into a 500.** The refusal is the
    correct answer and the caller must still get it, so the whole body is guarded
    and the worst case is a trail with a gap -- which ``omitted_since_prev``
    exists to make disclosable rather than ambiguous. The failure is *reported*
    rather than swallowed, so a reviewer reading the logs can see that the trail
    dropped something instead of believing it is complete.

    **A seeded event's chain contains `denied` entries with no actor, and that is
    not noise.** `tools/run_acceptance.py`'s route-existence preconditions
    deliberately send **no credential** -- they are asking "is this URL routed at
    all", and attaching a role would make them answer a different question (F-42).
    So the portal refuses them, and refusing an anonymous request to a protected
    route is exactly the event an organizer wants in the trail. The first run of
    this feature produced a chain whose entries 4 and 5 were the gate's own
    probes; that is the refusal contract working, recorded honestly rather than
    filtered out for tidiness.
    """
    try:
        raw = request.META.get("REMOTE_ADDR", "") or ""
        audit_chain.append(
            event,
            audit_chain.ACTION_DENIED,
            actor=actor.user if actor is not None else None,
            object_type="request",
            object_id=object_id,
            after={"guard": guard},
            ip_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32] if raw else "",
        )
    except Exception as exc:  # pragma: no cover - the trail is best-effort by design
        logger.warning("audit append failed for %s: %s: %s", object_id, type(exc).__name__, exc)


def _review_label(review) -> str:
    """A stable, readable identifier for one review.

    **History, because the shape of this function is a scar.** It used to print
    ``Review.source_key`` directly, and produced **a CSV whose first column was
    126 empty cells**: a structurally perfect export in which one column contains
    nothing at all. That is F-61's exact shape, and the test that caught it
    asserts every exported value against the database rather than the header --
    the column was never the interesting assertion. Recorded as **F-69**.

    The immediate repair was this fallback to the ``(judge, project)`` natural
    key. **FEAT-07 then fixed the cause** -- the loader now writes
    ``Review.source_key`` -- which is what a NULL-keyed row needed, because the
    bulk importer matches on the natural key and a NULL-keyed review could not
    round-trip at all.

    **So the fallback is now dead on loaded data, and that is worth saying out
    loud rather than deleting.** It is still reachable for a review created inside
    the portal, which has no external identity; and the mutation that removes it
    became *undetectable* the moment the loader started writing the column --
    which is a warning about every test that only ever exercises the happy path.
    ``tests/test_bulk_round_trip.py`` now builds a review with no ``source_key``
    on purpose so this branch stays load-bearing.
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
        guard = REFUSED_BY_SUBJECT if subject is not None else REFUSED_BY_ROLE
        _log_denial(event, actor, request, f"judge/scores?judge={raw_subject or '-'}", guard)
        return deny(guard)

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
        _log_denial(event, actor, request, "export.csv", REFUSED_BY_EXPORT)
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
    rows = _export_rows(qs, criteria)
    for row in rows:
        writer.writerow(row)

    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="judges-scores.csv"'

    # The audit trail records the EXPORT, not just the denial -- a bulk read of
    # every score in the event is the single action an organizer most needs to be
    # able to answer for. `scope_reason` is the receipt, so the entry answers
    # "what was this actor able to see" as well as "what did they do".
    #
    # `with_counts` rather than the bare `Scope`: the receipt is only useful with
    # the numbers, and `as_dict` lives on the counted form. Same object the
    # response body already renders, so the two cannot disagree.
    receipt = qs.scope.with_counts(qs.count(), qs.scope_total_count())
    audit_chain.append(
        event,
        audit_chain.ACTION_EXPORT_RUN,
        actor=actor.user,
        object_type="event",
        object_id=event.pk,
        after={"rows": len(rows), "columns": [c.key for c in criteria]},
        scope_reason=receipt.as_dict(),
    )
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


# ---------------------------------------------------------------- the leaderboard


@require_http_methods(["GET"])
def results(request, event) -> HttpResponse:
    """``/api/v1/results`` -- the ranking, when the actor is allowed to see one.

    **Refused while results are hidden, for everyone but an organizer.** The
    shipped fixture is born with ``results_state = hidden``, so on the demo data
    this endpoint is a 403 for a judge, a participant and a visitor, and a 200
    for an organizer. That is the ``aggregate`` cell of the isolation matrix and
    it is the one its own docstring called "nobody tests and everybody forgets".

    **Why the refusal matters more here than anywhere else on the portal.** A
    judge browsing their own reviews sees only their own; there is nothing to
    infer. A judge reading a *ranking* can infer what other judges scored, and
    the score they are about to give stops being their own. This is the one
    capability where "scoped to your own rows" is the wrong frame, because the
    rows are not the leak -- the ordering is.
    """
    actor = Actor.for_request(request, event)
    if not results_module.results_visible_to(actor):
        return deny(REFUSED_BY_RESULTS)

    board = results_module.leaderboard(actor)
    return _json(
        {
            "actor": {"label": actor.label, "roles": sorted(actor.roles)},
            "results_state": event.results_state,
            "normalization": results_module.NORMALIZATION,
            "count": len(board),
            "ranking": board,
        }
    )


# ------------------------------------------------------------------ the audit view


@require_http_methods(["GET"])
def audit(request, event) -> HttpResponse:
    """``/api/v1/audit`` -- the chain, its head, and whether it verifies.

    **Organizer and admin only.** There is no honest per-actor slice of an audit
    trail: a judge asking for their own history would get a trail with gaps where
    other people's actions were, and a gap in an audit trail is exactly what
    ``omitted_since_prev`` exists to stop being ambiguous. All or nothing.

    The verification result is part of the response rather than a separate
    command, because **a reader who has to run a second tool to find out whether
    the trail they were shown is intact will not run it.**
    """
    actor = Actor.for_request(request, event)
    entries, permitted = audit_chain.for_actor(actor)
    if not permitted:
        return deny(REFUSED_BY_AUDIT)

    problems = audit_chain.verify_chain(event)
    return _json(
        {
            "count": len(entries),
            "chain_head": audit_chain.AuditEntry.chain_head(event),
            "verified": not problems,
            "problems": problems,
            "entries": [
                {
                    "seq": entry.seq,
                    "action": entry.action,
                    "actor": entry.actor.email if entry.actor_id else None,
                    "object": f"{entry.object_type}:{entry.object_id}".strip(":"),
                    "at": entry.created_at.isoformat(),
                    "entry_hash": entry.entry_hash,
                    "prev_hash": entry.prev_hash,
                    "omitted_since_prev": entry.omitted_since_prev,
                }
                for entry in entries
            ],
        }
    )


# ------------------------------------------------------------ the influence report


@require_http_methods(["GET"])
def influence(request, event) -> HttpResponse:
    """``/api/v1/influence`` -- the anti-abuse report, before publication (D-13).

    **Readable while the leaderboard is refused, and that asymmetry is the point.**
    ``/api/v1/results`` is a 403 for everyone but an organizer until
    ``results_state`` is published, because a ranking during judging lets a judge
    infer what other judges are scoring. This endpoint is about *concentration*,
    not about the outcome, and the organizer has to see it **before** deciding to
    publish -- that is the whole value of a report over a mechanism. Refusing it
    until after publication would make it a post-mortem.

    **So the two endpoints answer different questions and are gated differently on
    purpose**, and there is a test that pins the contrast: a judge is refused the
    leaderboard *and* refused this, an organizer sees both, and the organizer sees
    this one while results are still hidden. If a later change ever makes the two
    share a guard, the report stops being able to do its job.

    **The empty case is a 200 with an explicit ``no_votes`` reason, never a table
    of zeros.** The shipped fixture has no votes, and forty-one rows of
    ``gini 0.00`` would be F-61 for the fifth time: a structurally perfect report
    saying nothing, indistinguishable from a clean one. ``report()`` returns
    ``None`` and this view says so in a field whose name is the claim.
    """
    actor = Actor.for_request(request, event)
    payload, permitted = influence_module.report_for_actor(actor)
    if not permitted:
        return deny(REFUSED_BY_INFLUENCE)

    if payload is None:
        return _json(
            {
                "status": "no_votes",
                "reason": (
                    "No ballots have been cast for this event, so there is no vote "
                    "concentration to report. This is not a finding that no "
                    "brigade exists."
                ),
                "method": influence_module.REPORT_METHOD,
                "ranking": [],
            }
        )

    return _json({"status": "ok", **payload})


# Re-exported so a caller does not have to know which module owns the header name.
__all__ = [
    "REFUSED_BY_AUDIT",
    "REFUSED_BY_EXPORT",
    "REFUSED_BY_HEADER",
    "REFUSED_BY_INFLUENCE",
    "REFUSED_BY_RESULTS",
    "REFUSED_BY_ROLE",
    "REFUSED_BY_SUBJECT",
    "audit",
    "csv_export",
    "influence",
    "judge_scores",
    "results",
]
