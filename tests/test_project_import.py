"""Bulk project import: a spreadsheet with mistakes in it.

**The test file is arranged around what a real export looks like**, not around a
clean file. A CSV an organizer produces from Google Forms has a BOM, columns we do
not read, two titles that collide, a track they invented, and a URL that is not a
URL. The properties worth testing are therefore:

- **a bad row is skipped and named, and the rest still import** (F-61's shape, at
  the file level: "38 of 40" is the only useful output);
- **re-running changes nothing** — the most likely thing an organizer does;
- **an unknown track is refused rather than invented**, because the assignment
  engine is built per track and a silent new track means projects nobody can judge;
- **a title is only ever a fallback key**, because `Project.title` is deliberately
  not unique.
"""

from __future__ import annotations

import pytest

from reviewer.setup.imports import FileRefused, RowRefused, import_projects, read_rows

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(db):
    from tests.factories import make_event, make_track

    from reviewer.events.models import VOTING_OPEN_LINK

    event = make_event(voting_mode=VOTING_OPEN_LINK)
    make_track(event, "General")
    make_track(event, "Hardware")
    return event


def _csv(tmp_path, body: str, name: str = "entries.csv"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


GOOD = (
    "source_key,title,summary,track,team,repo_url\n"
    "ext_1,Glass Signal,A neat thing,General,Ada,https://example.org/glass\n"
    "ext_2,Small Meadow,Another thing,Hardware,Grace,https://example.org/meadow\n"
)


class TestTheHappyPath:
    def test_it_creates_the_projects(self, world, tmp_path):
        from reviewer.projects.models import Project

        result = import_projects(_csv(tmp_path, GOOD))
        assert result.created == 2
        assert Project.objects.filter(event=world).count() == 2

    def test_the_rows_carry_what_the_sheet_said(self, world, tmp_path):
        from reviewer.projects.models import Project

        import_projects(_csv(tmp_path, GOOD))
        glass = Project.objects.get(title="Glass Signal")

        assert glass.source_key == "ext_1"
        assert glass.summary == "A neat thing"
        assert glass.repo_url == "https://example.org/glass"
        assert glass.track.name == "General"
        assert glass.status == "submitted", "an imported entry is submitted, not a draft"
        assert glass.submitted_at is not None

    def test_two_projects_from_one_team_share_it(self, world, tmp_path):
        from reviewer.projects.models import Project

        body = (
            "source_key,title,track,team\n"
            "a1,First,General,Team Rocket\n"
            "a2,Second,General,Team Rocket\n"
        )
        import_projects(_csv(tmp_path, body))
        assert Project.objects.filter(team__name="Team Rocket").count() == 2

    def test_a_missing_summary_falls_back_to_the_title(self, world, tmp_path):
        """A spreadsheet with only a title is the common case, and an empty
        summary is worse than a redundant one."""
        from reviewer.projects.models import Project

        import_projects(_csv(tmp_path, "title,track\nSomething,General\n"))
        assert Project.objects.get().summary == "Something"

    def test_a_missing_team_becomes_one_named_for_the_row(self, world, tmp_path):
        from reviewer.projects.models import Project

        import_projects(_csv(tmp_path, "title,track\nSolo,General\n"))
        assert Project.objects.get().team.name


class TestItIsIdempotent:
    def test_running_twice_creates_nothing_new(self, world, tmp_path):
        from reviewer.projects.models import Project

        first = import_projects(_csv(tmp_path, GOOD))
        second = import_projects(_csv(tmp_path, GOOD))

        assert first.created == 2
        assert second.created == 0
        assert second.unchanged == 2, "re-importing identical rows should be a no-op"
        assert Project.objects.filter(event=world).count() == 2

    def test_a_changed_row_updates_in_place(self, world, tmp_path):
        from reviewer.projects.models import Project

        import_projects(_csv(tmp_path, GOOD))
        changed = GOOD.replace("A neat thing", "A much better thing")
        result = import_projects(_csv(tmp_path, changed, "v2.csv"))

        assert result.updated == 1
        assert Project.objects.count() == 2, "an update must not also create"
        assert Project.objects.get(source_key="ext_1").summary == "A much better thing"

    def test_a_source_key_updates_even_when_the_title_changed(self, world, tmp_path):
        """**Why ``source_key`` is the primary key for an import.** The title is
        the thing an organizer edits most, so a title-based re-import would create
        a duplicate for every renamed entry."""
        from reviewer.projects.models import Project

        import_projects(_csv(tmp_path, GOOD))
        renamed = GOOD.replace("Glass Signal", "Glass Signal v2")
        result = import_projects(_csv(tmp_path, renamed, "v2.csv"))

        assert result.updated == 1
        assert Project.objects.filter(source_key="ext_1").count() == 1
        assert Project.objects.filter(title="Glass Signal v2").exists()
        assert not Project.objects.filter(title="Glass Signal").exists()


class TestBadRowsAreSkippedAndNamed:
    """**The F-61 shape at the file level.** A report of "imported 40" when two
    were silently dropped is worse than no report."""

    def test_a_bad_track_does_not_stop_the_file(self, world, tmp_path):
        from reviewer.projects.models import Project

        body = (
            "source_key,title,track\n"
            "ok1,Fine,General\n"
            "bad1,Wrong track,Nonexistent\n"
            "ok2,Also fine,Hardware\n"
        )
        result = import_projects(_csv(tmp_path, body))

        assert result.created == 2
        assert len(result.rejected) == 1
        assert Project.objects.count() == 2

    def test_the_rejection_names_the_line_and_the_reason(self, world, tmp_path):
        body = "title,track\nFine,General\nWrong,Nonexistent\n"
        result = import_projects(_csv(tmp_path, body))

        rejected = result.rejected[0]
        assert rejected.line == 3, "line 2 is the bad row: 1 is the header"
        assert "Nonexistent" in rejected.detail
        assert "General, Hardware" in rejected.detail, "the error must say what does exist"

    def test_an_unknown_track_is_never_invented(self, world, tmp_path):
        """**A silently created track has no judges bound to it**, so its projects
        could never be assigned -- an event where some entries cannot be judged."""
        from reviewer.events.models import Track

        body = "title,track\nFine,General\nInvented,Nonexistent\n"
        import_projects(_csv(tmp_path, body))
        assert not Track.objects.filter(name__iexact="Nonexistent").exists()

    def test_a_row_with_no_title_is_skipped(self, world, tmp_path):
        body = "title,track\nFine,General\n,Hardware\n"
        result = import_projects(_csv(tmp_path, body))
        assert result.created == 1
        assert "no title" in result.rejected[0].detail

    def test_a_url_that_is_not_a_url_is_skipped(self, world, tmp_path):
        body = "title,track,repo_url\nFine,General,not-a-url\n"
        result = import_projects(_csv(tmp_path, body))
        assert result.created == 0
        assert "http(s) URL" in result.rejected[0].detail

    def test_a_rejected_row_creates_no_team(self, world, tmp_path):
        """**One transaction per row, and that is the reason.** A file-wide
        transaction would roll back the good rows too, and the organizer's team
        list would be left inconsistent with the projects in it."""
        from reviewer.teams.models import Team

        body = "title,track,team\nWrong,Nonexistent,The Rocket\n"
        import_projects(_csv(tmp_path, body))
        assert not Team.objects.filter(name="The Rocket").exists()

    def test_an_over_long_summary_is_truncated_not_refused(self, world, tmp_path):
        """A 500-character field is a mistake in the sheet, not a reason to lose
        the entry -- and refusing would teach an organizer to avoid the tool."""
        from reviewer.projects.models import Project

        body = f"title,summary,track\nFine,{'x' * 900},General\n"
        result = import_projects(_csv(tmp_path, body))

        assert result.created == 1
        assert len(Project.objects.get().summary) == 500


class TestRealSpreadsheets:
    def test_a_bom_does_not_hide_the_header(self, tmp_path):
        """**Windows spreadsheet exports carry one**, and it makes the first
        column read as ``﻿title`` -- so every row fails on a missing column that
        the organizer can plainly see."""
        path = tmp_path / "bom.csv"
        path.write_bytes("title,track\nFine,General\n".encode("utf-8-sig"))
        assert read_rows(path)[0]["title"] == "Fine"

    def test_columns_we_do_not_read_are_ignored(self, world, tmp_path):
        """A Google Forms export carries a dozen columns. Refusing the file over
        an extra one would make the tool useless on real data."""
        from reviewer.projects.models import Project

        body = (
            "timestamp,title,track,team,email,how_old_are_you,why_this_track\n"
            "2026-01-01,Fine,General,Ada,ada@example.org,25,because\n"
        )
        result = import_projects(_csv(tmp_path, body))
        assert result.created == 1
        assert Project.objects.get().title == "Fine"

    def test_column_names_are_matched_case_insensitively(self, world, tmp_path):
        from reviewer.projects.models import Project

        import_projects(_csv(tmp_path, "Title,Track,Team\nFine,General,Ada\n"))
        assert Project.objects.count() == 1

    def test_an_empty_file_is_refused_by_name(self, tmp_path):
        with pytest.raises(FileRefused, match="empty"):
            read_rows(_csv(tmp_path, ""))

    def test_a_missing_required_column_is_refused_and_says_which(self, tmp_path):
        with pytest.raises(FileRefused, match="no track column"):
            read_rows(_csv(tmp_path, "title,team\nFine,Ada\n"))

    def test_a_missing_file_is_refused_by_name(self, tmp_path):
        with pytest.raises(FileRefused, match="does not exist"):
            read_rows(tmp_path / "nope.csv")

    def test_a_header_only_file_imports_nothing_rather_than_failing(self, world, tmp_path):
        result = import_projects(_csv(tmp_path, "title,track\n"))
        assert result.total == 0


class TestNoEventYet:
    def test_it_says_what_to_do_first(self, tmp_path):
        """**An error with no next step is how a first run ends.**"""
        with pytest.raises(FileRefused, match="no event yet"):
            import_projects(_csv(tmp_path, GOOD))


class TestTheDryRun:
    def test_it_reports_without_writing(self, world, tmp_path):
        from reviewer.projects.models import Project

        result = import_projects(_csv(tmp_path, GOOD), dry_run=True)

        assert result.created == 2
        assert Project.objects.count() == 0

    def test_it_still_names_the_teams_it_would_make(self, world, tmp_path):
        """**The point of a dry run here is the team list**, because a real run
        creates them and an organizer should see that before committing."""
        body = "title,track,team\nFine,General,The Rocket\n"
        result = import_projects(_csv(tmp_path, body), dry_run=True)

        assert result.teams_made == ["The Rocket"]
        from reviewer.teams.models import Team

        assert Team.objects.count() == 0

    def test_it_still_reports_bad_rows(self, world, tmp_path):
        body = "title,track\nFine,Nonexistent\n"
        result = import_projects(_csv(tmp_path, body), dry_run=True)
        assert len(result.rejected) == 1


class TestTheExceptionsAreNotConfused:
    def test_a_file_refusal_and_a_row_refusal_are_different_types(self):
        """**A caller must be able to tell "this file is wrong" (fatal) from
        "this row is wrong" (skip and continue).** Collapsing them is how a tool
        either gives up on a whole file over one line, or silently imports a
        malformed one."""
        assert not issubclass(RowRefused, FileRefused)
        assert not issubclass(FileRefused, RowRefused)

    def test_neither_shadows_a_builtin(self):
        """``ImportError`` is a builtin; shadowing it sends a reader hunting
        through Python's import machinery."""
        import builtins

        from reviewer.setup import imports

        assert imports.RowRefused is not builtins.ImportError
        assert not hasattr(imports, "ImportError_"), "the underscore name should be gone"
