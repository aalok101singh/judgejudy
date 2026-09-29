"""The influence report: who is actually carrying each project, before publication.

**This is the anti-abuse answer, and D-13 chose it deliberately.** The brief asks
for *"an answer to people trying to cheat it"*, and the project decided the
answer is **a report, not a mechanism** (D-13, `bible/06` §6.2). The reasoning
worth keeping: quadratic voting is a door we cannot close (`bible/06` §6.1 -- it
is cost amplification inside an identity budget, *not* Sybil resistance, because
we have no cost to obtaining an identity), so a brigade is possible. A brigade
that is *visible before publication* is worth more than a mechanism that is
subtly better against it, because the organizer is the one who has to decide
whether to publish.

**The shape comes from `bible/06` §6.2 and is quoted, not invented:** per project,
the distinct verified identities, the first-preference share, the Gini of the
vote mass, and the identities flagged by clustering. The worked example is the
point of the whole section -- ``prj_14`` takes **19.8% of first preferences from
14% of voters at Gini 0.71**, and is "winning on concentration". A brigaded vote,
in a table, before anyone is told the result.

**Three detectors, and none of them has a tunable constant.** This is deliberate
and it is the D-04 lesson applied to abuse rather than to normalization: a
threshold we invented would be the largest thing a reviewer could attack, and we
would have to defend it. So the report *measures and ranks* and says which
project is most concentrated, rather than deciding what concentrated means:

* **Gini of vote mass** -- are this project's supporters spread evenly, or is a
  handful carrying it? 0 is perfectly even, and the value approaches 1 as the
  mass collapses onto one identity.
* **Identical-ballot clusters** -- identities whose vote vectors are *byte
  identical*. This one is a structural fact rather than a threshold, which is
  why it is the sharpest of the two: it needs no cut-off because identical is
  identical.

**A third metric was built, measured, and cut, and the reason is worth more than
the metric was.** The first draft ranked by a *lift* -- first-preference share
divided by voter share -- on the reasoning that a project over-represented
against its own base is the shape of a bloc vote. The synthetic attack scored
**exactly 1.0**, and the reason is structural: every voter casts exactly one
first preference, so ``first_share == voter_share`` whenever a project's backers
are its first-preferencers, which is the overwhelmingly common case. It can only
depart from 1 when people first-preference a project they do not back, which is
not a brigade -- it is a ballot display that disagrees with a vote.

So it was a number that would have read as a real signal on every row of the
report while carrying no information, and **a column that looks like a detector
and is not one is worse than no column**: a reader would reason about a "lift of
1.0" as though it meant something. `bible/06` §6.2's table has four columns, the
two detectors are both real, and the ranking is now **clustered identities, then
Gini, then first-preference share** -- the three numbers that are each either a
structural fact or a measurement. **D-04's lesson applied to abuse rather than to
normalization: a metric we cannot demonstrate is non-degenerate is a tunable
constant with a decimal point, and it would have been the easiest thing in the
report for a reviewer to attack.**

**What the report deliberately does NOT claim.** A cluster of identical ballots
is not a brigade; it is an enthusiastic table of friends, a shared browser
profile, or a genuinely aligned preference. **The report shows concentration and
refuses to name a culprit**, and its `interpretation` field says so in every
response. That restraint is the feature: the brief asks for an answer to people
cheating, and an answer that accuses the wrong people is worse than no answer.

**The empty case is the one this project keeps getting wrong.** F-61, F-69 and
F-71 were all a structure that could return the right *shape* while containing
nothing, and the shipped fixture has **zero votes**, so a report that iterates
projects and prints zeros would be exactly that defect a fifth time -- forty-one
rows of `gini 0.00, lift 0.00` reading as "verified, and no project is
brigaded". So `report()` returns ``None`` when nothing has been cast, the command
prints *no votes have been cast*, and the API says ``null`` with an explicit
reason. **There is no table of zeroes, and there is a test that fails if one
appears.**
"""

from __future__ import annotations

from reviewer.ballots.models import Ballot, Vote

