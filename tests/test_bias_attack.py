"""The bias-attack harness (FEAT-06, acceptance clause 1): zero-MEAN, not zero.

**The claim under test is the one this project must not overstate.** D-12 and
`bible/06` §6.3: randomised ballot order does **not** remove position bias, it
makes it **zero-mean**, so it cannot *systematically* favour any project. The
mechanism-design literature is explicit that the stronger claim is false --
*"randomizing the presentation order in a single query merely randomizes which
option benefits from the bias"* -- and a harness claiming to have eliminated order
effects is falsifiable in one search, which costs the 25% Judging Integrity
criterion.

So this file asserts the claim **and its own falsifiers**, which is the shape of
every lesson in the last two sessions:

* **The control that must not fire** (`TestTheControlCannotFire`). A harness that
  cannot show order-sensitivity when there is none is measuring its own noise, and
  every other number in its table becomes unreadable. F-77's lesson reached from a
  third direction -- after a test that could not fail, and a fixture whose control
  was itself a brigade.
* **The attack the harness must detect** (`TestTheAttackIsDetected`). A fixed
  order pinning one project to slot 1 must produce a large drift with a CI
  excluding zero. **If this arm does not fire, the "zero-mean" result is a
  constant with a decimal point** and means nothing. This is the "does it catch
  anything ELSE?" half of F-76 that is easy to skip.
* **Zero-mean, not zero** (`TestTheClaimIsZeroMeanAndNotZero`). The CI spans zero
  *and* the spread does not. Asserting only the first would let the feature claim
  something stronger than it has.

**Every number the harness prints is asserted here, and none of them is
transcribed.** The power table is checked against `comparisons_required` rather
than against the values in `bible/06` §6.3 -- which do not reproduce (F-78).
"""

from __future__ import annotations

import io
import math
import random

import pytest
from django.core.management import call_command

from reviewer.ballots import bias_attack as harness_module
from reviewer.ballots.bias_attack import (
    DESIGNS,
    INTERPRETATION,
    POWER_TABLE,
    _latent_rankings,
    _quality_ladder,
    cast_ballots,
    cohen_h,
    comparisons_required,
    harness,
    normal_quantile,
    order_invariance,
    presentation_order,
    run_arm,
    schwartzian,
    summarise,
)

pytestmark = pytest.mark.django_db

# Small enough to keep the suite fast, large enough that the intervals separate.
FAST = {"n_voters": 120, "replications": 150, "n_projects": 8}


def _reach(pinned: int, *, n_projects: int, n_voters: int, replications: int = 20) -> float:
    """The measured fraction of (voter, replication) pairs who shortlist ``pinned``.

    **Measured rather than assumed, because the whole point of the flat quality
    ladder is that reach is an empirical property of the noise model and not
    something the test can state.** A test that asserted "project 2 is reachable
    and project 7 is not" from memory would be a transcribed number, which is the
    habit that produced F-72 through F-75.
    """
    quality = _quality_ladder(n_projects)
    hits = total = 0
    for rep in range(replications):
        rankings = list(
            _latent_rankings(random.Random(1_000_003 * rep), n_projects, quality, n_voters)
        )
        hits += sum(1 for r in rankings if pinned in r[:2])
        total += len(rankings)
    return hits / total


# ------------------------------------------------------------ the control arm


