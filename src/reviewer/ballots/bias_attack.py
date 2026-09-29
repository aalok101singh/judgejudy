"""The bias-attack harness: does randomised ballot order make position bias zero-MEAN?

**This is the first acceptance clause of FEAT-06**, and the whole claim is one
sentence that is easy to overstate and expensive to get wrong:

> Randomised presentation order does not remove position bias. **It makes it
> zero-mean**, so it cannot systematically favour any project. A voter who prefers
> the left slot gains nothing, because the permutation is seeded per voter and
> stable across requests -- a refresh cannot re-roll it. **We do not claim the bias
> is zero.** (`bible/06` §6.3, and D-12.)

The mechanism-design literature is explicit that the stronger claim is false, and
§6.3 quotes it: *"randomizing the presentation order in a single query merely
randomizes which option benefits from the bias."* **A harness that reported
"position bias eliminated" would be falsifiable in one search, and that costs the
credibility of the 25% Judging Integrity criterion.** So this module reports the
drift's *mean* and its *spread* as two separate numbers, and the honest answer --
zero-mean, not zero -- is only available because both are measured.

**The estimand is the one thing the first two drafts of this harness got wrong,
and getting it wrong is invisible.** The obvious design is to compare "biased
voters under a random order" against "no bias at all". That measures the *bias
mechanism*, not the *order*, and it does not test the claim at all: it returns a
large number that has nothing to do with whether randomisation helps. The
estimand D-12 actually asserts is about the **order alone**, with the bias held
fixed::

    reference_j  =  E[ points_j | BALANCED order , same population ]
    drift_j      =  points_j(design)  -  reference_j

**A balanced order puts every project in slot 1 exactly equally often, so it
favours nobody by construction** and is the right null. Holding the voters and the
bias mechanism fixed and varying only the order is the only comparison in which
"zero-mean" is a statement about randomisation rather than about primacy.

**The harness is falsifiable in three directions, and all three are asserted by
tests.** A measurement that cannot fail is a tunable constant with a decimal
point, which is F-76 -- the ``lift`` column that scored the synthetic attack at
exactly 1.0 and was cut:

======================  =================================================
arm                     what it must show
======================  =================================================
``order_invariance``    the **control that must NOT fire**: with no
                        position bias, the scores under all three
                        designs must be **bit-identical**. A harness that
                        reports order-sensitivity where there is no
                        position bias is measuring its own noise, and
                        every other number in the table becomes
                        unreadable (F-77's lesson, reached from the other
                        side).
``fixed``               the **attack the harness must detect**: one
                        project pinned to slot 1 for every voter, drift
                        large and the CI excluding zero. **If this arm
                        does not fire, the harness is a constant** and the
                        other two arms prove nothing.
``randomised``          the **claim**: mean drift not distinguishable from
                        zero, with a **nonzero spread**. Zero-mean, not
                        zero.
``balanced``            the alternative §6.3 offers, measured the same way.
======================  =================================================

**The control is exact rather than statistical, and that took a second attempt.**
The first version differenced a no-bias population against the pooled reference
and asserted "near zero"; it read ``+0.051``, and the command refused to pass --
correctly. The ``+0.051`` is **the reference's own sampling noise**, because the
reference is a different ensemble of populations, not the order's influence.
Asserting a magnitude the test cannot resolve is the same defect as a tunable
constant with a decimal point. `order_invariance` therefore compares the **same
population** under all three designs and requires the scores to be *bit-identical*:
a boolean, not a decimal, which fails loudly if an order ever leaks into the tally.

**The control is not vacuous either.** Every design still *generates* a per-voter
permutation and every ballot is still cast through the same code path; only the
voters' choice is unaffected. The ``fixed`` arm is what proves the pipeline is
live -- a control that skipped the code under test would be the F-41 shape.

**Position bias is modelled as the serial-position effect, and the modelling
choice is load-bearing.** A position-biased voter is one who **resolves its own
top two by which one is displayed first**. The first draft of this harness instead
let a biased voter promote *whatever* was in slot 1 regardless of quality, and
that model does not measure position bias at all -- it transfers points from
good projects to bad ones, so it reported a large drift for a *randomised* order
and the harness would have "confirmed" D-12 with a number that was really a
statement about rank transfer. A metric that reads as a detector and measures
something else is F-76 again, one level up. The top-two model is also the
defensible one: serial position is an effect on *choices between presented
alternatives*, so a voter who never shortlists a project cannot be moved by where
it is displayed.

**Why the synthetic population and not the shipped fixture.** `fixtures.json` has
zero ballots, so there is nothing to attack, and a harness run against a real
event with 100 voters cannot resolve the effect at all (§6.3's own power
analysis, re-derived below). The harness is a *controlled* experiment, which is
the only way to put a known bias into a population and measure what the
estimator does with it. Its numbers describe the **mechanism**, and the shipped
event is measured by a different tool -- the influence report, which is the other
clause of this acceptance line.

**The statistics are computed, not imported.** No SciPy is in the image (D-04 and
the dependency budget), so the normal quantile is a bisection on ``math.erfc``
and the sample-size requirement is Fleiss' one-sample proportion formula. Both
are asserted against closed-form values in the tests, because a hand-rolled
statistic that is quietly wrong is a number shipped with a decimal point.

**One number in `bible/06` §6.3 did not reproduce, and the run won.** §6.3's
power table quotes 28,573 / 4,556 / 1,125 / 490 comparisons for side preferences
of 0.52 / 0.55 / 0.60 / 0.65. The formula Fleiss gives is 4,904 / 783 / 194 / 85
-- a near-constant 5.8x smaller, with a ratio that varies by less than 1% across
the four rows, which is the signature of a single wrong convention rather than
four independent slips. **§6.3's error is in the conservative direction**: it
overstates the sample a real event would need, so the conclusion it supports --
that a panel of 100-1,000 cannot resolve residual position bias -- survives, and
`POWER_TABLE` below is the generated one. F-78.
"""

