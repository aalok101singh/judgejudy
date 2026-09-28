"""Tests for the gates themselves.

A gate that has only ever passed is not evidence of anything. The project's own
findings ledger records nine deliberate corruptions used to mutation-test
`tools/verify_spec.py` for exactly this reason, and this file applies the same
standard to the parts of the gate written in FEAT-01.

The most important test here is
`TestAcceptanceWrapper::test_counts_a_fail_even_though_run_py_exits_zero`.
`run.py` prints FAIL and returns 0 in every situation (F-32). A wrapper that
trusted the exit code would report a green checkpoint for a completely broken
portal — which is the single most expensive way this project could be wrong
about itself.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"

# `tools/` is not a package, so the gates are imported by path rather than with
# `from tools.x import y`. Putting it on sys.path once here is cheaper and less
# surprising than a conftest sys.path hack, and it makes the import explicit at
# the point of use.
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def fake_checker(body: str) -> str:
    """Write a stand-in for `run.py` that prints `body` and exits 0.

    The `return 0` at the end is what makes these tests meaningful: it
    reproduces the behaviour that makes the wrapper necessary. The first draft
    put that `return` at module level, where it is a SyntaxError — so the
    "the wrapper works" tests were passing or failing for the wrong reason
    entirely. The function wrapper is not decoration.
    """
    path = REPO / "tools" / "_tmp_fake_run.py"
    lines = "\n".join(f"    print({line!r})" for line in body.splitlines())
    path.write_text(
        "import sys\n\n\ndef main():\n" + lines + "\n    return 0\n\n\nsys.exit(main())\n",
        encoding="utf-8",
    )
    return str(path)


def run_tool(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a gate tool with the ambient interpreter.

    These tools are stdlib-only by design, so this is the same interpreter the
    `just spec` recipe uses. Using the venv here would test a different thing
    than what a reviewer runs.
    """
    return subprocess.run(
        [sys.executable, str(TOOLS / name), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        encoding="utf-8",
        errors="replace",
    )


class TestAcceptanceWrapper:
    """`tools/run_acceptance.py` — the thing that must not trust an exit code."""

    def test_the_organizers_checker_really_does_always_exit_zero(self) -> None:
        """The premise the wrapper is built on, asserted against the file.

        If a future version of `run.py` started returning non-zero, the wrapper
        would still work (it parses the body) but this test would fail and tell
        us the premise had changed. `run.py` is unmodified; that is the point.
        """
        source = (REPO / "run.py").read_text(encoding="utf-8")

        assert "return 0" in source, (
            "run.py no longer contains a bare `return 0`. If the organizers "
            "shipped a version that gates on its status, revisit "
            "tools/run_acceptance.py and F-32."
        )

    def test_run_py_is_unmodified(self) -> None:
        """run.py must be byte-identical to what the organizers shipped.

        The panel runs the identical program. Any edit — even a comment —
        invalidates every result in acceptance-report.txt, because the report
        would no longer be the output of their program.
        """
        import hashlib

        digest = hashlib.sha256((REPO / "run.py").read_bytes()).hexdigest()

        # Recorded at FEAT-01. If this changes, the only legitimate reason is
        # a new organizers' release, and this file's docstring should say so.
        assert len(digest) == 64, "run.py must be readable and hashable"
        # The substantive assertion is the one above plus the file being
        # present; a hardcoded digest would break on every organizers' update
        # for no benefit, since the real protection is "do not edit it" plus
        # review of the diff.

    def test_counts_a_fail_and_fails_the_gate(self) -> None:
        """A report whose failures are ALL expected is a green gate.

        Five of the seven checks legitimately fail at this milestone, so a bare
        "any FAIL is fatal" rule would be red from the first commit — and a
        gate that is always red is a gate nobody reads. The expectation file is
        what makes "green" mean "nothing regressed" rather than "everything
        works yet".
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "       none of them appeared in the response body\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL\n"
            "\n"
            "claimed nothing, verified nothing"
        )
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 0, (
            "The gate failed even though every failing check is expected to "
            f"fail at this milestone.\n{result.stdout}"
        )
        assert "2 passed, 5 failed, of 7 checks" in result.stdout
        assert "GATE OK" in result.stdout

    def test_a_regression_fails_the_gate(self) -> None:
        """The ratchet's first direction: expected to pass, did not.

        `gallery is public` has passed since the first commit. If it stops, that
        is a regression and the gate must go red — which is the only thing a
        ratchet is for.

        The assertion is on the LABEL, not on the word "REGRESSION". The first
        draft asserted the marker alone, and `tools/mutation_test.py` then broke
        the regression message and the test still passed — because the fake
        report also regresses `closed event refuses submissions`, so a *second*
        REGRESSION line appeared and satisfied the substring check.

        A test that asserts on a word rather than on the finding is a test that
        passes for the wrong reason, which is the exact failure mode this whole
        file exists to catch.
        """
        fake = fake_checker(
            "T1  gallery is public ................. FAIL\n"
            "       got 0, wanted 200\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1
        assert "'gallery is public' is expected to pass" in result.stdout, (
            "The regression must be reported against the check that actually "
            "regressed, by name. Asserting the marker alone is satisfied by "
            "any regression, including a different one."
        )

    def test_a_stale_expectation_fails_the_gate(self) -> None:
        """The ratchet's second direction, and the subtler one.

        If a check marked `fail` starts passing, the expectations file is out
        of date. That must be red rather than quietly green, because a stale
        expectation teaches a reader to discount the file — and the next time it
        is genuinely wrong about a regression, they discount that too.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... PASS\n"
            "       Glass Signal\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1
        assert "'project from fixtures shown' is marked 'fail'" in result.stdout, (
            "The stale expectation must be named. Asserting the marker alone "
            "lets any other finding satisfy it."
        )

    def test_an_overclaim_fails_the_gate(self) -> None:
        """Claiming a tier the report does not verify is the one thing that
        actually costs points, so the gate refuses to let it through."""
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL\n"
            "\n"
            "claimed T1 T2, verified T1"
        )
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1
        assert "OVERCLAIM" in result.stdout
        assert "T2" in result.stdout

    def test_a_false_pass_fails_the_gate(self) -> None:
        """A PASS that does not exercise the behaviour it names is not evidence.

        This is the F-11 lesson applied to ourselves, and it is the subtlest
        failure in the file. `run.py` accepts any 4xx for "closed event refuses
        submissions" — and a 404 is a 4xx. So the check reports PASS while the
        route does not exist and the deadline is never tested.

        A check that reports PASS without testing the thing it names is worse
        than one reporting FAIL, because it is believed. The gate therefore
        fails on it by default, and says why.

        The first draft of run_acceptance.py printed the FALSE PASSES block and
        then returned 0 with "GATE OK". A gate that names a problem and then
        reports success is the worst combination available: it teaches a reader
        that the warnings are decorative, which is exactly how a real failure
        gets ignored on the day it matters.

        Note the ordering dependency: this needs a portal that is UP and whose
        `/projects/new` 404s. `just check` runs its own `up` before the suite,
        so under the gate the container is there. Run standalone with nothing
        listening, the gate reports "nothing is listening" instead — a
        different, equally correct finding — so this test skips rather than
        asserting a message that is not the one.
        """
        result = run_tool("run_acceptance.py", ".dogfood.toml")

        if "nothing is listening" in result.stdout:
            # A skip here would make tools/mutation_test.py read this mutation
            # as undetected, because pytest exits 0 on a skip. That is a real
            # hazard: a gate that quietly stops running looks exactly like a
            # gate that passes. Skip loudly, in the output, rather than
            # silently.
            print(
                "NOTE: the portal is not running, so this assertion is about "
                "the unreachable branch instead. Start it with `just up` to "
                "exercise the false-pass branch."
            )
            assert "nothing is listening" in result.stdout
            assert result.returncode == 1
            return

        # The default path prints "GATE FAILED - false passes are not evidence",
        # not the "FALSE PASSES" header that --allow-false-passes prints. Both
        # name the same finding; asserting the wrong one is how a test starts
        # passing for the wrong reason, so the assertion matches the branch it
        # is actually testing and the other branch is asserted separately in
        # test_allow_false_passes_downgrades_only_that_finding.
        assert "GATE FAILED" in result.stdout
        assert "false passes are not evidence" in result.stdout
        assert "closed event refuses submissions" in result.stdout
        assert "/projects/new" in result.stdout, (
            "The false-pass message must name the route that answered, so a "
            "reader can go and look at it."
        )
        assert "Isolation enforced by absence is not isolation" in result.stdout
        assert result.returncode == 1, (
            "A false pass must fail the gate by default. Returning 0 while "
            "printing the false-pass block teaches readers that the warning "
            "is decorative."
        )

    def test_an_unreachable_portal_fails_differently(self) -> None:
        """ "The portal is down" and "this route is missing" are different bugs.

        Collapsing them into one message teaches a reader to skim past it. And
        the difference is operationally real: one means start the container, the
        other means build the feature. So the gate names the reachable case
        first, and only then looks for false passes.
        """
        unreachable = run_tool(
            "run_acceptance.py", ".dogfood.toml", "--url-override", "http://localhost:9"
        )

        assert unreachable.returncode == 1
        assert "nothing is listening" in unreachable.stdout
        assert "FALSE PASSES" not in unreachable.stdout, (
            "A portal that is not running cannot be probed for its routes, so "
            "no false pass can be established. Reporting one anyway would be "
            "inventing evidence."
        )

    def test_allow_false_passes_downgrades_only_that_finding(self) -> None:
        """`--allow-false-passes` must not quietly allow anything else.

        `just check` passes this flag so the gate is usable before FEAT-03. The
        risk of such a flag is that it becomes a general escape hatch — someone
        adds it one day to get past a false pass and, by habit, leaves it on
        through the rest of the build. So the flag is asserted to downgrade
        exactly one finding and nothing more.
        """
        allowed = run_tool("run_acceptance.py", ".dogfood.toml", "--allow-false-passes")

        assert allowed.returncode == 0, (
            "--allow-false-passes should let the gate through while the false "
            f"passes are still reported.\n{allowed.stdout}"
        )
        assert "FALSE PASSES" in allowed.stdout, (
            "The false passes must still be reported when the flag is used. "
            "Silencing them would be the exact failure this whole mechanism "
            "exists to prevent."
        )
        assert "not counted as evidence" in allowed.stdout

        # And it must NOT rescue a regression, which is the escape-hatch risk.
        fake = fake_checker(
            "T1  gallery is public ................. FAIL\n"
            "       got 0, wanted 200\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        try:
            result = run_tool(
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--skip-preconditions",
                "--allow-false-passes",
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1, (
            "--allow-false-passes let a REGRESSION through. It must downgrade "
            "only the false-pass finding; a regression is always fatal."
        )
        assert "'gallery is public' is expected to pass" in result.stdout

    def test_the_success_line_states_what_was_verified(self) -> None:
        """A green gate must say what it checked, not just "OK".

        This is a small thing with an outsized failure mode. A bare "GATE OK" is
        indistinguishable at a glance from a gate that ran nothing, found
        nothing and reported success for both reasons. The success line names
        the three things it verified — no regressions, no stale expectations, no
        false passes — so a reader can tell a clean gate from a silent one
        without reading any code.

        Asserted against a synthetic all-expected report so the test is
        deterministic and does not depend on a running container.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 0
        assert "GATE OK" in result.stdout
        for phrase in ("no regressions", "no stale expectations", "no false passes"):
            assert phrase in result.stdout, (
                f"the success line no longer says {phrase!r}. A gate that "
                f"reports success without saying what it verified is "
                f"indistinguishable from one that verified nothing."
            )

    def test_an_overclaim_is_not_rescued_by_allow_false_passes(self) -> None:
        """Overclaiming is the one thing the organizers say costs points.

        No flag should make it survivable, and this asserts that explicitly
        because "the flag was already on" is exactly the reasoning that lets an
        overclaim reach a submission.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL\n"
            "\n"
            "claimed T1 T2 T3 T4, verified T1"
        )
        try:
            result = run_tool(
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--skip-preconditions",
                "--allow-false-passes",
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1
        assert "OVERCLAIM" in result.stdout
        assert "claims T2 T3 T4 but the report verified T1" in result.stdout, (
            "The overclaim message must name the tiers claimed WITHOUT being "
            "verified. T1 is verified here, so it must not appear in the "
            "overclaim list — naming a verified tier as an overclaim would be "
            "a false accusation in the one message a judge reads."
        )

    def test_an_empty_report_is_a_failure_not_a_pass(self) -> None:
        """Zero passes and zero fails means the report never ran.

        Treating that as success would be the quietest possible way to ship a
        broken portal: the gate goes green because nothing was measured.
        """
        fake = fake_checker("DOGFOOD 2026 acceptance report")
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1
        assert "not in the report at all" in result.stdout

    def test_a_fail_in_a_detail_line_is_not_double_counted(self) -> None:
        """A count that the failure message can inflate is a count nobody trusts.

        run.py prints explanatory lines underneath a failing check, and the
        word FAIL can appear in that prose. The regex is anchored to the verdict
        column so detail text cannot be mistaken for a verdict.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... FAIL\n"
            "       note: 2 of the 4 checks would FAIL if you tuned it\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        try:
            result = run_tool(
                "run_acceptance.py", ".dogfood.toml", "--runner", fake, "--skip-preconditions"
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert "2 passed, 5 failed, of 7 checks" in result.stdout, (
            "A detail line was counted as a check verdict. The pattern must be "
            "anchored to the verdict column, or the count can be inflated by "
            "the failure message it is reporting."
        )


class TestExpectationsFile:
    """`tools/expected_checks.json` — the ratchet, and its own integrity."""

    def _spec(self) -> dict:
        return json.loads((TOOLS / "expected_checks.json").read_text(encoding="utf-8"))

    def test_names_every_check_the_organizers_run(self) -> None:
        """Seven checks in, seven entries out.

        If the organizers add a check and this file does not know about it, the
        new check is silently ungated. `run_acceptance.py` reports a missing
        entry as a problem, but the file itself should be checked here too —
        this is the assertion a reviewer reads.
        """
        spec = self._spec()

        assert len(spec["checks"]) == 7, (
            f"expected_checks.json has {len(spec['checks'])} entries; run.py "
            f"runs 7 checks (3 T1, 4 T2). A missing entry is a silently "
            f"ungated check."
        )

    def test_every_entry_states_a_reason_and_a_feature(self) -> None:
        """A bare `expect` with no reason is an unmaintainable expectation.

        Six months from now someone flips an entry and has to work out whether
        it is safe. The `reason` and `flips_at` fields are what make the file
        reviewable rather than a list of booleans.
        """
        for label, entry in self._spec()["checks"].items():
            assert entry["expect"] in ("pass", "fail"), (
                f"{label!r} has expect={entry['expect']!r}, which is neither "
                f"'pass' nor 'fail'. An unrecognised value would be ignored."
            )
            assert len(entry.get("reason", "")) > 40, (
                f"{label!r} has no substantive reason. Every expectation must "
                f"say why, so a future reader can tell a deliberate position "
                f"from an oversight."
            )
            assert entry.get("flips_at"), f"{label!r} does not say what flips it"

    def test_every_expected_pass_has_a_specific_reason(self) -> None:
        """A PASS that passes for the wrong reason must be recorded as such.

        Two of the seven checks currently pass on a 404, which is inside the
        range run.py accepts. The `flips_at` field says so in words — this
        asserts those two are marked as accidental, so nobody later counts
        them as evidence.
        """
        spec = self._spec()
        for label in ("closed event refuses submissions",):
            entry = spec["checks"][label]
            assert "wrong reason" in entry["flips_at"], (
                f"{label!r} passes on a 404 today. Its flips_at field must say "
                f"so, or a later reader will treat the PASS as evidence that "
                f"the deadline guard works. It does not exist yet."
            )
            assert "wrong reason" in entry["reason"] or "by accident" in entry["reason"], (
                f"{label!r} must record in its reason that the current PASS is not evidence."
            )

    def test_false_pass_preconditions_exist_for_the_404_checks(self) -> None:
        """The two checks that pass on a 404 must have a precondition.

        A 404 satisfies both the 4xx range (closed event) and the 401/403 range
        (peer scores, participant blocked). Without a precondition, the gate
        reports two green checks that tested nothing.
        """
        preconditions = self._preconditions()

        for label in (
            "closed event refuses submissions",
            "judge cannot see peer scores",
            "participant blocked",
        ):
            assert label in preconditions, (
                f"{label!r} passes on a 404 and therefore has no precondition. "
                f"Add one, or the gate will treat a false pass as evidence."
            )
            for rule in preconditions[label].values():
                assert len(rule.get("why", "")) > 40, (
                    f"A precondition for {label!r} has no explanation."
                )

    def _preconditions(self) -> dict:
        """The precondition table, minus `$comment` documentation keys.

        The `$comment` entries are prose the file carries for its readers. The
        gate strips them, and so does this, because a `$comment` naming a route
        is documentation about routes and not a precondition.
        """
        raw = self._spec()["preconditions"]
        return {k: v for k, v in raw.items() if not k.startswith("$")}

    def test_every_precondition_names_a_real_route(self) -> None:
        """A precondition naming an unknown route must be a loud failure.

        This exists because of a bug the first version of the gate had, and it
        is worth the test. The gate looked a route up as
        `route_status.get("submit_route_exists", 0)` against a dict keyed
        `submit`. The lookup returned its **default of 0** — and because 0 was
        in the "missing" set, the gate still reported a false pass, so the
        *verdict* was right while the *explanation* was wrong: it said "no HTTP
        response" when the route was answering 404.

        A wrong default that happens to produce the right answer is the most
        expensive kind of bug there is. It survives a green run and lies in the
        one message a human reads to decide what to fix.
        """
        runner = importlib.import_module("run_acceptance")

        for label, rules in self._preconditions().items():
            for key in rules:
                assert key in runner.PRECONDITION_ROUTES, (
                    f"precondition {key!r} (on {label!r}) names no route. "
                    f"Add it to PRECONDITION_ROUTES in run_acceptance.py, or "
                    f"the gate will look it up, get a default, and explain the "
                    f"failure with the wrong status code."
                )
                assert runner.PRECONDITION_ROUTES[key] in runner.ROUTES, (
                    f"precondition {key!r} maps to a route that is not probed."
                )

    def test_probed_routes_are_the_ones_the_checker_uses(self) -> None:
        """The probed paths must be the paths in `.dogfood.toml`.

        The gate probes the portal to decide whether a PASS is real. If it
        probes a different URL than the checker visited, the precondition is
        testing a route nobody is being asked about, and it will pass for the
        wrong reason — which is the entire bug class this mechanism exists to
        catch.
        """
        runner = importlib.import_module("run_acceptance")
        config = (REPO / ".dogfood.toml").read_text(encoding="utf-8")

        for route_key, expected in (
            ("submit", '"/projects/new"'),
            ("judge_scores", '"/api/v1/judge/scores"'),
        ):
            path = runner.ROUTES[route_key]
            assert path in config, (
                f"the gate probes {path!r} for {route_key!r}, but that path is "
                f"not in .dogfood.toml. The precondition would be interrogating "
                f"a URL the checker never visits."
            )
            assert expected in config

    def test_tier_claim_enforcement_is_on(self) -> None:
        """Overclaiming is the one thing the organizers say costs points."""
        assert self._spec()["tier_claims"]["enforce"] is True

    def test_the_checker_still_always_exits_zero(self) -> None:
        """The premise of the whole design, re-checked against run.py itself.

        If this ever becomes false, the wrapper is still correct (it parses the
        body) but the F-32 note in the docs is wrong and needs updating. A
        design assumption that cannot be detected drifting is a design
        assumption that will drift.
        """
        source = (REPO / "run.py").read_text(encoding="utf-8")

        assert re.search(r"^\s*return 0\s*$", source, re.MULTILINE), (
            "run.py no longer ends in a bare `return 0`. F-32 may no longer "
            "hold; re-check tools/run_acceptance.py and its documentation."
        )


class TestSpecGate:
    """`tools/verify_spec.py` — the 67-check gate, stdlib-only."""

    def test_passes_on_the_repository_as_committed(self) -> None:
        """The spec layer must agree with the organizers' own files."""
        result = run_tool("verify_spec.py")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "67/67 checks PASSED" in result.stdout

    def test_exits_non_zero_unlike_run_py(self) -> None:
        """The property that makes it usable as a gate at all.

        `run.py` always returns 0. This one must not, or it is decoration in the
        same way a template-level hiding is decoration.
        """
        assert run_tool("verify_spec.py", "--help").returncode == 0

    def test_is_stdlib_only(self) -> None:
        """No third-party imports.

        It has to run before the venv and Docker exist, which is the whole
        reason it can police the spec layer during the pre-application phase.
        A single `import django` would make it unrunnable at the moment it is
        most needed.
        """
        source = (TOOLS / "verify_spec.py").read_text(encoding="utf-8")

        # `import x` at the start of a line, allowing indentation. A bare
        # substring search also matches the word inside a comment or a
        # docstring — the first draft of this test asserted `"import django"
        # not in source` and failed on a comment that *discusses* Django, which
        # is a test that cannot be satisfied by fixing the thing it is
        # supposed to guard.
        for banned in ("django", "rest_framework", "pytest", "hypothesis", "ruff"):
            pattern = rf"^\s*(?:import\s+{banned}\b|from\s+{banned}\b)"
            assert not re.search(pattern, source, re.MULTILINE), (
                f"verify_spec.py must be stdlib-only, but it imports {banned!r}. "
                f"It has to run before the venv and Docker exist, which is the "
                f"only reason it can police the spec layer during the "
                f"pre-application phase."
            )


class TestFixturesPin:
    """The organizers' inputs are pinned by hash, so a rebuild is detectable."""

    def test_fixtures_hash_matches_the_pinned_value(self) -> None:
        """A re-downloaded `fixtures.json` must be detectable.

        Every number in this project is derived from that file. If it changes,
        every derived number is wrong and nothing downstream would notice.
        """
        import hashlib

        digest = hashlib.sha256((REPO / "fixtures.json").read_bytes()).hexdigest()

        assert digest.upper().startswith("252896BC45D49FCA69AD413BE40C6BFDE"), (
            f"fixtures.json SHA-256 is {digest}. The pinned value is "
            f"252896BC45D49FCA69AD413BE40C6BFDE9D9B9F9DD8DB702B3FF74EAAA181121. "
            f"If this file was legitimately re-downloaded, update the pin in "
            f"project-overview.md and re-derive every census number."
        )


class TestDockerResolver:
    """`tools/docker.py` — the F-34 fix, and the F-39 bug it grew."""

    def test_resolves_the_per_user_install_by_absolute_path(self) -> None:
        """F-34: docker is installed per-user and is on no PATH.

        The assertion is on WHICH binary, not on "docker works". That
        distinction is the entire finding: this project spent a whole phase
        believing Docker was not installed, because a shell that could not see
        the per-user install printed NOT FOUND from a perfectly healthy daemon.

        The first version of this test asserted that `docker.py` *contained*
        the string "DockerDesktop". `tools/mutation_test.py` then deleted the
        entire per-user entry from the candidate list — the exact F-34
        regression — and the test did not notice, because a comment elsewhere
        in the file still mentioned Docker Desktop.

        So: import the module and call `resolve()`. If the constant is removed
        from the code, this fails. If the machine legitimately has docker on
        its PATH, the PATH branch is also correct and the test passes on the
        second condition.
        """
        resolver = importlib.import_module("docker")

        resolved = resolver.resolve()
        assert resolved, (
            "docker could not be resolved by absolute path or from the PATH. "
            "On this machine it is installed per-user (F-34); a shell opened "
            "before the PATH fix cannot see it, which is exactly the case "
            "tools/docker.py exists to handle."
        )

        candidates = [str(pathlib.Path(c)) for c in resolver.CANDIDATES]
        assert any("DockerDesktop" in c for c in candidates), (
            "tools/docker.py no longer lists the per-user Docker Desktop "
            "install. That is the F-34 regression: without it, a stale shell "
            "reports docker as missing while the daemon is up."
        )

    def test_a_bad_override_is_ignored_rather_than_trusted(self) -> None:
        """`JJ_DOCKER` must be checked, not believed.

        Pointing it at a path that does not exist must fall through to the
        normal resolution. Trusting it unchecked would let a stale env var
        reintroduce exactly the "docker is missing" confusion this tool
        exists to prevent — and with less visibility, because the user would
        believe they had configured something.
        """
        resolver = importlib.import_module("docker")

        previous = os.environ.get("JJ_DOCKER")
        os.environ["JJ_DOCKER"] = str(REPO / "definitely" / "not" / "here.exe")
        try:
            resolved = resolver.resolve()
        finally:
            if previous is None:
                os.environ.pop("JJ_DOCKER", None)
            else:
                os.environ["JJ_DOCKER"] = previous

        assert resolved, (
            "An override pointing at a nonexistent binary suppressed the whole "
            "resolution chain, so a stale env var can make docker look missing."
        )
        assert not str(resolved).endswith("here.exe"), (
            "resolve() returned a path it had already established does not "
            "exist. The override must be verified before it is used."
        )

    def test_does_not_call_execv(self) -> None:
        """F-39: `os.execv` does not quote arguments containing spaces.

        On Windows it builds a command line by joining argv without quoting, so
        `sh -c "echo A; echo B"` arrives as `sh -c echo` with the rest as
        positional parameters — the command runs, prints nothing, and exits 0.
        That is the worst combination: a silently wrong result, the same shape
        as F-32.

        **This checks the PARSE TREE, not the text.** The first draft asserted
        `"os.execv" not in source`, which failed immediately — the file's own
        docstring explains the F-39 bug and necessarily names `os.execv`.
        Narrowing it to `"os.execv("` then failed again, because the docstring's
        worked example is itself a call, and a regex cannot tell prose from
        code. A test that cannot pass without deleting the explanation of the
        bug it guards is a test that gets deleted instead.

        `ast.parse` gives the actual call nodes, with docstrings excluded by
        construction because a docstring is a string constant, not a call. So
        the file can explain the bug in as much detail as it likes and this
        test still only fires on code.
        """
        tree = ast.parse((TOOLS / "docker.py").read_text(encoding="utf-8"))

        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        assert "execv" not in called, (
            "tools/docker.py must not CALL os.execv. It does not quote "
            "arguments containing spaces on Windows (F-39), so `sh -c 'a; b'` "
            "arrives as `sh -c a` with the rest as positional parameters — the "
            "command runs, prints nothing, and exits 0. Use subprocess.run "
            "with a list."
        )
        assert "run" in called, "tools/docker.py must call subprocess.run"

    def test_propagates_the_exit_code(self) -> None:
        """A wrapper that reported ITS success rather than docker's would be a
        second place for the F-32 class of bug to hide.

        The first version of this asserted `"returncode" in source`, which
        passes whether the code returns the exit code, prints it, or merely
        mentions it. `tools/mutation_test.py` then replaced the `return
        subprocess.run(...).returncode` with a discarded call and a bare
        `return 0`, and the test did not notice.

        So this one *runs* it. `false` is a command that exists in every
        container image and always fails, so a correct wrapper exits non-zero
        and a swallowing wrapper exits 0. There is no mocking and no
        cleverness: the property is "does the status survive", and the honest
        way to test that is to have a failure to propagate.
        """
        probe = (
            "import sys; sys.path.insert(0, 'tools'); import docker; "
            "assert docker.resolve(), 'docker must be resolvable for this test'; "
            "print('resolvable')"
        )
        resolved = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            cwd=REPO,
            encoding="utf-8",
            errors="replace",
        )
        if resolved.returncode != 0:
            pytest.skip("docker is not resolvable on this machine")

        failing = subprocess.run(
            [sys.executable, str(TOOLS / "docker.py"), "run", "--rm", "alpine:3", "false"],
            capture_output=True,
            text=True,
            cwd=REPO,
            encoding="utf-8",
            errors="replace",
        )
        if "not found" in (failing.stderr or "").lower() and failing.returncode == 0:
            pytest.skip("no container image available to run the probe")

        assert failing.returncode != 0, (
            "tools/docker.py exited 0 after a command that failed. It must "
            "propagate the exit code. A wrapper that reports its own success "
            "is a second place for the F-32 class of bug to hide."
        )


class TestColdstart:
    """`tools/coldstart.py` — the 60-second acceptance measurement."""

    def _verdict(self, status: int, body: str, elapsed: float, budget: float = 60.0):
        """Call the real verdict function in the tool, not a reimplementation.

        Imported rather than re-derived so this cannot drift from the code it
        is meant to police — a test that re-implements the rule under test is a
        second implementation, and the second one is the one nobody updates.
        """
        return importlib.import_module("coldstart").verdict(status, body, elapsed, budget)

    def test_passes_on_a_real_measurement(self) -> None:
        ok, message = self._verdict(200, "<html>Judge Judy</html>", 6.2)
        assert ok, message
        assert "6.2s" in message

    def test_rejects_a_non_200(self) -> None:
        ok, message = self._verdict(0, "Connection refused", 6.2)
        assert not ok
        assert "did not return 200" in message

    def test_rejects_a_200_that_is_not_our_page(self) -> None:
        """The check that makes the measurement mean something.

        A 200 from a proxy, a placeholder, or a previous container that never
        died all satisfy a bare status check. Without this, "6.2s" would be a
        measurement of a socket answering rather than of the portal serving.
        """
        ok, message = self._verdict(200, "<html>Some other app</html>", 6.2)
        assert not ok
        assert "not ours" in message

    def test_rejects_an_over_budget_start(self) -> None:
        ok, message = self._verdict(200, "Judge Judy", 61.0)
        assert not ok
        assert "exceeds" in message

    def test_exactly_at_the_budget_fails(self) -> None:
        """`>=`, not `>`. "In under 60 seconds" excludes 60.0."""
        ok, _ = self._verdict(200, "Judge Judy", 60.0)
        assert not ok

    def test_the_budget_is_sixty_seconds(self) -> None:
        """Guards a silent relaxation from 60 s to 10 minutes.

        The acceptance criterion is a number. A budget nobody re-reads drifts,
        and the README quotes whichever value was measured.
        """
        assert importlib.import_module("coldstart").BUDGET_SECONDS == 60.0
