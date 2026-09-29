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
    "csv_export": "/api/v1/export.csv",
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
    "submit_refused_by_deadline": "submit",
    "judge_scores_route_exists": "judge_scores",
    "peer_scores_refused_by_scope": "judge_scores",
    "participant_scores_refused_by_role": "judge_scores",
    "csv_export_route_exists": "csv_export",
    "gallery_route_exists": "gallery",
}

#: A precondition that carries a `probe` is a DIFFERENT kind of rule, and the
#: difference is the whole point of this section.
#:
#: A route-existence rule asks "is this URL routed at all", and it is blind to
#: *why* a request was refused. `run.py` accepts any 4xx for "closed event
#: refuses submissions", so from its point of view a CSRF rejection, a 401 for an
#: unrecognised credential, an emptied `[auth]` block and a 404 are the same
#: result. All four report PASS. Only one of them is the deadline working.
#:
#: So a probe re-sends the checker's own request — same method, same JSON body,
#: same credential, read out of the same `.dogfood.toml` — and asserts on the
#: RESPONSE BODY. A refusal that does not name the mechanism that produced it is
#: reported as a false pass with the body it got instead, which is the message a
#: human needs and which a status code cannot give.
#:
#: Stated as a limit: a probe is only as good as its marker. Ours is the guard's
#: own function name, which the view puts in `refused_by` — see
#: `reviewer/events/deadlines.py`. A view that refused everything with the same
#: body would pass this, and that is why
#: `tests/test_denial_contract.py::test_the_same_form_post_is_refused_only_by_the_clock`
#: sends the identical request with the window open and requires a 201.
PROBE_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def read_config_auth(config_path: pathlib.Path) -> dict:
    """The ``[auth]`` block from the config the checker itself was given.

    Read with ``tomllib`` when it is available, and with ``run.py``'s own
    fallback parser otherwise, so a value that authenticates under one parser
    authenticates under both. A stale or empty value is not "handled" here -- it
    is reported by the probe, because that is exactly the false pass this whole
    mechanism exists to catch.
    """
    try:
        import tomllib

        with config_path.open("rb") as handle:
            return tomllib.load(handle).get("auth", {})
    except Exception:
        return {}


def run_probe(base_url: str, path: str, spec: dict, auth: dict) -> dict:
    """Send the checker's own request and describe what came back.

    Returns a dict rather than raising, so a portal that is down, a route that
    500s and a credential that does not verify all produce a *report* naming
    what happened, which is what a reader needs. A probe that raised would turn
    every one of those into the same traceback.
    """
    import json as _json
    import urllib.error
    import urllib.request

    method = str(spec.get("method", "GET")).upper()
    if method not in PROBE_METHODS:
        return {"error": f"probe method {method!r} is not one this tool will send"}

    # `path_suffix` exists for the peer-scores probe, and the reason it is worth
    # having is that the peer URL and the bare URL are DIFFERENT URLs testing
    # DIFFERENT things. Probing the bare one as judge_b would be satisfied by the
    # role rule, which is the same refusal for the wrong reason -- and it would
    # leave the peer-blindness of `for_actor_and_subject` untested by the one
    # gate whose entire job is to test it. The suffix is taken from the same
    # `.dogfood.toml` route the checker visits, not written here, so the two
    # cannot drift.
    suffix = str(spec.get("path_suffix", ""))
    url = base_url.rstrip("/") + path + suffix
    header = auth.get(str(spec.get("auth", ""))) if spec.get("auth") else None
    if spec.get("auth") and not header:
        return {
            "error": f"[auth] {spec['auth']!r} is empty in the config, so the probe "
            "cannot present the credential the checker used. Every 4xx still "
            "counts as a pass for the checker, and none of them is the deadline."
        }

    request = urllib.request.Request(url, method=method)
    if header:
        name, _, value = str(header).partition(":")
        request.add_header(name.strip(), value.strip())
    body = None
    if method not in ("GET", "HEAD") and spec.get("json") is not None:
        body = _json.dumps(spec["json"]).encode()
        request.data = body
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status, text, headers = (
                response.status,
                response.read().decode("utf-8", "replace"),
                dict(response.headers),
            )
    except urllib.error.HTTPError as exc:
        status, text, headers = exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"status": status, "body": text, "headers": headers}