from __future__ import annotations

import math
import random
import statistics

#: How a position-biased voter is modelled. A string rather than a comment, so a
#: reader can see which model produced a table without opening the source.
POSITION_BIAS_MODEL = "primacy: a biased voter resolves its own top two by display order"

#: What the harness claims, in the words the acceptance line uses. Travelling with
#: every payload for the same reason the influence report's caveat does: a person
#: skimming a table does not read docstrings.
INTERPRETATION = (
    "Randomised order makes position bias zero-MEAN, not zero: the drift's "
    "confidence interval spans zero while its spread does not. A single run can "
    "still favour a project by chance, and a determined voter cannot re-roll their "
    "own order because the permutation is seeded per voter and stable across "
    "requests. This is not Sybil resistance and it is not the removal of order "
    "effects."
)

#: The designs under comparison, and what each one is FOR. A design with no stated
#: role is a knob, and a knob is a tunable constant waiting to be justified.
DESIGNS = {
    "fixed": "the attack: one project pinned to slot 1 for every voter",
    "randomised": "the shipped mechanism: a per-voter seeded permutation",
    "balanced": "every project in slot 1 equally often -- favours nobody",
}

#: The arm with no position bias at all. It MUST read zero, and that is the point.
CONTROL = "no_bias"

#: `bible/06` §6.3 quotes 28,573 / 4,556 / 1,125 / 490 here. Fleiss gives
#: 4,904 / 783 / 194 / 85 -- a near-constant 5.8x smaller, which is one wrong
#: convention rather than four slips, and conservative, so §6.3's conclusion holds.
#: Generated by `comparisons_required`, never transcribed (F-78).
POWER_TABLE = {0.52: 4904, 0.55: 783, 0.60: 194, 0.65: 85}


# --------------------------------------------------------------------- statistics


