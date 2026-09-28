#!/usr/bin/env python3
"""Assert the interpreter is the one the plan means, and name it if it is not.

F-38 is the reason this file exists, and it is worth stating in full because
the shape of it is the whole lesson.

There are three Pythons in play on this machine and two of them are not the one
the plan refers to:

    python  (on PATH)            3.14.6   no Django installed
    .venv\\Scripts\\python.exe    3.13.13   Django 5.2.17, DRF 3.18.1
    container python:3.13-slim   3.13.15   installed by the Dockerfile

Django 5.2.17 declares `Requires-Python: >=3.10` with **no upper bound**, so
the version pin in requirements.txt looks satisfied on 3.14.6 and the
dependency resolver will not stop the mistake. A bare `python manage.py` in a
fresh terminal therefore fails on the first import, with an ImportError that
reads like a missing dependency rather than a missing interpreter.

Naming the venv path explicitly fixes half of it. This script is the other
half: it *verifies* rather than assumes, so a substitution is a clear message
here instead of an ImportError twenty frames later.

The exact expected version is a command-line argument rather than a constant
in this file, so the same guard can check the container's 3.13.15 (a different
patch release, same minor line) and the local 3.13.13 without either being
special-cased.

Exit codes: 0 = correct line. 1 = wrong minor version. 2 = not Python at all.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert the Python minor version.")
    parser.add_argument("--expect", default="3.13", help="expected major.minor (default: 3.13)")
    parser.add_argument(
        "--allow-patch",
        action="store_true",
        default=True,
        help="a differing patch release is fine (default)",
    )
    parser.add_argument(
        "--exact",
        dest="allow_patch",
        action="store_false",
        help="require the full major.minor.patch to match",
    )
    args = parser.parse_args()

    expected = tuple(int(part) for part in args.expect.split("."))
    actual = sys.version_info[: len(expected)]

    where = sys.executable or "(unknown)"

    if actual == expected:
        print(f"   interpreter ok: Python {sys.version.split()[0]} at {where}")
        return 0

    if not args.allow_patch and actual[:3] == expected[:3]:
        print(f"   interpreter ok: Python {sys.version.split()[0]} at {where}")
        return 0

    print("", file=sys.stderr)
    print("FATAL: wrong interpreter.", file=sys.stderr)
    print(f"  expected: Python {args.expect}", file=sys.stderr)
    print(f"  actual:   Python {sys.version.split()[0]}", file=sys.stderr)
    print(f"  resolved: {where}", file=sys.stderr)
    print("", file=sys.stderr)
    if actual[:2] != expected[:2]:
        print("  The ambient `python` on PATH is a different minor version and", file=sys.stderr)
        print("  does not have Django installed. Django 5.2's Requires-Python", file=sys.stderr)
        print("  has no upper bound, so the pin will not catch this for you.", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Use the venv interpreter explicitly:", file=sys.stderr)
        print("    .venv\\Scripts\\python.exe   (Windows)", file=sys.stderr)
        print("    .venv/bin/python            (macOS / Linux)", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Inside the container the image's own Python is used and this", file=sys.stderr)
        print("  is never a problem. This is finding F-38.", file=sys.stderr)
    else:
        print(f"  The minor version matches {args.expect} but the full version", file=sys.stderr)
        print("  does not. Pass --exact if that should be fatal.", file=sys.stderr)
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
