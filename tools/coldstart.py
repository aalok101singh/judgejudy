#!/usr/bin/env python3
"""Time a cold start: empty volume -> build -> healthy -> serving page.

This exists because the FEAT-01 acceptance criterion is a *number* — a serving
page in under 60 seconds from a clean volume with no network — and the rule
this project has written down is that every number in a shipped document is
generated rather than transcribed. A timing quoted from memory is exactly the
kind of claim that F-11 was about.

So the measurement is a script, it prints the seconds, and whatever ends up in
the README comes from this output.

Two things it is careful about:

- **It stops the stopwatch at the serving page, not at "healthy".** A green
  healthcheck is the container's opinion about itself; the criterion is about
  a judge seeing a page. They are normally within a second of each other and
  the difference is exactly the sort of thing that gets rounded away.
- **It refuses to pass on a page that is not ours.** A 200 from a proxy, or
  from a previous container that never died, would satisfy a bare status check.
  The body has to contain our own title.

Stdlib only. It drives `docker` as a subprocess, so it works with the
per-user install path (F-34) via whatever `docker` resolves to on the PATH.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent

# The absolute per-user Docker Desktop path (F-34). Preferred over a bare
# `docker` so a stale shell cannot turn the measurement into a PATH failure.
DOCKER_FALLBACK = pathlib.Path(
    r"C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)

BUDGET_SECONDS = 60.0
EXPECTED_TITLE = "Judge Judy"


def docker() -> str:
    """Resolve the docker CLI, preferring the known per-user install."""
    if DOCKER_FALLBACK.exists():
        return str(DOCKER_FALLBACK)
    found = shutil.which("docker")
    if not found:
        print(
            "FAIL: docker not found. It IS installed (per-user, F-34) — this "
            "is a PATH problem. Do not reinstall.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return found


def run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    printable = " ".join(args)
    print(f"$ {printable}", flush=True)
    result = subprocess.run(
        args,
        cwd=REPO,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        if capture:
            sys.stdout.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
        raise SystemExit(f"command failed ({result.returncode}): {printable}")
    return result


def fetch(url: str, timeout: float = 5.0) -> tuple[int, str]:
    """Return (status, body). Never raises — a refusal is a measurement too.

    `urlopen` on a caller-supplied URL is S310 and it is deliberately not
    suppressed globally: the only caller passes `http://localhost:<port>`, and
    the scheme is asserted here rather than trusted, so the lint rule's
    underlying concern is actually addressed instead of muted.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing to fetch a non-HTTP URL: {url!r}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def verdict(
    status: int, body: str, elapsed: float, budget: float = BUDGET_SECONDS
) -> tuple[bool, str]:
    """Decide pass/fail from a measurement. Pure — no I/O, no clock.

    Extracted so the decision can be tested without a container, a network or a
    stopwatch. The first version of this file inlined it in `main()`, and the
    consequence was concrete: `tools/mutation_test.py` could corrupt
    `elif EXPECTED_TITLE not in body:` to `elif False:` — removing the
    content assertion entirely, which is the check that stops a 200 from a
    proxy counting as a pass — and nothing noticed, because the only way to
    exercise that line was to boot a container for 60 seconds.

    A rule that can only be tested by running the whole system is a rule that
    does not get tested. Hence: pure function, tested directly.
    """
    if status != 200:
        return False, (
            f" FAIL  the portal did not return 200 (got {status})\n       body: {body[:200]!r}"
        )
    if EXPECTED_TITLE not in body:
        return False, (
            f" FAIL  the page returned 200 but is not ours "
            f"(no {EXPECTED_TITLE!r} in the body)\n"
            f"       A 200 from something else is not a passing page."
        )
    if elapsed >= budget:
        return False, f" FAIL  {elapsed:.1f}s exceeds the {budget:.0f}s budget"
    return True, (f" PASS  serving page in {elapsed:.1f}s, budget {budget:.0f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure a cold start.")
    parser.add_argument("--url", default=None, help="portal URL (default from JJ_PORT)")
    parser.add_argument(
        "--budget",
        type=float,
        default=BUDGET_SECONDS,
        help=f"budget in seconds (default {BUDGET_SECONDS:.0f})",
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="reuse the existing image; measures boot only"
    )
    args = parser.parse_args()

    port = os.environ.get("JJ_PORT", "8080")
    url = args.url or f"http://localhost:{port}/"
    d = docker()
    compose = [d, "compose", "-f", "docker-compose.yml"]

    print("=" * 62)
    print(" COLD START — empty volume, build, up, first serving page")
    print(f" budget: {args.budget:.0f}s   url: {url}")
    print("=" * 62)

    # The reset. This is the whole point: a warm volume is not the claim.
    run([*compose, "down", "-v", "--remove-orphans"])

    if args.skip_build:
        print("\n-- skipping build, measuring boot only --")
    else:
        print("\n-- build (the long step) --")
        started = time.perf_counter()
        run([*compose, "build"])
        print(f"   build took {time.perf_counter() - started:.1f}s")

    print("\n-- up --")
    started = time.perf_counter()

    # --wait blocks until the healthcheck passes, which is the container's own
    # definition of ready. The page fetch after it is what stops the clock for
    # the criterion.
    run([*compose, "up", "-d", "--wait", "--wait-timeout", "120"])
    healthy_at = time.perf_counter() - started
    print(f"   healthcheck green at {healthy_at:.1f}s")

    status, body = 0, ""
    deadline = started + args.budget
    while time.perf_counter() < deadline:
        status, body = fetch(url)
        if status == 200 and EXPECTED_TITLE in body:
            break
        time.sleep(0.25)

    elapsed = time.perf_counter() - started
    print(f"   serving page at {elapsed:.1f}s (HTTP {status})")

    print("\n-- compose ps --")
    ps = run([*compose, "ps"], check=False)
    sys.stdout.write(ps.stdout or "")

    print("\n" + "=" * 62)
    ok, message = verdict(status, body, elapsed, args.budget)
    print(message)
    if ok:
        # The two numbers are different measurements and both are worth having:
        # the healthcheck turning green is the container's opinion about
        # itself, and the page arriving is the thing a judge sees. The
        # difference between them is normally a fraction of a second, and that
        # is exactly the sort of thing that gets rounded away and then quoted.
        print(f"       healthcheck green at {healthy_at:.1f}s")

    # Print the measured number in a copy-pasteable form, because the README
    # quotes it and transcribing it by hand is how it goes stale.
    print(
        f"\n cold start: {elapsed:.1f}s to a serving page "
        f"(healthcheck {healthy_at:.1f}s), measured by tools/coldstart.py"
    )
    print("=" * 62)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