def normal_quantile(two_sided_alpha: float) -> float:
    """The standard normal quantile for a two-sided tail ``alpha``.

    **A bisection on ``math.erfc`` rather than an import**, because SciPy is
    deliberately absent (D-04's dependency budget) and `statistics.NormalDist`
    would do the same job with less code -- this is here because the harness
    needs the *value* it computed to be assertable against 1.9600, and because
    the bisection is four lines with no dependency to audit.

    200 iterations of bisection on [0, 40] is exact to double precision and takes
    microseconds, so the iteration count is a constant rather than a tolerance.
    """
    lo, hi = 0.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if math.erfc(mid / math.sqrt(2)) > two_sided_alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def cohen_h(p1: float, p0: float = 0.5) -> float:
    """Cohen's *h*, the effect size for two proportions.

    **Present because a p-value on its own is the wrong instrument for a claim
    about magnitude** (§6.3 asks for it by name). ``h = 2*asin(sqrt(p1)) -
    2*asin(sqrt(p0))``, and it is 0.1002 for a 5-point side preference -- which is
    the reason 783 comparisons are needed rather than 40.
    """
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p0))


def comparisons_required(
    p1: float, *, p0: float = 0.5, alpha: float = 0.05, power: float = 0.80
) -> int:
    """Comparisons needed to detect ``p1`` against ``p0`` (Fleiss, one-sample).

    ``n = (z_{1-alpha/2}*sqrt(p0q0) + z_{power}*sqrt(p1q1))^2 / (p1-p0)^2``

    **Both z arms are two-sided quantiles**, because the power arm needs
    ``z_{power} = z at 2*(1-power) = 0.8416`` and taking a one-sided quantile there
    is the off-by-a-factor-of-two that makes a power table quietly optimistic. The
    value is asserted against the closed form in the tests rather than trusted.
    """
    z_alpha = normal_quantile(alpha)
    z_power = normal_quantile(2 * (1 - power))
    p1q1 = p1 * (1 - p1)
    p0q0 = p0 * (1 - p0)
    return math.ceil((z_alpha * math.sqrt(p0q0) + z_power * math.sqrt(p1q1)) ** 2 / (p1 - p0) ** 2)


def summarise(samples: list[float], *, confidence: float = 0.95) -> dict:
    """Mean, spread and a CI for a sample of drifts, in the harness's own dict.

    **The spread is reported next to the interval and never folded into it**, and
    that separation is the entire deliverable. ``spans_zero`` answers "is the mean
    distinguishable from nothing?"; ``sd`` answers "how far can a single run move?"
    Collapsing them into one number is how a zero-mean result gets reported as a
    zero result.

    **A single sample returns ``None`` for the interval, not ``[0, 0]``.** F-13's
    rule, the sixth time in this project: an empty or degenerate collection is a
    valid value, so a caller testing the truthiness of the interval would read
    "certainty" where the truth is "no measurement".
    """
    n = len(samples)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "sd": None,
            "ci": None,
            "spans_zero": None,
            "min": None,
            "max": None,
            "mde": None,
        }
    mean = statistics.fmean(samples)
    if n == 1:
        return {
            "n": 1,
            "mean": mean,
            "sd": None,
            "ci": None,
            "spans_zero": None,
            "min": mean,
            "max": mean,
            "mde": None,
        }
    sd = statistics.stdev(samples)
    half_width = normal_quantile(1 - confidence) * sd / math.sqrt(n)
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "ci": (mean - half_width, mean + half_width),
        "spans_zero": abs(mean) <= half_width,
        "min": min(samples),
        "max": max(samples),
        # The minimum drift this many replications could have detected. Reporting
        # it is what stops the CI from being read as "the effect is zero" -- it
        # says "the effect is smaller than this", which is a different sentence.
        "mde": half_width,
    }


# ----------------------------------------------------------------- the population


#: How far apart the projects' true qualities are, from best to worst. **The single
#: most consequential number in this module, and it was wrong on the first two
#: attempts.** See `_quality_ladder` for why 0.45 and not "0 to 1".
QUALITY_SPREAD = 0.45


