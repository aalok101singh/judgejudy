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

import importlib
import json
import subprocess
import sys
from pathlib import Path

from tests import fake_http

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"

#: Imported rather than shelled out to, so the probe's decision function can be
#: called directly. `run_probe` and `judge_probe` are pure enough to test against
#: a stubbed `urlopen`, and testing them through the CLI would mean asserting on
#: a formatted report string -- which is F-41's shape.
sys.path.insert(0, str(TOOLS))
run_acceptance_module = importlib.import_module("run_acceptance")

GUARD = "assert_open_for_submission"
SPEC = {
    "method": "POST",
    "auth": "participant",
    "json": {"title": "dogfood-late-submission-probe", "summary": "probe"},
    "expect_status": "4xx",
    "body_must_contain": GUARD,
    "must_not_have_header": "Location",
}
CREDENTIAL = "Authorization: JJ1.deadbeef.who@example.org"
#: What ``run_probe`` is handed: the whole ``[auth]`` block, keyed as in the
#: config. Passing the bare string instead is the mistake this shape exists to
#: prevent -- ``run_probe`` looks the key up in it, and a string has no ``.get``.
AUTH_BLOCK = {"participant": CREDENTIAL}


def probe(answer, *, auth=AUTH_BLOCK, spec=None, raise_http_error=True, monkeypatch=None):
    """`(ok, why, recorder)` for one probe, against a stubbed `urlopen`."""
    spec = spec or SPEC
    recorder = fake_http.install(monkeypatch, answer, raise_http_error=raise_http_error)
    outcome = run_acceptance_module.run_probe("http://portal", "/projects/new", spec, auth)
    ok, why = run_acceptance_module.judge_probe(outcome, spec)
    return ok, why, recorder


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


