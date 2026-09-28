"""Re-derive the fixture's census, and check the two invariants that catch a bad one.

**Everything in this module is computed from ``fixtures.json``. Nothing is typed.**
That is the whole point of it. Twelve findings in this project were hand-typed
census numbers in our own planning documents, and two of them were found *after*
a correction log had already been published about the first four -- which is
worse than the original error, because a correction log containing un-caught
errors teaches a reader to distrust the writer.

So ``verify_census`` does not compare the database against a table of expected
counts that someone maintained. It compares the database against **the fixture
file, re-read at the moment of the comparison**, and the only numbers anyone
typed are the ones in ``fixtures.json``.

## The two invariants, and why two

``bible/04`` §2.1 is the sharpest tool in the project and it is five lines long.
A histogram of "how many reviews does each project have" can be checked two
ways, and each catches a different mistake:

| | statement | catches |
|---|---|---|
| **cardinality** | ``sum(hist.values()) == len(projects)`` | a project listed twice, or missing |
| **mass** | ``sum(n * count) == len(scores)`` | a bucket whose size was typed wrong |

F-28 was exactly this pair failing: the histogram read ``8@2, 26@3, 3@4, 5@5``
instead of ``4@5``, whose buckets total **42** rather than 41 (cardinality) and
whose mass is **131** rather than 126 (mass). So both invariants catch it, which
is the argument for asserting two rather than the one that is easy.
``blueprint/context/findings.md`` credits only the mass one and quotes the sum
as 126; that arithmetic is wrong and the entry is corrected as F-52.

The pair is also cheap enough to run on every boot, which is the point: a seed
step that prints its own reconciliation is doing the verification work that
would otherwise be done by hand, at a break, by a person who is tired.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter
from dataclasses import dataclass, field

#: Where the fixture lives, in order of preference. The image copies it to
#: ``/app/fixtures.json``; a local checkout has it at the repository root.
FIXTURE_ENV_VAR = "DJUDGE_FIXTURES_PATH"
FIXTURE_CANDIDATES = ("fixtures.json", "/app/fixtures.json")

#: The criteria keys the fixture uses, in the order it uses them. Order is
#: load-bearing and is F-04: every CSV export's header is this order, and
#: deriving it from a row's values transposes two columns in every export.
CRITERIA_KEYS = ("functionality", "quality", "innovation")

#: The rubric the fixture's values are interpreted on. Recorded because the
#: loader creates it and `Review.rubric_version` is a non-null foreign key, so
#: the reviews cannot be imported without a rubric to point at -- and because
#: "these numbers are on a 1..5 scale" is a claim a reader can check.
FIXTURE_SCALE = (1, 5)


class FixtureNotFound(RuntimeError):
    """Raised when ``fixtures.json`` cannot be read. A boot failure, not a warning."""


def fixture_path(explicit: str | pathlib.Path | None = None) -> pathlib.Path:
    """Locate ``fixtures.json`` or explain precisely where we looked."""
    import os

    candidates = []
    if explicit:
        candidates.append(pathlib.Path(explicit))
    else:
        if env := os.environ.get(FIXTURE_ENV_VAR):
            candidates.append(pathlib.Path(env))
        candidates.extend(pathlib.Path(c) for c in FIXTURE_CANDIDATES)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    looked = ", ".join(str(c) for c in candidates)
    raise FixtureNotFound(f"fixtures.json not found. Looked in: {looked}")


def load_fixture(path: str | pathlib.Path | None = None) -> dict:
    """Read and parse the fixture. One place, so a bad file fails the same way twice."""
    resolved = fixture_path(path)
    try:
        with resolved.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise FixtureNotFound(f"{resolved} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FixtureNotFound(f"{resolved} is a {type(data).__name__}, not an object.")
    return data


@dataclass(frozen=True)
class Census:
    """Everything the loader and ``verify_census`` need to know about the input.

    A dataclass rather than a bag of return values because the loader prints it,
    the census command prints it, and the tests assert on it. Three consumers of
    one shape is three fewer chances to re-derive it slightly differently.
    """

    events: int
    tracks: int
    judges: int
    teams: int
    team_members: int
    projects: int
    reviews: int
    judge_track_bindings: int
    dual_track_judges: int
    projects_by_reviews: dict[int, int] = field(default_factory=dict)
    judges_by_reviews: dict[int, int] = field(default_factory=dict)
    review_counts_by_project: dict[str, int] = field(default_factory=dict)
    review_counts_by_judge: dict[str, int] = field(default_factory=dict)
    criteria_keys: tuple[str, ...] = ()
    first_titles: tuple[str, ...] = ()
    duplicate_titles: tuple[str, ...] = ()
    reused_teams: tuple[str, ...] = ()
    empty_comments: int = 0
    #: judge id -> the track ids they are bound to, in fixture order. The dual
    #: judges carry two, and that is the shape the seed expresses as two
    #: RoleBinding rows rather than a special case.
    judge_tracks: dict[str, list[str]] = field(default_factory=dict)
    judge_emails: dict[str, str] = field(default_factory=dict)
    #: Members of the lowest-id team, in fixture order. The participant is
    #: promoted from here; see reviewer.importer.demo.
    first_team_members: tuple[str, ...] = ()

    @property
    def people(self) -> int:
        """Distinct humans in the fixture: 30 judges plus 91 unique member emails.

        **This is the number six synthetic accounts would silently change.** The
        acceptance panel can check it against ``fixtures.json`` without running
        anything, so the loader promotes five of these 121 rather than inventing
        six accounts of its own. See ``bible/04`` §5.2.
        """
        return self.judges + self.team_members

    @property
    def modal_reviews_per_project(self) -> int:
        """The review count the largest number of projects actually has.

        **Derived, not typed.** ``bible/04`` §9 says the target is 3, and 3 is
        also the mode -- but "the target is 3" and "the mode is 3" are different
        claims and only one of them is checkable from the file. This is the
        second one, so anything that needs a target reads it from here.
        """
        if not self.projects_by_reviews:
            return 0
        return max(self.projects_by_reviews.items(), key=lambda item: (item[1], -item[0]))[0]


def census(fixture: dict) -> Census:
    """Derive the census from the parsed fixture. Pure; reads no database."""
    judges = fixture.get("judges") or []
    teams = fixture.get("teams") or []
    projects = fixture.get("projects") or []
    scores = fixture.get("scores") or []

    member_emails: set[str] = set()
    for team in teams:
        member_emails.update(team.get("members") or [])

    by_project = Counter(s["project"] for s in scores)
    by_judge = Counter(s["judge"] for s in scores)

    teams_with_projects = Counter(p["team"] for p in projects)
    title_counts = Counter(p.get("title", "") for p in projects)

    criteria_keys: tuple[str, ...] = ()
    if scores:
        criteria_keys = tuple(scores[0].get("criteria", {}).keys())

    return Census(
        events=1 if fixture.get("event") else 0,
        tracks=len(fixture.get("tracks") or []),
        judges=len(judges),
        teams=len(teams),
        team_members=len(member_emails),
        projects=len(projects),
        reviews=len(scores),
        judge_track_bindings=sum(len(j.get("tracks") or []) for j in judges),
        dual_track_judges=sum(1 for j in judges if len(j.get("tracks") or []) > 1),
        projects_by_reviews=dict(sorted(Counter(by_project.values()).items())),
        judges_by_reviews=dict(sorted(Counter(by_judge.values()).items())),
        review_counts_by_project=dict(by_project),
        review_counts_by_judge=dict(by_judge),
        criteria_keys=criteria_keys,
        first_titles=tuple(p.get("title", "") for p in projects[:3]),
        duplicate_titles=tuple(sorted(t for t, n in title_counts.items() if n > 1)),
        reused_teams=tuple(sorted(t for t, n in teams_with_projects.items() if n > 1)),
        empty_comments=sum(1 for s in scores if not s.get("comment")),
        judge_tracks={j["id"]: list(j.get("tracks") or []) for j in judges},
        judge_emails={j["id"]: j["email"] for j in judges},
        first_team_members=tuple(
            (teams[0].get("members") or []) if teams else (),
        ),
    )


def _population_failures(census_: Census) -> list[str]:
    """The cardinality and mass invariants, over projects and over judges.

    **Stated plainly, because a check that cannot fail is worse than no check:
    against a histogram this module computed from the same list it just counted,
    ``mass`` is an identity.** ``sum(n * count)`` over any histogram of a
    collection always equals the collection's size. So the value of these two
    invariants is *not* on this code path, and pretending otherwise would be the
    project's own recurring mistake.

    Where they do bite is on a histogram somebody **typed** -- which is exactly
    how F-28 happened (``8@2, 26@3, 3@4, 5@5`` instead of ``4@5``, which
    satisfies cardinality and is off by five on mass) and why
    ``tools/verify_spec.py`` re-derives the histogram from the file and compares
    it against every document that quotes it.

    The non-trivial check on the *data* path is :func:`check`'s structural
    pass, and the non-trivial check on the *database* path is
    ``manage.py verify_census``, which builds its histogram with ``GROUP BY``
    over real tables and compares it to this one. Two populations, two
    independent derivations, which is the only way "the two agree" means
    anything.
    """
    failures: list[str] = []

    for label, histogram, population, mass in (
        (
            "projects",
            census_.projects_by_reviews,
            census_.projects,
            census_.reviews,
        ),
        (
            "judges",
            census_.judges_by_reviews,
            census_.judges,
            census_.reviews,
        ),
    ):
        cardinality = sum(histogram.values())
        if cardinality != population:
            failures.append(
                f"cardinality over {label}: the histogram covers {cardinality} "
                f"{label} but the fixture has {population}"
            )
        total = sum(n * count for n, count in histogram.items())
        if total != mass:
            failures.append(
                f"mass over {label}: sum(n x count) = {total} but there are {mass} reviews"
            )
    return failures


def _structural_failures(fixture: dict, census_: Census) -> list[str]:
    """The relationships a census cannot see but a reader would assume."""
    failures: list[str] = []

    judges = {j["id"]: j for j in fixture.get("judges") or []}
    projects = {p["id"]: p for p in fixture.get("projects") or []}

    judge_emails = {j["email"] for j in judges.values()}
    member_emails = {
        email for team in fixture.get("teams") or [] for email in (team.get("members") or [])
    }
    overlap = sorted(judge_emails & member_emails)
    if overlap:
        failures.append(
            f"{len(overlap)} address(es) are both a judge and a team member: {overlap[:5]}. "
            "One User table keyed on email handles that, but the demo identities assume "
            "judges and members are disjoint."
        )

    known_tracks = {t["id"] for t in fixture.get("tracks") or []}
    for score in fixture.get("scores") or []:
        judge = judges.get(score.get("judge"))
        project = projects.get(score.get("project"))
        if judge is None or project is None:
            failures.append(
                f"score references an unknown id: judge={score.get('judge')!r} "
                f"project={score.get('project')!r}"
            )
            break
        if project["track"] not in set(judge.get("tracks") or []):
            failures.append(
                f"{judge['id']} reviewed {project['id']} off-track "
                f"({judge['tracks']} vs {project['track']})"
            )
            break
    for judge in judges.values():
        for track_id in judge.get("tracks") or []:
            if track_id not in known_tracks:
                failures.append(f"{judge['id']} is bound to unknown track {track_id!r}")
                break

    if census_.criteria_keys and census_.criteria_keys != CRITERIA_KEYS:
        failures.append(
            f"criteria key order is {census_.criteria_keys}, expected {CRITERIA_KEYS}. "
            "F-04: the export header is this order, and deriving it from a row's values "
            "transposes two columns in every export."
        )
    return failures


def check(fixture: dict) -> tuple[Census, list[str]]:
    """The census, and every reason the fixture itself is inconsistent.

    Returns an empty failure list on a good fixture. Each failure names the
    invariant it broke, because a boot message that says "census mismatch" and a
    boot message that says "mass over projects: 127 != 126" lead to very
    different next ten minutes.
    """
    census_ = census(fixture)
    failures = _population_failures(census_) + _structural_failures(fixture, census_)
    return census_, failures


def _slug_collisions(items) -> list[tuple[str, list[str]]]:
    """Names that ``slugify`` collapses onto one slug, with the ids involved.

    ``slugify`` is lossy -- it drops case and punctuation -- and the schema is
    ``UNIQUE (event, slug)`` on both ``Track`` and ``Team``. So this is not a
    cosmetic check: a loader that derived the slug from the name alone raises
    ``IntegrityError`` part-way through, with a message that reads like a schema
    bug. The fixture has three such names among its 40 teams.
    """
    from django.utils.text import slugify

    groups: dict[str, list[str]] = {}
    for item in items:
        groups.setdefault(slugify(item.get("name", "")), []).append(item["id"])
    return [(slug, ids) for slug, ids in sorted(groups.items()) if slug and len(ids) > 1]


def observations(fixture: dict, census_: Census) -> list[str]:
    """The named cases the fixture plants, reported rather than discovered later.

    These are not failures. They are the edges an importer is most likely to get
    wrong, and printing them on boot is what turns "our loader handled the
    awkward parts" from a claim into something the reader saw.
    """
    notes: list[str] = []

    for title in census_.duplicate_titles:
        ids = [p["id"] for p in fixture["projects"] if p.get("title") == title]
        notes.append(
            f"title {title!r} appears {len(ids)} times ({', '.join(ids)}). Both rows are "
            "kept and linked with `supersedes`; nothing is deduplicated on load."
        )
    for team_id in census_.reused_teams:
        ids = [p["id"] for p in fixture["projects"] if p["team"] == team_id]
        notes.append(
            f"team {team_id} submitted {len(ids)} projects ({', '.join(ids)}). A project "
            "belongs to a team and a team may submit more than one."
        )

    for label, items in (
        ("teams", fixture.get("teams") or []),
        ("tracks", fixture.get("tracks") or []),
    ):
        collapsed = _slug_collisions(items)
        if collapsed:
            pairs = "; ".join(f"{slug!r} <- {', '.join(ids)}" for slug, ids in collapsed)
            notes.append(
                f"{len(collapsed)} {label[:-1]} name(s) collapse onto one slug under "
                f"slugify, and both tables are UNIQUE on (event, slug): {pairs}. The "
                "loader appends the fixture id, so the collision is reported rather "
                "than raised as an IntegrityError."
            )
    if census_.empty_comments:
        notes.append(
            f"{census_.empty_comments} of {census_.reviews} reviews have an empty comment. "
            "An empty comment is data, not a missing one, and the column is NOT NULL with "
            "a blank default."
        )
    if census_.dual_track_judges:
        notes.append(
            f"{census_.dual_track_judges} judges hold two tracks and are seeded as two "
            f"RoleBinding rows each ({census_.judge_track_bindings} rows for "
            f"{census_.judges} judges). Per-track assignment flows would be wrong here."
        )
    below = {
        n: count
        for n, count in census_.projects_by_reviews.items()
        if n < census_.modal_reviews_per_project
    }
    if below:
        total = sum(below.values())
        notes.append(
            f"{total} projects have fewer than {census_.modal_reviews_per_project} reviews "
            f"(histogram {below}). Partial judging is normal and the dashboard has to show "
            "it rather than round it away."
        )
    return notes