def _quality_ladder(n_projects: int) -> list[float]:
    """True qualities, best first, within a narrow band.

    **A steep ladder (1.0 down to 0.12) makes the harness a one-project
    instrument.** Measured, not reasoned: with that ladder and 200 voters, project 0
    was in *some* voter's top two 100% of the time, project 2 only 13%, and
    projects 5 and 7 **never** -- so the primacy model, which can only move a
    project a voter has shortlisted, could not touch them at all. Pinning the worst
    project produced a drift of ``-0.317`` against a spread of 4.69, i.e. a
    **structurally zero row in a table of measurements**, which is F-61's seventh
    appearance and F-76's shape at the level of the fixture.

    At `QUALITY_SPREAD` the top three projects are reachable (95% / 68% / 26% of
    voters) and pinning the third still gives a fixed-order drift of **+7.43 with a
    CI excluding zero** while randomised order spans zero. **The harness now
    discriminates at two points on the ladder rather than one**, which is what makes
    the randomised result a statement about the *order* rather than about helping
    the winner.

    The band is narrow because that is the adversarial case, not the easy one: a
    field of near-equal projects is where a position advantage changes the
    outcome, and a field with one clear winner is where it cannot.
    """
    if n_projects == 1:
        return [1.0]
    step = QUALITY_SPREAD / (n_projects - 1)
    return [1.0 - step * i for i in range(n_projects)]


def _latent_rankings(rng: random.Random, n_projects: int, quality: list[float], n_voters: int):
    """A population of voters, each with a noisy ranking of the projects.

    **The noise is the reason the spread is nonzero and the mean is not.** If
    every voter ranked identically there would be no variance to average over and
    "zero-mean" would be vacuous -- every design would return the same number. A
    panel where everyone agrees is not a panel, and testing an estimator on one
    measures nothing.

    Quality enters through a fixed descending ladder whose band is
    `QUALITY_SPREAD` wide, and **the width is a modelling decision with a measured
    consequence** -- see `_quality_ladder`. A ladder that spans 0 to 1 leaves the
    bottom half of the field in nobody's top two, so the model can only ever move
    the winner and the harness degenerates into a one-project instrument.
    """
    scale = 0.12
    for _ in range(n_voters):
        keys = [-quality[i] - abs(rng.gauss(0.0, scale)) for i in range(n_projects)]
        yield sorted(range(n_projects), key=lambda i: (keys[i], i))


def presentation_order(
    design: str, *, seed: int, voter: int, replication: int, n_projects: int
) -> list[int]:
    """The order a voter is shown, per design.

    **Seeded per voter and per replication, never from a global stream.** A single
    ``random.Random`` consumed in voter order would make a voter's order depend on
    how many voters came before them, so a voter who loaded the page twice in
    different orders would get a different ballot -- which is exactly the
    re-rolling that D-12 exists to prevent. Deriving the seed from
    ``(replication, voter)`` makes the order a pure function of the identity, which
    is the property the claim rests on.

    ``balanced`` cycles the slot-1 project with the voter index so that across one
    replication every project occupies slot 1 exactly ``n_voters / n_projects``
    times. That is what makes it the null: it cannot favour anybody.
    """
    if design == "balanced":
        first = (voter + replication) % n_projects
        rest = [i for i in range(n_projects) if i != first]
        random.Random(1_000_003 * replication + voter).shuffle(rest)
        return [first, *rest]
    order = list(range(n_projects))
    random.Random(7_919 * replication + 104_729 * voter + seed).shuffle(order)
    return order


def schwartzian(ballots: list[list[int]], n_projects: int) -> list[float]:
    """The Schwartzian (Borda) score per project: ``n-1`` for first, ``0`` for last.

    **The estimator under test, and it is `bible/06` §6.2's choice** -- the unique
    linear rank aggregator satisfying the Condorcet criterion, explainable as
    "two points for first, one for second". It is a constant-sum aggregator, which
    is exactly what the drift is measured against: total points are fixed, so any
    drift is a genuine *redistribution* toward or away from one project, and there
    is no room for a uniform inflation to hide inside.
    """
    totals = [0.0] * n_projects
    for ballot in ballots:
        for position, project in enumerate(ballot):
            totals[project] += n_projects - 1 - position
    return totals