def _status_is(expected: str, status: int) -> bool:
    """Whether ``status`` satisfies an ``expect_status`` from the expectations file.

    Three forms, because the checker's own assertions use three and the file
    should be able to say the same thing the checker says: ``4xx``, ``401/403``,
    or an exact number. An unparseable expectation is False rather than a
    default that happens to pass -- F-42's shape, which is how the previous
    version of this file reported a correct verdict for a wrong reason.
    """
    text = expected.strip()
    if text == "4xx":
        return 400 <= status < 500
    if "/" in text:
        try:
            allowed = {int(part) for part in text.split("/") if part.strip()}
        except ValueError:
            return False
        return status in allowed
    try:
        return status == int(text)
    except ValueError:
        return False


def judge_probe(outcome: dict, spec: dict) -> tuple[bool, str]:
    """``(ok, why)`` for one probe. ``why`` names what came back, not what broke.

    Every failure branch ends with the *observed* status and body, because the
    reader's next question is always "what did it actually say?" and a verdict
    without that sends them to the source. The body is truncated -- a portal that
    answers 500 with a Django traceback is 3 kB of somebody else's problem, and a
    gate that prints 3 kB stops being read.
    """
    if "error" in outcome:
        return False, f"could not be probed: {outcome['error']}"

    status = outcome["status"]
    body = outcome["body"] or ""
    expected = str(spec.get("expect_status", "4xx"))
    if not _status_is(expected, status):
        return False, f"answered HTTP {status}, wanted {expected}"

    marker = spec.get("body_must_contain")
    if marker and marker not in body:
        snippet = " ".join(body.split())[:220] or "(empty body)"
        return (
            False,
            f"answered HTTP {status} with no {marker!r} in the body, so the refusal "
            f"did not come from the mechanism this check names. It said: {snippet}",
        )

    forbidden = spec.get("must_not_have_header")
    if forbidden and forbidden in {k.title() for k in outcome["headers"]}:
        return (
            False,
            f"answered HTTP {status} WITH a {forbidden} header, and run.py follows "
            "redirects -- so this refusal would arrive as a 200",
        )

    # `header_must_contain` is the API-side twin of `body_must_contain`, and it
    # exists because of a genuine conflict rather than a preference.
    #
    # D-02 requires a refusal to have an EMPTY body, so an API refusal cannot
    # name its own guard in the body the way the deadline guard's form page does.
    # F-40 requires the refusal to be attributable, so that a 403 from the
    # isolation layer is distinguishable from a 403 from CSRF, from a 401 for an
    # unrecognised credential, or from a 404. Both requirements are satisfiable at
    # once because they land on different parts of the response: the body stays
    # empty and the reason travels in `X-Refused-By`.
    #
    # Without this assertion the T2 probes would be satisfied by a refusal for
    # any reason at all, which is the whole defect F-40 was filed about.
    header_marker = spec.get("header_must_contain")
    if header_marker:
        present = [
            name for name, value in outcome["headers"].items() if header_marker in (value or "")
        ]
        if not present:
            seen = ", ".join(
                f"{name}={value!r}"
                for name, value in sorted(outcome["headers"].items())
                if name.lower().startswith("x-")
            )
            return (
                False,
                f"answered HTTP {status} with no header carrying {header_marker!r}, so "
                f"the refusal did not come from the mechanism this check names. "
                f"Headers seen: {seen or '(none starting with X-)'}",
            )

    detail = f"answered HTTP {status}"
    if marker:
        detail += f" naming {marker!r}"
    if header_marker:
        detail += f" naming {header_marker!r} in a header"
    if forbidden:
        detail += f" with no {forbidden} header"
    return True, detail


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
            with urllib.request.urlopen(url, timeout=5) as response:
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

    config_auth: dict = {}
    if not args.skip_preconditions and not portal_down:
        config_auth = read_config_auth(pathlib.Path(args.config))

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

            if rule.get("probe") is not None:
                # A probe precondition: the MECHANISM, not the route's existence.
                outcome = run_probe(base_url, ROUTES[route_name], rule["probe"], config_auth)
                ok, why = judge_probe(outcome, rule["probe"])
                if not ok:
                    false_passes.append((label, f"{route_name} {why}"))
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
