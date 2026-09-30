"""``manage.py export_run`` -- write the whole database as a portable archive.

The escape hatch. *"A migration path in and out, because a platform you cannot
leave is a trap"* (``bible/05`` §8a).

Two things this command does that a naive ``dumpdata`` does not, and both are the
reason it exists:

* **It writes the manifest and refuses to guess.** ``schema_version`` and an
  explicit ``compatible_with`` list travel with the bytes, so a later importer
  knows what it is reading because we said so, not because someone hoped.
* **It re-emits the passthrough.** Columns an earlier import preserved because
  this build had never heard of them come back out, in their original column of
  their original rows. Without that the organizer gets one clean export and
  lossy ones forever after, which is worse than dropping them loudly.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from reviewer.io import bundle
from reviewer.io.models import KIND_EXPORT, RunSnapshot


class Command(BaseCommand):
    help = "Export every source_key table as a canonical, signed JSONL archive."

    def add_arguments(self, parser):
        parser.add_argument("destination", help="Directory to write the archive into.")
        parser.add_argument("--event", default="", help="Only this event's rows.")
        parser.add_argument(
            "--passthrough-from",
            default="latest",
            help=(
                "Which import's preserved columns to re-emit: 'latest', 'none', "
                "or a RunSnapshot id. 'latest' is why an unknown column survives."
            ),
        )
        parser.add_argument(
            "--exclude",
            default="",
            help="Comma-separated table labels to leave out, e.g. the io bookkeeping tables.",
        )

    def handle(self, *args, **options):
        destination = Path(options["destination"])
        exclude = tuple(x.strip() for x in options["exclude"].split(",") if x.strip())

        passthrough = self._passthrough(options["event"], options["passthrough_from"])
        querysets = self._querysets(options["event"], exclude)

        manifest = bundle.export_archive(
            destination, querysets=querysets, passthrough=passthrough, exclude=exclude
        )

        event = self._event(options["event"])
        run = bundle.snapshot_run(
            event,
            KIND_EXPORT,
            {"dry_run": False, "files": manifest["files"]},
            manifest,
            dry_run=False,
        )

        rows = sum(meta["rows"] for meta in manifest["files"].values())
        self.stdout.write(
            f"EXPORTED {rows} rows across {len(manifest['files'])} tables\n"
            f"  archive_hash {manifest['archive_hash']}\n"
            f"  snapshot     {run.pk}"
        )
        if passthrough:
            columns = sum(len(cols) for table in passthrough.values() for cols in table.values())
            self.stdout.write(f"  passthrough   {columns} preserved column(s) re-emitted")

    def _passthrough(self, event_id: str, source: str) -> dict:
        if source == "none":
            return {}
        snapshot = self._snapshot(event_id, source)
        return bundle.passthrough_for(snapshot) if snapshot is not None else {}

    def _snapshot(self, event_id: str, source: str):
        snaps = RunSnapshot.objects.filter(kind=bundle.KIND_IMPORT)
        if event_id:
            snaps = snaps.filter(event_id=event_id)
        if source == "latest":
            return snaps.order_by("-generated_at").first()
        return snaps.filter(pk=source).first()

    def _event(self, event_id: str):
        from reviewer.events.models import Event

        if event_id:
            return Event.objects.get(pk=event_id)
        found = Event.objects.first()
        if found is None:
            raise CommandError("no event exists; load the fixtures before exporting")
        return found

    def _querysets(self, event_id: str, exclude: tuple) -> dict:
        """Narrow to one event's rows when asked.

        **A table with a nullable ``event`` keeps its unowned rows.** Filtering
        those on ``event_id`` alone would silently drop them, and "we exported this
        event" would quietly mean "we exported the parts of this event that have
        an event column" -- the F-89 shape, where the command succeeds and the
        archive is missing something nobody was told about.
        """
        if not event_id:
            return {}
        out: dict = {}
        for model in bundle.ordered_models():
            label = model._meta.label_lower
            if label in exclude:
                continue
            fields = {f.name: f for f in model._meta.concrete_fields}
            event_field = fields.get("event")
            if event_field is None:
                continue
            if event_field.null:
                out[label] = model.objects.filter(Q(event_id=event_id) | Q(event__isnull=True))
            else:
                out[label] = model.objects.filter(event_id=event_id)
        return out
