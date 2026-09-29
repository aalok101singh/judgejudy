"""Casting a vote, and turning votes into a ranking (REQ-T3-01).

**The budget is the whole design, and it is one number's worth of arithmetic.**

D-12 says voting claims cost **amplification inside an identity budget, not
Sybil resistance** -- we are not trying to stop someone buying forty identities,
we are trying to stop one identity concentrating. So the rule is a **cap on the
total weight a single ``voter_key`` may spend, equal to the number of projects on
that voter's ballot.**

The consequence is the point: **casting weight 1 on every project exactly exhausts
the budget and no more.** A voter who wants to give a project weight 3 must give
something else up. That is what makes the ballot **constant-sum**, and constant-sum
is the property `bias_attack.schwartzian`'s docstring relies on when it says total
points are fixed "so any drift is a genuine redistribution ... and there is no room
for a uniform inflation to hide inside."

**A budget that cannot bind is not a budget.** An earlier framing of this was
"weight 1..3, cap 3 x n_projects", which permits weight 3 on *every* project --
non-binding by construction, and therefore decoration. The binding version is
below and the tests assert it binds.

**Why amplification exists at all when the estimator is Borda.** Borda reads a
*ranking*; weight is the honest way to say "this one matters more than its rank
alone suggests", and it is stored as a column rather than inferred from row counts
so that the column is already there if the mechanism is ever changed. What weight
buys is *concentration*; what it cannot buy is *volume*.

**Abstention is mandatory, attributable, and free.** Every voter who reaches the
page has a ``Ballot`` row; casting no ``Vote`` rows against it IS the abstention,
and the row is what makes it attributable and distinguishable from someone who
never arrived. No separate flag: a flag that can be forgotten is not mandatory, and
a "did not vote" state that is indistinguishable from a "voted no" state cannot be
audited afterwards.
"""

from __future__ import annotations

from django.db.models import Sum

from reviewer.ballots.bias_attack import schwartzian
from reviewer.ballots.models import Ballot, Vote

#: The most a single project may be given, and the reason it is not larger.
#: Quadratic voting (1, 4, 9, ...) is the classic alternative and D-13 already
#: rules it out: this project's stated anti-abuse answer is the published
#: influence report, not a fancyer ballot. Three is enough for "matters more"
#: to mean something inside a budget of n.
MAX_WEIGHT_PER_PROJECT = 3

#: The budget, as a multiple of the ballot size. One means "cast weight 1
#: everywhere and you are exactly at the cap", which is the binding rule above.
BUDGET_MULTIPLIER = 1


def budget_for(ballot: Ballot) -> int:
    """Total weight this voter may spend: one unit per project on the ballot."""
    return BUDGET_MULTIPLIER * len(ballot.order)


def spent(event, voter_key: str) -> int:
    """Total weight this identity has already spent, across every vote it holds."""
    total = Vote.objects.filter(event=event, voter_key=voter_key).aggregate(total=Sum("weight"))[
        "total"
    ]
    return total or 0


def can_afford(event, voter_key: str, ballot: Ballot, weight: int) -> bool:
    """Whether casting ``weight`` more would stay inside the budget."""
    return spent(event, voter_key) + weight <= budget_for(ballot)


def cast(event, ballot: Ballot, *, ranking: list[tuple[str, int]]) -> tuple[list[Vote], str]:
    """Record ``ranking`` as this voter's votes. Returns ``(votes, error)``.

    ``ranking`` is ``(project_pk, weight)`` in the order the voter submitted it.

    **Four refusals, and each names a different failure** -- a merged error string
    would make a 403 from the budget indistinguishable from a 400 for a project not
    on the ballot, which is the F-40 shape one level down:

    * a weight outside ``1..MAX_WEIGHT_PER_PROJECT``;
    * a project that is not on **this** ballot (a vote for something the voter was
      never shown, which is exactly what the randomisation exists to make awkward);
    * a duplicate project in one submission;
    * **the budget**, which is a 403 and not a 400, because it is a *refusal of
      the claim* rather than a malformed request. D-02: a 403 with an empty body.
    """
    from reviewer.ballots.views import REFUSED_BY_BUDGET
    from reviewer.isolation.refusal import deny

    seen: set[str] = set()
    planned = 0
    for project_pk, weight in ranking:
        if not isinstance(weight, int) or weight < 1 or weight > MAX_WEIGHT_PER_PROJECT:
            return [], f"weight for {project_pk} must be 1..{MAX_WEIGHT_PER_PROJECT}"
        if project_pk in seen:
            return [], f"{project_pk} appears twice in one ranking"
        if project_pk not in ballot.order:
            return [], f"{project_pk} is not on this ballot"
        seen.add(project_pk)
        planned += weight

    if spent(event, ballot.voter_key) + planned > budget_for(ballot):
        return [], deny(REFUSED_BY_BUDGET)

    votes = []
    for project_pk, weight in ranking:
        vote, _ = Vote.objects.update_or_create(
            event=event,
            voter_key=ballot.voter_key,
            project_id=project_pk,
            defaults={
                "weight": weight,
                "ip_hash": ballot.voter_key,
                "user_agent_hash": ballot.seed,
            },
        )
        votes.append(vote)
    return votes, ""


