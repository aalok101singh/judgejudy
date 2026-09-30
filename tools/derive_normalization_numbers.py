"""Regenerate every number FEAT-08 publishes. Nothing in the docs is typed.

    just derive-normalization      # or, in the container:
    python manage.py shell < tools/derive_normalization_numbers.py

**This is the half of the guarantee that `tests/test_normalization.py` is not.**
The tests FREEZE the published figures so a refactor that changes the method
fails; this script PRODUCES them so a figure that was transcribed rather than
derived cannot survive a re-run.

**It exists because two of this project's published numbers did not regenerate**
(F-92), and the only way that is ever discovered is by re-deriving. The variance
decomposition reproduces `bible/06` §4.1b to four decimals. The **location
p-value reproduces only as a seed draw** -- 0.2266 at seed 0, and the published
0.234 sits inside the six-seed range -- so it is *correct* and merely
seed-dependent. The **dispersion p-value does not reproduce under either
permutation scheme** and the published 0.186 should be treated as wrong.

**Everything printed here is also asserted in CI**, so a drift between this
script and the tests is a failing test rather than a disagreement nobody
notices.
"""

from __future__ import annotations

import statistics

from reviewer.events.models import Event
from reviewer.normalization import detectability as detect
from reviewer.normalization import estimators as est
from reviewer.normalization import sensitivity as sens
from reviewer.normalization.loader import by_judge, composites
from reviewer.rubrics.models import Rubric


def main() -> None:
    event = Event.objects.get(pk="evt_01")
    rubric = Rubric.objects.filter(event=event).order_by("version").first()
    groups = by_judge(event)
    rows = composites(event)
    rule = "=" * 70

    print(rule)
    print("FEAT-08 - every published number, generated")
    print(rule)

    print("\n[1] ICC(1) VARIANCE DECOMPOSITION  (bible/06 4.1b)")
    vc = detect.variance_components(groups)
    for label, value in (
        ("grand mean", vc.grand_mean),
        ("n_bar (reviews per judge)", vc.n_bar),
        ("MSB  between-judge", vc.msb),
        ("MSW  within-judge", vc.msw),
        ("n0", vc.n0),
        ("between-judge variance", vc.between_variance),
        ("SAMPLING-NOISE FLOOR", vc.noise_floor),
        ("excess above floor", vc.excess),
        ("ICC(1)", vc.icc),
    ):
        print(f"  {label:<30} {value: .4f}")
    print(f"  {'N composites / judges':<30} {vc.n} / {vc.k}")
    print(f"  {'EFFECT BELOW THE NOISE?':<30} {vc.below_noise}")

    print("\n[2] PERMUTATION TESTS  (20000 draws, seeded)")
    loc = detect.permutation_p(groups, draws=20_000, seed=0)
    dis = detect.dispersion_p(groups, seed=0, draws=20_000)
    print(f"  location   p = {loc:.4f}   (bible/06 records 0.234 -- a legitimate seed draw)")
    print(f"  dispersion p = {dis:.4f}   (bible/06 records 0.186 -- DOES NOT REPRODUCE, F-92)")
    print(f"  Brown-Forsythe F = {detect.brown_forsythe_f(groups):.4f}  (bible/06 records 1.069)")

    print("\n[3] WHAT APPLYING THE ESTIMATOR COSTS")
    out = est.normalize(rows, rubric=rubric)
    shifts = [n.shift for n in out]
    print(f"  reviews normalized        {len(out)}")
    print(f"  mean |shift|              {statistics.fmean(abs(s) for s in shifts):.4f}")
    print(f"  max |shift|               {max(abs(s) for s in shifts):.4f}")
    print(f"  reviews changed at all    {sum(1 for s in shifts if abs(s) > 1e-9)}")
    print("  the largest movers:")
    for n in sorted(out, key=lambda n: -abs(n.shift))[:5]:
        why = "; ".join(n.reasons) or "no special case"
        print(f"    {n.project} {n.raw:.2f} -> {n.normalized:.2f} ({n.shift:+.3f})  [{why}]")

    print("\n[4] SENSITIVITY CURVES  (bible/06 4.4b - the non-tuning evidence)")
    grid = sens.sweep(rows, rubric=rubric)
    print(f"  {'k':>4} {'eps':>5} {'mean|shift|':>12} {'max|shift|':>11} {'held-out RMSE':>14}")
    for row in grid:
        mark = (
            "  <- SHIPPED" if (row["k"], row["epsilon"]) == (est.SHRINKAGE_K, est.MAD_FLOOR) else ""
        )
        print(
            f"  {row['k']:>4} {row['epsilon']:>5.2f} {row['mean_abs_shift']:>12.4f} "
            f"{row['max_abs_shift']:>11.4f} {row['held_out_rmse']:>14.4f}{mark}"
        )
    best = min(grid, key=lambda r: r["held_out_rmse"])
    shipped = next(r for r in grid if (r["k"], r["epsilon"]) == (est.SHRINKAGE_K, est.MAD_FLOOR))
    print(f"\n  the held-out metric's optimum is k={best['k']}, eps={best['epsilon']}")
    print(f"  we ship                       k={shipped['k']}, eps={shipped['epsilon']}")
    if (best["k"], best["epsilon"]) != (est.SHRINKAGE_K, est.MAD_FLOOR):
        print("  -> the curve does NOT peak on our values, which is the point:")
        print("     the constants are a legibility decision, and saying so is checkable.")
    print(rule)


main()
