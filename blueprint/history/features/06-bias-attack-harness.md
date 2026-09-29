# FEAT-06 — Public surface: the bias-attack harness (increment 3)

> **The acceptance line's FIRST clause**, and the one this project is most likely
> to overclaim. Voting, comments and randomised ballot order as a *product* are
> not in this increment; the influence report was increment 2. The harness went
> after the report because it needs an attack to be visible against — and it
> needed three attempts before the instrument could see anything at all.

**Date:** 2026-09-29 · **Phase F** · **Gate:** none (BREAK-3 is next, `v-t3-verified`)

---

## What shipped

| Piece | Where | What it is |
|---|---|---|
| The harness | `src/reviewer/ballots/bias_attack.py` | a controlled experiment: does randomised order make position bias zero-**mean**? |
| The estimand | `run_arm` | drift against a **balanced-order** null, with the bias held fixed |
| The control | `order_invariance` | with no bias, all three orders must score **bit-identically** |
| The statistics | `normal_quantile`, `cohen_h`, `comparisons_required`, `summarise` | computed, no SciPy, asserted against closed forms |
| The render | `manage.py bias_attack` | the control, the three arms, the claim, the caveat |

**No schema change, no migration, no new route, no new model.** The harness is
pure Python over a synthetic population, which is why it needed no permission work
at all — and why it is a *controlled* experiment rather than a measurement of
`fixtures.json`, which has zero ballots.

---

## The acceptance line, observed in the container

```
  CONTROL -- no position bias in the population at all:
    the same population, scored under all three orders:
    max difference across orders = 0

  pinned project #0:
    design       drift mean                95% CI       sd  verdict
    fixed           +27.643      [+26.20, +29.09]   +9.047  EXCLUDES zero
    randomised       -0.530        [-2.11, +1.05]   +9.872  spans zero
    balanced         -0.884        [-2.31, +0.54]   +8.899  spans zero

  pinned project #2:
    fixed            +7.391        [+4.89, +9.89]  +15.608  EXCLUDES zero
    randomised       -0.262        [-2.60, +2.08]  +14.627  spans zero
    balanced         +0.031        [-2.29, +2.35]  +14.503  spans zero

    mean drift = -0.530 with a 95% CI of [-2.11, +1.05] -- indistinguishable from 0
    spread     = sd +9.872, range [-21.4, +23.6] -- NOT zero
```

**The CI spans zero and the spread does not.** That is the whole deliverable, and
it is reported as two numbers precisely because they can disagree — a harness
reporting only the interval would let a reader conclude the bias was *removed*,
which `bible/06` §6.3 says is false and which one citation refutes.

**The fixed arm is the part that makes the other two mean anything.** Without it,
"near zero" would be what a blind instrument also reports.

---

## Three decisions worth keeping

**1. The estimand is the order, not the bias.** The obvious design differences
"biased voters under a random order" against "no bias at all", and that measures
the *mechanism*, not the *order* — it returns a large number with no bearing on
whether randomisation helps. D-12 asserts something about the order **with the
bias held fixed**, so the null is a **balanced** order: every project in slot 1
equally often, favouring nobody by construction. This was wrong in the first two
drafts and the module docstring says so.

**2. The control is exact, not statistical.** The first version differenced a
no-bias population against the pooled reference and read **`+0.051`**, and the
command *refused to pass* — correctly. The `+0.051` is the reference's own
sampling noise; the reference is a different ensemble. Asserting a magnitude the
test cannot resolve is F-76's shape in a statistical costume. `order_invariance`
now compares the same population across designs and requires **bit-identical**
scores: a boolean, not a decimal.

**3. Two pinned projects, because one is not enough.** Pinning only the best
project would let a harness that simply cannot see position bias pass the entire
file. Project #2 is shortlisted by ~25% of voters and pinning it gives **+7.39
with a CI excluding zero** — the discriminating case, and the one that says the
instrument reads *position* rather than *helping the winner*.

---

## Three findings, and every one is about verification

### F-79 [P1] — the first model measured rank transfer, not position bias

The first draft let a position-biased voter promote *whatever* was in slot 1,
regardless of quality. It reported **−48 for the best project and +47 for the
worst** under a *randomised* order.