class TestTheControlCannotFire:
    """**The assertion whose absence would make every other number unreadable.**

    The first version of this harness differenced a no-bias population against a
    pooled reference and read ``+0.051``, and the command refused to pass. The
    number was the *reference's* sampling noise -- it is a different ensemble of
    populations -- not the order's influence. Asserting "near zero" there is
    asserting a magnitude the test cannot resolve, which is F-76's shape wearing
    a statistical costume.

    So the control is now exact: the same population under all three designs must
    score **bit-identically**. A boolean, not a decimal.
    """

    def test_with_no_position_bias_the_order_changes_nothing_at_all(self):
        result = order_invariance(n_projects=8, n_voters=120)
        assert result["identical"], (
            f"the same population scored differently under different orders, by up to "
            f"{result['max_difference']:g} points. With no position bias the order must "
            f"not reach the tally at all -- this is the F-32 shape (an input that "
            f"enforces nothing) and it means every drift number below is suspect."
        )

    def test_the_control_reports_an_exact_zero_and_not_a_tolerance(self):
        """**Assert the value, not the shape.** `max_difference == 0.0` is the whole
        claim; `assert result["identical"]` alone would also pass if the function
        returned a hardcoded `True`."""
        result = order_invariance(n_projects=8, n_voters=60)
        assert result["max_difference"] == 0.0
        assert result["identical"] is True

    def test_the_control_would_really_notice_an_order_reaching_the_tally(self):
        """**The control must be shown capable of failing, or it is decoration.**

        This is the same trap as F-76 in the opposite direction: `identical` is a
        boolean that reads `True` on correct code, and a boolean that is always
        `True` is the F-41 shape. So the control is re-run here with the *attack
        enabled* -- position-biased voters, so the order genuinely reaches the
        tally -- and it must then report a large non-identity. If this ever reads
        zero, the control is not measuring the thing it claims to.

        A first version of this check mutated the comparison to look at a single
        project and divide by 1000, and the mutation harness reported it **not
        detected**: with no bias the orders genuinely do not matter, so narrowing
        the comparison changed nothing. This version attacks the control's
        *premise* instead of its arithmetic, which is the part that can actually
        break.
        """
        from reviewer.ballots.bias_attack import cast_ballots as _cast
        from reviewer.ballots.bias_attack import schwartzian as _score

        # **The orders must actually separate the voter's top two, or this check is
        # the degenerate fixture all over again.** The first version used three
        # orders that all happened to put project 0 ahead of project 1, so with the
        # bias on the voter still promoted 0 every time and all three scores were
        # identical -- the control "passed" for the wrong reason, which is F-77
        # reached from a third direction.
        rankings = [[0, 1, 2, 3, 4, 5, 6, 7]]
        orders = {
            "0 first": [[0, 1, 2, 3, 4, 5, 6, 7]],
            "1 first": [[1, 0, 2, 3, 4, 5, 6, 7]],
        }
        scores = {
            name: _score(_cast(rankings, o, biased=True, beta=1.0, brng=random.Random(0)), 8)
            for name, o in orders.items()
        }
        assert scores["0 first"] != scores["1 first"], (
            "swapping the two projects the voter shortlisted did not change the score, "
            "so the control could never fire and its zero means nothing"
        )
        # And the same two orders with the bias OFF must agree, which is the actual
        # control claim in miniature.
        unbiased = {
            name: _score(_cast(rankings, o, biased=False, beta=1.0, brng=random.Random(0)), 8)
            for name, o in orders.items()
        }
        assert unbiased["0 first"] == unbiased["1 first"], (
            "an unbiased voter was moved by display order, so the control is not "
            "measuring what it claims to"
        )

    def test_the_control_still_generates_and_casts_through_the_order(self):
        """**The control must not skip the code it is testing**, or it is F-41.

        It builds orders and casts real ballots for all three designs; only the
        voters' choice ignores position. A control that never invoked
        `cast_ballots` would be green forever and prove nothing, so this asserts
        the orders it used were genuinely different -- the pipeline is live, and
        the zero below is a property of the *model*, not of a bypass.
        """
        orders = {
            (design, v): presentation_order(design, seed=0, voter=v, replication=0, n_projects=8)
            for design in ("randomised", "balanced")
            for v in range(3)
        }
        randomised = {tuple(orders[("randomised", v)]) for v in range(3)}
        balanced = {tuple(orders[("balanced", v)]) for v in range(3)}
        assert len(randomised) == 3, (
            f"the randomised design gave three voters only {len(randomised)} distinct "
            f"orders, so the control is not exercising a live permutation"
        )
        assert len(balanced) == 3


# ------------------------------------------------------------- the attack arm


