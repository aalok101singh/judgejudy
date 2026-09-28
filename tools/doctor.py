#!/usr/bin/env python3
"""Report the toolchain, and fail if anything needed to build is missing.

Run before a break, and after any environment change. It is deliberately
read-only and takes about a second.

Why it is a script and not a justfile recipe body: the recipe version needed
`python -c "import a, b; print(...)"` inside `cmd /c`, and cmd.exe's handling
of nested quotes is the reason the first draft of the justfile failed. The
lesson is not "avoid cmd" — the fork has to work on a hackathon laptop — it
is that a diagnostic which itself can fail to parse is not a diagnostic.

Three checks, in the order that fails cheapest:

1. **The interpreter is 3.13.** F-38. The ambient `python` is 3.14.6 with no
   Django, and Django's own `Requires-Python: >=3.10` has no upper bound, so
   nothing upstream will stop it.
2. **Docker is reachable, and we know WHICH docker.** F-34. It is installed
   per-user, so a shell opened before the PATH fix cannot see it. Reporting the
   resolved path is the point: "docker is not installed" was the wrong
   diagnosis for a whole phase of this build, and the honest one was a PATH
   problem.
3. **`just` is present.** F-35. `just check` is the gate command, named in four
   files, and the binary was absent until it was checked.

Exit code is 0 when everything is present, 1 when something is missing. The
missing thing is named, and where it is a PATH problem the message says so
rather than implying a missing install.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# Import the resolver rather than repeating its paths.
#
# The first draft of this file carried its own copy of the per-user Docker
# path (F-34). `tools/mutation_test.py` then removed the path from
# `docker.py` — the F-34 regression — and doctor.py reported everything fine,
# because doctor.py was not using docker.py. Two copies of one fact, one of
# which nothing checks.
#
# So: import it. If the resolver is broken, this tool is broken too, and that
# is the correct coupling for a diagnostic.
sys.path.insert(0, str(REPO / "tools"))
import docker as docker_resolver  # noqa: E402  (path set up immediately above)

# The expected runtime packages and the reason each is in the image. The
# versions are the resolver's output, not ours (F-23), so this checks presence
# and major/minor rather than an exact pin that a patch release would break.
EXPECTED = {
    "django": "5.2",
    "rest_framework": "3.18",
    "drf_spectacular": "0.30",
    "whitenoise": "6.12",
    "cryptography": "50.0",
}

DOCKER_FALLBACK = pathlib.Path(
    r"C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
)


def classify_docker_source(binary: str) -> str:
    """Report WHERE a docker binary came from, which is the F-34 diagnosis.

    A bare "docker works" is not enough. This project spent a whole phase
    believing Docker was not installed, because `docker --version` printed
    NOT FOUND from a shell that could not see the per-user install. The
    question that settles it is never "does it work" but "which binary, and is
    it on the PATH from a plain `shutil.which`".

    So the three states are reported separately:

    - resolved from the per-user path  -> correct, and fragile (a fresh shell
      that predates the PATH fix will not see it)
    - resolved from the PATH            -> a shell that can see it
    - not found                         -> a PATH problem, not a missing install
    """
    if pathlib.Path(binary) == DOCKER_FALLBACK:
        return "per-user install path (F-34)"
    if binary == shutil.which("docker"):
        return "PATH"
    return "other"


def rule(title: str) -> None:
    print(f"\n== {title} ==")


def check_interpreter() -> list[str]:
    problems: list[str] = []
    rule("interpreter")

    print(f"   version:  {sys.version.split()[0]}")
    print(f"   resolved: {sys.executable}")
    print(f"   cwd:      {os.getcwd()}")

    if sys.version_info[:2] != (3, 13):
        problems.append(f"interpreter is {sys.version.split()[0]}, expected the 3.13 line (F-38)")
        print("   FAIL      not the 3.13 line — Django 5.2's Requires-Python has no")
        print("             upper bound, so the pin cannot catch this for you (F-38)")
    else:
        print("   ok        3.13 line")

    for name, want in EXPECTED.items():
        try:
            module = importlib.import_module(name)
        except ImportError:
            problems.append(f"{name} is not importable")
            print(f"   MISSING   {name}")
            continue
        got = getattr(module, "__version__", None) or getattr(module, "VERSION", None)
        if callable(got):
            got = got()
        if got is None:
            # Django exposes get_version() rather than __version__ on some
            # paths; absence of a version string is not a failure worth
            # reporting when the import succeeded.
            print(f"   ok        {name} (imports; no version attribute)")
            continue
        got = str(got)
        if got.startswith(want):
            print(f"   ok        {name} {got}")
        else:
            problems.append(f"{name} is {got}, expected {want}.x")
            print(f"   MISMATCH  {name} {got}, expected {want}.x")

    return problems


def check_docker() -> list[str]:
    problems: list[str] = []
    rule("docker")

    # Delegate to the one resolver the justfile and the gates use, so this tool
    # cannot report a healthy toolchain the gate would then fail to find.
    binary = docker_resolver.resolve()
    source = classify_docker_source(binary) if binary else None

    if not binary:
        print("   NOT FOUND on PATH or at the known per-user path.")
        print()
        print("   Docker Desktop IS installed per-user on this machine. A shell")
        print("   opened before the PATH fix keeps its old PATH (F-34).")
        print("   Open a NEW terminal. Do not reinstall Docker; it was never missing.")
        problems.append("docker not found — almost certainly PATH, not install (F-34)")
        return problems

    print(f"   binary:   {binary}")
    print(f"   via:      {source}")

    for args, label in (
        (["--version"], "version"),
        (["compose", "version"], "compose"),
    ):
        try:
            result = subprocess.run(
                [binary, *args],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            problems.append(f"`docker {label}` failed: {exc}")
            print(f"   FAIL      docker {label}: {type(exc).__name__}: {exc}")
            continue

        if result.returncode != 0:
            problems.append(f"`docker {label}` exited {result.returncode}")
            print(f"   FAIL      docker {label} exited {result.returncode}")
            continue

        line = (result.stdout or result.stderr).strip().splitlines()
        print(f"   ok        {line[0] if line else '(no output)'}")

    # The daemon. A working CLI with a stopped daemon is a fourth state that
    # reads exactly like "installed" from the outside, and the acceptance
    # criteria are about the daemon.
    try:
        result = subprocess.run(
            [binary, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            print(f"   ok        daemon up, server {result.stdout.strip()}")
        else:
            tail = (result.stderr or "").strip().splitlines()
            detail = tail[-1] if tail else "unknown"
            print(f"   WARN      daemon not responding: {detail}")
            print("             Start Docker Desktop and re-run. The image can still be built.")
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"   WARN      `docker info` failed: {type(exc).__name__}: {exc}")

    return problems


def check_just() -> list[str]:
    problems: list[str] = []
    rule("gate tooling")
    found = shutil.which("just")
    if found:
        try:
            result = subprocess.run(
                [found, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            print(f"   ok        {result.stdout.strip()}")
        except (OSError, subprocess.SubprocessError) as exc:
            problems.append(f"`just --version` failed: {exc}")
    else:
        print("   MISSING   just — `just check` is the gate command (F-35)")
        print("             winget install --id Casey.Just")
        problems.append("just not installed (F-35)")

    for path in (
        "docker-compose.yml",
        "Dockerfile",
        ".dogfood.toml",
        "docker/entrypoint.sh",
        "docker/healthcheck.py",
        "justfile",
        "LICENSE",
        "README.md",
    ):
        exists = (REPO / path).exists()
        print(f"   {'ok       ' if exists else 'MISSING  '} {path}")
        if not exists and path not in (".dogfood.toml",):
            problems.append(f"{path} is missing")

    return problems


def main() -> int:
    print("=" * 62)
    print(" Judge Judy — toolchain check")
    print(f" {REPO}")
    print("=" * 62)

    problems = []
    problems += check_interpreter()
    problems += check_docker()
    problems += check_just()

    print("\n" + "=" * 62)
    if problems:
        print(f" NOT READY — {len(problems)} problem(s):")
        for problem in problems:
            print(f"   - {problem}")
        print("=" * 62)
        return 1

    print(" READY — interpreter, container runtime and gate tooling all present.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
