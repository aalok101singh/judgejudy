#!/usr/bin/env python3
"""JJ01 -- forbid an unscoped read of a ``Review`` queryset.

**Why this is a separate program and not a ruff plugin.** Ruff's plugin API is
Rust. A Python-side AST check is the version of this rule we can write, review
and test inside the window, and the rule it enforces is *syntactic* -- which is
the one kind of rule that is mechanically checkable at all (D-03). The
alternative, expressing it in ``pyproject.toml`` with ruff's ``banned-api``, was
rejected for a specific reason rather than a general one: ``banned-api`` can only
ban an exact dotted path, so it would have to be fed ``Review.objects.all`` and
would silently allow ``Review.objects.filter(...)``, which is the same leak by
another name. A banned *method name on a named model* needs the two pieces of
knowledge together, and that is what an AST walk has and a string match does not.

**What it forbids.** Any read off ``Review.objects`` that is not a sanctioned
accessor. Reads are ``.all()``, ``.filter()``, ``.get()``, ``.count()`` and the
rest of the queryset surface; writes are ``.create()``, ``.bulk_create()``,
``.get_or_create()`` and friends, which do not leak anything and which every
test needs.

**What it cannot catch, stated rather than implied.** It is a *syntactic* rule,
so it sees ``Review.objects.all()`` and not ``manager.all()`` where
``manager = Review.objects`` on the previous line. A determined bypass exists and
always will; the point is that the accidental form -- the one a tired session
writes at hour 40 -- is a build failure rather than a review comment. The
property being enforced is "there is no code path *written in the obvious way*
from a view to an unscoped Review", not "no code path whatsoever".

**Why the allowlist is a named, reasoned, asserted list.** Three modules need
the unscoped form to exist at all: the accessor that *is* the scope, the module
that builds the manager, and the one test file that establishes ground truth for
the receipt's "3 of 126" denominator. An escape hatch with no list is an escape
hatch with no audit trail, so the list lives here as data, every entry carries a
reason, and ``tests/test_isolation_lint.py`` fails if an entry has no reason or
if the list grows.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The models whose reads must be scoped. One model today, on purpose.
#:
#: ``Assignment`` and ``Score`` are NOT here, and the reason is worth stating
#: because leaving them out is a real gap: a ``Score.objects.all()`` in a view
#: leaks every score in the event, which is the same isolation failure one hop
#: over. They are absent because **they have no scoped accessor yet**, and adding
#: them to this list before that accessor exists would ban every call with no
#: alternative -- and a ban with no alternative gets deleted the first time
#: somebody is on a deadline. The order is: write ``for_actor`` on both, then add
#: them here, in the same commit.
GUARDED_MODELS = {"Review"}

#: The only calls that may be made on a guarded model's manager. Everything else
#: is a read and needs an actor.
SANCTIONED_METHODS = {
    # The accessors themselves.
    "for_actor",
    "for_actor_and_subject",
    # Writes. A test factory calling create() leaks nothing.
    "create",
    "bulk_create",
    "get_or_create",
    "update_or_create",
    "bulk_update",
    # Plumbing.
    "objects",
    "_default_manager",
    "as_manager",
    "using",
    "db_manager",
}

#: Modules that must be able to write the unscoped form, each with the reason.
#: Asserted by tests/test_isolation_lint.py: an entry without a reason, or a
#: list that has grown, is a failing test rather than a review comment.
ALLOWLIST = {
    "src/reviewer/reviews/queryset.py": (
        "This IS the accessor. It has to be able to see the whole event to compute "
        "the receipt's denominator, and that call is the one place allowed to."
    ),
    "src/reviewer/reviews/management/commands/isolation_proof.py": (
        "The published matrix. This is the one file whose entire job is to see "
        "every review and print what each role may see, so scoping it would leave "
        "a proof that proves nothing. It is also the only file that reports the "
        "rule's own name in its output, so a reader can see the exception exists."
    ),
    "src/reviewer/reviews/models.py": (
        "Declares the manager (ReviewQuerySet.as_manager()) and the indexes. It "
        "reads no rows; a call added here would be caught by the review of the "
        "diff rather than by this file."
    ),
    "tools/check_isolation.py": (
        "The rule's own source. The names above are strings in it, and a checker "
        "that flags its own table of forbidden spellings fires on every run."
    ),
    "tests/ground_truth.py": (
        "The event-wide totals every scoping test checks itself against. The "
        "receipt claims '3 of 126', and 126 has to be computed independently of "
        "the filter that produced the 3 -- otherwise the receipt is quoting its "
        "own filter back at the reader as evidence. One named module, one reason."
    ),
}

#: How many entries the allowlist is allowed to have. A cap and not a prohibition:
#: if a sixth module ever needs the unscoped form, the answer is to write a scoped
#: accessor for it, and this number is what makes "just add it to the list" a
#: decision rather than a reflex. The FEAT-02 value is 5.
ALLOWLIST_CAP = 5

#: The default source roots. `tests` and `tools` are included on purpose: a test
#: that reaches for the unscoped form is an unscoped path in a place nobody
#: reviews (see pyproject.toml's [tool.ruff] src comment, which says the same
#: thing about linting).
DEFAULT_ROOTS = ["src", "tests", "tools"]


class Finding:
    """One violation, with enough context to fix it without opening the file."""

    def __init__(self, path: pathlib.Path, node: ast.AST, method: str) -> None:
        self.path = path
        self.line = getattr(node, "lineno", 0)
        self.col = getattr(node, "col_offset", 0)
        self.method = method

    def render(self, root: pathlib.Path) -> str:
        try:
            shown = self.path.relative_to(root)
        except ValueError:
            shown = self.path
        return (
            f"{shown}:{self.line}:{self.col}: JJ01 unscoped read of a Review "
            f"queryset ({self.method!r}). Use Review.objects.for_actor(actor) -- "
            "the unscoped form is the isolation bug the spec names."
        )

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "line": self.line,
            "col": self.col,
            "method": self.method,
        }


def dotted_name(node: ast.AST) -> str | None:
    """Render ``Review.objects.all`` as a string, or None if it is not an attribute chain."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _is_guarded_call(node: ast.Call) -> tuple[bool, str | None]:
    """Whether this call is an unscoped read, and the method name if it is."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False, None
    method = func.attr
    if method in SANCTIONED_METHODS:
        return False, None
    dotted = dotted_name(func)
    if dotted is None:
        return False, None
    for model in GUARDED_MODELS:
        for manager in ("objects", "_default_manager"):
            if dotted == f"{model}.{manager}.{method}":
                return True, method
    return False, None


class UnparsableFileError(Exception):
    """A file the rule could not read. Reported, never treated as clean.

    A rule that silently exempts anything it fails to parse has the worst
    possible failure direction for a security check: a file it cannot read
    looks exactly like a file with no findings. So this is an error with its
    own exit code, and the message says which file and why.
    """


def check_source(path: pathlib.Path, root: pathlib.Path) -> list[Finding]:
    """Parse one file and return its JJ01 findings."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise UnparsableFileError(f"{rel(path)}: {exc}") from exc
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        unscoped, method = _is_guarded_call(node)
        if unscoped:
            findings.append(Finding(path, node, method))
    return findings