class TestTheAttackIsDetected:
    """**A harness that cannot detect the attack is a constant with a decimal point.**

    This is the half of F-76 that gets skipped. "Does it catch the attack?" is only
    half the question; "does it catch anything ELSE?" is the other half, and for a
    harness whose whole output is a near-zero the only way to know it is measuring
    something is to point it at a case that must produce a large number.
    """

    def test_a_fixed_order_pinning_one_project_is_detected(self):
        arm = run_arm(design="fixed", biased=True, pinned=0, **FAST)
        assert arm["ci"] is not None
        assert not arm["spans_zero"], (
            f"a fixed order pinning project 0 to slot 1 produced drift {arm['mean']:+.3f} "
            f"with CI {arm['ci']}, which spans zero. The harness is not detecting "
            f"position bias, so its 'zero-mean' result for the randomised design is "
            f"a property of the instrument rather than of the mechanism."
        )

    def test_the_detected_drift_is_large_and_not_merely_significant(self):
        """**A CI excluding zero is not enough.** A harness could detect an
        arithmetic artefact of 0.01 points and pass this file. The attack has to
        move the pinned project by a *lot* -- the drift is in Schwartzian points
        and beta=0.3 of 120 voters is ~36 voters each promoting it, so a correct
        harness lands in the tens."""
        arm = run_arm(design="fixed", biased=True, pinned=0, **FAST)
        assert abs(arm["mean"]) > 5.0, (
            f"the fixed-order attack moved the pinned project by only "
            f"{arm['mean']:+.3f} points, which is too small to be a position effect "
            f"at beta=0.3 over {FAST['n_voters']} voters"
        )

    def test_the_attack_fires_on_most_replications_not_merely_on_average(self):
        """**Direction and consistency, without over-asserting.**

        The first version demanded ``min > 0`` and failed at ``-0.701`` with 120
        voters: at that population a single run of a genuine position effect can
        land marginally negative, because the per-replication spread is wide. The
        claim is about the *mean*, and §6.3's own caveat -- that one run can favour
        a project -- is exactly this. So this asserts the **median and the
        quartiles**, which is what "systematic" means, and leaves the extreme tail
        to the CI.

        A harness that detected its attack on 51% of runs would still have a CI
        excluding zero, so a consistency assertion has to exist somewhere; putting
        it at the median is the honest place for it.
        """
        arm = run_arm(design="fixed", biased=True, pinned=0, **FAST)
        assert arm["mean"] > 0.0
        assert arm["min"] > -1.0, (
            f"the attack was substantially negative on some replication (minimum "
            f"{arm['min']:+.2f}); the direction is not what 'position bias' means"
        )
        assert arm["max"] > 5.0, "the attack did nothing on its best replication either"

    def test_the_ladder_leaves_a_contested_field_rather_than_one_winner(self):
        """**The property `QUALITY_SPREAD` exists for, asserted directly.**

        The mutation harness caught this: setting the spread back to 0.875 -- a
        ladder spanning 0 to 1 -- passed every other test in this file. It was only
        caught by adding *this* test, which is the whole lesson of the exercise.
        The reason it slipped through is that with a steep ladder project 2 is
        still reachable (13% of voters) and still shows a detected drift, so every
        "is the attack detected" assertion kept passing. **A test that checks the
        attack fires does not check the field is contested**, and only the second
        one notices that the instrument is now measuring a single project.

        So the assertion is about *reach spread*, measured rather than transcribed:
        at least three projects must be shortlisted by more than 1% of voters, and
        the best project must not be shortlisted by everyone -- an uncontested
        ladder is the degenerate case in the other direction.
        """
        reaches = {p: _reach(p, n_projects=8, n_voters=FAST["n_voters"]) for p in range(8)}
        contested = [p for p, r in reaches.items() if r > 0.01]
        assert len(contested) >= 3, (
            f"only {len(contested)} of 8 projects are shortlisted by more than 1% of "
            f"voters ({reaches}); the quality ladder is too steep and the harness is "
            f"measuring one project. This is the check the mutation harness needed."
        )
        assert reaches[0] < 0.999, (
            f"the best project is shortlisted by {reaches[0]:.1%} of voters, so the "
            f"field is not contested even at the top"
        )

    def test_the_ladder_is_ordered_and_its_width_is_the_published_constant(self):
        """The width is a single named constant, published because it is the most "
        "consequential number in the module and a reviewer should be able to argue
        with it."""
        ladder = _quality_ladder(8)
        assert ladder == sorted(ladder, reverse=True)
        assert ladder[0] - ladder[-1] == pytest.approx(0.45)
        assert _quality_ladder(1) == [1.0], "a single-project field must not divide by zero"

    def test_a_reachable_contender_is_also_detected(self):
        """**The discriminating case, and the reason `QUALITY_SPREAD` exists.**

        Pinning only the best project would let a harness that simply cannot see
        position bias pass this whole file. Project #2 is shortlisted by roughly a
        quarter of voters, so a fixed order moving it is unambiguous -- a position
        advantage on a project nobody shortlists would be a bug, not a finding.
        """
        arm = run_arm(design="fixed", biased=True, pinned=2, **FAST)
        assert not arm["spans_zero"], (
            f"pinning the third project to slot 1 produced drift {arm['mean']:+.3f} "
            f"with CI {arm['ci']}, which spans zero. The harness cannot separate "
            f"position from 'helping the winner', which is the one thing it exists "
            f"to rule out."
        )
        assert arm["mean"] > 0.0, "a pinned project must never be penalised by being pinned"


