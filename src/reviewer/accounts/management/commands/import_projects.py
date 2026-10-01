"""``manage.py import_projects`` -- bulk-load a hackathon's entries from a CSV.

**Prints one line per row.** An import that reports "38 of 40 imported" and stops
there teaches an organizer nothing; one that names the two lines it refused, and
why, is the difference between a five-minute fix and an hour of guessing.

The refusal summary deliberately goes to **stderr** while the tally goes to
stdout, so `import_projects projects.csv | wc -l` stays useful in a pipeline
without swallowing the warnings.
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand, CommandError

from reviewer.setup.imports import COLUMNS, FileRefused, import_projects


class Command(BaseCommand):
    help = "Create or update an event's projects from a CSV of entries."

    def add_arguments(self, parser):
        parser.add_argument("path", help="a CSV file, one project per row")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would happen without writing anything",
        )

    def handle(self, *args, **options):
        try:
            result = import_projects(options["path"], dry_run=options["dry_run"])
        except FileRefused as exc:
            raise CommandError(str(exc)) from exc

        for rejected in result.rejected:
            self.stderr.write(f"  line {rejected.line}: skipped -- {rejected.detail}")

        prefix = "would import" if options["dry_run"] else "imported"
        self.stdout.write(
            f"{result.total} row(s): {result.created} new, "
            f"{result.updated} updated, {result.unchanged} already correct, "
            f"{len(result.rejected)} skipped."
        )
        if result.teams_made:
            self.stdout.write(f"teams created: {', '.join(sorted(set(result.teams_made)))}")
        if result.rejected:
            self.stdout.write(
                f"{prefix} anyway -- each bad row is skipped, not fatal, so a "
                "spreadsheet with two mistakes still lands the rest."
            )
        self.stdout.write("")
        self.stdout.write(f"Columns read: {', '.join(COLUMNS)}")
        self.stdout.write("Anything else in the file is ignored, not an error.")
        if not options["dry_run"] and result.total:
            self.stdout.write("")
            self.stdout.write(
                "Next: run the assignment plan at /organizer/assignments/ once your "
                "judges are bound."
            )
        sys.stdout.flush()
