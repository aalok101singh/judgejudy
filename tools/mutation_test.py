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
    # --- FEAT-05: the T2 surface and the refusal primitive -------------------
    # The first three were run by hand DURING FEAT-05 and three of five produced
    # no failure at all, which is recorded in the FEAT-05 archive as the reason
    # `tests/test_gates.py::TestTheApiProbes` exists. They are here so the same
    # corruption cannot come back unnoticed.
    (
        "tools/run_acceptance.py",
        '    header_marker = spec.get("header_must_contain")',
        "    header_marker = None",
        "the probe stops requiring the refusal to NAME its guard, so a 403 from "
        "CSRF or from an unrecognised credential satisfies a T2 check again -- "
        "F-40, in the layer the F-40 repair was written for",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestTheApiProbes"
            "::test_a_refusal_with_an_empty_body_and_no_reason_is_caught",
            "-q",
        ],
    ),
    (
        "tools/run_acceptance.py",
        "        if not present:",
        "        if False:",
        "the header marker matches every response, so the peer probe is a bare "
        "status check and cannot tell the peer rule from the role rule",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestTheApiProbes"
            "::test_a_refusal_with_an_empty_body_and_no_reason_is_caught",
            "-q",
        ],
    ),
    (
        "tools/run_acceptance.py",
        '    url = base_url.rstrip("/") + path + suffix',
        '    url = base_url.rstrip("/") + path',
        "the peer probe visits the BARE route as judge_b, so it is satisfied by "
        "the role refusal — a correct refusal of the wrong check, and the "
        "peer-blindness of for_actor_and_subject goes unverified while the gate "
        "stays green",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_gates.py::TestTheApiProbes::test_the_peer_probe_visits_the_peer_url",
            "-q",
        ],
    ),
    # --- the refusal primitive, which every surface now shares ---------------
    (
        "src/reviewer/isolation/refusal.py",
        "    response = HttpResponse(status=status)\n",
        '    response = HttpResponse(status=302, headers={"Location": "/"})\n',
        "the portal's ONE refusal primitive starts redirecting — D-02, and it "
        "now breaks the judge console, the scoped scores and the export at once "
        "because they all call it",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheJudgeSeesOnlyTheirOwn"
            "::test_a_judge_cannot_open_a_peers_review",
            "-q",
        ],
    ),
    (
        "src/reviewer/isolation/refusal.py",
        "    response[REFUSED_BY_HEADER] = refused_by\n",
        "    pass  # was: response[REFUSED_BY_HEADER] = refused_by\n",
        "refusals stop naming why, which is the one thing the acceptance gate's "
        "T2 probes use to tell the isolation layer from anything else",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheJudgeSeesOnlyTheirOwn"
            "::test_a_judge_cannot_open_a_peers_review",
            "-q",
        ],
    ),
    # --- the T2 surface itself ----------------------------------------------
    (
        "src/reviewer/reviews/api.py",
        "    if qs.scope.decision == DECISION_DENY:\n",
        "    if False:\n",
        "the refusal branch never fires, so a participant and a peer-blocking "
        "judge_b both receive a 200 with an empty list — the single most "
        "dangerous shape available, because it satisfies every status check the "
        "organizers' run.py makes while enforcing nothing",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheJudgeCannotSeePeerScores::test_a_peer_is_refused_not_filtered",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        "    if qs.scope.decision == DECISION_DENY:",
        "    if not qs.exists():",
        "the branch is written on EMPTINESS instead of on the decision, so a "
        "judge with no reviews is refused for having none — F-61, and the two "
        "answers are exactly what this accessor exists to keep apart",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheJudgeCannotSeePeerScores"
            "::test_a_judge_with_no_reviews_is_not_refused",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        "        qs = Review.objects.for_actor_and_subject(actor, subject)\n",
        "        qs = Review.objects.for_actor(actor)\n",
        "the peer-blind accessor is bypassed, so judge_b asking about judge_a is "
        "silently answered with judge_b's OWN scores — a wrong answer produced "
        "by a missing lookup, indistinguishable from a right one",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheJudgeCannotSeePeerScores::test_a_peer_is_refused_not_filtered",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        "        if subject is None:\n            return _json(\n",
        "        if False:\n            return _json(\n",
        "an unresolvable ?judge= falls through and answers with your own scores "
        "instead of a 400 — F-42's shape, in a request path",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheJudgeCannotSeePeerScores"
            "::test_an_unknown_subject_is_a_400_and_never_a_fall_through",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        '    return list(rubric.criteria.order_by("position"))\n',
        '    return list(rubric.criteria.order_by("key"))\n',
        "the export header stops being the fixture's KEY order — F-04, which "
        "transposes two columns in every row of every export and is invisible "
        "because a CSV with the right columns in the wrong order is well formed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheCsvExport::test_the_header_is_the_fixtures_key_order",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        '                *(by_key.get(criterion.key, "") for criterion in criteria),\n',
        '                *(list(by_key.values()) + [""] * 3),\n',
        "the export pairs values POSITIONALLY instead of by criterion key — the "
        "other half of F-04, and the one a correct header hides completely",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheCsvExport"
            "::test_a_values_position_matches_its_own_column_everywhere",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        "    if not actor.can_read_all_reviews:\n        return deny(REFUSED_BY_EXPORT)\n",
        "    if False:\n        return deny(REFUSED_BY_EXPORT)\n",
        "everybody gets the export, so a judge — or a participant — can read "
        "every score in the event through a documented route",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheCsvExport::test_a_judge_is_refused_the_export",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/api.py",
        "    if review.source_key:\n        return review.source_key\n",
        "    if True:\n        return review.source_key\n",
        "the review label loses its natural-key fallback, so the export's first "
        "column is 126 empty cells — F-69, a structurally valid export "
        "containing nothing, which is F-61's shape one column wide",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api.py::TestTheCsvExport::test_no_column_in_the_export_is_empty_throughout",
            "-q",
        ],
    ),
    # --- FEAT-04: the assignment engine and the judge console -----------------
    # These sixteen were RUN at FEAT-04 and recorded in three documents as
    # "16/16 on the new modules" — and **no command in this repository could
    # produce them** (F-67). `tools/mutation_test.py` had exactly one MUTATIONS
    # list of eighteen, none of which touched `reviewer/assignment/` or
    # `console.py`. A verification row that no command reproduces is an
    # unreproducible claim wearing the costume of a passing one, which is F-47
    # and F-48 verbatim, and F-59's `check_recipes` cannot see it because that
    # check asks whether a command EXISTS, not whether a number about it can be
    # re-derived.
    #
    # They live here now so the claim is reachable. Each names the test that must
    # notice, and the reason is the specific rule rather than a marker word (F-41).
    #
    # --- the engine: 8 ------------------------------------------------------
    (
        "src/reviewer/assignment/flow.py",
        "        return [0 if d == INF else int(d) for d in dist]\n",
        "        return [0 for d in dist]\n",
        "the initial Johnson potentials are zeroed instead of taken from "
        "Bellman-Ford, leaving negative reduced costs for Dijkstra — the same "
        "class as F-60, reintroduced at the initialisation rather than the update",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestTheSolver"
            "::test_negative_marginal_costs_give_the_minimum_cost_flow",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/flow.py",
        "        return edge.capacity - edge.cap\n",
        "        return 0\n",
        "flow_on reports zero on every arc, so the planner would read a full "
        "assignment as an empty one and demand would be met by nothing",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestFeasibleInstance"
            "::test_every_project_reaches_its_target_exactly",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/planner.py",
        "    if capacity is None:\n",
        "    if capacity is 0:\n",
        "the parametric capacity search never runs, so the tightest capacity is "
        "taken from the upper bound instead of searched for — the layer whose "
        "whole job is that the answer is found rather than guessed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestFeasibleInstance"
            "::test_the_search_finds_the_tightest_capacity_not_a_guessed_one",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/planner.py",
        "    network, handles = _build_network(graph, index, capacity=capacity,"
        " seed=seed, costs=True)\n",
        "    network, handles = _build_network(graph, index, capacity=capacity,"
        " seed=seed, costs=False)\n",
        "the tidying pass is rebuilt without costs, so the load-imbalance term "
        "stops being the thing that spreads the work and the plan is feasible "
        "but unfair — invisible on any assertion about coverage",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestLayersAreLoadBearing"
            "::test_the_cost_function_is_what_spreads_the_load",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/planner.py",
        "        saturated = [uid for uid in track.judge_user_ids if loads[uid] >= capacity]\n",
        "        saturated = [uid for uid in track.judge_user_ids if loads[uid] > capacity]\n",
        "a judge AT capacity is no longer reported as saturated — the exact "
        "off-by-one F-61 existed to prevent, since the whole point of the "
        "bottleneck list is the judges who cannot take one more project",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestInfeasibleInstance"
            "::test_the_bottleneck_judges_are_named_not_counted",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/planner.py",
        "                deficit=demand - supplied,\n",
        "                deficit=demand - supplied + 1,\n",
        "the deficit is off by one, so the certificate names a shortfall one "
        "larger than the min-cut proves — the number an organizer acts on",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestInfeasibleInstance::test_the_deficit_is_named_per_track",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/planner.py",
        "        needed = -(-d.demand // capacity) - judge_count\n",
        "        needed = d.demand // capacity - judge_count\n",
        "the 'invite more judges' remedy floors instead of ceiling, so the "
        "remedy's own arithmetic no longer shows k x c >= demand — the sentence "
        "that makes the remedy checkable",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestInfeasibleInstance"
            "::test_three_remedies_each_with_sufficient_arithmetic",
            "-q",
        ],
    ),
    (
        "src/reviewer/assignment/graph.py",
        "    if judge.user_id in team_members.get(project.team_id, ()):\n"
        '        return "submitting_team_member"\n',
        '    if False:\n        return "submitting_team_member"\n',
        "the conflict-of-interest rule stops excluding — and it is UNREACHABLE "
        "on the shipped fixture (F-64), so nothing about the real data would "
        "ever have noticed",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_assignment.py::TestLayersAreLoadBearing"
            "::test_a_judge_cannot_review_their_own_teams_project",
            "-q",
        ],
    ),
    # --- the console: 6 -----------------------------------------------------
    # The D-02 redirect and the refusal-reason header USED to be mutations
    # against `console.py`, and they no longer are: FEAT-05 moved `_deny` into
    # `reviewer/isolation/refusal.py` so the console and the API share one
    # refusal primitive, and this harness correctly reported both as
    # `pattern not found` rather than as passing. The two replacements live in
    # the FEAT-05 block above, pointed at the new home, and the same test names
    # are used — so the property is still covered and is now covered *once*,
    # at the place a future edit is most likely to break it.
    (
        "src/reviewer/reviews/console.py",
        "    return actor.is_judge or actor.can_read_all_reviews\n",
        "    return True\n",
        "anyone may open the judge console, so a participant and a visitor get "
        "the judging surface instead of a refusal",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheJudgeSeesOnlyTheirOwn"
            "::test_a_participant_is_refused_the_console",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/console.py",
        "        return _deny(REFUSED_BY_ASSIGNMENT)\n",
        "        return HttpResponse(status=200)\n",
        "a judge who is not the assignee gets a 200 instead of a refusal, which "
        "is the exact 'hide it in the template' failure the spec names",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheJudgeSeesOnlyTheirOwn"
            "::test_a_judge_cannot_open_a_peers_review",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/console.py",
        '        return _deny("judge_console.review_locked", status=409)\n',
        "        return _render_form(request, event, actor, review, {}, "
        'review.overall_comment, "")\n',
        "a submitted review stops being locked, so a judge can revise scores they "
        "have already turned in",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheReviewForm::test_a_submitted_review_is_locked",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/console.py",
        "        if not (rubric.scale_min <= value <= rubric.scale_max):\n",
        "        if False:  # was: not (rubric.scale_min <= value <= rubric.scale_max)\n",
        "the rubric's own scale stops bounding the score, so an organizer who "
        "scales 1..10 silently accepts 47",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheReviewForm"
            "::test_a_score_outside_the_rubric_is_refused_by_name",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/console.py",
        "    if error or (submitting and any(v is None for v in values.values())):\n",
        "    if error:  # was: or (submitting and any(v is None for v in values.values()))\n",
        "submitting no longer requires every criterion, so a half-scored review "
        "is recorded as a submission",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheReviewForm::test_submitting_requires_every_criterion",
            "-q",
        ],
    ),
    (
        "src/reviewer/reviews/console.py",
        "    if not actor.can_read_all_reviews:\n        return _deny(REFUSED_BY_ROLE)\n",
        "    if not actor.can_read_all_reviews:\n        return HttpResponse(status=200)\n",
        "a judge is admitted to the organizer's plan screen — the certificate, "
        "the capacity curve and every other judge's load",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_judge_console.py::TestTheJudgeSeesOnlyTheirOwn"
            "::test_the_organizers_plan_screen_is_refused_to_a_judge",
            "-q",
        ],
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