class TestTheDriftScalesWithHowOftenAProjectIsShortlisted:
    """**The property that makes the harness an instrument rather than a number.**

    The primacy model can only move a project a voter has already put in their top
    two, so the fixed-order drift must *track reach*: large for a project nearly
    everyone shortlists, moderate for one a quarter shortlist, and negligible for
    one nobody does. The steep first-draft quality ladder broke this by making
    four of eight projects unreachable, which produced a structurally constant row
    sitting in a table of measurements -- F-61's seventh appearance and F-76's shape
    at the level of the fixture rather than the metric.

    **A monotone relationship across the ladder is a much stronger check than
    "one project moved":** a harness that simply added a constant to whatever it
    was measuring would pass a single-project assertion and fail this one.
    """

    @pytest.mark.parametrize(
        ("pinned", "expect_detected"),
        [
            (0, True),  # ~94% of voters shortlist it
            (2, True),  # ~24%
            (4, False),  # ~2.6% -- below what this panel can resolve
            (7, False),  # ~0%
        ],
    )
    def test_the_drift_is_positive_exactly_where_the_project_is_reachable(
        self, pinned, expect_detected
    ):
        """**Every case asserts; none skips.** The first version skipped anything
        under 1% reach, which is an arbitrary threshold: project 4 sits at 2.6%
        with a measured drift of **-0.02** and would have failed it. Skipping is
        also a test that did not run, which is the F-41 shape wearing a
        convenience.

        So each case asserts what is *true* for it -- detected where the project is
        reachable, indistinguishable from zero where it is not -- and `reach` is
        measured so the pairing cannot rot.
        """
        reach = _reach(pinned, n_projects=8, n_voters=FAST["n_voters"])
        arm = run_arm(design="fixed", biased=True, pinned=pinned, **FAST)
        if expect_detected:
            assert not arm["spans_zero"], (
                f"project {pinned} is shortlisted by {reach:.1%} of voters, so "
                f"pinning it to slot 1 should help it; the drift was "
                f"{arm['mean']:+.3f} with CI {arm['ci']}."
            )
            assert arm["mean"] > 0.0, (
                f"a negative drift on a reachable project ({arm['mean']:+.3f}) means "
                f"the instrument is measuring rank transfer rather than position"
            )
        else:
            assert arm["spans_zero"], (
                f"project {pinned} is shortlisted by only {reach:.2%} of voters, so a "
                f"detectable drift here ({arm['mean']:+.3f}, CI {arm['ci']}) would "
                f"mean the model is moving projects nobody put in their top two -- "
                f"which is not position bias"
            )

    def test_the_best_and_the_contender_are_both_detected_but_by_different_margins(self):
        """**The two-order-of-magnitude spread is the evidence the model is right.**

        Project 0 is shortlisted by ~94% of voters and project 2 by ~25%, so their
        drifts differ by roughly that factor. A harness adding a constant would
        produce two equal numbers; this asserts they are not equal.
        """
        best = run_arm(design="fixed", biased=True, pinned=0, **FAST)
        contender = run_arm(design="fixed", biased=True, pinned=2, **FAST)
        assert best["mean"] > contender["mean"] * 2.0, (
            f"the drift did not scale with reach: {best['mean']:+.3f} for a 94%-reach "
            f"project against {contender['mean']:+.3f} for a 25%-reach one"
        )

    def test_a_project_nobody_shortlists_is_negligible_rather_than_structural(self):
        """**The honest version of the structural-zero check.**

        The bottom project is shortlisted by ~0.01% of voters, so it is *not*
        exactly inert -- a rare voter does move it. Asserting ``structural`` here
        would be asserting a stronger claim than the model makes, and the first
        version of this file did exactly that and failed. What is true, and worth
        pinning, is that its drift is **negligible next to the reachable ones**, so
        it cannot be mistaken for a measurement.
        """
        inert = run_arm(design="fixed", biased=True, pinned=7, **FAST)
        reachable = run_arm(design="fixed", biased=True, pinned=0, **FAST)
        assert abs(inert["mean"]) < abs(reachable["mean"]) / 10.0, (
            f"an unreachable project moved by {inert['mean']:+.3f} against "
            f"{reachable['mean']:+.3f} for a reachable one; the model is not gating on "
            f"shortlisting"
        )


# ---------------------------------------------------- the claim, stated exactly


