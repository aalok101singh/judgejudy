"""The isolation lint rule, proved in BOTH directions.

**Why this file exists at all.** The build plan's acceptance line is *"the lint
rule fires on a deliberately unscoped view and passes when scoped"*. A test that
only ran the rule over the repository and asserted it was clean would satisfy
the second half of that sentence and prove nothing about the first -- and a rule
that has only ever passed is not evidence of anything (F-33). So the deliberately
unscoped view is written to disk and the rule is run against it, and both the
firing and the non-firing are asserted.

**What is asserted, and why not a substring** (F-41). Not ``"JJ01" in output``:
a marker word is satisfied by a rule that fires for the wrong reason, or by a
message that was never going to be right. The assertions are on the exit code
and on the *specific finding* -- the method name and the line number -- so a rule
that flagged everything, or flagged a different call, fails.

These tests invoke the checker as a subprocess rather than importing it. The
exit code is the contract; a unit test of the return value of ``main()`` would
pass even if ``sys.exit`` were dropped and the tool stopped gating anything.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CHECKER = REPO / "tools" / "check_isolation.py"

#: A view that reaches for the whole table. This is the bug the spec names:
#: "hiding another judge's scores in your template is not refusing".
UNSCOPED_VIEW = '''\
"""A deliberately unscoped view. Written by a test, never shipped."""

from reviewer.reviews.models import Review


def all_reviews(request):
    return Review.objects.all()


def one_review(request, pk):
    return Review.objects.get(pk=pk)


def some_reviews(request, **params):
    return Review.objects.filter(**params).order_by("id")
'''

#: The same view, correctly scoped. Every read goes through the accessor.
SCOPED_VIEW = '''\
"""The same view, scoped. Also written by a test, never shipped."""

from reviewer.isolation import Actor
from reviewer.reviews.models import Review


def all_reviews(request, event):
    return Review.objects.for_actor(Actor.for_request(request, event))


def one_review(request, event, pk):
    return Review.objects.for_actor(Actor.for_request(request, event)).get(pk=pk)


def some_reviews(request, event, **params):
    actor = Actor.for_request(request, event)
    return Review.objects.for_actor(actor).filter(**params).order_by("id")
'''


def run_checker(*roots: str) -> subprocess.CompletedProcess:
    """Run the real CLI and return the completed process."""
    return subprocess.run(
        [sys.executable, str(CHECKER), *roots],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def findings(result: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in result.stdout.splitlines() if ": JJ01 " in ln]


class TestTheRuleFires:
    def test_an_unscoped_view_is_rejected(self, tmp_path):
        view = tmp_path / "leaky_view.py"
        view.write_text(UNSCOPED_VIEW, encoding="utf-8")
        result = run_checker(str(view))
        assert result.returncode == 1, (
            "JJ01 must exit non-zero on an unscoped read. It exited "
            f"{result.returncode} with output:\n{result.stdout}"
        )

    def test_it_names_each_offending_call(self, tmp_path):
        view = tmp_path / "leaky_view.py"
        view.write_text(UNSCOPED_VIEW, encoding="utf-8")
        found = findings(run_checker(str(view)))
        # Three reads, three findings. Asserting the COUNT matters: a rule that
        # reports once per file would pass this file and leave the other two
        # calls in place for someone to find at a break.
        assert len(found) == 3, f"expected 3 findings, got {len(found)}: {found}"

    def test_it_names_the_specific_method(self, tmp_path):
        view = tmp_path / "leaky_view.py"
        view.write_text(UNSCOPED_VIEW, encoding="utf-8")
        found = " ".join(findings(run_checker(str(view))))
        for method in ("'all'", "'get'", "'filter'"):
            assert method in found, f"JJ01 did not name {method}: {found}"

    def test_it_points_at_the_offending_line(self, tmp_path):
        view = tmp_path / "leaky_view.py"
        view.write_text(UNSCOPED_VIEW, encoding="utf-8")
        result = run_checker(str(view))
        # Read the expected line out of the source rather than hardcoding it: a
        # line number typed next to the fixture is a number that goes stale the
        # first time the fixture is edited, and then this test fails for a reason
        # that has nothing to do with the rule.
        expected = UNSCOPED_VIEW.splitlines().index("    return Review.objects.all()") + 1
        assert f":{expected}:" in result.stdout, (
            f"JJ01 must point at line {expected} of the call, not the top of the "
            f"file:\n{result.stdout}"
        )

    def test_the_message_says_what_to_do_instead(self, tmp_path):
        view = tmp_path / "leaky_view.py"
        view.write_text(UNSCOPED_VIEW, encoding="utf-8")
        assert "for_actor" in run_checker(str(view)).stdout


class TestTheRulePasses:
    def test_a_scoped_view_is_accepted(self, tmp_path):
        view = tmp_path / "scoped_view.py"
        view.write_text(SCOPED_VIEW, encoding="utf-8")
        result = run_checker(str(view))
        assert result.returncode == 0, "JJ01 rejected a correctly scoped view:\n" + result.stdout

    def test_writes_are_allowed(self, tmp_path):
        """`create()` reads nothing, and a test suite without it cannot exist."""
        factory = tmp_path / "factory.py"
        factory.write_text(
            "from reviewer.reviews.models import Review\n"
            "\n"
            "def make(**kw):\n"
            "    return Review.objects.create(**kw)\n"
            "\n"
            "def make_many(rows):\n"
            "    return Review.objects.bulk_create(rows)\n",
            encoding="utf-8",
        )
        result = run_checker(str(factory))
        assert result.returncode == 0, result.stdout

    def test_an_unrelated_model_is_not_flagged(self, tmp_path):
        """The rule is about Review. Flagging every manager would make it noise."""
        other = tmp_path / "other.py"
        other.write_text(
            "from reviewer.events.models import Event\n"
            "\n"
            "def every_event():\n"
            "    return Event.objects.all()\n",
            encoding="utf-8",
        )
        assert run_checker(str(other)).returncode == 0

    def test_the_repository_is_clean(self):
        """The real gate: the actual tree has no unscoped read."""
        result = run_checker()
        assert result.returncode == 0, result.stdout


class TestCoverage:
    """Where the rule looks is part of what it means."""

    def test_it_scans_tests_and_tools_not_just_src(self):
        """A test holding an unscoped handle is an unscoped path nobody reviews."""
        import tools.check_isolation as checker

        assert set(checker.DEFAULT_ROOTS) == {"src", "tests", "tools"}

    def test_it_actually_flags_a_file_in_the_tests_tree(self, tmp_path):
        """Proves the previous test's claim rather than restating it.

        `DEFAULT_ROOTS` could say "tests" and `iter_python_files` could skip the
        directory, and the previous test would still pass. This one puts an
        unscoped read at a path under tests/ and checks it is found.
        """
        import tools.check_isolation as checker

        staged = REPO / "tests" / "_jj01_probe.py"
        assert not staged.exists(), (
            "a leftover probe file from an earlier run would make this test "
            "assert against its own leftover"
        )
        staged.write_text(
            "from reviewer.reviews.models import Review\n"
            "\n"
            "def probe():\n"
            "    return Review.objects.all()\n",
            encoding="utf-8",
        )
        try:
            files = checker.iter_python_files(["tests"])
            assert staged in files, "iter_python_files skipped the tests tree"
            assert checker.check_source(staged, REPO), "check_source found nothing"
        finally:
            staged.unlink()


class TestAllowlist:
    """The escape hatch has to be auditable, or it is not an escape hatch."""

    def test_every_entry_carries_a_real_reason(self):
        import tools.check_isolation as checker

        for path, reason in checker.ALLOWLIST.items():
            assert isinstance(reason, str)
            # Long enough to be a sentence. A bare filename is how an
            # allowlist becomes a list of files nobody can query.
            assert len(reason.split()) >= 12, f"{path} has no substantive reason"

    def test_the_allowlist_has_not_grown(self):
        import tools.check_isolation as checker

        assert len(checker.ALLOWLIST) <= checker.ALLOWLIST_CAP, (
            f"the allowlist has grown to {len(checker.ALLOWLIST)} entries "
            f"(cap {checker.ALLOWLIST_CAP}). A sixth module needing the "
            "unscoped form means a sixth accessor is missing, not that the "
            "exception list is short."
        )

    def test_every_entry_points_at_a_file_that_exists(self):
        """A stale entry silently disables the rule for a file nobody is reading.

        Renaming `queryset.py` leaves an allowlist key matching nothing, and the
        next person reads a clean rule as evidence the accessor is not exempt.
        """
        import tools.check_isolation as checker

        for path in checker.ALLOWLIST:
            assert (REPO / path).is_file(), (
                f"allowlist entry {path!r} does not exist. Either the file moved "
                "or the entry is dead weight; both should be a diff, not silence."
            )

    def test_the_exceptions_are_explained_on_request(self):
        result = run_checker("--explain-allowlist")
        assert result.returncode == 0
        for path in ("src/reviewer/reviews/queryset.py", "tools/check_isolation.py"):
            assert path in result.stdout


class TestRuleSemantics:
    """The parts of the rule that a future edit could plausibly get wrong."""

    def test_a_bare_manager_reference_is_not_a_read(self, tmp_path):
        """`Review.objects` on its own hands out no rows."""
        f = tmp_path / "bare.py"
        f.write_text(
            "from reviewer.reviews.models import Review\n"
            "\n"
            "def manager():\n"
            "    return Review.objects\n",
            encoding="utf-8",
        )
        assert run_checker(str(f)).returncode == 0

    def test_the_default_manager_spelling_is_also_guarded(self, tmp_path):
        """`_default_manager` is a second, equally easy spelling of the same read."""
        f = tmp_path / "default_manager.py"
        f.write_text(
            "from reviewer.reviews.models import Review\n"
            "\n"
            "def all_reviews():\n"
            "    return Review._default_manager.all()\n",
            encoding="utf-8",
        )
        assert run_checker(str(f)).returncode == 1

    def test_a_chained_read_is_still_a_read(self, tmp_path):
        """`.filter().all()` is the same read, one call later.

        Reported ONCE, at the outermost read off the manager. Reporting it
        twice would be noise, and noise is how a rule gets switched off -- but
        the chain must be caught at all, because a fix that silences the
        reported `.filter()` and leaves the pattern in place would otherwise
        read as having addressed the finding.
        """
        f = tmp_path / "chained.py"
        f.write_text(
            "from reviewer.reviews.models import Review\n"
            "\n"
            "def every():\n"
            "    return Review.objects.filter(status='submitted').all()\n",
            encoding="utf-8",
        )
        result = run_checker(str(f))
        assert result.returncode == 1
        found = findings(result)
        assert len(found) == 1, f"expected one finding for the chain, got {found}"
        assert "'filter'" in found[0]

    def test_json_output_is_machine_readable(self, tmp_path):
        import json

        f = tmp_path / "leak.py"
        f.write_text(
            "from reviewer.reviews.models import Review\n"
            "\n"
            "def every():\n"
            "    return Review.objects.all()\n",
            encoding="utf-8",
        )
        result = run_checker("--json", str(f))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        # An object, not a bare list: the JSON has to be able to say "I checked
        # one file and it was unreadable" as well as "I checked one file and it
        # was clean". A list of findings cannot carry that distinction, and a
        # machine consumer that cannot tell the two apart treats them the same.
        assert payload["files_checked"] == 1
        assert payload["unparsable"] == []
        assert len(payload["findings"]) == 1
        assert payload["findings"][0]["method"] == "all"
        assert payload["findings"][0]["line"] == 4

    def test_a_syntax_error_is_not_a_pass(self, tmp_path):
        """A file the rule cannot parse is not a file with no findings.

        The alternative is a rule that silently exempts anything it fails to
        read, which is the worst possible failure direction for a security
        check: it looks identical to a clean run. So an unparsable file is
        JJ02, reported by name, and it still fails the gate.
        """
        f = tmp_path / "broken.py"
        f.write_text("def oops(:\n", encoding="utf-8")
        result = run_checker(str(f))
        assert result.returncode == 1, (
            "an unparsable file must not pass the rule:\n" + result.stdout
        )
        assert "JJ02" in result.stdout
        assert "broken.py" in result.stdout
