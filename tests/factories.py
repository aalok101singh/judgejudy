"""Small, explicit builders for a test world.

Deliberately not factories with random values. Every number in an isolation test
is load-bearing -- "3 of 126" only means something because 126 is known -- and a
builder that invents a random track id turns a failure into a puzzle. These
build exactly what the test says it is building.

**Why nothing here reaches an unscoped ``Review``.** Every read goes through
``for_actor``, because ``tools/check_isolation.py`` scans ``tests/`` too and
because a test that quietly held an unscoped handle would be the one place the
rule stopped applying. The ground truth -- the event-wide totals that the
receipt's denominator is checked against -- lives in
``tests/test_schema_contract.py``, which is on the allowlist with a reason.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from reviewer.accounts.models import RoleBinding, User
from reviewer.events.models import Event, Track
from reviewer.projects.models import Project
from reviewer.reviews.models import Assignment, Review, Score
from reviewer.rubrics.models import Criterion, Rubric
from reviewer.teams.models import Team

#: The fixture's close date is in the PAST, so the portal is born closed. The
#: same fact appears in settings, bible/04 and DATA-MODEL; it is repeated here
#: because a test that quietly opened the deadline would be testing a portal
#: that does not exist.
SUBMISSIONS_CLOSE = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)
SUBMISSIONS_OPEN = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def make_event(event_id: str = "evt_01", **kwargs) -> Event:
    fields = {
        "slug": event_id.replace("_", "-"),
        "name": "Test Event",
        "starts_at": SUBMISSIONS_OPEN,
        "submissions_open": SUBMISSIONS_OPEN,
        "submissions_close": SUBMISSIONS_CLOSE,
    }
    fields.update(kwargs)
    return Event.objects.create(id=event_id, **fields)


def make_track(event: Event, name: str, **kwargs) -> Track:
    """A track with a surrogate primary key.

    There is no way to name a track's id here, and that is deliberate: the
    receipt prints track *ids*, so a test that depends on a specific one is
    reading it out of the database it just wrote. Tests that care assert on
    ``receipt.bindings``, which carries the ids the code actually used.
    """
    return Track.objects.create(
        event=event,
        name=name,
        slug=name.lower().replace(" ", "-"),
        **kwargs,
    )


def make_team(event: Event, name: str, team_id: int | None = None) -> Team:
    return Team.objects.create(
        event=event,
        name=name,
        slug=name.lower().replace(" ", "-"),
        invite_code=f"invite-{team_id or name}",
    )


def make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(
        email=email,
        password="not-a-real-hash",
        display_name=kwargs.pop("display_name", email),
        **kwargs,
    )


def bind(user: User, event: Event, role: str, track: Track | None = None) -> RoleBinding:
    return RoleBinding.objects.create(user=user, event=event, role=role, track=track)


def make_rubric(event: Event, version: int = 1) -> Rubric:
    rubric = Rubric.objects.create(event=event, name="Standard", version=version)
    for position, key in enumerate(("functionality", "quality", "innovation")):
        Criterion.objects.create(rubric=rubric, key=key, label=key.title(), position=position)
    return rubric


def make_project(
    project_id: str,
    event: Event,
    team: Team,
    track: Track,
    *,
    status: str = "submitted",
    supersedes: Project | None = None,
) -> Project:
    kwargs = {
        "event": event,
        "team": team,
        "track": track,
        "slug": project_id.lower(),
        "title": f"Project {project_id}",
        "summary": "A project.",
    }
    if status == "draft":
        kwargs["submitted_at"] = None
    else:
        kwargs["submitted_at"] = SUBMISSIONS_CLOSE - timedelta(days=1)
    return Project.objects.create(id=project_id, status=status, supersedes=supersedes, **kwargs)


def make_review(
    project: Project,
    judge: User,
    rubric: Rubric,
    *,
    value: int = 4,
    status: str = "submitted",
) -> Review:
    """Create a submitted review with one score per criterion.

    ``submitted_at`` is set whenever the status is ``submitted`` because the
    schema has a CHECK constraint saying so, and a test that trips its own
    constraint is a test about the wrong thing.
    """
    assignment = Assignment.objects.create(
        event=project.event, judge=judge, project=project, status=status
    )
    review = Review.objects.create(
        assignment=assignment,
        judge=judge,
        project=project,
        event=project.event,
        rubric_version=rubric,
        status=status,
        submitted_at=(SUBMISSIONS_CLOSE - timedelta(days=1)) if status == "submitted" else None,
    )
    for criterion in rubric.criteria.all():
        Score.objects.create(
            review=review,
            criterion=criterion,
            value=value if status == "submitted" else None,
        )
    return review