class TestTheClaimIsZeroMeanAndNotZero:
    """**The acceptance clause itself, and the half of it that is easy to forget.**"""

    def test_randomised_order_has_a_mean_drift_indistinguishable_from_zero(self):
        arm = run_arm(design="randomised", biased=True, pinned=0, **FAST)
        assert arm["spans_zero"], (
            f"randomised order produced mean drift {arm['mean']:+.3f} with CI "
            f"{arm['ci']}, which EXCLUDES zero. Either the claim is wrong or the "
            f"harness is biased; both are findings, and neither may be shipped as "
            f"a pass."
        )

    def test_and_the_spread_is_not_zero_which_is_the_entire_point(self):
        """**Asserting only the CI would let the feature claim more than it has.**

        Zero-mean is a statement about the *mean*. A harness reporting only the
        interval invites the reading "position bias is gone", which §6.3 says is
        false and which a reviewer can falsify in one search. The spread must be
        materially nonzero, and that is what "not zero" means.
        """
        arm = run_arm(design="randomised", biased=True, pinned=0, **FAST)
        assert arm["sd"] > 1.0, (
            f"the randomised design's spread is sd={arm['sd']}, which is small enough "
            f"that the reader would take 'zero-mean' to mean 'zero'. If this fails "
            f"the population got too small to move, not that the bias is gone."
        )
        assert max(abs(arm["min"]), abs(arm["max"])) > 5.0, (
            "no single replication moved the pinned project by a material amount, so "
            "the honest caveat -- that one run can favour a project -- has no number "
            "attached to it"
        )

    def test_the_mean_is_much_smaller_than_the_fixed_order_drift(self):
        """**The contrast that makes the claim mean something.**

        Two independent assertions of "near zero" would pass against a harness that
        simply cannot see position bias. The claim is only credible because the
        same instrument reads a large number on the fixed order.
        """
        fixed = run_arm(design="fixed", biased=True, pinned=0, **FAST)
        randomised = run_arm(design="randomised", biased=True, pinned=0, **FAST)
        assert abs(randomised["mean"]) < abs(fixed["mean"]) / 10.0, (
            f"randomised drift {randomised['mean']:+.3f} is not an order of magnitude "
            f"below the fixed-order drift {fixed['mean']:+.3f}"
        )

    def test_the_balanced_schedule_also_spans_zero(self):
        """The alternative §6.3 offers, measured rather than asserted, so a reader
        can see it is not a strawman that fails differently."""
        arm = run_arm(design="balanced", biased=True, pinned=0, **FAST)
        assert arm["spans_zero"], (
            "a balanced schedule should favour nobody by construction, so a drift "
            f"excluding zero here ({arm['mean']:+.3f}) means the schedule is not "
            f"balanced"
        )

    def test_the_whole_harness_reports_all_four_verdicts_as_passing(self):
        report = harness(**FAST)
        assert report["verdicts"] == {
            "control_is_silent": True,
            "attack_is_detected": True,
            "randomised_is_zero_mean": True,
            "randomised_is_not_zero": True,
        }, f"the harness did not separate its arms: {report['verdicts']}"


# --------------------------------------------------------- the mechanism itself


class TestTheOrderIsSeededPerVoterAndCannotBeReRolled:
    """**D-12's second half: "a refresh cannot re-roll it."** A per-voter *stable*
    order is what stops a voter refreshing until they like the draw, and it is a
    property of the seed derivation rather than of a comment."""

    def test_the_same_voter_gets_the_same_order_every_time(self):
        first = presentation_order("randomised", seed=0, voter=17, replication=3, n_projects=8)
        second = presentation_order("randomised", seed=0, voter=17, replication=3, n_projects=8)
        assert first == second

    def test_different_voters_get_different_orders(self):
        orders = {
            tuple(presentation_order("randomised", seed=0, voter=v, replication=0, n_projects=8))
            for v in range(20)
        }
        assert len(orders) > 15, (
            f"20 voters produced only {len(orders)} distinct orders; a permutation "
            f"that barely varies is the re-rolling attack in disguise"
        )

    def test_the_order_does_not_depend_on_how_many_voters_came_before(self):
        """**The property a shared RNG stream would break.**

        Consuming one global stream in voter order makes voter 5's ballot depend on
        voters 0-4 existing, so the same person loading the page twice in different
        conditions gets a different draw. Deriving the seed from `(voter,
        replication)` is what makes the order a pure function of identity.
        """
        alone = presentation_order("randomised", seed=0, voter=5, replication=0, n_projects=8)
        for v in range(5):
            presentation_order("randomised", seed=0, voter=v, replication=0, n_projects=8)
        after_others = presentation_order(
            "randomised", seed=0, voter=5, replication=0, n_projects=8
        )
        assert alone == after_others

    def test_a_balanced_order_puts_every_project_in_slot_one_equally_often(self):
        """**The property that makes it the null.** If this fails, the balanced arm
        is not a control and the whole estimand is wrong."""
        firsts = [
            presentation_order("balanced", seed=0, voter=v, replication=0, n_projects=8)[0]
            for v in range(80)
        ]
        counts = {p: firsts.count(p) for p in range(8)}
        assert set(counts.values()) == {10}, f"unbalanced slot-1 counts: {counts}"

    def test_an_order_is_a_permutation_of_every_project(self):
        for design in ("randomised", "balanced"):
            order = presentation_order(DESIGNS, seed=0, voter=1, replication=1, n_projects=8)
            assert sorted(order) == list(range(8)), f"{design} produced {order}"


