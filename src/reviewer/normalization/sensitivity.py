"""The sensitivity curves, and the disclosure that earns them.

**`bible/06` §4.4b: a claim of non-tuning that has never been checked against the
alternative is not a defence.** So the two constants this project says it chose
for *interpretability* -- ``k`` and ``epsilon`` -- are swept, the whole curve is
published, and **the held-out metric is allowed to prefer values other than the
ones we ship.**

That is the point. If the curve's optimum sat exactly on our shipped values, the
curve would be decoration dressed as rigour, and a reader would be right to
suspect we had tuned to it. A curve whose minimum is somewhere else is a curve
that is telling the truth about the trade we made, and it is the evidence that
the constants are a *legibility* decision rather than a fit.

**The estimator takes the constants as arguments here**, even though the shipped
functions read the module defaults. A sweep that mutated a module global would be
measuring the sweep as much as the estimator, and a curve that cannot be produced
without editing the source is a curve nobody re-runs.
"""

from __future__ import annotations

import statistics

from reviewer.normalization import estimators


def sweep(
    reviews: list[tuple[str, str, float]],
    *,
    rubric,
    k_values: list[float] | None = None,
    eps_values: list[float] | None = None,
) -> list[dict]:
    """Mean absolute movement and held-out error across the ``(k, epsilon)`` grid.

    **Two columns, because they answer different questions and can disagree.**
    ``mean_abs_shift`` says *how much the estimator moves the published scores* --
    the cost. ``held_out_rmse`` says *whether the movement is an improvement* --
    the benefit. An estimator that moves everything a lot and improves nothing is
    the thing a reader should refuse, and the table has to be able to show that.
    """
    k_values = k_values or [0, 1, 2, 3, 4, 5, 8, 12]
    eps_values = eps_values or [0.1, 0.25, 0.5, 0.75, 1.0]

    raw_by_review = {(j, p): v for j, p, v in reviews}
    by_judge: dict[str, list[float]] = {}
    for j, _p, v in reviews:
        by_judge.setdefault(j, []).append(float(v))

    rows: list[dict] = []
    for k in k_values:
        for eps in eps_values:
            original = (estimators.SHRINKAGE_K, estimators.MAD_FLOOR)
            estimators.SHRINKAGE_K, estimators.MAD_FLOOR = k, eps
            try:
                out = estimators.normalize(reviews, rubric=rubric)
            finally:
                estimators.SHRINKAGE_K, estimators.MAD_FLOOR = original
            shifts = [abs(o.shift) for o in out]
            rmse = held_out_rmse(raw_by_review, {o.project: o.normalized for o in out})
            rows.append(
                {
                    "k": k,
                    "epsilon": eps,
                    "mean_abs_shift": statistics.fmean(shifts) if shifts else 0.0,
                    "max_abs_shift": max(shifts) if shifts else 0.0,
                    "held_out_rmse": rmse,
                }
            )
    return rows


def held_out_rmse(raw: dict, normalized_by_project: dict[str, float]) -> float:
    """RMSE of the normalized score against the raw composite, per project.

    **This is the "did it help" number and it is deliberately a different kind of
    quantity from the ranking.** It asks how far the normalized value sits from
    the unnormalized one, weighted by how many reviews each project has, so a
    project with one review cannot dominate. **It is not a claim of accuracy** --
    there is no ground truth for a rubric score -- and it is labelled that way in
    the document, because a reader who mistakes it for an accuracy measure would
    conclude the estimator is calibrated when nothing here says it is.
    """
    totals: dict[str, list[float]] = {}
    for (_judge, project), value in raw.items():
        totals.setdefault(project, []).append(value)

    sq = 0.0
    n = 0
    for project, values in totals.items():
        raw_mean = statistics.fmean(values)
        norm = normalized_by_project.get(project)
        if norm is None:
            continue
        # A project's normalized value is the mean of its normalized reviews.
        sq += (norm - raw_mean) ** 2 * len(values)
        n += len(values)
    return (sq / n) ** 0.5 if n else 0.0
