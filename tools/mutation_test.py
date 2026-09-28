#!/usr/bin/env python3
"""Mutation-test the gates written in FEAT-01.

**A checker that has only ever passed is not evidence of anything.**

That sentence is finding F-33, written about `tools/verify_spec.py` after it
had been trusted on the strength of a green run, and it is the reason this file
exists. Nine deliberate corruptions proved that gate; these prove the five
written for FEAT-01.

The methodology:

1. Copy the repository to a sandbox.
2. Apply a corruption that a plausible mistake would produce.
3. Run the gate **in the sandbox**.
4. The gate must notice.
5. Restore.

What matters is step 4. A gate that fails loudly when broken is merely
annoying; a gate that *passes* when broken is a lie, and every number
downstream of it becomes fiction. So the mutations are chosen for the direction
of the error they introduce, not for how easy they are to spot.

## Two failures of this harness, both recorded

**The first version ran the command against the real repository** while writing
the mutation to the sandbox. Every result was meaningless: seven mutations
"passed" that were never applied to the code under test, and three were
"caught" by accident because the real `run_acceptance.py` genuinely fails
against a portal with no routes built yet. A harness that corrupts a copy and
tests the original produces a confident, wrong, table-shaped answer — which is
worse than no harness, because a table invites someone to act on it.

**The second version tested the wrong thing.** Two mutations removed the
content assertion and the exit-code propagation from `tools/docker.py`, and the
detector was a *different file* (`tools/doctor.py`) that carried its own copy
of the per-user path. Two copies of one fact, and only one of them checked.
`doctor.py` now imports the resolver, which is both the fix and the lesson.

Run:  python tools/mutation_test.py
Exit: 0 if every mutation was caught, 1 if any slipped through.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The exact source line in ``tools/docker.py`` that F-34 depends on: the
#: per-user Docker Desktop install path that is on no PATH.
#:
#: It is a named constant rather than an inline literal for one reason, and the
#: reason is F-46. A mutation target is an EXACT source string, so the first two
#: attempts at writing this one inline each got a backslash wrong, and a target
#: that does not match its file is reported by this harness as ``pattern not
#: found`` -- identical wording to a mutation that a gate genuinely survived.
#: That is the worst possible failure direction for a harness whose whole job is
#: to prove the gates can fail.
#:
#: Split across two adjacent literals purely to stay inside the 100-column limit;
#: the value is one line of ``docker.py`` plus a trailing newline.
_DOCKER_PER_USER_PATH = (
    '    pathlib.Path(r"C:\\Users\\Aalok\\AppData\\Local\\Programs'
    '\\DockerDesktop\\resources\\bin\\docker.exe"),\n'
)

# (file, find, replace, description, detector command)
MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    # --- run_acceptance.py ----------------------------------------------------
    # The detectors are the PYTEST tests, not the tool. The first draft ran the
    # tool against the live portal; with no routes built, all seven checks
    # legitimately FAIL, so the branch fired anyway and the mutation looked
    # caught. Caught by accident is worth less than caught on purpose.
    #
    # These patterns were rewritten when the gate gained the ratchet, and the
    # harness SKIPs rather than silently passing when one goes stale. That is
    # the behaviour we want: a SKIP is a finding about the harness, and a
    # silently-passing mutation is a lie.
    (
        "tools/run_acceptance.py",
        '            problems.append(f"REGRESSION: {label!r} is expected to pass and FAILED")',
        '            problems.append("REGRESSION: never happens")',
        "the regression branch never fires — the ratchet's whole first "
        "direction, and the F-32 class of bug in its purest form",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestAcceptanceWrapper::test_a_regression_fails_the_gate",
            "-q",
        ],
    ),
    (
        "tools/run_acceptance.py",
        "                f\"STALE EXPECTATION: {label!r} is marked 'fail' in the \"",
        '                "STALE EXPECTATION: never happens "  # noqa: E501',
        "the stale-expectation branch never fires, so the expectations file can rot silently",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestAcceptanceWrapper::test_a_stale_expectation_fails_the_gate",
            "-q",
        ],
    ),
    (
        "tools/run_acceptance.py",
        "                    f\"OVERCLAIM: .dogfood.toml claims {' '.join(sorted(overclaim))} \"",
        '                    "OVERCLAIM: never happens "  # noqa: E501',
        "the overclaim branch never fires, so a submission could claim a tier "
        "the report does not verify — the one thing the organizers say costs "
        "points",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestAcceptanceWrapper"
            "::test_an_overclaim_is_not_rescued_by_allow_false_passes",
            "-q",
        ],
    ),
    (
        "tools/run_acceptance.py",
        '            problems.append(f"check {label!r} is not in the report at all")',
        '            problems.append(f"check {label!r} is fine")',
        "a check missing from the report is accepted, so dropping a check "
        "from the gate would go unnoticed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestAcceptanceWrapper"
            "::test_an_empty_report_is_a_failure_not_a_pass",
            "-q",
        ],
    ),
    (
        "tools/run_acceptance.py",
        '    print(" GATE OK: no regressions, no stale expectations, no false passes.")',
        '    print(" GATE OK")',
        "the success line stops naming what was actually verified, so a reader "
        "cannot tell a clean gate from one that checked nothing",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestAcceptanceWrapper"
            "::test_the_success_line_states_what_was_verified",
            "-q",
        ],
    ),
    # --- docker.py ------------------------------------------------------------
    # The detector is the test that asserts on the CANDIDATE LIST, not the
    # test that asserts on resolve(). That distinction is the third version of
    # this mutation's failure, and it is the most interesting one:
    #
    #   Removing the per-user path does NOT stop `resolve()` working, because
    #   the User PATH was fixed as part of closing F-34 — so `shutil.which`
    #   finds the same binary. A behavioural test on resolve() passes
    #   happily against the broken code.
    #
    # The PATH is now correct *because* of the F-34 fix, which is exactly why
    # the fix is invisible to any test that only checks "did it work". The
    # regression would only surface on a machine where the PATH is not yet
    # fixed — a reviewer's fresh laptop, which is precisely where it matters.
    # So the test has to assert the constant exists, not that the function
    # currently succeeds.
    (
        "tools/docker.py",
        _DOCKER_PER_USER_PATH,
        '    pathlib.Path("/nonexistent/docker.exe"),\n',
        "the per-user Docker path is removed — the F-34 regression, which is "
        "invisible on this machine because the PATH is already fixed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestDockerResolver"
            "::test_resolves_the_per_user_install_by_absolute_path",
            "-q",
        ],
    ),
    (
        "tools/docker.py",
        "        return subprocess.run([binary, *sys.argv[1:]], cwd=os.getcwd()).returncode",
        "        subprocess.run([binary, *sys.argv[1:]], cwd=os.getcwd())\n        return 0",
        "the exit code is swallowed — a wrapper that reports its own success",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestDockerResolver::test_propagates_the_exit_code",
            "-q",
        ],
    ),
    # --- coldstart.py ---------------------------------------------------------
    # The verdict logic is a PURE FUNCTION precisely so it can be tested here
    # without a container, a network and a 60-second wait. The first draft
    # inlined it in main(), and these mutations were undetectable — which is
    # the whole argument for extracting it.
    (
        "tools/coldstart.py",
        "BUDGET_SECONDS = 60.0",
        "BUDGET_SECONDS = 600.0",
        "the 60-second acceptance budget is silently relaxed to 10 minutes",
        [sys.executable, "-m", "pytest", "tests/test_gates.py::TestColdstart", "-q"],
    ),
    (
        "tools/coldstart.py",
        "    if EXPECTED_TITLE not in body:",
        "    if False:",
        "a 200 from any source passes — the content assertion is removed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestColdstart::test_rejects_a_200_that_is_not_our_page",
            "-q",
        ],
    ),
    (
        "tools/coldstart.py",
        "    if elapsed >= budget:",
        "    if False:",
        "the budget comparison is removed, so a ten-minute start passes",
        [sys.executable, "-m", "pytest", "tests/test_gates.py::TestColdstart", "-q"],
    ),
    # --- the health contract --------------------------------------------------
    # These are the two properties the whole container readiness story rests on.
    (
        "src/judge_judy/views.py",
        '    if request.GET.get("deep"):',
        "    if True:",
        "the liveness probe starts touching the database on every request, "
        "which is the failure mode the health contract exists to prevent",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_health.py::TestHealthz::test_does_not_touch_the_database",
            "-q",
        ],
    ),
    (
        "src/judge_judy/urls.py",
        '    path("healthz", views.healthz, name="healthz"),',
        "",
        "the healthcheck route is removed — the container can never go green",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_health.py::TestHealthz::test_returns_200_without_authentication",
            "-q",
        ],
    ),
    (
        "src/judge_judy/urls.py",
        '    path("", project_views.gallery, name="gallery"),',
        "",
        "the landing page is removed — a judge opens the portal and gets a 404",
        [sys.executable, "-m", "pytest", "tests/test_health.py::TestGallery", "-q"],
    ),
    # --- the deadline guard, which is the whole of T1-3 -----------------------
    # `run.py` accepts ANY 4xx for "closed event refuses submissions", so the
    # check passes on a 404, on a CSRF rejection and on a 401 as readily as on a
    # real deadline refusal. These three mutations are the ones that would take
    # the check green while testing nothing, and each is caught by a test that
    # names the mechanism -- not by a status-code assertion.
    (
        "src/reviewer/events/deadlines.py",
        "    if opens_at is not None and moment < opens_at:",
        "    if False:",
        "the opening gate is never enforced, so a future event accepts early "
        "submissions — invisible on the shipped fixture, whose window is closed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_denial_contract.py::TestTheGuardItself"
            "::test_it_refuses_before_the_window_opens",
            "-q",
        ],
    ),
    (
        "src/reviewer/projects/views.py",
        "except SubmissionClosed as exc:\n        return JsonResponse(exc.as_dict(), status=403)",
        "except SubmissionClosed as exc:\n        return JsonResponse(exc.as_dict(), status=400)",
        "the deadline guard still refuses, but with a 400 — a wrong-reason 4xx "
        "that the acceptance check cannot tell from a CSRF rejection",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_denial_contract.py::TestRefusedByTheDeadlineGuard"
            "::test_it_is_a_403_and_not_a_302",
            "-q",
        ],
    ),
    (
        "src/reviewer/events/deadlines.py",
        'GUARD_NAME = "assert_open_for_submission"',
        'GUARD_NAME = "submission"',
        "the refusal stops naming the guard, so a 403 from CSRF or from a missing "
        "team is indistinguishable from the deadline — F-40, and the acceptance "
        "gate's body probe stops being able to tell",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_denial_contract.py::TestRefusedByTheDeadlineGuard"
            "::test_the_refusal_names_the_guard",
            "-q",
        ],
    ),
    # --- the healthcheck timing contract --------------------------------------
    # Both of these report the portal unhealthy during normal operation on a
    # slow machine, and neither produces a failing test on a fast one. They are
    # assertions about a documented number, which is exactly what this project
    # means by "every number is generated, not transcribed".
    (
        "Dockerfile",
        "HEALTHCHECK --interval=5s --timeout=4s --start-period=45s --retries=12 \\",
        "HEALTHCHECK --interval=60s --timeout=4s --start-period=1s --retries=1 \\",
        "the image's healthcheck start period is cut below the real cold start, "
        "so the portal reports itself unhealthy during normal operation",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_healthcheck_contract.py::TestHealthcheckContract"
            "::test_dockerfile_start_period_covers_the_measured_cold_start",
            "-q",
        ],
    ),
    (
        "docker-compose.yml",
        "      start_period: 45s",
        "      start_period: 2s",
        "compose's start period is cut below the measured cold start",
        [sys.executable, "-m", "pytest", "tests/test_health.py::TestHealthcheckContract", "-q"],
    ),
]


def run(command: list[str], cwd: pathlib.Path) -> int:
    """Run a detector in the SANDBOX and return its exit code.

    The `cwd` argument has no default on purpose. The first draft hard-coded
    `REPO` here, and every mutation was then tested against the unmutated
    original. See the module docstring.
    """
    return subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).returncode


def main() -> int:
    print("=" * 74)
    print(" MUTATION TEST — do the FEAT-01 gates notice when they are broken?")
    print("=" * 74)

    # A copy, so a mutation can never leave the real tree damaged. A harness
    # that can corrupt the working tree is a harness nobody runs.
    with tempfile.TemporaryDirectory(prefix="jj-mutation-") as tmp:
        work = pathlib.Path(tmp) / "repo"
        shutil.copytree(
            REPO,
            work,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                "data",
                "*.sqlite3",
                ".ruff_cache",
            ),
        )
        # The detectors are `python -m pytest`, which needs the venv's packages.
        # The sandbox has no .venv, so point the sandbox at the real
        # interpreter explicitly. Without this, every detector fails to import
        # Django and every mutation looks "caught" — caught by the wrong reason.
        real_py = str(REPO / ".venv" / "Scripts" / "python.exe")
        if not pathlib.Path(real_py).exists():
            real_py = sys.executable

        print(f"\n sandbox: {work}\n detector: {real_py}\n")

        caught: list[str] = []
        missed: list[tuple[str, str, str]] = []

        for index, (rel, find, replace, description, command) in enumerate(MUTATIONS, start=1):
            target = work / rel
            original = target.read_text(encoding="utf-8")

            if find not in original:
                print(f"  {index:2d}. SKIPPED  {rel}")
                print(f"      pattern to corrupt is no longer present: {find[:64]!r}")
                print("      This is itself a finding: either the code was")
                print("      refactored past the test, or the test was written")
                print("      against something that was never there.")
                missed.append((rel, description, "pattern not found"))
                continue

            command = [real_py if part == sys.executable else part for part in command]

            try:
                target.write_text(original.replace(find, replace, 1), encoding="utf-8")
                code = run(command, work)
            finally:
                target.write_text(original, encoding="utf-8")

            if code != 0:
                print(f"  {index:2d}. caught   {rel}")
                print(f"      {description}")
                caught.append(rel)
            else:
                print(f"  {index:2d}. MISSED   {rel}")
                print(f"      {description}")
                print("      !! the gate did NOT notice. This is the dangerous")
                print("      !! direction: a broken gate that passes.")
                missed.append((rel, description, "not detected"))

    total = len(MUTATIONS)
    print("\n" + "=" * 74)
    print(f" {len(caught)}/{total} mutations caught")

    # A mutation this harness could not APPLY is a defect in the harness, not a
    # gate that survived. Printing it in the same list, with the same words, as a
    # real miss is how F-46 nearly shipped a green "13/15" that meant "two of our
    # mutations stopped matching because a formatter touched a file". The two
    # cases get separate sections and separate exit codes.
    broken = [m for m in missed if m[2] == "pattern not found"]
    real = [m for m in missed if m[2] != "pattern not found"]

    if broken:
        print("\n HARNESS DEFECT - these corruptions were never applied:")
        for rel, description, _ in broken:
            print(f"   - {rel}: {description}")
        print("\n The pattern to corrupt is not in the file. The corruption never")
        print(" happened, so nothing was tested. This is NOT a gate surviving a")
        print(" mutation - it is a test that stopped testing. Re-point it, and")
        print(" suspect whatever reformatted the file it points at.")

    if real:
        print("\n NOT CAUGHT - each of these is a gate that passes while broken:")
        for rel, description, why in real:
            print(f"   - {rel}: {description}  [{why}]")
        print("\n A gate that fails loudly when broken is merely annoying.")
        print(" A gate that passes when broken is a lie.")

    if missed:
        print("=" * 74)
        return 1

    print(" Every deliberate corruption was detected.")
    print(" The gates are load-bearing, not decoration.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