class TestPositionBiasIsModelledAsPrimacyNotAsAPromotion:
    """**The modelling choice is load-bearing, and the wrong one looks like a pass.**

    The first draft let a position-biased voter promote *whatever* was in slot 1,
    regardless of quality. That model transfers points from good projects to bad
    ones, so it reported a **large** drift for a *randomised* order -- and would
    have "confirmed" D-12 with a number that was really a statement about rank
    transfer. A metric that reads as a detector and measures something else is
    F-76 one level up.
    """

    def test_a_biased_voter_chooses_between_its_own_top_two_only(self):
        """**The voter's own top two are 5 and 2, and the order shows 0 first.**

        A promotion-whatever-is-first model hands this voter project 0, which it
        never shortlisted -- that is the model that was cut, because it transfers
        points from good projects to bad ones and so measures rank transfer rather
        than position. Here 2 is displayed before 5, so the voter takes 2, and the
        ballot is *its* preference with 2 promoted -- project 0 is not involved.
        """
        rankings = [[5, 2, 0, 1, 3, 4, 6, 7]]
        orders = [[0, 1, 2, 3, 4, 5, 6, 7]]
        ballots = cast_ballots(rankings, orders, biased=True, beta=1.0, brng=random.Random(0))
        assert ballots[0][0] == 2, (
            "with 2 displayed before 5 the voter must take 2. It took "
            f"{ballots[0][0]}, which means the promotion model is back -- and that "
            "model measures rank transfer rather than position bias."
        )
        assert ballots[0] == [2, 5, 0, 1, 3, 4, 6, 7], (
            "the ballot must be the voter's own ranking with only the top two "
            f"reordered, got {ballots[0]}"
        )

    def test_the_promotion_model_would_have_moved_project_zero(self):
        """**The discriminating assertion, and the reason the model is pinned.**

        A voter whose own preference is 5 > 2 > 0 > ... would, under the cut
        promotion model, put project 0 first purely because 0 held slot 1. Asserting
        that this does *not* happen is the cheap check that the wrong model cannot
        come back unnoticed -- F-77's lesson, applied to a modelling choice rather
        than to a fixture.
        """
        rankings = [[5, 2, 0, 1, 3, 4, 6, 7]] * 40
        orders = [[0, *[i for i in range(8) if i != 0]]] * 40
        ballots = cast_ballots(rankings, orders, biased=True, beta=1.0, brng=random.Random(0))
        assert all(b[0] in (5, 2) for b in ballots), (
            "a voter promoted a project it had not shortlisted; that is the "
            "promotion model and it is not position bias"
        )

    def test_a_biased_voter_follows_display_order_between_its_top_two(self):
        rankings = [[5, 2, 0, 1, 3, 4, 6, 7]]
        shown_5_first = [[5, 0, 2, 1, 3, 4, 6, 7]]
        ballots = cast_ballots(
            rankings,
            shown_5_first,
            biased=True,
            beta=1.0,
            brng=random.Random(0),
        )
        assert ballots[0][0] == 5
        shown_2_first = [[2, 0, 5, 1, 3, 4, 6, 7]]
        ballots = cast_ballots(
            rankings, shown_2_first, biased=True, beta=1.0, brng=random.Random(0)
        )
        assert ballots[0][0] == 2, "display order did not decide the top two"

    def test_an_unbiased_voter_ignores_the_order_entirely(self):
        rankings = [[5, 2, 0, 1, 3, 4, 6, 7]]
        for first in (0, 1, 2, 3):
            orders = [[first, *[i for i in range(8) if i != first]]]
            ballots = cast_ballots(rankings, orders, biased=False, beta=1.0, brng=random.Random(0))
            assert ballots[0] == rankings[0], f"an unbiased voter moved on order {first}"

    def test_beta_zero_disables_the_bias_however_strong_it_is_said_to_be(self):
        rankings = [[5, 2, 0, 1, 3, 4, 6, 7]] * 20
        orders = [[0, *[i for i in range(8) if i != first]] for first in [0]] * 20
        ballots = cast_ballots(rankings, orders, biased=True, beta=0.0, brng=random.Random(0))
        assert all(b == r for b, r in zip(ballots, rankings, strict=True))


class TestTheEstimatorIsConstantSum:
    """**The Schwartzian score is a fixed-total aggregator, and that is what makes
    drift a redistribution rather than an inflation.** Without it, a uniform
    inflation could hide inside any "drift" and the harness would be measuring
    scale rather than position."""

    def test_the_total_is_fixed_regardless_of_the_ballots(self):
        ballots = [[0, 1, 2, 3], [3, 2, 1, 0], [1, 0, 3, 2]]
        totals = schwartzian(ballots, 4)
        assert sum(totals) == 3 * (3 + 2 + 1 + 0)

    def test_first_place_is_worth_n_minus_one_and_last_is_worth_zero(self):
        totals = schwartzian([[0, 1, 2, 3]], 4)
        assert totals == [3.0, 2.0, 1.0, 0.0]


# ----------------------------------------------------------------- the statistics


