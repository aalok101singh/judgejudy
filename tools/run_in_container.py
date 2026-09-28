#!/usr/bin/env python3
"""Run a management command inside the running container, or explain its absence.

Three things go wrong if the justfile does this with a shell `||`:

1. **cmd.exe mangles a quoted left-hand side of `||`.** The repository path
   contains a space ("Judge Judy"), so the interpreter must be quoted; and
   cmd.exe's handling of `"C:\\...\\python.exe" something || echo fallback`
   is not the same as its handling of the same command without the `||`. The
   first draft of this justfile hit exactly that, and the symptom was
   `'C:\\Users\\Aalok\\Desktop\\Judge' is not recognized as an internal or
   external command` — a message about a path, pointing at a quoting bug.

2. **The `||` swallows the distinction between "not built yet" and "broken".**
   Every management command in this project arrives on a schedule, and the
   honest output for one that does not exist yet is SKIP with the feature that
   owns it. That is information, and it belongs in a message rather than in a
   shell's exit code.

3. **A SKIP that prints a Python traceback is a SKIP nobody reads.** During
   FEAT-01 the entrypoint guards seeding the same way, and it logs a normal line
   rather than a traceback — a red log line you have learned to ignore is a red
   log line that later means something.

So: SKIP for a command that does not exist yet, and a real failure (with full
output) for anything else. A missing command is a schedule; a failing command
is a defect.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# Which feature owns each not-yet-built command, so the SKIP line says why
# rather than just that.
OWNERS = {
    "isolation_proof": "FEAT-02",
    "verify_census": "FEAT-03",
    "load_fixtures": "FEAT-03",
}


def venv_python() -> str:
    candidate = REPO / ".venv" / "Scripts" / "python.exe"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_in_container.py <management-command> [args...]", file=sys.stderr)
        return 2

    command = sys.argv[1:]
    name = command[0]
    owner = OWNERS.get(name, "a later feature")

    docker = [venv_python(), str(REPO / "tools" / "docker.py")]

    # `docker exec`, NOT `docker compose exec` — so there is no `-T`/`--tty`
    # flag. The first draft of this file used `-T`, which is a
    # `docker compose exec` option, and docker exec rejected it with
    # `unknown shorthand flag: 'T' in -T`.
    #
    # `docker exec` also allocates no TTY by default, so the output is clean in
    # a justfile, which is what we want. And it addresses the container by
    # name, so it depends on compose's default naming — which is a fair trade
    # for one fewer moving part, and `tools/doctor.py` is where a mismatch
    # would surface.
    def in_container(*args: str) -> list[str]:
        return [*docker, "exec", "judgejudy-portal-1", *args]

    # `help` is asked first: it is cheap, it exits 0 whatever the project
    # contains, and it lists every registered command. That is how we tell
    # "not built yet" from "built and broken" without a try/except on stderr.
    listing = subprocess.run(  # noqa: S603
        in_container("python", "src/manage.py", "help"),
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if listing.returncode != 0:
        # The container is not reachable at all. That is a real failure and it
        # is not the same thing as an unbuilt command.
        print(f"FAIL: cannot reach the container to check for {name!r}.")
        print("  Is it running?  just up")
        if listing.stderr.strip():
            print(listing.stderr.strip())
        return 1

    if name not in listing.stdout:
        print(f"SKIP: {name!r} is not built yet (owned by {owner}).")
        return 0

    result = subprocess.run(  # noqa: S603
        in_container("python", "src/manage.py", *command),
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
