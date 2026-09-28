#!/usr/bin/env python3
"""Run the organizers' acceptance checker and gate on what it says.

`run.py` **always exits 0** — including when every one of its seven checks
prints FAIL. That is what the published program does, and the panel runs the
identical program (F-32). So any wrapper that gates on the return code reports
a green checkpoint for a completely broken portal.

This wrapper gates on the **body** instead, and on two things beyond it.

## 1. The ratchet

Gating on "any FAIL is fatal" cannot work during a build. Five of the seven
checks depend on a gallery, a judge console and a CSV export that do not exist
until FEAT-05, and **a gate that is red from the first commit is a gate nobody
reads.** That is the same reason a healthcheck that cries wolf is worse than no
healthcheck.

So `tools/expected_checks.json` records, per check, whether it is *expected* to
pass yet, with the reason and the feature that flips it. The gate then enforces
**both directions**:

- expected `pass` but FAILs → **red**. A regression.
- expected `fail` but PASSES → **red**. The expectation file is stale, and a
  stale expectation is worse than none: it teaches a reader to discount the
  document the next time it is genuinely wrong.

The file only ever moves from `fail` to `pass`, and only when the feature that
owns the check is done and its acceptance line has passed. That is what makes
it a ratchet rather than a wish list.

## 2. The preconditions

Two of the seven checks currently pass **for the wrong reason.** A 404 is
inside the range `run.py` accepts for both "closed event refuses submissions"
(4xx) and "judge cannot see peer scores" (401/403). So those checks report PASS
while the route is absent and nothing is being tested at all.

That is finding F-11 turned on ourselves: **a check that reports PASS without
exercising the behaviour it names is worse than one that reports FAIL, because
it is believed.** The precondition table says which passes are conditional, and
a conditional pass that is not met is reported as a **FALSE PASS** and fails
the gate — loudly, with the reason, rather than being quietly counted.

Isolation enforced by absence is not isolation.

Stdlib only, and it stays that way: this runs at a break when the container is
the thing under suspicion, and the tool verifying it should be the simplest
thing in the repository.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
EXPECTED = HERE / "expected_checks.json"

# A report line: `T1  gallery is public ................. PASS`
CHECK_LINE = re.compile(r"^(?P<tier>T\d)\s+(?P<label>.+?)\s+\.*\s*(?P<verdict>PASS|FAIL)\s*$")
CLAIMED = re.compile(r"^claimed\s+(?P<claim>.+?),\s*verified\s+(?P<verified>.+?)\s*$")
NOTHING = "nothing"


def parse_report(body: str) -> tuple[dict[str, str], str, str]:
    """Return ({label: verdict}, claimed, verified) from a report body.

    The verdicts are read out of the organizers' own printed lines rather than
    recomputed, so this cannot disagree with the program it wraps.
    """
    verdicts: dict[str, str] = {}
    for line in body.splitlines():
        match = CHECK_LINE.match(line.strip())
        if match:
            verdicts[match.group("label").strip()] = match.group("verdict")

    claimed = verified = NOTHING
    for line in body.splitlines():
        match = CLAIMED.match(line.strip())
        if match:
            claimed = match.group("claim").strip()
            verified = match.group("verified").strip()
            break

    return verdicts, claimed, verified


ROUTES = {
    "gallery": "/",
    "submit": "/projects/new",
    "judge_scores": "/api/v1/judge/scores",
}

# Maps a precondition key in expected_checks.json to a route in ROUTES above.
#
# This table exists because the first version looked the route up by the
# precondition's own key — `route_status.get("submit_route_exists", 0)` against
# a dict keyed `submit`. It returned the default 0, and because 0 was in the
# "missing" set the gate still reported a false pass, so the *verdict* was
# right and the *explanation* was wrong: it said "no HTTP response" when the
# route was answering 404.
#
# A wrong default that happens to produce a passing result is the most
# expensive kind of bug there is — it survives a green test run and lies in the
# one message a human reads to decide what to fix. Every key is now mapped
# explicitly, and `test_every_precondition_names_a_real_route` fails loudly if
# one is missing rather than defaulting.
PRECONDITION_ROUTES = {
    "submit_route_exists": "submit",
    "judge_scores_route_exists": "judge_scores",
    "gallery_route_exists": "gallery",
}


def probe_routes(base_url: str) -> dict[str, int]:
    """Ask the running portal whether the routes behind the preconditions exist.

    Deliberately crude: a status code per route, no auth, no cleverness. The
    question is only "is this URL routed at all", and a 404 or a 302 both mean
    no — a route that redirects is not the route the precondition is about.

    The first probe also establishes reachability, which the caller uses to
    tell "the portal is down" apart from "this route is missing". Collapsing
    those two into one message teaches a reader to skim past it.
    """
    import urllib.error
    import urllib.request

    status: dict[str, int] = {}
    for name, path in ROUTES.items():
        url = base_url.rstrip("/") + path
        try:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"refusing to probe a non-HTTP URL: {url!r}")
            with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
                status[name] = response.status
        except urllib.error.HTTPError as exc:
            status[name] = exc.code
        except Exception:
            status[name] = 0
    return status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run run.py, then gate on its body plus an expectation ratchet."
    )
    parser.add_argument("config", nargs="?", default=".dogfood.toml")
    parser.add_argument(
        "--runner", default="run.py", help="the organizers' checker (default: run.py)"
    )
    parser.add_argument("--expectations", default=str(EXPECTED), help="the expectation file")
    parser.add_argument(
        "--quiet", action="store_true", help="only print the report when something is wrong"
    )
    parser.add_argument(
        "--skip-preconditions",
        action="store_true",
        help="do not probe the running portal for the false-pass "
        "preconditions. Only for testing this wrapper "
        "against a synthetic report: the preconditions "
        "exist to interrogate a LIVE portal, and with a "
        "fake report there is nothing to interrogate.",
    )
    parser.add_argument(
        "--allow-false-passes",
        action="store_true",
        help="report false passes loudly but do not fail on "
        "them. Used by `just check` while the features "
        "that own those routes are unbuilt. Everything "
        "else — regressions, stale expectations, an "
        "overclaimed tier — still fails the gate.",
    )
    parser.add_argument(
        "--url-override",
        default=None,
        help="probe THIS base_url instead of the one in the "
        "report. Only for testing that an unreachable "
        "portal is reported as unreachable rather than "
        "as a false pass; the report's own portal line "
        "is what the real gate uses.",
    )
    args = parser.parse_args()

    runner = pathlib.Path(args.runner)
    if not runner.is_absolute():
        runner = REPO / runner
    if not runner.exists():
        print(
            f"FAIL: {args.runner} not found. It ships with the organizers and must not be edited.",
            file=sys.stderr,
        )
        return 2

    if not pathlib.Path(args.expectations).exists():
        print(f"FAIL: expectations file {args.expectations} not found.", file=sys.stderr)
        return 2

    spec = json.loads(pathlib.Path(args.expectations).read_text(encoding="utf-8"))
    # `$comment` keys are documentation, not configuration. They are stripped
    # here rather than at each use site so that a reader adding a comment to
    # the expectations file cannot accidentally make the gate start treating it
    # as a check. A tool that requires its own documentation to be absent from
    # the file it documents is a tool that discourages documentation.
    expected = {k: v for k, v in spec.get("checks", {}).items() if not k.startswith("$")}
    preconditions = {
        k: v for k, v in spec.get("preconditions", {}).items() if not k.startswith("$")
    }

    # `run.py` is stdlib-only, so the ambient interpreter is the correct one to
    # run it with. F-38 is about that interpreter having no Django, not about
    # it being unable to run the organizers' program.
    completed = subprocess.run(
        [sys.executable, str(runner), args.config],
        capture_output=True,
        text=True,
        cwd=REPO,
        encoding="utf-8",
        errors="replace",
    )

    body = completed.stdout or ""
    if completed.stderr.strip():
        # Surfaced, not swallowed: a traceback here is a real boot problem and
        # hiding it is how a broken checkpoint gets signed off.
        body += "\n--- stderr from run.py ---\n" + completed.stderr

    verdicts, claimed, verified = parse_report(body)

    problems: list[str] = []
    notes: list[str] = []

    # The base_url in the report is the one the checker actually used, and that
    # is what the real gate probes. The override exists so a test can point the
    # probe at a dead port and assert the "unreachable" branch — which is a
    # different finding from a false pass, and the two must not be conflated.
    base_url = "http://localhost:8080"
    for line in body.splitlines():
        if line.startswith("portal:"):
            base_url = line.split(":", 1)[1].strip()
            break
    if args.url_override:
        base_url = args.url_override

    route_status = (
        {}
        if (args.skip_preconditions or not any(preconditions.values()))
        else probe_routes(base_url)
    )

    # --- the ratchet, both directions ----------------------------------------
    for label, want in expected.items():
        got = verdicts.get(label)
        if got is None:
            problems.append(f"check {label!r} is not in the report at all")
            continue

        if want["expect"] == "pass" and got == "FAIL":
            problems.append(f"REGRESSION: {label!r} is expected to pass and FAILED")
        elif want["expect"] == "fail" and got == "PASS":
            # A stale expectation. The gate goes red so the file gets updated,
            # because a stale expectation teaches a reader to discount it.
            problems.append(
                f"STALE EXPECTATION: {label!r} is marked 'fail' in the "
                f"expectations file but the report says PASS. Update "
                f"tools/expected_checks.json — the feature that owns it has "
                f"landed."
            )

    # --- the preconditions ----------------------------------------------------
    # A conditional pass whose condition is unmet is a FALSE PASS, and it is
    # reported as one rather than being counted quietly.
    #
    # Reachability first. "The portal is not answering" and "this route does
    # not exist" are different problems, and collapsing them into one message
    # is how a reader learns to skim past it.
    gallery_status = route_status.get("gallery", 0)
    portal_down = gallery_status in (0,)

    false_passes: list[tuple[str, str]] = []
    for label, got in verdicts.items():
        if got != "PASS" or portal_down:
            continue
        rules = preconditions.get(label)
        if not rules:
            continue
        for route_key, rule in rules.items():
            route_name = PRECONDITION_ROUTES.get(route_key)
            if route_name is None:
                # Loud, not defaulted. A precondition naming a route that does
                # not exist is a broken precondition, and reporting it as
                # "the route is missing" would blame the portal for a typo in
                # the expectations file.
                problems.append(
                    f"precondition {route_key!r} for {label!r} names no known "
                    f"route. Add it to PRECONDITION_ROUTES in this file."
                )
                break

            status = route_status.get(route_name, 0)
            if status in (0, 404, 410):
                observed = "no HTTP response" if status == 0 else f"HTTP {status}"
                false_passes.append(
                    (
                        label,
                        f"{route_name} ({ROUTES[route_name]}) answered "
                        f"{observed}, so this PASS is not testing the "
                        f"behaviour it names — {rule['why']}",
                    )
                )
                break

    # --- the tier claim -------------------------------------------------------
    if spec.get("tier_claims", {}).get("enforce"):
        if claimed != NOTHING:
            claimed_tiers = set(claimed.split())
            verified_tiers = set() if verified == NOTHING else set(verified.split())
            overclaim = claimed_tiers - verified_tiers
            if overclaim:
                problems.append(
                    f"OVERCLAIM: .dogfood.toml claims {' '.join(sorted(overclaim))} "
                    f"but the report verified "
                    f"{verified if verified != NOTHING else 'nothing'}. The "
                    f"organizers state that overclaiming is the one thing that "
                    f"actually costs points."
                )
        else:
            notes.append(
                "claimed: nothing — correct at this milestone. The tier claim "
                "is made at a verification break, against what is green."
            )

    # --- report ---------------------------------------------------------------
    if not args.quiet or problems or false_passes:
        print(body.rstrip())

    passed = sum(1 for v in verdicts.values() if v == "PASS")
    failed = sum(1 for v in verdicts.values() if v == "FAIL")

    print()
    print("-" * 62)
    print(f" acceptance: {passed} passed, {failed} failed, of {len(verdicts)} checks")
    print(f" (run.py itself exited {completed.returncode}, which is always 0)")

    for note in notes:
        print(f" note: {note}")

    # The false-pass finding is printed in exactly one place, at the end, where
    # the verdict is. The first draft printed it twice — once in the summary
    # and again in the verdict block — because the two were written at
    # different times. A warning printed twice reads as two separate problems,
    # and a reader counting them stops trusting the count.
    if problems:
        print()
        print(" GATE FAILED:")
        for problem in problems:
            print(f"   - {problem}")
        if portal_down and not args.skip_preconditions:
            print(
                "   - the portal is not answering on "
                f"{base_url}. The checks above are being reported against "
                "nothing; run `just up` first."
            )
        if false_passes:
            print(
                f"   - {len(false_passes)} FALSE PASS(es): a check reporting "
                f"PASS without exercising the behaviour it names"
            )
        print("-" * 62)
        return 1

    if portal_down and not args.skip_preconditions:
        print()
        print(f" GATE FAILED: nothing is listening on {base_url}.")
        print(" A report full of 0s is not a report about the portal.")
        print("-" * 62)
        return 1

    if false_passes:
        # A false pass fails the gate by default. This is deliberate and it is
        # the whole reason the precondition table exists: a check reporting
        # PASS without testing the deadline is worse than a check reporting
        # FAIL, because it is believed — and the F-11 lesson was learned the
        # expensive way, where a documented DRF default was recalled rather
        # than executed and would have made the deadline check pass without
        # testing the deadline.
        #
        # Note the first draft of this function printed "FALSE PASSES" and then
        # still returned 0 with "GATE OK". A gate that names a problem and then
        # reports success is the worst possible combination: it teaches a reader
        # that the warnings are decorative, which is exactly how a real failure
        # gets ignored the day it matters.
        print()
        if args.allow_false_passes:
            print(" FALSE PASSES — reported as PASS by the checker, but not testing")
            print(" the behaviour they name. Treating these as evidence would be")
            print(" the F-11 mistake applied to us:")
        else:
            print(" GATE FAILED — false passes are not evidence:")
        for label, why in false_passes:
            print(f"   - {label}: {why}")

        if not args.allow_false_passes:
            print()
            print(" Isolation enforced by absence is not isolation. A check that")
            print(" reports PASS without exercising the behaviour it names is worse")
            print(" than one that reports FAIL, because it is believed.")
            print("-" * 62)
            return 1

        print()
        print(" Isolation enforced by absence is not isolation. These passes are")
        print(" not counted as evidence of anything.")
        print(" They are allowed only because the features that own those")
        print(" routes are unbuilt; see --allow-false-passes.")
        print("-" * 62)
        return 0

    if not verdicts:
        print()
        print(" GATE FAILED: the report contains no checks at all.")
        print("-" * 62)
        return 1

    print()
    print(" GATE OK: no regressions, no stale expectations, no false passes.")
    print(f" {passed} checks pass; {failed} fail as expected for this milestone.")
    print("-" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
