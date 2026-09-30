# FEAT-08 — the normalization proof

**Date:** 2026-09-29 · **Phase H · PROTECTED** · **Gate:** none

The proof, not a bigger σ reduction. **Every published number was generated**
by `tools/derive_normalization_numbers.py` and **asserted in CI** by
`tests/test_normalization.py`. The deliverable is
`docs/REAL-FIXTURE-RESULTS.md`.

---

## The first thing the generator did was refuse to reproduce two numbers

That is the headline, and it is the whole argument for generating figures
standing in front of a document.

| | generated | `bible/06` §4.1b | verdict |
|---|---|---|---|
| every variance-decomposition term | 3.5651 / 0.4981 / 0.4079 / **0.0217** / **0.0971** / −0.0754 / 0.0506 | identical to 4 dp | **reproduces exactly** |
| Brown–Forsythe `F` | 1.0686 | 1.069 | reproduces |
| **location p** | **0.2266** (seed 0); 6-seed range 0.2266–0.2415 | 0.234 | **reproduces as a seed draw** — 0.234 is inside the range |
| **dispersion p** | **0.5376** (seed 0); 0.39 under the other scheme | 0.186 | **DOES NOT REPRODUCE — F-92** |

**The asymmetry between the two p-values is worse than either being wrong.** A
permutation p is a function of a seed, and `bible/06` recorded a value without
one. The location figure lands inside the seed-to-seed spread so it reads as
correct; the dispersion figure does not so it reads as wrong. **A reader has no
way to tell those apart without re-deriving.**

**The conclusion is unaffected and that is the half that matters.** Both p-values
are an order of magnitude above 0.05 and point the same way, so "no severity
effect on this fixture" is supported by **two independent tests**, and the
quantitative core reproduces to four decimals. **The number is wrong; the finding
is right.** We report the finding and do not report 0.186.

---

## The null result

```
between-judge variance  0.0217
sampling-noise floor    0.0971     <- what 30 judges x 4 reviews produce by chance
excess                 -0.0754
```

**There is no severity effect to remove, because there is no severity effect.**
The estimator is therefore *optional* rather than load-bearing, and `/results/`
keeps its `unnormalized-raw-weighted-mean` label with a measured reason behind it.

---

## What applying the estimator would COST — and it is not flattering

We built it, and on this fixture it would **move all 126 reviews, mean |shift|
0.5702 rubric points, largest 1.4411**. That is on data where the analysis says
there is nothing to correct.

**That number is in the document and asserted in a test**
(`test_the_mean_movement_matches_the_documented_cost`). A proof whose estimator
quietly did nothing would be easier to sell and worth less.

---

## The sensitivity curves, and why they do not peak on our values

```
held-out RMSE:  0.6749 (k=0)  ->  0.6133 (k=12, eps=0.75)   <- the metric's optimum
we ship:                          k=3, eps=0.5
```

**The curve does not peak on our constants, and that is the entire point.** If it
did, it would be decoration dressed as rigour. Both trends are visible and both
are the opposite of "we fitted this": RMSE improves monotonically as `k` rises,
because with no severity effect the best setting is the one that **does the
least**. And the RMSE is not an accuracy measure — there is no ground truth for a
rubric score — so a curve saying "do less" is a curve that correctly detected
there is nothing to fix.

`k = 3` is "a judge needs about three reviews to be worth listening to". `ε = 0.5`
is half a rubric point. Both are legible in a sentence and **neither is what the
data would have chosen**, which is the checkable version of "not tuned".

---

## Two things the gates caught in my own new code

**JJ01 refused the loader.** `normalization/loader.py` read
`Review.objects.filter(...)` — the exact form D-01 calls the isolation bug. The
honest responses are "write a scoped accessor" or "put the module on the
allowlist"; the first is right, the second is a habit. **This project had already
written down a third option that is better than both** — a *sanctioned method
whose name says what it exposes*, as `public_review_counts` does. So
`Review.objects.for_cross_judge_analysis(event_id)` was added, sanctioned, and
documented; **the rule keeps applying to every other read in every other file.**

Its docstring says why the proof needs it, because "it needs everything" is the
sentence that has produced every scope bug in this project: *a variance
decomposition measures the variance BETWEEN judges, so scoping it to an actor is
a category error rather than a security decision — there is no actor, because the
unit of analysis is the panel.*

**And then the lint rule caught my own test for it.** A check cannot be phrased
with the thing it is checking for: the first two versions of
`test_the_accessor_is_still_filtered_to_the_one_event` reached for
`Review.objects` directly, and JJ01 refused both. The third creates a second event
and asks the sanctioned accessor about each — same property, no rule broken.

---

## The sabotage runs

| sabotage | red |
|---|---|
| remove the shrinkage (`severity = med`) | **3** |
| make `excess` absolute, so `below_noise` is always true | **3** |

The second is the most dangerous class of mutation in this project and it is
new: **not a wrong number, a conclusion that cannot be contradicted.** `excess`
is the *signed* distance from the noise floor and its sign IS the finding; taking
`abs()` makes "below the noise" unconditionally true, so a real severity effect
could never be reported. Both are now mutations with named detectors.

---

## What it cost

| | |
|---|---|
| Tests | 575 → **607** (32 in `tests/test_normalization.py`) |
| Mutations | 86 → **90** (4 new) |
| Findings | **F-92 [P1]** |
| Code | `normalization/{estimators,detectability,sensitivity,loader}.py`, one sanctioned accessor, one tool, one document |
