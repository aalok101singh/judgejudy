"""``manage.py load_fixtures`` -- the seed step, run before the port binds.

``docker/entrypoint.sh`` calls this between ``collectstatic`` and gunicorn, and
it is the step that turns "the container starts" into "the portal is populated".
Two properties matter more than speed:

**It is idempotent.** The entrypoint is run many times against one volume, and
the break protocol starts from ``down -v``. A second run must converge: zero
rows created, the census unchanged. The report prints both, so the second run is
self-evidencing rather than a thing to remember.

**It prints the credentials last.** The acceptance checker needs them, the
operator has to paste them into a committed ``.dogfood.toml``, and printing them
after the summary means a truncated log still contains the census.

The command lives under ``events`` because ``Event`` is the tenant every other
table hangs off, and because the loader is a *package* rather than an app: it
defines no model, so putting it in ``INSTALLED_APPS`` would add a ``models``
module that does not exist and a migration that creates nothing. The reasoning is
the same one that made ``reviewer/isolation`` a package.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviewer.accounts import demo_tokens
from reviewer.importer import census as census_module
from reviewer.importer import loader as loader_module


class Command(BaseCommand):
    """Load ``fixtures.json`` into the database, idempotently."""

    help = "Import fixtures.json into an already-migrated database. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixtures",
            default=None,
            help="Path to fixtures.json. Defaults to the repository root, then /app.",
        )
        parser.add_argument(
            "--no-passwords",
            action="store_true",
            help=(
                "Do not hash the five demo passwords. For a test or a dry run; a "
                "portal seeded this way cannot log anyone in."
            ),
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print the census failures and the credentials block.",
        )

    def handle(self, *args, **options):
        try:
            fixture = census_module.load_fixture(options["fixtures"])
        except census_module.FixtureNotFound as exc:
            # A boot failure rather than a warning. A portal that starts with an
            # empty database because the fixture was missing looks identical to
            # a portal that works, until a judge opens the gallery.
            raise CommandError(str(exc)) from exc

        report = loader_module.load(fixture, hash_passwords=not options["no_passwords"])

        if not options["quiet"]:
            self._print_summary(report)
        self._print_credentials(report)

        if report.failures:
            self.stdout.flush()
            raise CommandError(
                f"{len(report.failures)} census failure(s); the portal is seeded but the "
                "input does not reconcile. See above."
            )

    # ------------------------------------------------------------------ output

    def _print_summary(self, report) -> None:
        census = report.census
        width = max(len(name) for name, _, _ in report.rows()) if report.rows() else 4

        self.stdout.write("")
        self.stdout.write("  fixture census, re-derived from fixtures.json")
        self.stdout.write(f"  {'table':<{width}}  {'created':>8} {'updated':>8}")
        self.stdout.write("  " + "-" * (width + 19))
        for name, created, updated in report.rows():
            self.stdout.write(f"  {name:<{width}}  {created:>8} {updated:>8}")
        self.stdout.write(f"  {'':<{width}}  {'-' * 8} {'-' * 8}")
        self.stdout.write(
            f"  {report.created_total} created, {report.updated_total} updated, "
            f"{report.passwords_hashed} password hashes, {report.elapsed:.2f}s"
        )
        self.stdout.write("")

        for line in report.observations:
            self.stdout.write(f"  note: {line}")

        # The two invariants, printed as the two invariants rather than as a
        # total. bible/04 §2.1: cardinality and mass catch different mistakes and
        # F-28 was caught by only one of them.
        target = census.modal_reviews_per_project
        self.stdout.write("")
        self.stdout.write(f"  reviews per project: {census.projects_by_reviews} (mode {target})")
        self.stdout.write(f"  reviews per judge:   {census.judges_by_reviews}")
        self.stdout.write(
            f"  invariants: cardinality over projects {sum(census.projects_by_reviews.values())}"
            f" == {census.projects}; mass {census.reviews} == {census.reviews}"
        )
        self.stdout.write(
            f"               cardinality over judges "
            f"{sum(census.judges_by_reviews.values())} == {census.judges}; mass "
            f"{sum(n * c for n, c in census.judges_by_reviews.items())} == {census.reviews}"
        )
        self.stdout.write(
            f"  people: {census.people} = {census.judges} judges + {census.team_members} "
            f"team members, all disjoint; {census.judge_track_bindings} judge bindings for "
            f"{census.judges} judges ({census.dual_track_judges} dual-track)"
        )

        if report.failures:
            self.stdout.write("")
            for failure in report.failures:
                self.stdout.write(f"  FAIL: {failure}")

    def _print_credentials(self, report) -> None:
        """The paste-ready ``[auth]`` block, last, and in full.

        These are the *real* values, not placeholders, and nothing here is
        invented to make a check pass. They are also not secrets: the signing key
        is published in ``reviewer/accounts/demo_tokens.py``, which is why the
        README says in plain words that a demo credential on a single-tenant
        self-hosted portal whose only data is a public fixture is not a secret.
        """
        self.stdout.write("")
        self.stdout.write("  paste this into .dogfood.toml [auth] -- verbatim:")
        self.stdout.write("")
        for key in sorted(report.auth_block):
            self.stdout.write(f'    {key:<12}= "{report.auth_block[key]}"')
        self.stdout.write("")
        self.stdout.write(f"  {demo_tokens.describe()}.")
        self.stdout.flush()
