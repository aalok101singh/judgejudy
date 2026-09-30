"""``manage.py import_run`` -- read an archive back, and say what happened.

The other half of the escape hatch, and the half that has to be honest. Four
behaviours, each one a refusal rather than a guess (``bible/05`` §8c):

1. **An unknown ``schema_version`` is refused.** Not guessed at.
2. **``compatible_with`` is checked against *this* build**, not against the
   archive's own claim -- a self-certifying archive is not a certificate.
3. **Unknown columns are preserved**, values included, and handed back to the
   next export.
4. **Unmatchable and malformed rows are quarantined with a reason**, never
   silently discarded, and one bad row does not abort the other 10,000.

``--dry-run`` reports without writing **and still records a ``RunSnapshot``**,
because a dry run whose output only existed in a terminal scrollback is not a
thing anyone can go back and read.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from reviewer.io import bundle
from reviewer.io.models import KIND_IMPORT


class Command(BaseCommand):
    help = "Import a canonical JSONL archive, reporting everything it refused."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Directory holding the archive.")
        parser.add_argument("--event", default="", help="Attribute the run to this event.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without writing. The report is still saved as a RunSnapshot.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not (source / bundle.MANIFEST_NAME).exists():
            raise CommandError(f"{source} does not look like an archive: no {bundle.MANIFEST_NAME}")

        try:
            report = bundle.import_archive(source, dry_run=options["dry_run"])
        except bundle.IncompatibleArchive as exc:
            # A refusal, printed as a refusal. The exit code is non-zero so a
            # script cannot mistake it for a successful restore.
            raise CommandError(str(exc)) from exc

        from reviewer.events.models import Event

        event = (
            Event.objects.get(pk=options["event"]) if options["event"] else Event.objects.first()
        )
        run = bundle.snapshot_run(
            event,
            KIND_IMPORT,
            report,
            bundle.read_manifest(source),
            dry_run=options["dry_run"],
        )

        if not options["dry_run"]:
            bundle.write_passthrough(run, report)

        created = sum(report["created"].values())
        updated = sum(report["updated"].values())
        self.stdout.write(
            f"{'DRY RUN - nothing written' if options['dry_run'] else 'IMPORTED'}: "
            f"{created} created, {updated} updated\n"
            f"  quarantined   {len(report['quarantined'])}\n"
            f"  orphans       {len(report['orphans'])}\n"
            f"  passthrough    {len(report['passthrough'])} table(s)\n"
            f"  archive_hash  {run.archive_hash}\n"
            f"  snapshot      {run.pk}"
        )
        if report["quarantined"]:
            self.stdout.write("  first refusal: " + str(report["quarantined"][0]))
