"""``/vote/`` -- the ballot, in an order this voter cannot re-roll.

**The claim this surface makes, stated the way D-12 states it:** randomised
order makes position bias zero-**mean**, not zero. The page says so, in the
markup, on every render -- because a page that showed a randomised order without
saying what the randomisation does is the kind of page a reviewer reads as
"position bias solved", and the harness says in `bias_attack.py` that it is not.

**What the page will not do is pretend the guarantee is stronger than it is.**
Two things are therefore rendered that a demo would hide:

* the **seed**, so the order is reproducible and checkable rather than merely
  asserted to have existed (`Ballot.seed`'s own docstring);
* the fact that the order is stored, so a refresh returns the same ballot. A
  reader who cannot see the mechanism cannot audit it.

**Why a refusal here is a refusal and not an empty page.** A visitor who cannot
be identified gets a 403 naming the guard, and so does a closed event. "You may
not" and "there is nothing here" are different answers -- see
`isolation/refusal.py` -- and the ballot is exactly the case where conflating
them would be most costly, because an empty ballot and a random ballot look the
same to whoever is trying to stack the vote.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from reviewer.ballots import order as ballot_order_module
from reviewer.ballots import tally
from reviewer.ballots.models import Ballot, Vote
from reviewer.isolation import Actor, refusal
from reviewer.projects.models import Project

#: Refusal reasons. The names are the machine-readable half of F-40: a 403 with a
#: reason in the header can be told apart from a 403 produced by CSRF, a 401, or
#: a route that does not exist.
REFUSED_BY_VOTING_CLOSED = "ballot.voting_closed"
REFUSED_BY_NO_IDENTITY = "ballot.no_identity"
REFUSED_BY_NO_EVENT = "ballot.no_event"
REFUSED_BY_BUDGET = "ballot.identity_budget_exhausted"

#: The wording the page is not allowed to drift away from. D-12's caveat, as a
#: constant, so a template edit cannot quietly upgrade "zero-mean" into
#: "eliminates" -- which `tests/test_bias_attack.py` already forbids in the
#: harness output, and which would be the same lie in a second place.
ZERO_MEAN_CAVEAT = (
    "This order is randomised per voter, stably across requests. "
    "That makes position bias zero-MEAN across the panel, not zero for any one "
    "ballot. The bias-attack harness measures the residual spread, and it does "
    "not vanish."
)


def voting_open(event) -> bool:
    """Whether the voting window is open, as a named predicate.

    Same shape as ``results.results_visible_to``: a named question rather than a
    comparison at each call site, because "is voting open" and "may this actor
    vote" are separately interesting and a caller that inlines them will
    eventually apply only one.
    """
    return event.voting_mode != "closed"


def ballot(request, event) -> HttpResponse:
    """``/vote/`` -- this voter's randomised ballot, and the cast path.

    **The POST is CSRF-enforced, through the wrapper ``projects.views`` already
    wrote.** That wrapper is imported rather than reimplemented, and the reason is
    the same one that produced D-02: a claim like "our writes are CSRF-protected"
    is only worth anything if there is one implementation of it. A second copy
    would be a second thing to get wrong, in the layer where a mistake lets a
    third party cast a vote as somebody else.

    The wrapper is only reached for requests a cross-origin form could have sent --
    ``_requires_csrf`` already encodes that rule and is reused too, so the
    exemption surface is decided in one place.
    """
    from reviewer.projects.views import _csrf_enforced, _requires_csrf

    if _requires_csrf(request):
        # The `event` is bound here rather than passed through, because
        # `_csrf_enforced` calls the view as `view(request)` with no positional
        # arguments -- it is written for `/projects/new`, which takes only the
        # request. Passing `event` positionally would arrive as a second
        # positional argument the wrapper does not forward.
        return _csrf_enforced(lambda r: _ballot(r, event))(request)
    return _ballot(request, event)


@require_http_methods(["GET", "POST"])
def _ballot(request, event) -> HttpResponse:
    """``/vote/`` -- this voter's randomised ballot, and the cast path.

    **GET renders the order; POST records a ranking against it.** ``ballot`` above
    is the entry point and owns the CSRF decision; this is the work.
    """
    if event is None:
        return refusal.deny(REFUSED_BY_NO_EVENT)
    if not voting_open(event):
        return refusal.deny(REFUSED_BY_VOTING_CLOSED)

    actor = Actor.for_request(request, event)
    voter_key = ballot_order_module.voter_identity(event, request, user=actor.user)
    if voter_key is None:
        # Refused, not anonymous. See the module docstring.
        return refusal.deny(REFUSED_BY_NO_IDENTITY)

    # Sorted by primary key, explicitly, because `ballot_order` permutes
    # POSITIONS and the base order has to be deterministic for the seed to
    # determine what the voter sees. This is that determinism.
    projects = list(Project.objects.filter(event=event).order_by("pk"))
    by_pk = {p.pk: p for p in projects}

    ballot_row = ballot_order_module.ballot_order(event, voter_key, projects)
    shown = ballot_order_module.ordered_projects(ballot_row, by_pk)

    context = {
        "event": event,
        "actor": actor,
        "projects": shown,
        "ballot": ballot_row,
        "total": len(projects),
        "caveat": ZERO_MEAN_CAVEAT,
        "budget": tally.budget_for(ballot_row),
        "spent": tally.spent(event, ballot_row.voter_key),
        "max_weight": tally.MAX_WEIGHT_PER_PROJECT,
        "rows": [],
        "error": "",
        "cast": False,
    }

    # The weight each project already carries, joined onto the row so the template
    # does not need a dict lookup by variable key (there is no such filter). A
    # project not yet voted on renders as an EMPTY box rather than 0, so
    # "unvoted" and "voted zero" are not the same submission.
    cast_weights = dict(
        Vote.objects.filter(event=event, voter_key=ballot_row.voter_key).values_list(
            "project_id", "weight"
        )
    )
    context["rows"] = [{"project": p, "weight": cast_weights.get(p.pk, "")} for p in shown]

    if request.method == "POST":
        return _cast(request, event, ballot_row, context)

    return render(request, "ballots/ballot.html", context)


def _parse_ranking(request, ballot_row) -> tuple[list[tuple[str, int]], str]:
    """Read ``project`` / ``weight`` field pairs into an ordered ranking.

    **The submission order is the ranking**, read from the sorted field-name index
    rather than from a hidden ``position`` field, so a voter who reorders the page
    in their browser cannot reorder their own ballot: what they submit is the
    ballot order the server already fixed, and the weights are what they chose.
    That is the difference between a ballot and a free-text ranking, and it is why
    a determined voter cannot use the form to submit an order they were never
    shown.
    """
    pairs: list[tuple[int, str, int]] = []
    for key in request.POST:
        if not key.startswith("weight_"):
            continue
        project_pk = key[len("weight_") :]
        raw = (request.POST.get(key) or "").strip()
        if raw == "":
            continue
        try:
            weight = int(raw)
        except ValueError:
            return [], f"weight for {project_pk} must be a whole number, not {raw!r}"
        if project_pk not in ballot_row.order:
            return [], "a submitted project is not on this ballot"
        pairs.append((ballot_row.order.index(project_pk), project_pk, weight))
    pairs.sort()
    return [(pk, w) for _, pk, w in pairs], ""


def _cast(request, event, ballot_row, context) -> HttpResponse:
    """Record the submitted ranking, or explain precisely why it was refused."""
    ranking, error = _parse_ranking(request, ballot_row)
    if error:
        context["error"] = error
        return render(request, "ballots/ballot.html", context, status=400)

    if request.POST.get("action") == "abstain":
        # An abstention IS a ballot with no votes. Attributable because the
        # Ballot row exists, and free because it spends nothing. See tally.py.
        context["cast"] = True
        context["abstained"] = True
        context["error"] = ""
        return render(request, "ballots/ballot.html", context)

    _votes, error = tally.cast(event, ballot_row, ranking=ranking)
    if error:
        # A budget refusal is a 403 with an EMPTY BODY (D-02) and arrives here as
        # an HttpResponse rather than a string. A malformed request is a 400 with
        # a message, and the two must not be conflated: F-40's shape.
        if isinstance(error, HttpResponse):
            return error
        context["error"] = error
        return render(request, "ballots/ballot.html", context, status=400)

    context["cast"] = True
    context["error"] = ""
    # F-85: the budget line is RE-READ after the write. It was built with the
    # context, which happens before the cast, so the page a voter lands on after
    # voting said "0 of 41 weight spent" -- a stale value rendered as a current
    # one. Structurally correct, factually a lie about the voter's own action, and
    # invisible to every shape assertion. A context is a snapshot, and this one
    # was being reused after the fact it describes had changed.
    _recompute(context, event, ballot_row)
    return render(request, "ballots/ballot.html", context)


def _recompute(context: dict, event, ballot_row) -> None:
    """Refresh the values a page shows about the voter's own state.

    Split out because the context is assembled once and the ballot changes during
    the request, and the two must not be confused: ``budget`` is a property of
    the ballot and never changes, while ``spent`` and the per-project weights are
    properties of what the voter has done.
    """
    context["spent"] = tally.spent(event, ballot_row.voter_key)
    cast_weights = dict(
        Vote.objects.filter(event=event, voter_key=ballot_row.voter_key).values_list(
            "project_id", "weight"
        )
    )
    context["rows"] = [
        {"project": row["project"], "weight": cast_weights.get(row["project"].pk, "")}
        for row in context["rows"]
    ]


def ballot_for(event, request, *, user=None) -> Ballot | None:
    """The stored ballot for this request, or ``None`` if there is no identity.

    Kept beside the view rather than inside it because the harness and the audit
    trail need the same answer and neither should go through a view. **It does not
    render**, so importing it cannot create a ballot by accident -- a test that
    wanted to *assert* no ballot exists would otherwise create one.
    """
    voter_key = ballot_order_module.voter_identity(event, request, user=user)
    if voter_key is None:
        return None
    return Ballot.objects.filter(event=event, voter_key=voter_key).first()
