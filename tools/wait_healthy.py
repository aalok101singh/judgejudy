#!/usr/bin/env python3
"""Bring the stack up and wait for it, with a deadline and a diagnosis.

**This replaces ``docker compose up -d --wait --wait-timeout 120``, and the
reason is that the flag is not trustworthy.**

On Docker 28.0.4 with Compose **v2.38.2** (a GitHub Actions runner, October
2026) that command was observed to block indefinitely while the container it was
waiting for reported **healthy**. It was cancelled at 45, then 75, then 120
minutes, three runs in a row, each with this line as the last thing in the log::

    portal-1 | [INFO] Control socket listening at /home/judge/.gunicorn/gunicorn.ctl

and then two hours of silence. The container was fine. A ``diagnose`` job in the
same workflow brought the identical stack up **without** ``--wait`` and found it
healthy in **20 seconds**, with ``healthcheck.py`` exiting 0.

The same command in the same job shape is exercised by ``tools/coldstart.py``,
and it passed -- so this is a Compose-version behaviour rather than a property of
this project. That is exactly why it is worth replacing instead of working
around: **an unbounded wait cannot fail, cannot explain itself, and reports
nothing about the code** when it is eventually cancelled.

So: ``up -d`` (which returns promptly), then a **bounded** poll of the
container's own health status. On timeout this prints the container's status, its
full health log, the healthcheck's own output, and the tail of the application
log -- because "it did not become healthy" is only useful if the reason is
attached to it.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from docker import resolve  # sibling module; the path insert above is what makes this legal

# **Line buffering, or this tool says nothing while it is waiting for
# something.** `just` runs recipes through a shell, so stdout here is a pipe
# rather than a terminal, and Python block-buffers a pipe in 8 KB chunks. The
# first version of this helper therefore emitted *no output at all* on a CI
# runner -- not one line, for two hours -- because it was blocked and never
# flushed. A tool whose whole purpose is to tell you what it is waiting for
# cannot have its output buffered until it is done. This was found by reading a
# log with zero lines in it and wondering why.
sys.stdout.reconfigure(line_buffering=True)

CONTAINER = "judgejudy-portal-1"


def run(argv: list[str], env_extra: dict[str, str] | None = None, timeout: float | None = None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)


def compose(seed_demo: bool, compose_file: str, *args: str) -> list[str]:
    binary = resolve()
    if binary is None:
        print("docker is not installed, or is not on PATH. Run 'just doctor'.", file=sys.stderr)
        raise SystemExit(127)
    return [binary, "compose", "-f", compose_file, *args]


def health(container: str) -> tuple[str, str]:
    """(container status, health status) -- ('missing', 'missing') if absent."""
    proc = run(
        [
            str(resolve()),
            "inspect",
            "--format",
            "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
            container,
        ]
    )
    if proc.returncode != 0:
        return ("missing", "missing")
    parts = proc.stdout.split()
    return (parts[0] if parts else "?", parts[1] if len(parts) > 1 else "none")


def diagnose(seed_demo: bool, compose_file: str, container: str) -> None:
    """Everything needed to act, in one place.

    **A timeout that arrives without a reason is a timeout you cannot fix.**
    Every branch below prints something a person can act on, which is the whole
    reason this exists rather than a longer ``--wait-timeout``.
    """
    bar = "=" * 70
    print(f"\n{bar}\n the container did not become healthy in time\n{bar}")

    ps = run(compose(seed_demo, compose_file, "ps"))
    print("\n-- compose ps --")
    print(ps.stdout or ps.stderr)

    print("\n-- container health log --")
    inspect = run([str(resolve()), "inspect", "--format", "{{json .State.Health}}", container])
    print(inspect.stdout[:4000] or "(no health log: not running, or no healthcheck defined)")

    print("\n-- healthcheck run by hand, so its own words are in the record --")
    hand = run(
        compose(seed_demo, compose_file, "exec", "-T", "portal", "python", "/app/healthcheck.py")
    )
    print(hand.stdout or hand.stderr)
    print(f"   healthcheck exit={hand.returncode}")

    print("\n-- last 60 lines of the application log --")
    print(run(compose(seed_demo, compose_file, "logs", "--tail=60")).stdout)
    print(bar)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bring the portal up and wait, bounded.")
    ap.add_argument(
        "--seed-demo",
        action="store_true",
        help="load the organizers' fixture (the acceptance checker needs it)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="seconds to wait for the healthcheck (default: 120)",
    )
    ap.add_argument(
        "--up-timeout",
        type=float,
        default=180.0,
        help="seconds to allow `compose up -d` itself (default: 180)",
    )
    ap.add_argument("-f", "--file", default="docker-compose.yml", help="compose file")
    ap.add_argument("--container", default=CONTAINER, help="container name")
    args = ap.parse_args(argv)

    env = {"JJ_SEED_DEMO": "1"} if args.seed_demo else None

    # **The bring-up inherits stdio and carries its own timeout.** Two reasons,
    # both learned the hard way on a runner where this hung for two hours.
    #
    # Inheriting stdio: `capture_output=True` makes `subprocess.run` wait for EOF
    # on the child's pipes, and Compose can hold a container's log stream open
    # even with `-d`. The child may have finished perfectly while the parent
    # waits forever for a pipe that will never close.
    #
    # A timeout: whatever Compose does, this process gets to finish and say so.
    # **A bring-up step with no bound is the defect this whole module exists to
    # remove** -- applying it only to the health poll, and not to the command
    # that starts the container, would have left the original hang exactly where
    # it was.
    print("-- up -d (deliberately not --wait; see the module docstring) --", flush=True)
    up_argv = [*compose(args.seed_demo, args.file, "up", "-d")]
    try:
        proc = subprocess.run(up_argv, env={**os.environ, **(env or {})}, timeout=args.up_timeout)
    except subprocess.TimeoutExpired:
        print(f"   compose up did not return within {args.up_timeout:.0f}s")
        diagnose(args.seed_demo, args.file, args.container)
        return 124
    if proc.returncode != 0:
        print(f"compose up exited {proc.returncode}")
        return proc.returncode

    deadline = time.monotonic() + args.timeout
    tick = 0
    while True:
        state, status = health(args.container)
        if status == "healthy":
            print(f"   healthcheck green ({state})")
            return 0
        if status == "unhealthy":
            print(f"   the container reports itself unhealthy ({state})")
            diagnose(args.seed_demo, args.file, args.container)
            return 1

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"   still {status!r} after {args.timeout:.0f}s")
            diagnose(args.seed_demo, args.file, args.container)
            return 1
        tick += 1
        if tick % 5 == 0:
            print(f"   {status} ({remaining:.0f}s left)")
        time.sleep(min(2.0, max(0.1, remaining)))


if __name__ == "__main__":
    sys.exit(main())