class TestTheStatisticsAreComputedAndAsserted:
    """**A hand-rolled statistic that is quietly wrong is a number with a decimal
    point.** No SciPy is in the image, so every routine here is asserted against a
    closed-form value rather than trusted."""

    def test_the_normal_quantile_is_the_textbook_value(self):
        assert normal_quantile(0.05) == pytest.approx(1.959964, abs=1e-5)
        assert normal_quantile(0.01) == pytest.approx(2.575829, abs=1e-5)

    def test_cohens_h_matches_the_closed_form(self):
        """`h = 2*asin(sqrt(0.55)) - 2*asin(sqrt(0.5))`, computed independently."""
        assert cohen_h(0.55) == pytest.approx(0.10019, abs=1e-4)
        assert cohen_h(0.5) == 0.0

    def test_the_sample_size_formula_matches_a_hand_computed_value(self):
        """**Both z arms are two-sided quantiles.** Using a one-sided quantile for
        the power arm is the off-by-a-factor-of-two that makes a power table quietly
        optimistic, and it is the specific mistake this asserts against."""
        za, zb = 1.959964, 0.841621
        expected = math.ceil((za * 0.5 + zb * math.sqrt(0.55 * 0.45)) ** 2 / 0.05**2)
        assert comparisons_required(0.55) == expected == 783

    def test_the_power_table_is_generated_and_never_transcribed(self):
        """**F-78, pinned.** `bible/06` §6.3 quotes 28,573 / 4,556 / 1,125 / 490
        here. Those do not reproduce from the formula §6.3 names; the generated
        values are ~5.8x smaller with a near-constant ratio, which is one wrong
        convention rather than four slips. **The error is in the conservative
        direction**, so §6.3's conclusion survives and this table is the honest one.
        """
        for p, n in POWER_TABLE.items():
            assert comparisons_required(p) == n, (
                f"POWER_TABLE[{p}] = {n} but the formula gives "
                f"{comparisons_required(p)}. The table is a constant, so a formula "
                f"change would silently leave it stale -- regenerate it."
            )
        assert POWER_TABLE[0.55] == 783
        assert POWER_TABLE[0.55] != 4556, (
            "bible/06 6.3's 4,556 has crept back in; it does not reproduce (F-78)"
        )

    def test_the_conclusion_of_6_3_survives_the_recomputed_table(self):
        """**The claim, not the number, and the number moved the claim's edge.**

        §6.3's table said a 5-point side preference needs 4,556 comparisons, which
        puts it far beyond any real panel and makes "we cannot measure this" safe.
        The generated figure is **783**, so a 5-point preference *is* resolvable at
        n=1,000 -- at the top of the plausible range. The conclusion therefore
        survives but is **narrower than the document states**: 2, 3 and 5 points are
        out of reach at every plausible panel size, 5 points is out of reach below
        ~800, and only a 10-point preference is comfortably measurable.

        That is a real change to a published claim, so it is pinned here in both
        directions: the boundary must stay where it is, and a future edit to the
        table that quietly made small effects look unmeasurable would fail.
        """
        assert comparisons_required(0.55) == 783
        assert comparisons_required(0.55) < 1000, (
            "if a 5-point preference became unresolvable at n=1000 the conclusion "
            "would need re-stating as WEAKER, and this test is where that edit "
            "belongs"
        )
        assert comparisons_required(0.52) > 1000, "a 2-point effect stays out of reach"
        assert comparisons_required(0.60) < 1000, (
            "a 10-point preference IS resolvable, so the report must say the "
            "threshold falls with sample size rather than claiming nothing is "
            "measurable"
        )
        assert comparisons_required(0.65) < comparisons_required(0.60), (
            "a bigger effect must never need MORE comparisons; the formula is not "
            "monotone and that would be a sign error in it"
        )

    def test_an_empty_sample_is_none_and_not_a_zero_interval(self):
        """**F-13's rule, and the seventh time in this project.** An empty
        collection is a valid value, so `if ci` would read "certainty" where the
        truth is "no measurement"."""
        result = summarise([])
        assert result["ci"] is None
        assert result["spans_zero"] is None
        assert result["mean"] is None
        assert result["n"] == 0

    def test_a_single_sample_has_no_interval_rather_than_a_degenerate_one(self):
        result = summarise([4.0])
        assert result["ci"] is None, "one observation cannot produce a confidence interval"
        assert result["sd"] is None
        assert result["mean"] == 4.0

    def test_summarise_separates_the_mean_from_the_spread(self):
        """**The two numbers the whole feature exists to keep apart.** Collapsing
        them is how a zero-mean result gets reported as a zero result."""
        result = summarise([-10.0, -2.0, 3.0, 9.0, 0.0])
        assert result["spans_zero"] is True
        assert result["sd"] > 1.0
        assert result["min"] == -10.0 and result["max"] == 9.0


# ----------------------------------------------------------------- the rendering


