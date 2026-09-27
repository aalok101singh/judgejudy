#!/usr/bin/env python3
"""Prove the container boots and serves with no network at all.

`--network none` gives the container an empty network namespace: no interfaces
except loopback, no route off the host, no DNS server to ask. If the portal
boots and serves in that namespace, nothing it does on boot depends on reaching
the outside world — which is acceptance requirement 1 of 5, stated as
"brings up a working, seeded portal with the network off".

It is a stronger test than switching off the host's Wi-Fi, and it is the right
one: a test that depends on the machine's connection state cannot be run by a
judge on a train.

## Why it is detached-and-exec'd rather than one `docker run`

Three attempts, all of them instructive, and the two that failed are recorded
because each failure mode is silent:

1. **Probe inlined into `sh -c`.** `repr()` of a multi-line string emits single
   quotes; `sh` treats those as a literal, not a program. Died with
   `Syntax error: ")" unexpected`.

2. **Probe as `docker run ... sh -c "..."`.** The image's ENTRYPOINT is
   `/app/entrypoint.sh`, and passing `sh -c ...` as the command hits its `*)`
   catch-all, which execs the command and **skips migrate, collectstatic and
   gunicorn entirely**. The probe then reported
   `Connection refused` — which reads exactly like a portal that failed to
   boot, and was actually a portal that was never started.

3. **`--mount` a probe file into a foreground run.** Mounts are not available
   in the form used, and a foreground run has no way to run a second command
   after the server comes up anyway.

What works: start the container detached with the real entrypoint, poll its own
healthcheck until it passes, `docker cp` the probe in, and `docker exec` it.
`docker exec` joins the container's existing network namespace, so the probe is
still running with no network — which is the property under test.

Lesson recorded for whoever simplifies this later: an entrypoint with a
catch-all `*)` branch will happily swallow your command and leave you testing
a process that was never started. **A `Connection refused` is a statement about
the network, not about the server.**
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
PROBE = REPO / "tools" / "offline_probe.py"
NAME = "jj-offline-proof"

# Generous, because a cold start runs migrations, collectstatic and seeding
# before gunicorn binds. It is bounded so a hang is a failure, not a stall.
READY_TIMEOUT = 90.0


def docker() -> list[str]:
    """The venv interpreter, then the docker resolver — the same two the
    justfile uses, so this proof and the gate cannot disagree."""
    py = str(REPO / ".venv" / "Scripts" / "python.exe")
    if not os.path.exists(py):
        py = sys.executable
    return [py, str(REPO / "tools" / "docker.py")]


def run(
    args: list[str],
    *,
    capture: bool = True,
    check: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        docker() + args,
        cwd=REPO,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def cleanup() -> None:
    run(["rm", "-f", NAME])


def main() -> int:
    print("=" * 62)
    print(" NETWORK ISOLATION — --network none, loopback only")
    print("=" * 62)

    if not PROBE.exists():
        print(f"FAIL: {PROBE} is missing", file=sys.stderr)
        return 2

    cleanup()

    print("\n$ docker run -d --network none " + NAME)
    started = time.perf_counter()
    result = run(["run", "-d", "--network", "none", "--name", NAME, "judgejudy:local"])
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        print("FAIL: the container would not start", file=sys.stderr)
        return 1
    print(f"  {result.stdout.strip()}")

    # Poll the container's OWN healthcheck script, which is the same file the
    # Dockerfile HEALTHCHECK and the compose healthcheck use. Polling that
    # rather than a bespoke probe means this proof also demonstrates that the
    # shipped healthcheck works with no network.
    print("\n$ waiting for the container's own healthcheck (offline)")
    ready = False
    while time.perf_counter() - started < READY_TIMEOUT:
        probe = run(["exec", NAME, "python", "/app/healthcheck.py"])
        if probe.returncode == 0:
            print(f"  healthy after {time.perf_counter() - started:.1f}s: "
                  f"{(probe.stdout or '').strip()}")
            ready = True
            break
        time.sleep(1.0)

    if not ready:
        print(f"\nFAIL: not healthy within {READY_TIMEOUT:.0f}s", file=sys.stderr)
        logs = run(["logs", "--tail", "60", NAME])
        sys.stderr.write(logs.stdout or "")
        sys.stderr.write(logs.stderr or "")
        cleanup()
        return 1

    # The probe goes in as a file. See the module docstring: inlining it
    # through two layers of shell quoting is what this design is avoiding.
    run(["cp", str(PROBE), f"{NAME}:/probe.py"])
    print("\n$ probing from inside the container (same empty netns)")
    probe = run(["exec", NAME, "python", "/probe.py"], capture=False)
    cleanup()

    print()
    if probe.returncode == 0:
        print("=" * 62)
        print(" PROVED: the portal boots and serves with no network namespace.")
        print(" No CDN, no hosted database, no external API, no API key.")
        print(" The shipped healthcheck also passes offline.")
        print("=" * 62)
        return 0

    print("=" * 62)
    print(f" NOT PROVED: the in-namespace probe exited {probe.returncode}.")
    print("=" * 62)
    return 1


if __name__ == "__main__":
    sys.exit(main())