That is not a position effect. The model moves points from good projects to bad
ones, so a harness using it would show a large number for randomised order and
thereby **"confirm" that randomisation works — for the wrong reason, with a
number that was never about the order.** The shipped model is the serial-position
effect: a biased voter **resolves its own top two by which is displayed first**.

**F-76 one level up.** `lift` was structurally *constant*; this was structurally
*wrong*. Both read as detectors. Found by prototyping before writing the module.

### F-80 [P2] — a one-project instrument, and all 48 tests passed

Qualities on a 1.0→0.12 ladder meant project 0 was in some voter's top two
**100%** of the time and projects 5 and 7 **never**. Since the model can only move
a shortlisted project, pinning the bottom produced **−0.317 against a spread of
4.69** — a structurally constant row in a table of measurements.

**Every test in the file still passed with the ladder restored to 0.875**, because
project 2 was still reachable. *A test that checks the attack fires does not check
the field is contested.*

Found by the mutation harness reporting its own mutation **NOT DETECTED** — the
dangerous direction, and one `pytest` cannot produce on its own. `QUALITY_SPREAD`
is now 0.45 and reach is **measured** by a helper rather than asserted from
memory.

### F-78 [P2] — `bible/06` §6.3's power table does not reproduce

§6.3 quotes **28,573 / 4,556 / 1,125 / 490** comparisons. Fleiss gives
**4,904 / 783 / 194 / 85** — a near-constant **5.8×**, which is *one* wrong
convention, not four slips. Solving for the implied `(z_alpha, z_power)` gives
**4.098** (alpha 0.000083) and **2.665** (power 0.9962); the stated pair is
1.9600 and 0.8416. No standard convention produces the quoted table.

**The error is conservative and the correction NARROWS the claim.** §6.3's
sentence — *a real event cannot measure residual position bias* — survives for
every realistic panel, and **fails at the top of its own stated range**: 783
comparisons detects a 5-point preference, and the range reaches 1,000. So the
shipped table reports what the measurement supports, and a test pins the
conclusion **in both directions** so a future edit cannot quietly strengthen it.

### F-81 [P3] — a mutation's detector was wired to the wrong tuple

The primacy mutation was reported **MISSED**; a manual replication proved the
identical corruption was caught. The description and the detector had ended up in
each other's tuple, so the corruption was checked with the *control's* tests, which
correctly pass. **A mis-wired mutation is worse than no mutation** — it reports a
confident false failure, and the normal response to a red mutation gate is to
blame the test. Two other mutations were genuinely undetectable (a hardcoded
verdict that happens to be `True`; a shuffle-seed change that leaves slot-1 balance
intact) and both now attack the **property** instead of the arithmetic, each
recording why the first attempt could not work.

---

## What it cost, and what is left

| | |
|---|---|
| Tests | 428 → **479** (51 in `tests/test_bias_attack.py`) |
| Mutations | 59 → **68** (9 new, each naming its detecting test) |
| Suite | 479 pass · `just check` **GATE GREEN** at 7/7 · spec 71/71 · lint clean · `prove-offline` pass |
| **The acceptance line** | **BOTH clauses now built** — the harness shows zero-mean, and the influence report renders for a synthetic attack |
| Still unstarted | randomised ballot order as a **product** path, voting, comments, public result hiding |

**The harness measures the mechanism; the product path that uses it is still
unbuilt.** `presentation_order` is the function the ballot feature will call, and
it is deliberately the *same* function the harness attacks, so the claim and the
implementation cannot drift apart.

---

## Do not

- **Do not say the harness eliminates position bias.** It makes it zero-**mean**.
  The rendered output says "Zero-MEAN, not zero" on every run and a test fails if
  the word "eliminates" appears in the interpretation.
- **Do not report only the interval.** The spread is the honest half of the claim,
  and it is the half that makes the caveat true.
- **Do not widen `QUALITY_SPREAD` back toward 1.0.** Four of eight projects
  become unreachable, the harness degenerates into a one-project instrument, and
  every "is the attack detected" test still passes. F-80.
- **Do not replace the primacy model with "promote whatever is in slot 1".** It
  measures rank transfer and would "confirm" the claim for the wrong reason. F-79.
- **Do not quote `bible/06` §6.3's power table.** It does not reproduce. F-78.
