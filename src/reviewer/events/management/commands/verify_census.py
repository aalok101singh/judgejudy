"""``manage.py verify_census`` -- the database, checked against the file it came from.

**Why this is a command and not a test.** ``just check`` runs it inside the
container, after ``load_fixtures``, on the database the acceptance checker will
actually be pointed at. A test proves the *code* imports correctly onto a
database the test built; this proves the *running portal* holds the population
the fixture describes. A loader that silently imported 39 of 40 teams would
leave a green test suite and a gallery missing a project.

**Nothing here is a typed expectation.** Every "expected" number is re-derived
from ``fixtures.json`` at the moment of the comparison, so the command cannot
drift from the file the way a hand-maintained table does -- which is how six of
this project's first twelve findings happened.

**And it fails loudly.** A count that disagrees with its stated population is a
non-zero exit and a named line, not a warning in a log nobody reads. A seed step
that prints its own reconciliation is doing the verification work that would
otherwise be done by hand, at a break, by someone who is tired.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from reviewer.core import ROLE_JUDGE
from reviewer.importer import census as census_module


def _portal_emails(census) -> list[str]:
    """The emails of the demo identities this portal created rather than imported.

    Derived from ``DemoIdentity.from_fixture``, which is the field that actually
    answers the question. See ``_census_tables`` for why this is not a
    ``source_key`` test.
    """
    from reviewer.importer import demo as demo_module

    return [i.email for i in demo_module.choose(census) if not i.from_fixture]


def _census_tables(census):
    """``(label, model, queryset, expected)`` where ``expected`` is a function.

    A *function*, not a number, and that is the entire point: this table has no
    literal in it to fall out of date. ``criterion`` and ``rubric`` counts are
    derived from the criteria keys rather than typed, for the same reason.

    ``User`` is **two rows, not one**, and the split is load-bearing. The
    fixture's 121 people are a number the acceptance panel can check against
    ``fixtures.json`` without running anything, so it is asserted on its own,
    and the two portal-created organizers are counted separately. A single
    "123" row would be true and would prove nothing, because it is also what
    six synthetic accounts would produce.
    """
    from reviewer.accounts.models import RoleBinding, User
    from reviewer.events.models import Event, Track
    from reviewer.importer import demo as demo_module
    from reviewer.projects.models import Project
    from reviewer.reviews.models import Assignment, Review, Score
    from reviewer.rubrics.models import Criterion, Rubric
    from reviewer.teams.models import Team, TeamMembership

    criteria = len(census_module.CRITERIA_KEYS)
    #: The split is by **provenance**, read off the demo identities'
    #: ``from_fixture`` flag, not by whether ``source_key`` happens to be NULL.
    #: Those two were the same thing until FEAT-07 gave the portal-created demo
    #: users a generated ``demo:``-prefixed natural key -- which they need,
    #: because a NULL-keyed row cannot round-trip and our own escape hatch was
    #: silently dropping the demo logins. **The census then read 123 fixture
    #: users and 0 portal-created, and it was the census that was wrong**: it was
    #: using the presence of a key as a proxy for a question about origin.
    #: A proxy is fine until the thing it proxies for acquires a second reason to
    #: be false, and then it is a bug that only fires on the day you fix something
    #: else.
    return [
        ("events.Event", Event, Event.objects.all(), lambda c: c.events),
        ("events.Track", Track, Track.objects.all(), lambda c: c.tracks),
        (
            "accounts.User (from fixtures.json)",
            User,
            User.objects.exclude(email__in=_portal_emails(census)),
            lambda c: c.people,
        ),
        (
            "accounts.User (portal-created)",
            User,
            User.objects.filter(email__in=_portal_emails(census)),
            lambda c: sum(1 for i in demo_module.choose(c) if not i.from_fixture),
        ),
        # F-12, asserted rather than assumed. Hashing all 121 people costs ~48 s
        # against a 10-second acceptance timeout, so five get real hashes and
        # the rest get UNUSABLE_PASSWORD. "Exactly five" is the invariant, and it
        # is checked in BOTH directions: too many is the timeout, too few is a
        # portal where the checker's credentials cannot authenticate. This row is
        # what caught a first run that shipped 123 rows with an empty password
        # (an empty password is a working login -- see
        # reviewer/importer/loader.py::_lacks_credential).
        (
            "accounts.User with a real hash",
            User,
            User.objects.exclude(password__startswith="!"),
            lambda c: sum(1 for i in demo_module.choose(c) if i.password),
        ),
        (
            "accounts.RoleBinding (judge)",
            RoleBinding,
            RoleBinding.objects.filter(role="judge"),
            lambda c: c.judge_track_bindings,
        ),
        ("teams.Team", Team, Team.objects.all(), lambda c: c.teams),
        (
            "teams.TeamMembership",
            TeamMembership,
            TeamMembership.objects.all(),
            lambda c: c.team_members,
        ),
        ("rubrics.Rubric", Rubric, Rubric.objects.all(), lambda c: 1),
        ("rubrics.Criterion", Criterion, Criterion.objects.all(), lambda c: criteria),
        ("projects.Project", Project, Project.objects.all(), lambda c: c.projects),
        ("reviews.Assignment", Assignment, Assignment.objects.all(), lambda c: c.reviews),
        ("reviews.Review", Review, Review.objects.all(), lambda c: c.reviews),
        ("reviews.Score", Score, Score.objects.all(), lambda c: c.reviews * criteria),
    ]


def _histogram(rows) -> dict[int, int]:
    """``{reviews-per-thing: how many things}`` from annotated rows.

    Two aggregations rather than a correlated subquery: 41 rows is not a
    performance question, and the explicit form is the one a reader can check.
    """
    histogram: dict[int, int] = {}
    for row in rows:
        histogram[row["n"]] = histogram.get(row["n"], 0) + 1
    return dict(sorted(histogram.items()))


class Command(BaseCommand):
    """Print every census table's own row count, and fail on a disagreement."""

    help = "Verify the seeded database against fixtures.json, and exit non-zero on drift."

    def add_arguments(self, parser):
        parser.add_argument("--fixtures", default=None, help="Path to fixtures.json.")
        parser.add_argument("--event", default=None, help="Event id. Defaults to the fixture's.")

    def handle(self, *args, **options):
        try:
            fixture = census_module.load_fixture(options["fixtures"])
        except census_module.FixtureNotFound as exc:
            raise CommandError(str(exc)) from exc

        census, problems = census_module.check(fixture)
        event_id = options["event"] or (fixture.get("event") or {}).get("id")

        self.stdout.write("")
        self.stdout.write(f"  census -- the database against {census_module.fixture_path()}")
        self.stdout.write(f"  {'table':<38}{'rows':>6}{'expected':>10}   ")
        self.stdout.write("  " + "-" * 58)

        for label, _model, queryset, expected_of in _census_tables(census):
            expected = expected_of(census)
            actual = queryset.count()
            if actual != expected:
                problems.append(f"{label}: {actual} rows, the fixture implies {expected}")
            self.stdout.write(
                f"  {label:<38}{actual:>6}{expected:>10}   "
                f"{'ok' if actual == expected else 'MISMATCH'}"
            )

        self.stdout.write("")
        self._print_invariants(event_id, census, problems)
        self._print_orphans(problems)

        self.stdout.write("")
        if problems:
            self.stdout.flush()
            for problem in problems:
                self.stdout.write(f"  FAIL: {problem}")
            raise CommandError(f"{len(problems)} census failure(s)")

        self.stdout.write("  census OK: every table holds the population the fixture describes.")
        self.stdout.write("")

    # ----------------------------------------------------------------- derived

    def _print_invariants(self, event_id, census, problems) -> None:
        """The two invariants, computed from the DATABASE, not restated from the file.

        This is the check that catches a loader which imported the right number
        of the wrong rows. The histograms come from ``GROUP BY`` over the tables
        themselves, so ``sum(n x count)`` is a statement about what is stored --
        and ``bible/04`` §2.1 is the argument for having two of them: cardinality
        and mass catch different mistakes, and F-28 was caught by only one.
        """
        from reviewer.projects.models import Project
        from reviewer.reviews.models import Review

        stored = Review.objects.filter(event_id=event_id)
        project_hist = _histogram(stored.values("project_id").annotate(n=Count("id")))
        judge_hist = _histogram(stored.values("judge_id").annotate(n=Count("id")))
        projects = Project.objects.filter(event_id=event_id).count()

        for _label, singular, histogram, population in (
            ("projects", "project", project_hist, projects),
            ("judges", "judge", judge_hist, census.judges),
        ):
            cardinality = sum(histogram.values())
            mass = sum(n * count for n, count in histogram.items())
            self.stdout.write(f"  reviews per {singular:<8} {histogram}")
            for statement, left, right, name in (
                ("cardinality", cardinality, population, "rows covered"),
                ("mass", mass, census.reviews, "reviews"),
            ):
                ok = left == right
                verdict = "ok" if ok else "MISMATCH"
                self.stdout.write(f"  {'':<16}{statement:<13} {left:>5} == {right:<5}  {verdict}")
                if not ok:
                    problems.append(
                        f"{statement} over {singular}s: the stored histogram accounts for "
                        f"{left} {name}, the table implies {right}"
                    )

    def _print_orphans(self, problems) -> None:
        """Rows that point at nothing, and reviews whose judge has no binding.

        A loader that resolves a foreign key wrong produces a row that exists and
        is unreachable, which no row count would notice. ``foreign_keys=ON``
        catches a *missing* target; this catches a *wrong* one -- and a review
        whose judge holds no judge binding is a row the isolation model would
        silently refuse to show anybody, which is the subtler version.
        """
        from reviewer.accounts.models import RoleBinding
        from reviewer.reviews.models import Review, Score

        checks = {
            "reviews with no Score row": Review.objects.filter(scores__isnull=True).count(),
            "reviews whose judge holds no judge binding": Review.objects.exclude(
                judge__role_bindings__role=ROLE_JUDGE
            ).count(),
            "dangling foreign keys": (
                Score.objects.filter(review__isnull=True).count()
                + RoleBinding.objects.filter(user__isnull=True).count()
            ),
        }
        for label, count in checks.items():
            self.stdout.write(f"  {label:<48}{count:>6}")
            if count:
                problems.append(f"{count} {label}")