#: What the report says about its own numbers. A report that publishes a bare
#: Gini invites the reader to assume we know the cut-off; we do not, and saying
#: so is the difference between a measurement and a verdict.
NORMALIZATION = "vote-mass concentration, not normalized scores"

#: The shape `bible/06` §6.2 prescribes, restated in the field names this code
#: emits. Named once so the command and the API cannot drift on the vocabulary.
REPORT_METHOD = "per-project vote-mass Gini, first-preference share, identical-ballot clusters"

#: The sentence that travels with every rendering of the report. It is a constant
#: rather than a per-project string because it is true of the *method*, and a
#: method caveat that varies per row is a method caveat nobody reads.
INTERPRETATION = (
    "Concentration is not proof. Identical ballots may be a brigade, an "
    "enthusiastic table of friends, a shared browser profile, or a genuinely "
    "aligned preference; this report ranks projects by how concentrated their "
    "support is and does not name a culprit."
)


def gini(values: list[float]) -> float | None:
    """The Gini coefficient of ``values``; ``None`` for an empty population.

    **The pairwise form**, ``G = sum_i sum_j |xi - xj| / (2 n^2 * mean)``, rather
    than the sorted-cumulative shortcut, because this runs on populations of a
    few dozen at most and the transparent formula is the one a reader can verify
    with a calculator. It is also the definition, so there is no index of
    correction to get backwards.

    **Two honest edges, named rather than smoothed over:**

    * **one value returns 0.0, not 1.0.** A single identity cannot be
      *differentially* concentrated -- there is nobody to concentrate *away
      from*. That is a structural zero, the same class as ``median(|x - med|)``
      over one element in F-10, and it is why a project voted for by exactly one
      identity is *not* evidence of a brigade. The alternative, reporting 1.0,
      would make a single enthusiastic voter the most brigaded thing on the page.
    * **an empty population returns ``None``, not 0.0.** F-13's rule: an empty
      collection is a valid value, so a caller that tests ``if gini`` cannot tell
      "no data" from "perfectly even", and the first row of a report with no
      votes would read as the most innocent project in the event.
    """
    if not values:
        return None
    n = len(values)
    if n == 1:
        return 0.0
    total = float(sum(values))
    if total <= 0:
        return None
    mean = total / n
    pairwise = sum(abs(a - b) for a in values for b in values)
    return pairwise / (2.0 * n * n * mean)


def _vote_vectors(event) -> dict[str, dict[str, int]]:
    """``voter_key -> {project source_key: weight}`` for one event.

    Built once and reused by both the per-project roll-up and the clustering
    detector, because they are two readings of the same rows and computing the
    tally twice would be two chances for the two to disagree.
    """
    vectors: dict[str, dict[str, int]] = {}
    for vote in Vote.objects.filter(event=event).select_related("project"):
        vectors.setdefault(vote.voter_key, {})[vote.project.source_key] = vote.weight
    return vectors


def identical_ballot_clusters(vectors: dict[str, dict[str, int]]) -> dict[str, int]:
    """``project source_key -> identities voting an identical vector for it``.

    **A cluster is an exact match, and exactness is the whole design.** Two
    identities count as a cluster for a project when their *entire* vote vector
    -- every project and every weight -- is identical, not merely when they
    happen to back the same project. Backing the same project is a preference;
    casting the same ballot as four hundred other people is a signature.

    **The consequence is stated because it is a real limitation:** a brigade that
    varies one weight is invisible to this detector, and so is a brigade spread
    across two clusters. The report says so in `INTERPRETATION` rather than
    letting a reader assume the detector is exhaustive.
    """
    by_vector: dict[str, list[str]] = {}
    for voter, vector in vectors.items():
        signature = repr(sorted(vector.items()))
        by_vector.setdefault(signature, []).append(voter)

    flagged: dict[str, int] = {}
    for members in by_vector.values():
        if len(members) < 2:
            continue
        # Every project the shared ballot touches inherits the cluster size, and
        # the *number of identities* in it -- not the number of clusters -- is
        # what an organizer needs to see.
        for project in vectors[members[0]]:
            flagged[project] = max(flagged.get(project, 0), len(members))
    return flagged