def iter_python_files(roots) -> list[pathlib.Path]:
    files = []
    for root in roots:
        base = ROOT / root
        if base.is_file() and base.suffix == ".py":
            files.append(base)
        elif base.is_dir():
            files.extend(sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts))
    return files


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "roots",
        nargs="*",
        default=DEFAULT_ROOTS,
        help="files or directories to check. Default: " + ", ".join(DEFAULT_ROOTS),
    )
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument(
        "--explain-allowlist",
        action="store_true",
        help="print every allowlisted file and why, then exit",
    )
    args = ap.parse_args(argv)

    if args.explain_allowlist:
        for path, reason in sorted(ALLOWLIST.items()):
            print(f"{path}\n    {reason}")
        return 0

    findings: list[Finding] = []
    unparsable: list[str] = []
    files = iter_python_files(args.roots)
    for path in files:
        if rel(path) in ALLOWLIST:
            continue
        try:
            findings.extend(check_source(path, ROOT))
        except UnparsableFileError as exc:
            unparsable.append(str(exc))

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "findings": [f.as_dict() for f in findings],
                    "unparsable": unparsable,
                    "files_checked": len(files),
                },
                indent=2,
            )
        )
        return 1 if (findings or unparsable) else 0

    for finding in findings:
        print(finding.render(ROOT))
    for problem in unparsable:
        print(f"{problem}: JJ02 file could not be parsed, so it was NOT checked.")

    if findings or unparsable:
        if findings:
            print(
                f"\nJJ01: {len(findings)} unscoped Review read(s) in {len(files)} file(s) checked."
            )
        if unparsable:
            print(
                f"\nJJ02: {len(unparsable)} file(s) could not be parsed and are "
                "therefore unchecked. A rule that cannot read a file has not "
                "cleared it."
            )
        print("The only sanctioned form is Review.objects.for_actor(actor).")
        return 1
    print(f"JJ01: no unscoped Review reads in {len(files)} file(s) checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