def one_shot_server(routes: dict, default=None) -> tuple[str, object]:
    """Serve a fixed ``{path: (status, body, headers)}`` map on an ephemeral port.

    The false-pass tests used to interrogate whatever happened to be listening on
    8080, which meant they exercised the *previous* feature's container and
    failed for reasons that had nothing to do with the false pass. This is a few
    lines of stdlib, and it makes the most important behaviour of the acceptance
    gate -- "a PASS that does not test what it names fails the gate" --
    reproducible on a laptop with nothing running.

    ``"*"`` is the fallback entry, and it may carry a fourth element: a callable
    taking the request and returning ``(status, body, headers)``, for the probe
    tests that need to look at the request rather than serve a fixed answer.

    Returns ``(base_url, server)``. The caller shuts the server down.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.1 with an explicit Content-Length, so the connection is
        # reusable and the client always reads a complete response. The 1.0
        # default closes the socket immediately after the body, which on Windows
        # surfaces to urllib as WSAECONNABORTED (10053) roughly one run in six --
        # a failure that has nothing to do with the thing under test.
        protocol_version = "HTTP/1.1"

        def _respond(self):
            entry = routes.get(self.path.split("?")[0]) or routes.get("*") or (404, "", {})
            if len(entry) == 4:
                status, body, headers = entry[3](self)
            else:
                status, body, headers = entry
            raw = body.encode()
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        # `do_GET` and friends are the names `http.server` dispatches on.
        do_GET = do_POST = do_PUT = _respond  # noqa: N815

        def log_message(self, *args):  # a test does not need a log
            pass

    # ThreadingHTTPServer, not HTTPServer: a redirect makes urllib open a SECOND
    # connection while the first is still open, and a single-threaded server
    # answers that with ConnectionAbortedError on Windows. Which is a test that
    # fails for a reason that has nothing to do with what it is testing.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", server


def write_expectations(name: str, checks: dict, preconditions: dict) -> str:
    """A temporary expectations file, so a test can declare its own milestone.

    The real `tools/expected_checks.json` is a ratchet that only moves from
    ``fail`` to ``pass``, so it can never express a scenario the build has not
    reached yet. That is the point of it, and it is also why a test that wants a
    false pass has to bring its own file.
    """
    path = REPO / "tools" / f"_tmp_{name}.json"
    path.write_text(
        json.dumps(
            {
                "checks": {
                    key: {"expect": value, "reason": "test fixture", "flips_at": "test"}
                    for key, value in checks.items()
                },
                "preconditions": preconditions,
                "tier_claims": {"enforce": False},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(path)


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
            "T1  project from fixtures shown ....... PASS\n"
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
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--skip-preconditions",
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 0, (
            "The gate failed even though every failing check is expected to "
            f"fail at this milestone.\n{result.stdout}"
        )
        assert "3 passed, 4 failed, of 7 checks" in result.stdout
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
            "T1  project from fixtures shown ....... PASS\n"
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

        The stale check here is `csv export works`, which FEAT-05 still owns. It
        used to be `project from fixtures shown`, which FEAT-03 flipped to
        `pass`; using the flipped one would have made this test assert that the
        ratchet never moves, which is the opposite of what a ratchet is for.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... PASS\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. PASS"
        )
        try:
            result = run_tool(
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--skip-preconditions",
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert result.returncode == 1
        assert "'csv export works' is marked 'fail'" in result.stdout, (
            "The stale expectation must be named. Asserting the marker alone "
            "lets any other finding satisfy it."
        )

    def test_an_overclaim_fails_the_gate(self) -> None:
        """Claiming a tier the report does not verify is the one thing that
        actually costs points, so the gate refuses to let it through."""
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... PASS\n"
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
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--skip-preconditions",
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
        submissions" -- and a 404 is a 4xx -- so the check reports PASS while
        the route does not exist and the deadline is never tested. A check that
        reports PASS without testing the thing it names is worse than one
        reporting FAIL, because it is believed.

        The first draft of run_acceptance.py printed the FALSE PASSES block and
        then returned 0 with "GATE OK". A gate that names a problem and then
        reports success is the worst combination available: it teaches a reader
        that the warnings are decorative, which is exactly how a real failure
        gets ignored on the day it matters.

        **Hermetic, and it used not to be.** The first version pointed the
        probe at whatever was listening on 8080, so the test exercised the
        PREVIOUS feature's container and failed for a reason that had nothing
        to do with false passes. A one-shot server plus a temporary
        expectations file makes the scenario -- a route that answers 404, and a
        report that calls that a pass -- the thing under test.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... PASS\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        expectations = write_expectations(
            "false_pass",
            {
                "gallery is public": "pass",
                "project from fixtures shown": "pass",
                "closed event refuses submissions": "pass",
                "judge sees own scores": "fail",
                "judge cannot see peer scores": "fail",
                "participant blocked": "fail",
                "csv export works": "fail",
            },
            {
                "closed event refuses submissions": {
                    "submit_route_exists": {
                        "why": "a 404 is a 4xx, so the deadline is never consulted",
                        "flips_at": "test",
                    }
                }
            },
        )
        base, server = one_shot_server({"/": (200, "<html>gallery</html>", {})})
        try:
            result = run_tool(
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--expectations",
                expectations,
                "--url-override",
                base,
            )
        finally:
            server.shutdown()
            server.server_close()
            Path(fake).unlink(missing_ok=True)
            Path(expectations).unlink(missing_ok=True)

        assert "GATE FAILED" in result.stdout
        assert "false passes are not evidence" in result.stdout
        assert "closed event refuses submissions" in result.stdout
        assert "/projects/new" in result.stdout, (
            "The false-pass message must name the route that answered, so a "
            "reader can go and look at it."
        )
        assert "HTTP 404" in result.stdout, (
            "and it must name the STATUS that answered. F-42 was a correct "
            "verdict with a wrong explanation, which is worse than either."
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

        **Hermetic, and it has to be.** The first version of this test pointed
        `--url-override` at a dead port but let ``run.py`` run against whatever
        happened to be listening on 8080. Under `just check` that is the
        container the gate just built, so it worked; run standalone against a
        stale container it reported a REGRESSION instead and returned 1 for the
        wrong reason, and the test failed on a message that had nothing to do
        with reachability. A fake runner removes the dependency entirely.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... PASS\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        try:
            unreachable = run_tool(
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--url-override",
                "http://localhost:9",
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert unreachable.returncode == 1
        assert "nothing is listening" in unreachable.stdout
        assert "FALSE PASSES" not in unreachable.stdout, (
            "A portal that is not running cannot be probed for its routes, so "
            "no false pass can be established. Reporting one anyway would be "
            "inventing evidence."
        )

    def test_allow_false_passes_downgrades_only_that_finding(self) -> None:
        """`--allow-false-passes` must not quietly allow anything else.

        `just check` passed this flag from FEAT-01 until FEAT-03, when the false
        passes it was covering actually went away. The risk of such a flag is
        that it becomes a general escape hatch -- someone adds it one day to get
        past a false pass and, by habit, leaves it on through the rest of the
        build. So the flag is asserted to downgrade exactly one finding and
        nothing more, in both directions.

        Hermetic, for the same reason the false-pass test is: a live portal has
        no false passes left, so the flag would have nothing to downgrade and
        the test would pass vacuously.
        """
        fake = fake_checker(
            "T1  gallery is public ................. PASS\n"
            "T1  project from fixtures shown ....... PASS\n"
            "T1  closed event refuses submissions .. PASS\n"
            "T2  judge sees own scores ............. FAIL\n"
            "T2  judge cannot see peer scores ...... FAIL\n"
            "T2  participant blocked ............... FAIL\n"
            "T2  csv export works .................. FAIL"
        )
        expectations = write_expectations(
            "allow_false",
            {
                "gallery is public": "pass",
                "project from fixtures shown": "pass",
                "closed event refuses submissions": "pass",
                "judge sees own scores": "fail",
                "judge cannot see peer scores": "fail",
                "participant blocked": "fail",
                "csv export works": "fail",
            },
            {
                "closed event refuses submissions": {
                    "submit_route_exists": {
                        "why": "a 404 is a 4xx, so the deadline is never consulted",
                        "flips_at": "test",
                    }
                }
            },
        )
        base, server = one_shot_server({"/": (200, "<html>gallery</html>", {})})

        def gate(*extra: str):
            return run_tool(
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--expectations",
                expectations,
                "--url-override",
                base,
                *extra,
            )

        try:
            allowed = gate("--allow-false-passes")
            strict = gate()

            # And it must NOT rescue a regression, which is the escape-hatch risk.
            # Inside the same `try` because it reuses the temporary expectations
            # file, and a file cleaned up one block too early produces exit code
            # 2 -- "no such file" -- which is not the answer this test is about.
            regressing = fake_checker(
                "T1  gallery is public ................. FAIL\n"
                "       got 0, wanted 200\n"
                "T1  project from fixtures shown ....... PASS\n"
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
                    regressing,
                    "--expectations",
                    expectations,
                    "--url-override",
                    base,
                    "--allow-false-passes",
                )
            finally:
                Path(regressing).unlink(missing_ok=True)
        finally:
            server.shutdown()
            server.server_close()
            Path(fake).unlink(missing_ok=True)
            Path(expectations).unlink(missing_ok=True)

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
        assert strict.returncode == 1, (
            "and without the flag the same scenario must fail. If both pass, the "
            "flag is doing nothing, which is the state an escape hatch rots into."
        )
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
            "T1  project from fixtures shown ....... PASS\n"
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
            "T1  project from fixtures shown ....... PASS\n"
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
                "run_acceptance.py",
                ".dogfood.toml",
                "--runner",
                fake,
                "--skip-preconditions",
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
            "T1  project from fixtures shown ....... PASS\n"
            "       note: 2 of the 4 checks would FAIL if you tuned it\n"
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
            )
        finally:
            Path(fake).unlink(missing_ok=True)

        assert "3 passed, 4 failed, of 7 checks" in result.stdout, (
            "A detail line was counted as a check verdict. The pattern must be "
            "anchored to the verdict column, or the count can be inflated by "
            "the failure message it is reporting."
        )


class TestExpectationsFile:
    """`tools/expected_checks.json` — the ratchet, and its own integrity."""

    def test_tier_claim_enforcement_is_on(self) -> None:
        """Overclaiming is the one thing the organizers say costs points."""
        assert self._spec()["tier_claims"]["enforce"] is True

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

    def test_a_check_marked_pass_is_not_passing_for_the_wrong_reason(self) -> None:
        """A PASS that passes for the wrong reason must be recorded as such.

        This assertion **inverted in FEAT-03**, and the inversion is the point.
        Until then, `closed event refuses submissions` was expected to pass with
        `flips_at: "already passing, but for the wrong reason"`, because the
        route 404ed and 404 is a 4xx. FEAT-03 built the route and the guard, and
        a body probe now proves the refusal came from the guard -- so an entry
        still claiming a wrong-reason pass is a *stale* claim, and is now a
        failing test rather than a passing one.

        The rule is unchanged and now enforced in both directions: every check
        expected to pass must either be genuinely right or say in words that it
        is not yet evidence.
        """
        spec = self._spec()
        for label, entry in spec["checks"].items():
            if entry["expect"] != "pass":
                continue
            wrong_reason = "wrong reason" in entry["flips_at"] or "by accident" in entry["reason"]
            assert not wrong_reason or label in spec["preconditions"], (
                f"{label!r} is recorded as passing for the wrong reason but has no "
                "precondition that would catch it. A wrong-reason pass with no "
                "ratchet is just a green check nobody believes."
            )

    def test_the_deadline_check_names_the_guard_in_its_reason(self) -> None:
        """The strongest sentence in the file, and it has to stay in the file.

        `run.py` accepts any 4xx here. So the only thing that distinguishes "the
        deadline held" from "something else refused first" is the guard's name
        appearing in the response body, and the reason a reviewer reads has to
        say that is what is being checked.
        """
        entry = self._spec()["checks"]["closed event refuses submissions"]

        assert entry["expect"] == "pass"
        assert "assert_open_for_submission" in entry["reason"]
        assert "FEAT-03" in entry["flips_at"]

    def test_a_probe_precondition_exists_for_the_deadline_check(self) -> None:
        """`submit_route_exists` alone is not enough, and the reason matters.

        A route that exists and is refused by CSRF, by a 401 or by an emptied
        `[auth]` block satisfies the checker's "any 4xx" exactly as well as a
        404 does. The route-existence precondition cannot see that; the body
        probe can, and it is the only thing in the repository that can.
        """
        rules = self._preconditions()["closed event refuses submissions"]

        assert "submit_route_exists" in rules
        probe_rules = [r for r in rules.values() if r.get("probe")]
        assert len(probe_rules) == 1, "exactly one probe, or the gate is guessing"
        probe = probe_rules[0]["probe"]
        assert probe["body_must_contain"] == "assert_open_for_submission"
        assert probe["auth"] == "participant", (
            "the probe must present the SAME credential run.py used, read out of "
            "the same .dogfood.toml -- otherwise it is testing a different request"
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
        """An unmapped precondition key is a broken precondition.

        The original defect (F-42) was the reverse: a key that *was* mapped by
        accident, through a dict lookup that returned a default of 0 and
        therefore produced the right verdict for the wrong reason. So both
        directions are asserted — the key resolves, and the route it resolves to
        is one the checker actually visits.
        """
        spec = json.loads((TOOLS / "expected_checks.json").read_text(encoding="utf-8"))
        rules = {k: v for k, v in spec.get("preconditions", {}).items() if not k.startswith("$")}

        checked = 0
        for label, entries in rules.items():
            for key, _rule in entries.items():
                assert key in run_acceptance_module.PRECONDITION_ROUTES, (
                    f"precondition {key!r} for {label!r} names no route. A key that "
                    "resolves to nothing is F-42 again."
                )
                route = run_acceptance_module.PRECONDITION_ROUTES[key]
                assert route in run_acceptance_module.ROUTES, route
                checked += 1
        assert checked >= 3, f"only {checked} preconditions are declared"

    def test_every_probe_carries_a_marker_and_a_method(self) -> None:
        """A probe with no marker is a status check wearing a probe's clothes.

        `run.py` already does the status check. The entire value of a probe is
        that it asserts on the response BODY, so a probe without
        `body_must_contain` is a precondition that says nothing the checker did
        not already say — and it would read as though something more were being
        verified.
        """
        spec = json.loads((TOOLS / "expected_checks.json").read_text(encoding="utf-8"))
        rules = {k: v for k, v in spec.get("preconditions", {}).items() if not k.startswith("$")}

        probes = [
            (label, key, rule)
            for label, entries in rules.items()
            for key, rule in entries.items()
            if rule.get("probe")
        ]
        assert probes, "the body probe was added in FEAT-03 and must still be declared"

        for label, key, rule in probes:
            probe = rule["probe"]
            assert probe.get("body_must_contain"), f"{label}/{key} probes nothing"
            assert probe.get("method", "").upper() in run_acceptance_module.PROBE_METHODS
            assert probe.get("expect_status"), f"{label}/{key} does not say what it wants"
            assert rule.get("why"), f"{label}/{key} has no reason a reviewer can read"


class TestTheDeadlineProbe:
    """FEAT-03's addition: a precondition that can tell a refusal from a refusal.

    Before this, the gate knew only whether `/projects/new` existed. That made
    F-40 disappear *mechanically* when the route was built -- and mechanically
    is not the same as genuinely, because `run.py` accepts any 4xx: a CSRF
    rejection, a 401 for an unrecognised credential, and an emptied `[auth]`
    block all report PASS.

    These drive `run_probe` and `judge_probe` against a stubbed `urlopen` rather
    than a real socket. The stub is faithful -- it raises `HTTPError` for a 4xx
    exactly as `urlopen` does, and it records the request -- so the code under
    test is the real code. The socket is gone because a Windows `http.server`
    aborts about one connection in six for reasons of its own, and a test that
    fails one run in six for its own infrastructure is one people learn to
    re-run.
    """

    def test_a_guard_refusal_passes_the_probe(self, monkeypatch):
        ok, why, _ = probe(
            (
                403,
                json.dumps({"refused_by": GUARD, "reason": "closed"}),
                {"Content-Type": "application/json"},
            ),
            monkeypatch=monkeypatch,
        )

        assert ok, why
        assert "naming" in why

    def test_a_csrf_refusal_is_caught(self, monkeypatch):
        """The F-11 trap, live: 403, an HTML body, and not the deadline."""
        ok, why, _ = probe(
            (
                403,
                "<h1>Forbidden</h1><p>CSRF verification failed.</p>",
                {"Content-Type": "text/html"},
            ),
            monkeypatch=monkeypatch,
        )

        assert not ok
        assert "did not come from the mechanism" in why
        assert "CSRF verification failed" in why, (
            "the message must quote what the portal actually said, or the reader has to go and look"
        )

    def test_a_404_is_caught(self, monkeypatch):
        ok, why, _ = probe((404, "<h1>Not Found</h1>", {}), monkeypatch=monkeypatch)

        assert not ok
        assert "answered HTTP 404" in why

    def test_a_401_is_caught(self, monkeypatch):
        """What an emptied `[auth]` block produces: the request is anonymous."""
        ok, why, _ = probe(
            (401, json.dumps({"refused_by": "new_project"}), {"Content-Type": "application/json"}),
            monkeypatch=monkeypatch,
        )

        assert not ok
        assert "answered HTTP 401" in why

    def test_a_200_is_caught(self, monkeypatch):
        """The redirect case's outcome: a refusal that arrives as a page."""
        ok, why, _ = probe((200, "<html>sign in</html>", {}), monkeypatch=monkeypatch)

        assert not ok
        assert "answered HTTP 200, wanted 4xx" in why

    def test_a_redirect_header_is_caught(self, monkeypatch):
        """D-02, stated as a property rather than as a status.

        `must_not_have_header` is the check that survives a portal which starts
        refusing with a 302: the status is a 4xx-adjacent success and the header
        is the whole tell.
        """
        ok, why, _ = probe(
            (403, json.dumps({"refused_by": GUARD}), {"Location": "/login/"}),
            monkeypatch=monkeypatch,
        )

        assert not ok
        assert "follows" in why and "Location" in why

    def test_an_emptied_auth_block_is_caught_before_a_request_is_sent(self, monkeypatch):
        """A stale `.dogfood.toml` must not be papered over with a default.

        This is the branch that matters most in practice: someone empties an
        `[auth]` value to tidy up a report, the checker's request becomes
        anonymous, and the check still passes on the resulting 401.
        """
        ok, why, recorder = probe(
            (403, "{}", {}), auth={"participant": ""}, monkeypatch=monkeypatch
        )

        assert not ok
        assert "is empty in the config" in why
        assert "none of them is the deadline" in why
        assert recorder.requests == [], (
            "no request may be sent without the credential the checker used, or "
            "the probe is testing something else"
        )

    def test_the_credential_is_actually_sent(self, monkeypatch):
        """A probe that dropped the header would pass against a portal that
        refuses everyone, which is the opposite of evidence."""
        _, _, recorder = probe(
            (403, json.dumps({"refused_by": GUARD}), {"Content-Type": "application/json"}),
            monkeypatch=monkeypatch,
        )
        sent = recorder.last

        assert sent.get_method() == "POST"
        assert sent.get_header("Authorization") == "JJ1.deadbeef.who@example.org", (
            f"the header was {sent.headers!r}. run.py splits the config value on "
            "the FIRST colon and attaches the remainder, so the token is the "
            "whole value -- not 'Authorization: JJ1...'."
        )
        assert sent.get_header("Content-type") == "application/json"
        assert json.loads(sent.data) == SPEC["json"], (
            "the probe must send the same body run.py sent, or it is testing a different request"
        )

    def test_a_dead_portal_is_reported_not_scored(self, monkeypatch):
        def explode(request):
            raise OSError("connection refused")

        ok, why, _ = probe(explode, raise_http_error=False, monkeypatch=monkeypatch)

        assert not ok
        assert "could not be probed" in why

    def test_an_unparseable_expectation_fails_rather_than_defaulting(self):
        """F-42's shape: a wrong value that happens to produce a passing result.

        `expect_status = "not a status"` must not be read as "close enough". A
        default here would re-create the exact defect the file was rewritten to
        remove.
        """
        assert run_acceptance_module._status_is("not a status", 403) is False
        assert run_acceptance_module._status_is("4xx", 403) is True
        assert run_acceptance_module._status_is("4xx", 200) is False
        assert run_acceptance_module._status_is("401/403", 403) is True
        assert run_acceptance_module._status_is("401/403", 200) is False
        assert run_acceptance_module._status_is("403", 403) is True

    def test_a_method_this_tool_will_not_send_is_refused(self, monkeypatch):
        ok, why, recorder = probe(
            (403, "{}"), spec={**SPEC, "method": "TRACE"}, monkeypatch=monkeypatch
        )

        assert not ok
        assert "is not one this tool will send" in why
        assert recorder.requests == []

    def test_the_declared_probe_matches_this_spec(self):
        """The expectations file and this module must agree on the marker.

        Two places naming the guard's function, and nothing tying them together,
        is how a rename leaves the gate quietly asserting a string the portal
        stopped returning -- and a gate that asserts a stale string is a gate
        that is always red or, worse, one somebody turns off.
        """
        expectations = json.loads(
            (REPO / "tools" / "expected_checks.json").read_text(encoding="utf-8")
        )
        rules = {
            key: value
            for label, entries in expectations["preconditions"].items()
            if not label.startswith("$")
            for key, value in entries.items()
        }
        probes = [rule["probe"] for rule in rules.values() if rule.get("probe")]

        assert len(probes) == 1
        assert probes[0]["body_must_contain"] == GUARD == SPEC["body_must_contain"]
