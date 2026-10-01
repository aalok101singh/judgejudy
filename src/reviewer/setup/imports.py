"""``manage.py import_projects`` -- a hackathon's entries from a spreadsheet.

**This is the difference between a tool and a demo.** An organizer with forty
entries should not fill in forty forms, and the only bulk path this project had
was the escape hatch -- a *whole-database* archive round trip, which is the right
tool for backup and a terrible tool for onboarding a new event.

So this reads the shape organizers actually have: a CSV exported from whatever
they used to collect entries, with a team name and a track on each row.

**Three decisions, each with a reason a reviewer can check.**

1. **Idempotent, keyed on ``source_key``.** A row carrying an external id updates
   that project; a row without one falls back to the title *within the event*.
   Re-running after adding three entries must not duplicate the first thirty --
   and ``Project.title`` is deliberately **not** unique, because a team may
   legitimately submit the same title twice (``bible/04`` §3.3), so the title is
   only ever a fallback and never a global key.
2. **An unknown track is refused, not invented.** Tracks are chosen at
   ``/setup/`` and the assignment engine is built per track, so silently creating
   one here would produce a track with no judges bound to it -- an event where
   some projects can never be judged. The error names the tracks that exist.
3. **Teams are created on demand, with an ``invite_code``** because the column is
   ``unique`` and not nullable. A row naming a team that already exists reuses it,
   so two projects from one team share it.

Every row is reported, and a bad row is **skipped rather than half-applied** --
which is why the whole import is one transaction per row rather than one for the
file: a file of forty entries with two bad ones should produce thirty-eight
projects, not a rollback that teaches the organizer nothing about which two
failed.
"""

from __future__ import annotations

import csv
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from reviewer.setup.provisioning import slugify

#: The columns this importer understands. An unknown column is **ignored**, not an
#: error: organizers export from forms that collect a dozen things and this
#: portal cares about five of them. Refusing the file over an extra column would
#: make the tool unusable on real exports.
COLUMNS = ("source_key", "title", "summary", "description", "track", "team", "repo_url")

REQUIRED = ("title", "track")

#: Summaries longer than this are truncated rather than refused -- it is a
#: one-line field, and a long one is a mistake in the sheet, not a reason to lose
#: the entry.
SUMMARY_CHARS = 500

_URL_RE = re.compile(r"^https?://\S+$")


class FileRefused(Exception):
    """The file itself cannot be read -- missing, empty, or missing a required column.

    Separate from RowRefused so a caller can tell "this file is wrong" from
    "this row is wrong". The first is fatal; the second is skipped and reported.
    """


class RowRefused(Exception):
    """One row could not be imported. Distinct from a file-level refusal.

    **Not named ``ImportError``.** Shadowing the builtin is the kind of
    convenience that makes a traceback lie about where a failure came from --
    somebody reading one would go looking in Python's import machinery. The
    trailing-underscore version had the same problem; this is the readable fix.
    """


@dataclass
class RowResult:
    line: int
    outcome: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome in ("created", "updated", "unchanged")


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: list[RowResult] = field(default_factory=list)
    teams_made: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged


def read_rows(path: str | Path) -> list[dict]:
    """Read the CSV, refusing a file whose header we cannot work with.

    **BOM-tolerant** (``utf-8-sig``) because a spreadsheet export on Windows
    carries one, and a header reading ``\\ufefftitle`` fails on every row with a
    message about a missing column -- which sends the organizer looking for a
    missing column they can see.
    """
    target = Path(path)
    if not target.exists():
        raise FileRefused(f"{path} does not exist.")
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise FileRefused(f"{path} is empty. Expected a header row.")

    present = {name.strip().lower() for name in reader.fieldnames if name}
    missing = [name for name in REQUIRED if name not in present]
    if missing:
        raise FileRefused(
            f"{path} has no {', '.join(missing)} column. Expected at least: {', '.join(REQUIRED)}."
        )
    return [
        {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader
    ]


def _new_project_id() -> str:
    return f"prj_{secrets.token_hex(4)}"


def _team_for(event, name: str, result: ImportResult, *, dry_run: bool = False):
    """Reuse a team by name, or make one. ``invite_code`` is unique and not
    nullable, so it is generated rather than left blank."""
    from reviewer.teams.models import Team

    trimmed = (name or "").strip() or "Unnamed team"
    existing = Team.objects.filter(event=event, name__iexact=trimmed).first()
    if existing:
        return existing
    if dry_run:
        result.teams_made.append(trimmed)
        return None

    team = Team.objects.create(
        event=event,
        name=trimmed,
        slug=slugify(trimmed),
        invite_code=secrets.token_hex(8),
    )
    result.teams_made.append(trimmed)
    return team


def import_projects(path: str | Path, *, dry_run: bool = False) -> ImportResult:
    """Create or update every project in the CSV. One transaction per row.

    ``dry_run`` reports exactly what a real run would do and writes nothing --
    which is worth having precisely because a real run *does* create teams, and an
    organizer should be able to see the team list before committing to it.
    """
    from reviewer.events.models import Event, Track
    from reviewer.projects.models import Project

    rows = read_rows(path)

    event = Event.objects.order_by("pk").first()
    if event is None:
        raise FileRefused(
            "This deployment has no event yet. Run /setup/ first, or "
            "`JJ_SEED_DEMO=1 docker compose up` to load the demo."
        )

    tracks = {t.name.strip().lower(): t for t in Track.objects.filter(event=event)}
    result = ImportResult()

    for offset, row in enumerate(rows, start=2):  # row 1 is the header
        try:
            outcome, _detail = _import_one(Project, event, tracks, row, result, dry_run=dry_run)
        except (RowRefused, ValueError) as exc:
            result.rejected.append(RowResult(line=offset, outcome="rejected", detail=str(exc)))
            continue
        if outcome == "created":
            result.created += 1
        elif outcome == "updated":
            result.updated += 1
        else:
            result.unchanged += 1

    return result


@transaction.atomic
def _import_one(project_model, event, tracks, row: dict, result: ImportResult, *, dry_run=False):
    title = (row.get("title") or "").strip()
    if not title:
        raise RowRefused("no title")

    track_name = (row.get("track") or "").strip()
    track = tracks.get(track_name.lower())
    if track is None:
        available = ", ".join(sorted(t.name for t in tracks.values())) or "none"
        raise RowRefused(
            f"no track called {track_name!r} in {event.name!r}. Available: {available}"
        )

    repo_url = (row.get("repo_url") or "").strip()
    if repo_url and not _URL_RE.match(repo_url):
        raise RowRefused(f"repo_url {repo_url!r} is not an http(s) URL")

    team = _team_for(event, row.get("team") or "", result, dry_run=dry_run)

    source_key = (row.get("source_key") or "").strip()
    existing = None
    if source_key:
        existing = project_model.objects.filter(source_key=source_key).first()
    if existing is None:
        # The title is a fallback *within this event only*, because
        # `Project.title` is deliberately not unique.
        existing = project_model.objects.filter(event=event, title__iexact=title).first()

    fields = {
        "title": title[:300],
        "summary": (row.get("summary") or title)[:SUMMARY_CHARS],
        "description": row.get("description") or "",
        "track": track,
        "team": team,
        "repo_url": repo_url[:500],
        "status": "submitted",
    }

    if existing is None:
        if dry_run:
            return "created", title
        # **`submitted_at` is set here and nowhere else.** The first draft put
        # `timezone.now()` in `fields`, so every re-import restamped every project
        # and reported all forty as "updated" -- a re-run that changes nothing but
        # tells the organizer their whole sheet was rewritten, and the churn report
        # becomes noise. When they submitted is a fact about the first submission.
        project_model.objects.create(
            event=event,
            id=_new_project_id(),
            source_key=source_key or None,
            slug=slugify(title)[:80],
            submitted_at=timezone.now(),
            **fields,
        )
        return "created", title

    if all(getattr(existing, name) == value for name, value in fields.items()):
        return "unchanged", title
    if dry_run:
        return "updated", title
    for name, value in fields.items():
        setattr(existing, name, value)
    existing.save()
    return "updated", title