def report(event) -> dict | None:
    """The whole influence report for one event, or ``None`` if nothing is cast.

    **``None`` rather than an empty report, and that is the load-bearing decision
    in this module.** The shipped fixture has zero votes, so the honest answer for
    a reader is *"there is nothing to report yet"* -- not forty-one rows of zeros,
    which is F-61's exact shape and the fifth time this project has built a
    structure that can be right while containing nothing.

    **First preferences come from ``Ballot.order``, not from a guess.** The
    ballot stores the per-voter permutation precisely so the report can name a
    *first* preference rather than inferring intent from weight, and so the order
    is reconstructable for the audit trail instead of merely asserted to have
    existed. A voter with a ballot but no first entry is skipped, not counted as
    a first preference somewhere else.
    """
    vectors = _vote_vectors(event)
    if not vectors:
        return None

    # --- first preferences, from the stored per-voter permutation --------------
    first_preference: dict[str, int] = {}
    distinct_voters: set[str] = set()
    for ballot in Ballot.objects.filter(event=event).order_by("event_id", "cast_at"):
        distinct_voters.add(ballot.voter_key)
        order = ballot.order or []
        if order:
            first_preference[order[0]] = first_preference.get(order[0], 0) + 1

    # Any identity that cast votes but never drew a ballot is still a voter; the
    # report's own denominator is the identities we actually saw, and a report
    # that dropped them would understate how many people are involved.
    distinct_voters.update(vectors)

    total_first = sum(first_preference.values())
    total_voters = len(distinct_voters)

    # --- per-project concentration --------------------------------------------
    mass_by_project: dict[str, dict[str, int]] = {}
    for voter, vector in vectors.items():
        for project, weight in vector.items():
            mass_by_project.setdefault(project, {})[voter] = weight

    flagged = identical_ballot_clusters(vectors)
    projects = {p.source_key: p for p in _projects_for(event)}

    rows = []
    for project_key, per_voter in mass_by_project.items():
        project = projects.get(project_key)
        identities = len(per_voter)
        firsts = first_preference.get(project_key, 0)
        concentration = gini(list(per_voter.values()))
        rows.append(
            {
                "project": project_key,
                "title": project.title if project else None,
                "identities": identities,
                "first_preference_share": round(firsts / total_first, 4) if total_first else 0.0,
                "vote_mass_gini": None if concentration is None else round(concentration, 4),
                "clustered_identities": flagged.get(project_key, 0),
            }
        )

    # Most suspicious first: an exact-match brigade, then a lopsided weight
    # distribution, then raw first-preference share. The sort is the report's
    # only verdict and it is a *ranking*, not a judgement -- the project key is
    # the final key so two runs over the same data order identically.
    rows.sort(
        key=lambda r: (
            -r["clustered_identities"],
            -(r["vote_mass_gini"] or 0.0),
            -r["first_preference_share"],
            r["project"],
        )
    )

    return {
        "method": REPORT_METHOD,
        "normalization": NORMALIZATION,
        "interpretation": INTERPRETATION,
        "identities": total_voters,
        "first_preferences": total_first,
        "votes": sum(len(v) for v in vectors.values()),
        "projects": len(rows),
        "ranking": rows,
    }


def _projects_for(event):
    from reviewer.projects.models import Project

    return Project.objects.filter(event=event)


def report_for_actor(actor) -> tuple[dict | None, bool]:
    """``(report, permitted)`` -- the influence report as this actor may see it.

    **Organizer and admin only, and the same all-or-nothing rule as the audit
    trail.** There is no honest per-actor slice: a report that showed each voter
    their own row would let a bloc see whether its cover was blown, and a report
    that hid the other rows would be a table with gaps -- which is the ambiguity
    ``omitted_since_prev`` exists to remove. All or nothing.

    **The returned tuple, not an exception**, for the reason the audit accessor
    gives: the isolation matrix has to be able to print the word **"refused"**,
    and a zero there reads as "verified, and the answer is none". A refusal and
    an empty result are different answers and the code has to keep them apart.
    """
    if not actor.can_read_all_reviews:
        return None, False
    return report(actor.event), True
