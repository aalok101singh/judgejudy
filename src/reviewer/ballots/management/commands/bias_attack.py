"""``manage.py bias_attack`` -- run the position-bias harness and print the verdict.

**This is the acceptance line for FEAT-06's first clause** ("a bias-attack harness
shows the estimator is zero-mean under position bias"), and it is a command rather
than a function only the suite calls for the reason `influence_report` is: a
harness that only ever runs under pytest is a claim about a number, and a panelist
with the repository and a container should be able to run it and watch the claim
fail if the code is wrong.

**The table leads with the control, not the result.** The first thing printed is the
arm with no position bias in it, and it is an **exact** comparison: the same
population scored under all three orders must be bit-identical. A harness that
cannot show *when it does not fire* cannot be believed when it does -- which is
F-77's lesson reached from a third direction, after a test that could not fail and
a fixture whose control was itself a brigade.

**The first version of that control asserted "near zero" and read ``+0.051``, and
the command refused to pass.** The number was the reference's own sampling noise,
not the order's influence: the reference is a different ensemble of populations.
Asserting a magnitude the test cannot resolve is the same defect as a tunable
constant with a decimal point, so the control became a boolean.

**The last two lines are the sentence the whole feature exists to earn.** The mean
spans zero and the spread does not. That is zero-*mean*, not zero, and printing
only the interval would let a reader take the claim to be stronger than it is.
The caveat travels with the output for the same reason the influence report's does:
a person skimming a table does not read docstrings.

**The power table is printed too, and it is generated.** `bible/06` §6.3's version
of this table does not reproduce from the formula it names (F-78); these numbers
are computed by `comparisons_required` on every run, so they cannot rot, and the
conclusion -- a real panel of 100-1,000 comparisons cannot resolve a 5-point side
preference -- is the reason the harness is synthetic rather than run against
`fixtures.json`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviewer.ballots import bias_attack as harness_module


class Command(BaseCommand):
    """Print the bias-attack harness: control, attack, and the zero-mean claim."""

    help = "Run the position-bias harness (zero-mean under randomised order, D-12)."

    def add_arguments(self, parser):
        parser.add_argument("--voters", type=int, default=400)
        parser.add_argument("--replications", type=int, default=400)
        parser.add_argument("--beta", type=float, default=0.30)

    def handle(self, *args, **options):
        report = harness_module.harness(
            n_voters=options["voters"],
            replications=options["replications"],
            beta=options["beta"],
        )
        if report["population"]["voters"] < report["population"]["projects"]:
            raise CommandError(
                f"a balanced order needs at least one full cycle of voters: "
                f"{report['population']['voters']} voters for "
                f"{report['population']['projects']} projects cannot place every "
                f"project in slot 1 equally often, so the null would not be a null"
            )

        pop = report["population"]
        self.stdout.write("=" * 78)
        self.stdout.write(" BIAS-ATTACK HARNESS -- is randomised order zero-MEAN?")
        self.stdout.write("=" * 78)
        self.stdout.write(f"  model    {report['model']}")
        self.stdout.write(
            f"  {pop['projects']} projects, {pop['voters']} voters, "
            f"{pop['replications']} replications, beta={pop['beta']}, "
            f"quality spread {pop['quality_spread']}"
        )
        self.stdout.write(
            f"  pinned   projects {pop['pinned_projects']} -- the best and a reachable "
            f"contender, so a harness that merely helps the winner cannot pass"
        )
        self.stdout.write("")

        control = report["control"]
        self.stdout.write("  CONTROL -- no position bias in the population at all:")
        self.stdout.write("    the same population, scored under all three orders:")
        self.stdout.write(f"    max difference across orders = {control['max_difference']:g}")
        self.stdout.write("    (must be exactly 0 -- the order is still generated and")
        self.stdout.write("     every ballot is still cast through it; the voters simply")
        self.stdout.write("     do not consult it)")
        self.stdout.write("")

        pinned = pop["pinned_projects"]
        for target in pinned:
            self.stdout.write(f"  pinned project #{target}:")
            header = f"    {'design':<11} {'drift mean':>11} {'95% CI':>21} {'sd':>8}  verdict"
            self.stdout.write(header)
            self.stdout.write("    " + "-" * (len(header) + 2))
            for design in ("fixed", "randomised", "balanced"):
                arm = report["arms"][design][str(target)]
                ci = arm["ci"]
                verdict = "spans zero" if arm["spans_zero"] else "EXCLUDES zero"
                self.stdout.write(
                    f"    {design:<11} {_fmt(arm['mean']):>11} "
                    f"{f'[{ci[0]:+.2f}, {ci[1]:+.2f}]':>21} {_fmt(arm['sd']):>8}  {verdict}"
                )
            self.stdout.write("")

        for design, role in report["designs"].items():
            self.stdout.write(f"  {design:<11} {role}")
        self.stdout.write("")

        self.stdout.write("  THE CLAIM, stated exactly (randomised order):")
        for target in pinned:
            arm = report["arms"]["randomised"][str(target)]
            worst = max(abs(arm["min"]), abs(arm["max"]))
            self.stdout.write(f"    project #{target}:")
            self.stdout.write(
                f"      mean drift = {_fmt(arm['mean'])} with a 95% CI of "
                f"[{arm['ci'][0]:+.2f}, {arm['ci'][1]:+.2f}] -- indistinguishable from 0"
            )
            self.stdout.write(
                f"      spread     = sd {_fmt(arm['sd'])}, range "
                f"[{arm['min']:+.1f}, {arm['max']:+.1f}] -- NOT zero"
            )
            self.stdout.write(
                f"      a single run moves it by up to {worst:.1f} points. Zero-MEAN, not zero."
            )
        self.stdout.write("")

        self.stdout.write("  what a real panel could measure (generated, not quoted):")
        self.stdout.write("    side preference   Cohen's h   comparisons needed")
        for key, row in report["power"].items():
            self.stdout.write(
                f"    P(slot 1)={key:<12}  h={row['cohens_h']:.4f}   "
                f"{row['comparisons_required']:>8,}"
            )
        self.stdout.write("    a real event has 100-1,000 comparisons, so it cannot")
        self.stdout.write("    resolve a 5-point side preference. Report the sample")
        self.stdout.write("    size, not a percentage the panel cannot defend.")
        self.stdout.write("")

        verdicts = report["verdicts"]
        self.stdout.write("  VERDICTS")
        for key, ok in verdicts.items():
            self.stdout.write(f"    {'PASS' if ok else 'FAIL'}  {key}")
        self.stdout.write("")

        for line in _wrap(report["interpretation"], 74):
            self.stdout.write(f"  {line}")

        if not all(verdicts.values()):
            raise CommandError(
                "the harness did not separate its arms: "
                + ", ".join(k for k, ok in verdicts.items() if not ok)
            )


def _fmt(value) -> str:
    """Three decimals, or an explicit dash. **Never `0` for `None`** -- F-13's rule,
    so a missing number cannot be read as a measured zero."""
    return "-" if value is None else f"{value:+.3f}"


def _wrap(text: str, width: int) -> list[str]:
    """Naive greedy wrap. Only ever applied to one constant, so it stays naive."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