def ranking_of(ballot: Ballot, event) -> list[str]:
    """This voter's submitted ranking as project pks, best first.

    Projects the voter did not vote for are appended in **ballot order**, which is
    what makes an abstention-within-a-ballot count as "ranked last" rather than as
    "not counted". That is the same reading ``cast``'s budget implies -- a vote
    you did not spend is a vote you spent last -- and it keeps the estimator
    constant-sum.

    **Returns ``[]`` for a voter who cast nothing at all.** That empty list is
    load-bearing: ``tally`` uses it to skip the ballot entirely, so an abstention
    contributes no points. Before it existed, an abstaining voter was ranked on
    their raw ballot order and the tally scored them as though they had voted
    (F-84).
    """
    votes = list(
        Vote.objects.filter(event=event, voter_key=ballot.voter_key)
        .order_by("-weight", "project_id")
        .values_list("project_id", flat=True)
    )
    if not votes:
        return []
    voted = set(votes)
    return votes + [pk for pk in ballot.order if pk not in voted]


def tally(event, ballots=None) -> list[dict]:
    """The public ranking, computed by the estimator the harness attacks.

    **``schwartzian`` is called, not reimplemented** -- the same rule as
    ``ballots/order.py`` calling ``presentation_order``. The harness measures drift
    on *this* function; a second copy would leave the measurement describing a
    function nothing calls.

    Every ``Vote`` is reached through ``Ballot.voter_key``, so a vote whose ballot
    is gone cannot contribute: there is no path from a ``Vote`` to the tally that
    does not pass through the ballot that fixed what the voter saw.

    **F-84: a ballot with no votes contributes NOTHING.** The first version
    ranked every ballot, so ``ranking_of`` on an abstaining voter returned their
    whole ballot order and the tally scored them as though they had voted for it
    -- **an abstention silently became a vote for the randomised order**, which is
    the one thing abstention is supposed to mean the opposite of. It was caught by
    a test that created a third ballot and asserted a tie: the extra ballot moved
    the numbers. Abstention now means the ballot is skipped, and the test that
    caught it is a test about the *negative*, which is the only place this class of
    bug is visible.
    """
    rows = Ballot.objects.filter(event=event).order_by("cast_at", "voter_key")
    if ballots is not None:
        rows = rows.filter(voter_key__in=ballots)

    project_ids: list[str] = []
    rankings: list[list[int]] = []
    for ballot in rows:
        order = list(ballot.order)
        if not order:
            continue
        if not project_ids:
            project_ids = sorted({pk for b in rows for pk in b.order})
        index = {pk: i for i, pk in enumerate(project_ids)}
        ranking = ranking_of(ballot, event)
        if not ranking:
            # An abstention. Contributes nothing -- see the docstring, F-84.
            continue
        permutation = [index[pk] for pk in ranking if pk in index]
        if permutation:
            rankings.append(permutation)

    if not project_ids:
        return []

    totals = schwartzian(rankings, len(project_ids))

    # `voters` is DISTINCT IDENTITIES THAT GAVE THIS PROJECT WEIGHT, read from
    # the `Vote` rows -- not "voters whose ranking mentions it". The distinction
    # is the same one the influence report makes (D-13's "distinct identities"),
    # and the two must agree: a project ranked last by a hundred voters has a
    # hundred rankings and *zero* support, and reporting the hundred would make
    # the leaderboard and the influence report contradict each other on the same
    # data.
    supporters: dict[str, int] = dict.fromkeys(project_ids, 0)
    for project_id, _voter_key in (
        Vote.objects.filter(event=event, project_id__in=project_ids)
        .values_list("project_id", "voter_key")
        .distinct()
    ):
        supporters[project_id] += 1

    board = [
        {
            "project": pk,
            "points": round(totals[i], 4),
            "voters": supporters.get(pk, 0),
        }
        for i, pk in enumerate(project_ids)
    ]
    board.sort(key=lambda r: (-r["points"], r["project"]))
    for position, row in enumerate(board, start=1):
        row["rank"] = position
    return board
