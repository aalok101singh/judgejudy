#!/usr/bin/env python3
"""Resolve the Docker CLI and exec it with the arguments given.

Why this file exists, in the project's own terms:

`docker --version` returned NOT FOUND for an entire phase of this build, and
the honest-looking conclusion drawn from it — "Docker is not installed" — was
**wrong**. Docker Desktop was installed and running the whole time. It is
installed *per-user*, at a path that was in neither the in-session PATH, nor
the User PATH, nor the Machine PATH (F-34). A failing command is evidence that
a command failed, not evidence about why it failed, and there were three
candidate explanations of which two were live.

A justfile that calls bare `docker` re-creates exactly that condition every
time somebody opens a fresh terminal. So the gate resolves the binary by
absolute path first and falls back to the PATH only if that fails, and the
failure message names the real cause instead of implying a missing install.

Stdlib only.

## Why this is subprocess and not os.execv

The first draft of this file used `os.execv`, on the reasonable-sounding
grounds that replacing the process is the cleanest possible argument
pass-through: the parent disappears, so the exit code, the terminal and the
signal handling are all docker's problem and none of them can be lost.

**That is wrong on Windows, and it was caught by running it rather than by
reasoning about it.** `os.execv` takes a list, but on Windows it does not
quote the elements when it builds a command line. An argument containing a
space arrives at the far end as two arguments. Concretely:

    os.execv(docker, [docker, "run", "--rm", "img", "sh", "-c", "echo A; echo B"])
      -> the container runs `sh -c echo A; echo B`
      -> `sh -c echo` prints an empty line, and `A;` `echo` `B` become its
         positional parameters. Nothing at all is printed.

`sh -c "..."` is exactly what the justfile's `sh` recipe does, so this broke a
real recipe while exiting 0 — the worst possible combination, and the same
shape as F-32 (`run.py` prints FAIL and returns 0).

`subprocess.run` with a list is the fix: on Windows it quotes correctly via
`list2cmdline`, and on POSIX it passes the vector straight through. The exit
code is propagated explicitly below, so nothing is lost by not exec'ing.

F-39, and the lesson is F-11's: a documented stdlib function recalled rather
than executed is a library claim recalled rather than executed.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

# The per-user Docker Desktop location, recorded from this machine. F-34.
CANDIDATES = [
    pathlib.Path(r"C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"),
    pathlib.Path("/usr/local/bin/docker"),
    pathlib.Path("/usr/bin/docker"),
    pathlib.Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
]

# Overridable for a machine that installs elsewhere, or for a test that wants
# to prove the fallback path works.
ENV_OVERRIDE = "JJ_DOCKER"


def resolve() -> str | None:
    """Return the docker CLI path, or None if it genuinely cannot be found."""
    override = os.environ.get(ENV_OVERRIDE)
    if override and pathlib.Path(override).exists():
        return override

    for candidate in CANDIDATES:
        if candidate.exists():
            return str(candidate)

    # Last resort: whatever the PATH offers. This is the path a stale shell
    # takes, and the one that was broken for a whole phase.
    return shutil.which("docker")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: docker.py <docker-subcommand> [args...]", file=sys.stderr)
        return 2

    # `--seed-demo` is ours, consumed here rather than passed on to docker. It is
    # the only portable way to put an environment variable in front of a compose
    # command from a justfile on this machine: **just runs recipes through
    # cmd.exe**, so `export VAR := "1"` fails with "not recognized as an internal
    # or external command", and a shell `set VAR=1` sets positional parameters
    # rather than the environment. Both were tried; both silently did nothing,
    # which is how the acceptance gate came to score an empty portal and report
    # three regressions that were not regressions. Doing it in Python is
    # dialect-free and testable.
    seed_demo = False
    argv = sys.argv[1:]
    if argv and argv[0] == "--seed-demo":
        seed_demo = True
        argv = argv[1:]

    binary = resolve()
    if not binary:
        sys.stderr.write(
            "docker could not be found.\n"
            "\n"
            "This is almost certainly a PATH problem, not a missing install.\n"
            "Docker Desktop is installed per-user on this machine. The binary\n"
            "lives at:\n"
            "  C:\\Users\\Aalok\\AppData\\Local\\Programs\\DockerDesktop\\resources\\bin\\\n"
            "\n"
            "If you have just fixed the PATH, open a NEW terminal — a shell\n"
            "opened before the change keeps its old PATH. Do not reinstall\n"
            "Docker; it was never missing. (F-34)\n"
        )
        return 127

    # subprocess, not os.execv — see the module docstring. The list is passed
    # as a list, which is the whole point: on Windows this quotes arguments
    # containing spaces correctly, and `sh -c "a; b"` therefore survives.
    #
    # The exit code is propagated verbatim. A wrapper that reported success
    # because IT succeeded, rather than because docker did, would be a second
    # place for the F-32 class of bug to hide.
    # `env=None` inherits this process's environment unchanged, which is the
    # default for everything except `--seed-demo`.
    env = None
    if seed_demo:
        env = os.environ.copy()
        env["JJ_SEED_DEMO"] = "1"

    try:
        return subprocess.run([binary, *argv], cwd=os.getcwd(), env=env).returncode
    except OSError as exc:
        sys.stderr.write(f"docker resolved to {binary} but could not be run: {exc}\n")
        return 127


if __name__ == "__main__":
    sys.exit(main())