def cast_ballots(
    rankings: list[list[int]],
    orders: list[list[int]],
    *,
    biased: bool,
    beta: float,
    brng: random.Random,
) -> list[list[int]]:
    """Turn each voter's latent ranking into the ballot they actually submit.

    **A position-biased voter promotes whichever of its OWN TOP TWO is displayed
    first** -- the serial-position effect, and the reason this is the model and
    not "promote whatever is in slot 1". The alternative model measures rank
    transfer rather than position: it hands points to bad projects and takes them
    from good ones, so it reports a large drift for a *randomised* order and would
    have "confirmed" D-12 with a number that was never about randomisation. See
    the module docstring; this is F-76 one level up.

    **Consequence worth stating: a project nobody shortlists cannot be moved by
    where it is displayed.** A voter who ranks a project seventh has no top-two
    decision in which its position could matter, so its drift is structurally
    zero. That is a real property of the effect, not a gap in the measurement, and
    the table says which rows are structural rather than letting a column of exact
    zeros read as "measured, and found clean".
    """
    ballots = []
    for index, ranking in enumerate(rankings):
        if not (biased and brng.random() < beta):
            ballots.append(list(ranking))
            continue
        first, second = ranking[0], ranking[1]
        shown = {project: position for position, project in enumerate(orders[index])}
        head = first if shown[first] < shown[second] else second
        ballots.append([head, *[p for p in ranking if p != head]])
    return ballots


# ------------------------------------------------------------------ the harness


def order_invariance(
    *, n_projects: int = 8, n_voters: int = 400, beta: float = 0.30, seed: int = 0
) -> dict:
    """The control: with **no position bias**, the order must not matter AT ALL.

    **This is the check that must not fire, and it is the sharpest one available
    because it is exact rather than statistical.** A control built by differencing
    a no-bias population against a pooled reference reads a small nonzero number --
    the reference is a *different* ensemble, so the difference is the reference's
    own sampling noise, not the order's influence. Asserting "small" there would
    be asserting a magnitude the test cannot resolve.

    Instead this compares the **same population** under all three designs and
    requires the Schwartzian scores to be **bit-identical**. With ``biased=False``
    the cast never consults the order, so any difference is a defect: an order
    leaking into the tally, which is the F-32 shape for this feature. The result is
    a boolean, not a decimal, and it can fail loudly.

    It is not vacuous either: every design still *generates* a per-voter
    permutation and every ballot is still cast through the same code path. Only the
    voters' choice is unaffected. A control that skipped the code under test would
    be the F-41 shape, and the attack arm is what proves the pipeline is live.
    """
    quality = _quality_ladder(n_projects)
    worst = 0.0
    for rep in range(3):
        rng = random.Random(1_000_003 * seed + rep)
        rankings = list(_latent_rankings(rng, n_projects, quality, n_voters))
        scores = {}
        for design in ("fixed", "randomised", "balanced"):
            orders = []
            for v in range(n_voters):
                if design == "fixed":
                    orders.append([0, *range(1, n_projects)])
                else:
                    orders.append(
                        presentation_order(
                            design, seed=seed, voter=v, replication=rep, n_projects=n_projects
                        )
                    )
            scores[design] = schwartzian(
                cast_ballots(
                    rankings,
                    orders,
                    biased=False,
                    beta=beta,
                    brng=random.Random(7_700_000 + rep),
                ),
                n_projects,
            )
        reference = scores["randomised"]
        for _design, points in scores.items():
            worst = max(worst, max(abs(a - b) for a, b in zip(points, reference, strict=True)))
    return {
        "voters": n_voters,
        "projects": n_projects,
        "replications": 3,
        "max_difference": worst,
        "identical": worst == 0.0,
    }


