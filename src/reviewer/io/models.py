"""RunSnapshot -- the manifest for a bulk export or import.

**This is the escape hatch, and the sentence that gives it weight:** *"a
migration path in and out, because a platform you cannot leave is a trap."* It is
filed under T4 in the plan and it is the cheapest goodwill in the project.

The property it exists to make checkable is the round trip: **export -> import
-> export is byte-identical, *including every ``source_key``*** (``bible/05``
§8a). That phrasing is a correction, and it is the difference between a test and
a non-test. The earlier draft said "byte-identical modulo generated IDs", and
"modulo generated IDs" quietly removes the property: if ids may differ the
assertion degrades to "the data is vaguely the same", and **it passes while a
column is silently dropped**, because a dropped column just makes the second
export shorter and nothing asserts the length.

**One row per run, with the manifest attached.** ``manifest`` holds the
per-file SHA-256 and row counts; ``archive_hash`` covers the whole archive. Four
rules belong with it (``bible/05`` §8c) and each is one line of code:

* **Refuse an unknown ``schema_version``. Do not guess.** A wrong guess silently
  drops data; a refusal costs an afternoon.
* ``compatible_with`` is an explicit list, so a v1 archive is importable by a v3
  portal *because the v3 importer says so*, not because someone hoped.
* Unknown **columns** in an incoming file are preserved in a passthrough table,
  not dropped and not rejected. An organizer's custom field survives a round trip
  through a portal that has never heard of it. That is the difference between
  "you cannot leave" and "we do not lose your data", and it is the single
  highest-value importer behaviour and almost nobody does it.
* Unknown **rows** are quarantined with a reason and reported, never silently
  discarded.

None of the four is implemented yet -- the exporter and importer are FEAT-07.
The table ships now because the manifest is a **contract**, and a contract
invented at the same moment as the code it describes is a contract that fits
whatever the code happened to do.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

KIND_EXPORT = "export"
KIND_IMPORT = "import"
KIND_CHOICES = [
    (KIND_EXPORT, "Export"),
    (KIND_IMPORT, "Import"),
]

STATUS_PLANNED = "planned"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_QUARANTINED = "quarantined"
STATUS_CHOICES = [
    (STATUS_PLANNED, "Planned"),
    (STATUS_COMPLETE, "Complete"),
    (STATUS_FAILED, "Failed"),
    (STATUS_QUARANTINED, "Quarantined"),
]


class RunSnapshot(SourceKeyMixin, TimeStampedModel, models.Model):
    """One export or import run, with the manifest that describes it.

    ``dry_run`` is a column rather than a command-line flag alone because the
    feature an organizer actually wants is a dry run that **reports without
    writing**, and the report has to survive as a row: counts in, counts out,
    orphan references, duplicates detected, near-duplicate submissions flagged.
    A dry run whose output only ever existed in a terminal scrollback is not a
    thing anyone can go back and read.
    """

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="run_snapshots"
    )
    kind = models.CharField(max_length=8, choices=KIND_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    #: Bumped when the export shape changes. The importer refuses anything it
    #: does not recognise -- see the module docstring.
    schema_version = models.PositiveIntegerField(default=1)
    #: Explicit list of versions this build can read. "Because the importer says
    #: so", not "because someone hoped".
    compatible_with = models.JSONField(default=list)
    generated_at = models.DateTimeField()
    #: {files: {name: {sha256, rows}}, compatible_with: [...], signature: {...}}
    manifest = models.JSONField(default=dict)
    #: SHA-256 over the whole archive, so a truncated download is detectable
    #: before anyone tries to read it.
    archive_hash = models.CharField(max_length=64, blank=True, default="")
    dry_run = models.BooleanField(default=False)
    #: The report: counts in, counts out, orphans, duplicates, quarantined rows
    #: with reasons. Kept even on a dry run -- see the class docstring.
    report = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        related_name="run_snapshots",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "io_runsnapshot"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["event", "kind", "-generated_at"], name="io_snapshot_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.event_id} v{self.schema_version}"


class PassthroughColumn(SourceKeyMixin, TimeStampedModel, models.Model):
    """A column the portal has never heard of, preserved rather than dropped.

    **This is the highest-value behaviour in the importer and almost nobody
    ships it** (``bible/05`` §8c). An organizer running a portal with a custom
    field on ``Project`` exports, upgrades, and imports. The naive importer reads
    a known column list and writes what it recognises -- and the custom field is
    gone, silently, with a successful exit code.

    The difference between "you cannot leave" and "we do not lose your data" is
    exactly this table. An unknown column is recorded here with its name, its
    per-row values, and the table it came from, so a round trip through a portal
    that has never heard of the field returns it **byte-identically**.
    """

    run = models.ForeignKey(
        "RunSnapshot", on_delete=models.CASCADE, related_name="passthrough_columns"
    )
    table = models.CharField(max_length=64)
    column = models.CharField(max_length=128)
    #: The JSON-ish type we saw it as, so a later reader knows how to cast back.
    value_type = models.CharField(max_length=16, default="unknown")

    class Meta:
        db_table = "io_passthroughcolumn"
        unique_together = [("run", "table", "column")]
        ordering = ["table", "column"]

    def __str__(self) -> str:
        return f"{self.table}.{self.column}"


class PassthroughRow(SourceKeyMixin, TimeStampedModel, models.Model):
    """One row's value for one unknown column, addressed by natural key.

    ``row_key`` is the owning row's ``source_key``, **not** its primary key: a
    primary key is local to one database and the whole point of this table is to
    survive the database being replaced.
    """

    column = models.ForeignKey(PassthroughColumn, on_delete=models.CASCADE, related_name="values")
    row_key = models.CharField(max_length=255)
    value = models.JSONField()

    class Meta:
        db_table = "io_passthroughrow"
        unique_together = [("column", "row_key")]
        ordering = ["column_id", "row_key"]

    def __str__(self) -> str:
        return f"{self.column_id}:{self.row_key}"