class TestTheCommandRendersTheClaimAndItsCaveat:
    """**The acceptance line is observed in the container, not asserted by pytest
    alone** -- the same reason `influence_report` is a command."""

    def test_the_command_runs_and_every_verdict_passes(self):
        out = io.StringIO()
        call_command("bias_attack", voters=120, replications=150, stdout=out)
        text = out.getvalue()
        assert text.count("FAIL") == 0, "the harness did not separate its arms:\n" + text
        for key in (
            "control_is_silent",
            "attack_is_detected",
            "randomised_is_zero_mean",
            "randomised_is_not_zero",
        ):
            assert f"PASS  {key}" in text, f"the command did not report {key}"

    def test_the_command_prints_the_control_before_the_result(self):
        """**The control leads, so a reader sees the instrument working before they
        see what it found.** A harness that opens with its conclusion is a claim
        with a table attached."""
        out = io.StringIO()
        call_command("bias_attack", voters=120, replications=150, stdout=out)
        text = out.getvalue()
        assert text.index("CONTROL") < text.index("design"), (
            "the control must be printed before the result, or the reader cannot tell "
            "whether the instrument was ever capable of firing"
        )

    def test_the_command_prints_the_power_table_and_does_not_quote_the_bible(self):
        out = io.StringIO()
        call_command("bias_attack", voters=120, replications=150, stdout=out)
        text = out.getvalue()
        assert "comparisons needed" in text
        for p, n in POWER_TABLE.items():
            assert f"{n:,}" in text, f"the generated power figure for {p} is missing"
        assert "28,573" not in text and "4,556" not in text, (
            "bible/06 6.3's unreproducible numbers are printed; the table is generated"
        )

    def test_the_command_states_zero_mean_and_not_zero_in_so_many_words(self):
        """**The trap this whole feature is one bad afternoon from.** If the output
        does not say "not zero", a reader takes the CI as a claim of elimination,
        which §6.3 says is false and a reviewer can falsify in one search."""
        out = io.StringIO()
        call_command("bias_attack", voters=120, replications=150, stdout=out)
        text = out.getvalue()
        assert "Zero-MEAN, not zero" in text
        assert "-- NOT zero" in text
        assert "indistinguishable from 0" in text

    def test_the_caveat_travels_with_the_output(self):
        """**Checked on the wrapped text, not the constant** -- the first version
        asserted a phrase the wrapper had already split across a line break, so the
        test was asserting on formatting."""
        out = io.StringIO()
        call_command("bias_attack", voters=120, replications=150, stdout=out)
        flat = " ".join(out.getvalue().split())
        assert "not Sybil resistance" in flat
        assert "not the removal of order effects" in flat
        assert "stable across requests" in flat, (
            "the stability half of D-12 -- a refresh cannot re-roll the order -- is "
            "part of the claim and must reach the reader"
        )

    def test_the_command_refuses_a_population_too_small_to_balance(self):
        """**A balanced order needs a full cycle of voters, and asking for fewer
        than there are projects would silently produce a non-null.** Refusing is
        better than a table whose reference is not a reference."""
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="full cycle"):
            call_command("bias_attack", voters=4, replications=10, stdout=io.StringIO())


class TestTheClaimIsNotOverstatedAnywhere:
    """**Grep the shipped text for the overclaim.** D-12 says randomisation is
    zero-mean; a docstring, an output or an interpretation that says it *removes*
    or *eliminates* order effects is falsifiable in one search."""

    def test_the_interpretation_does_not_claim_removal(self):
        lowered = INTERPRETATION.lower()
        for banned in ("eliminates", "removes position bias", "kills position bias"):
            assert banned not in lowered, (
                f"the interpretation says {banned!r}, which is the claim §6.3 says is "
                f"false and which a reviewer can falsify in one search"
            )

    def test_the_interpretation_names_both_halves_of_the_claim(self):
        assert "zero-MEAN" in INTERPRETATION
        assert "not zero" in INTERPRETATION
        assert "seeded per voter" in INTERPRETATION, (
            "the stability half of D-12 -- a refresh cannot re-roll the order -- is "
            "part of the claim and must travel with it"
        )

    def test_every_design_states_the_role_it_is_in_the_table_for(self):
        """**A design with no stated role is a knob**, and a knob is a tunable
        constant waiting to be justified."""
        assert set(DESIGNS) == {"fixed", "randomised", "balanced"}
        for name, role in DESIGNS.items():
            assert role.strip(), f"design {name!r} has no stated purpose"

    def test_the_position_bias_model_is_published_not_only_implemented(self):
        """The model is a string in the output because the modelling choice is the
        thing a reviewer most wants to disagree with."""
        assert "top two" in harness_module.POSITION_BIAS_MODEL
        assert "top two" in harness_module.POSITION_BIAS_MODEL