def run_arm(
    *,
    design: str,
    biased: bool,
    pinned: int,
    n_projects: int = 8,
    n_voters: int = 400,
    replications: int = 400,
    beta: float = 0.30,
    seed: int = 0,
) -> dict:
    """Drift of one project, across ``replications`` runs, for one design.

    The drift is against a **pooled balanced reference** computed from an ensemble
    several times larger, so the null is a population quantity rather than a
    single draw the treatment is differenced against. Differencing against one
    draw would fold the reference's own noise into every treatment variance and
    the interval would be too wide by a factor of about sqrt(2) -- a number that
    still says "spans zero" for a *weaker* reason than the one claimed.
    """
    quality = _quality_ladder(n_projects)

    def one_replication(rep: int, order_design: str) -> list[float]:
        rng = random.Random(1_000_003 * seed + rep)
        rankings = list(_latent_rankings(rng, n_projects, quality, n_voters))
        brng = random.Random(7_700_000 + rep)
        if order_design == "fixed":
            head = [pinned] + [i for i in range(n_projects) if i != pinned]
            orders = [head] * n_voters
        else:
            orders = [
                presentation_order(
                    order_design,
                    seed=seed,
                    voter=v,
                    replication=rep,
                    n_projects=n_projects,
                )
                for v in range(n_voters)
            ]
        return schwartzian(
            cast_ballots(rankings, orders, biased=biased, beta=beta, brng=brng), n_projects
        )

    reference_reps = max(4 * replications, 2000)
    pooled = [0.0] * n_projects
    for rep in range(reference_reps):
        points = one_replication(rep, "balanced")
        for i in range(n_projects):
            pooled[i] += points[i]
    reference = [total / reference_reps for total in pooled]

    drifts = [
        one_replication(rep, design)[pinned] - reference[pinned] for rep in range(replications)
    ]
    result = summarise(drifts)
    result.update(
        {
            "design": design,
            "biased": biased,
            "pinned": pinned,
            "reference_replications": reference_reps,
            "reference": reference[pinned],
            # A constant sample is a *structural* zero, and reporting it as a
            # measurement with a zero interval would be F-61's seventh appearance.
            "structural": len(set(drifts)) == 1,
        }
    )
    return result


def harness(
    *, n_projects: int = 8, n_voters: int = 400, replications: int = 400, beta: float = 0.30
) -> dict:
    """The whole experiment: a control, three designs, and the checks on them.

    **The control and the attack are the load-bearing part, and they are returned
    as data rather than asserted here.** A harness that raised on a failed check
    would be unusable as a report, and one that asserted nothing would be the
    constant F-76 warns about. So the command renders the table *and* the verdicts,
    and the tests assert the verdicts -- so a future change that breaks the
    separation fails a test instead of quietly printing a zero.

    Pinned projects are the **top two and the third**, because pinning only the
    best would let a harness that simply cannot see position bias pass this file.
    The third is the discriminating case: it is reachable by only ~26% of voters, so
    an order-based advantage there is unambiguous -- a position effect that moves a
    project nobody shortlists would be a bug, not a finding.
    """
    population = {
        "projects": n_projects,
        "voters": n_voters,
        "replications": replications,
        "beta": beta,
        "quality_spread": QUALITY_SPREAD,
    }
    population["pinned_projects"] = [0, 2] if n_projects > 2 else [0]

    control = order_invariance(n_projects=n_projects, n_voters=n_voters, beta=beta)
    arms = {
        design: {
            str(pinned): run_arm(
                design=design,
                biased=True,
                pinned=pinned,
                n_projects=n_projects,
                n_voters=n_voters,
                replications=replications,
                beta=beta,
            )
            for pinned in population["pinned_projects"]
        }
        for design in ("fixed", "randomised", "balanced")
    }
    return {
        "model": POSITION_BIAS_MODEL,
        "interpretation": INTERPRETATION,
        "designs": dict(DESIGNS),
        "population": population,
        "control": control,
        "arms": arms,
        "power": {
            str(p): {"comparisons_required": n, "cohens_h": round(cohen_h(p), 4)}
            for p, n in POWER_TABLE.items()
        },
        "verdicts": {
            "control_is_silent": control["identical"],
            "attack_is_detected": all(
                arm["ci"] is not None and not arm["spans_zero"] for arm in arms["fixed"].values()
            ),
            "randomised_is_zero_mean": all(
                arm["ci"] is not None and arm["spans_zero"] for arm in arms["randomised"].values()
            ),
            "randomised_is_not_zero": all(arm["sd"] for arm in arms["randomised"].values()),
        },
    }
