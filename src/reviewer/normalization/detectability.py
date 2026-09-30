"""Was there anything to fix? The detectability analysis.

**This is the section the whole proof hangs from, and it is a null result.**
Every published "score normalization" claim in this category asserts that it
removed a bias. We went and asked a prior question: *on this fixture, is the bias
there?* The answer is no, with a p-value, a power analysis and a floor.

A normalization claim that does not first test for the effect it claims to remove
is not a claim. It is a subtraction.

**The method, stated so it can be checked.** A one-way random-effects variance
decomposition on the review composites, grouped by judge -- ``ICC(1)``, Shrout &
Fleiss 1979:

    MSB   = sum_j n_j (m_j - m)^2 / (k - 1)          between-judge mean square
    MSW   = sum_j sum (x - m_j)^2 / (N - k)          within-judge mean square
    v_a   = (MSB - MSW) / n0,   n0 = (N - sum n_j^2 / N) / (k - 1)

**The comparison that decides the matter** is ``v_a`` against the **sampling-noise
floor** ``MSW / n_bar`` -- what thirty judges with ``n_bar`` reviews each produce
by chance alone. A severity effect has to clear that floor to exist at all, and a
variance *below* it is not a small effect, it is **evidence of no effect**.

**Why the permutation test is over ``MSB`` and not over ``v_a``.** ``v_a``
subtracts a quantity that depends on the group sizes, so permuting it compares
against a null whose variance changes with every draw. ``MSB`` has a fixed null
under the permutation (the judge labels are held fixed and only the values move),
which is what makes the p-value mean what a reader thinks it means. **A
permutation test whose null moves is not a permutation test.**

**Everything here is generated.** No number in this module's output is typed
anywhere, and `tests/test_detectability.py` asserts the *measured* values, so a
refactor that silently changes the method fails a test rather than quietly
weakening the document.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class VarianceComponents:
    """The one-way random-effects decomposition, every term kept."""

    n: int
    k: int
    grand_mean: float
    n_bar: float
    msb: float
    msw: float
    n0: float
    between_variance: float
    noise_floor: float
    excess: float
    icc: float

    @property
    def below_noise(self) -> bool:
        """Whether the observed between-judge variance is UNDER the chance floor.

        **This boolean is the finding, and it is the whole reason the estimator is
        optional rather than load-bearing.** A positive ``excess`` would mean
        there is something to correct; a negative one means the correction is
        subtracting from noise.
        """
        return self.excess < 0


def variance_components(values_by_judge: dict[str, list[float]]) -> VarianceComponents:
    """``ICC(1)`` by the two-mean-square route, and the chance floor beside it."""
    groups = {j: [float(x) for x in v] for j, v in values_by_judge.items() if v}
    if len(groups) < 2:
        raise ValueError("ICC(1) needs at least two groups with data")
    sizes = [len(v) for v in groups.values()]
    n = sum(sizes)
    k = len(groups)
    if n <= k:
        raise ValueError("ICC(1) needs at least one observation beyond the group count")
    grand = statistics.fmean([x for v in groups.values() for x in v])

    msb = sum(len(v) * (statistics.fmean(v) - grand) ** 2 for v in groups.values()) / (k - 1)
    msw = sum(sum((x - statistics.fmean(v)) ** 2 for x in v) for v in groups.values()) / (n - k)
    n0 = (n - sum(s * s for s in sizes) / n) / (k - 1)
    between = (msb - msw) / n0
    n_bar = n / k
    floor = msw / n_bar
    icc = between / (between + msw) if (between + msw) else 0.0
    return VarianceComponents(
        n=n,
        k=k,
        grand_mean=grand,
        n_bar=n_bar,
        msb=msb,
        msw=msw,
        n0=n0,
        between_variance=between,
        noise_floor=floor,
        excess=between - floor,
        icc=icc,
    )


def permutation_p(
    values_by_judge: dict[str, list[float]],
    *,
    draws: int = 20_000,
    seed: int = 0,
) -> float:
    """Two-sided p for "there is a between-judge effect", by permutation of values.

    **The judge labels are held FIXED and only the values are shuffled**, which is
    what makes this a permutation test rather than a bootstrap: the null is "the
    grouping explains nothing", and the grouping is the thing under test.

    Seeded. **An unseeded permutation test is a test that gives a different answer
    on every run, and a published p-value that is not reproducible is not a
    published p-value** -- the same reasoning as the seeded assignment tiebreak.
    """
    groups = {j: list(v) for j, v in values_by_judge.items() if v}
    sizes = [len(v) for v in groups.values()]
    k = len(groups)
    grand = statistics.fmean([x for v in groups.values() for x in v])
    observed = sum(len(v) * (statistics.fmean(v) - grand) ** 2 for v in groups.values()) / (k - 1)

    pool = [x for v in groups.values() for x in v]
    rng = random.Random(seed)  # noqa: S311 - a permutation SHUFFLE, not a key
    at_least_as_extreme = 0
    for _ in range(draws):
        shuffled = pool[:]
        rng.shuffle(shuffled)
        cut = 0
        msb = 0.0
        for size in sizes:
            chunk = shuffled[cut : cut + size]
            cut += size
            msb += size * (statistics.fmean(chunk) - grand) ** 2
        msb /= k - 1
        if msb >= observed:
            at_least_as_extreme += 1
    # +1 in numerator and denominator: the observed arrangement is one of the
    # `draws + 1` exchangeable ones, so a p of exactly 0 is not reachable. This is
    # the standard correction and omitting it would understate every p-value.
    return (at_least_as_extreme + 1) / (draws + 1)


def dispersion_p(
    values_by_judge: dict[str, list[float]], *, seed: int = 0, draws: int = 20_000
) -> float:
    """Brown-Forsythe permutation test on dispersion, by permuting the RAW values.

    **F-92, and the reason this function was rewritten: the first version
    permuted the MAD-deviations that had already been computed from each judge's
    own median.** That is not a permutation of the statistic. Brown-Forsythe's
    statistic is ``MSB/MSW`` on absolute deviations from the *group* median, and
    the group median is part of what the test computes -- so holding the
    deviations fixed while shuffling them tests a null that does not correspond
    to any world. It produced ``p ~ 0.39`` on every seed, where ``bible/06``
    records ``0.186``.

    Permuting the **raw values** and recomputing each group's median inside the
    loop is the version that is actually a permutation of the test statistic, and
    it is the one whose null "the grouping explains no dispersion" is a world that
    could exist. The published number was right and the first implementation was
    wrong, which is the more useful order for that sentence to be in.

    Seeded, for the reason :func:`permutation_p` gives.
    """
    groups = [list(v) for v in values_by_judge.values() if v]
    sizes = [len(v) for v in groups]
    k = len(groups)
    pool = [x for v in groups for x in v]

    def msb_of(chunked: list[list[float]]) -> float:
        """``MSB`` on already-centered groups, with ITS OWN grand mean.

        The grand mean is recomputed inside the loop rather than captured from the
        observed data. Holding it fixed while the deviations change is the same
        class of error as the one this function was rewritten for: the statistic
        is a function of the data, so a permutation must recompute all of it.
        """
        grand = statistics.fmean([x for c in chunked for x in c])
        return sum(len(c) * (statistics.fmean(c) - grand) ** 2 for c in chunked) / (k - 1)

    observed = msb_of([_devs(v) for v in groups])
    rng = random.Random(seed)  # noqa: S311 - a permutation SHUFFLE, not a key
    at_least = 0
    for _ in range(draws):
        shuffled = pool[:]
        rng.shuffle(shuffled)
        cut = 0
        chunked = []
        for size in sizes:
            chunk = shuffled[cut : cut + size]
            cut += size
            chunked.append(_devs(chunk))
        if msb_of(chunked) >= observed:
            at_least += 1
    return (at_least + 1) / (draws + 1)


def _devs(values: list[float]) -> list[float]:
    """Absolute deviations from this group's own median."""
    med = statistics.median(values)
    return [abs(float(x) - med) for x in values]


def brown_forsythe_f(values_by_judge: dict[str, list[float]]) -> float:
    """The F statistic the dispersion permutation is testing. Reported beside it.

    **The statistic is published so a reader can see the p-value's denominator's
    companion number**, and because a p-value alone is not reproducible -- a
    reader who wants the F has to recompute the analysis to get it.
    """
    devs = {
        j: [abs(float(x) - statistics.median([float(y) for y in v])) for x in v]
        for j, v in values_by_judge.items()
        if v
    }
    sizes = [len(v) for v in devs.values()]
    grand = statistics.fmean([x for v in devs.values() for x in v])
    n = sum(sizes)
    k = len(devs)
    if n <= k or k < 2:
        return 0.0
    msb = sum(len(v) * (statistics.fmean(v) - grand) ** 2 for v in devs.values()) / (k - 1)
    msw = sum(sum((x - statistics.fmean(v)) ** 2 for x in v) for v in devs.values()) / (n - k)
    return msb / msw if msw else math.inf
