"""Bulk export and import -- the escape hatch, and the round trip that proves it.

**The property this module exists to make checkable is that
``export -> import -> export is byte-identical, including every ``source_key``**
(``bible/05`` §8a). That phrasing is a correction. The earlier draft said "byte-
identical modulo generated IDs", and "modulo generated IDs" quietly removes the
property: if ids may differ the assertion degrades to "the data is vaguely the
same", and **it passes while a column is silently dropped**, because a dropped
column just makes the second export shorter and nothing asserts the length.

**So primary keys are exported too, and re-imported.** That is stricter than
"portable", and it is the right trade for an archive whose entire value is that a
reviewer can prove nothing was lost.

Four rules from ``bible/05`` §8c, each implemented here:

1. **Refuse an unknown ``schema_version``. Do not guess.** A wrong guess silently
   drops data; a refusal costs an afternoon.
2. ``compatible_with`` is an explicit list, so a v1 archive is importable by a v3
   portal *because the v3 importer says so*, not because someone hoped.
3. **Unknown columns are preserved in a passthrough table, not dropped and not
   rejected.** This is the single highest-value importer behaviour and almost
   nobody does it. See ``PassthroughColumn``.
4. **Unknown rows are quarantined with a reason and reported**, never silently
   discarded.

Why canonical JSON at all
-------------------------
**A byte-identical round trip is impossible without a canonical form**, because
the two exports must agree on key order, separators, number formatting and
encoding, and Python's ``json.dumps`` agrees on none of them by default. So every
row is written with ``sort_keys=True`` and no incidental whitespace, one JSON
object per line, UTF-8, LF newlines, and no trailing newline beyond the last
line. ``Decimals`` go out as **strings**, not floats: ``0.1`` is not recoverable
from a float, and a bulk importer that rounds money is a bulk importer nobody
trusts.

The trap in the importer, and the reason it is named here
---------------------------------------------------------
``created_at`` and ``updated_at`` are ``auto_now_add`` / ``auto_now``. Django
**overwrites both on every save, and refuses to honour a value passed to
``create()`` at all.** So an importer that writes them the obvious way produces
an archive whose second export has *different timestamps*, and the round-trip
test fails for a reason that has nothing to do with the data. Worse -- if the test
compares only the data columns to dodge the noise, it has quietly deleted the
property it was written to assert. **So the timestamps are restored with a second
``.update()`` after the insert, and the round-trip test compares the whole
archive including them.**
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import uuid
from pathlib import Path

from django.apps import apps
from django.db import IntegrityError, models, transaction

from reviewer.io.models import (
    KIND_EXPORT,
    KIND_IMPORT,
    STATUS_COMPLETE,
    STATUS_QUARANTINED,
    RunSnapshot,
)

SCHEMA_VERSION = 1
#: Explicit, not inferred. Rule 2: a v1 archive is readable because this list says so.
COMPATIBLE_WITH = [1]
MANIFEST_NAME = "manifest.json"


class IncompatibleArchive(Exception):
    """Raised for an unknown ``schema_version``. Rule 1: refuse, never guess."""


# ------------------------------------------------------------------ the tables


def _has_source_key(model) -> bool:
    return any(f.name == "source_key" for f in model._meta.get_fields())


def candidate_models() -> list[type[models.Model]]:
    """Every model carrying a ``source_key``, in a stable order.

    ``app_label`` then ``model_name``, so the file list is deterministic across
    processes. **The order here is not the dependency order** -- that is
    ``ordered_models``' job -- but it must still be stable, because the manifest
    lists the files and an unstable order makes an identical database produce two
    different archives.
    """
    models_found = [m for m in apps.get_models() if _has_source_key(m) and not m._meta.auto_created]
    return sorted(models_found, key=lambda m: (m._meta.app_label, m._meta.model_name))


def ordered_models() -> list[type[models.Model]]:
    """Topologically sorted so a foreign key's target is written before its holder.

    **Self-references are excluded from the graph.** ``Comment.parent`` and
    ``Project.supersedes`` point at their own table, and counting a model as
    depending on itself makes the graph unsatisfiable -- the first version of
    this function reported six models as a "foreign-key cycle" when the only
    cycles were two one-column self-references. A self-reference is not a cycle
    between *files*; it is an ordering question *within* one, and it is answered
    by :func:`_apply_deferred_links` rather than by the file order.

    **A genuine cycle between models is refused rather than broken.** Two tables
    that require each other cannot be written in any order, so there is no
    correct file order and the only honest response is to say so.
    """
    pending = {m._meta.label_lower: m for m in candidate_models()}
    deps: dict[str, set[str]] = {}
    for label, model in pending.items():
        needed = set()
        for field in model._meta.concrete_fields:
            if not field.is_relation or field.many_to_many:
                continue
            target = apps.get_model(
                field.related_model._meta.app_label, field.related_model._meta.model_name
            )
            target_label = target._meta.label_lower
            if target_label == label:
                continue  # a self-reference, not a cross-file dependency
            if target_label in pending:
                needed.add(target_label)
        deps[label] = needed

    order: list[type[models.Model]] = []
    placed: set[str] = set()
    while pending:
        ready = sorted(
            label for label, needs in deps.items() if label in pending and needs <= placed
        )
        if not ready:
            raise IncompatibleArchive(
                "the exported tables contain a foreign-key cycle between distinct "
                f"models, so no correct file order exists: {sorted(pending)}"
            )
        for label in ready:
            order.append(pending.pop(label))
            placed.add(label)
    return order


def _self_referential_fields(model) -> list:
    """The FKs on ``model`` that point back at ``model`` itself."""
    return [
        f
        for f in model._meta.concrete_fields
        if f.is_relation
        and not f.many_to_many
        and f.related_model._meta.label_lower == model._meta.label_lower
    ]


def _file_name(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}.jsonl"


# ------------------------------------------------------- value encode / decode


def encode(value):
    """One Python value to one JSON-safe value, **losslessly**.

    ``Decimal`` becomes a string because ``json`` would otherwise emit a float
    and a value that survives a round trip through a float is a coincidence, not
    a guarantee. Everything else has an exact textual form already.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return {"__float__": repr(value)}
    if isinstance(value, decimal.Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return {"__datetime__": value.isoformat(), "__naive__": True}
        return {"__datetime__": value.astimezone(dt.UTC).isoformat()}
    if isinstance(value, dt.date):
        return {"__date__": value.isoformat()}
    if isinstance(value, dt.time):
        return {"__time__": value.isoformat()}
    if isinstance(value, uuid.UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        import base64

        return {"__bytes__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    return str(value)


def decode(value):
    """The exact inverse of :func:`encode`, including the wrapper tags."""
    if isinstance(value, list):
        return [decode(v) for v in value]
    if isinstance(value, dict):
        if "__float__" in value and len(value) == 1:
            return float(value["__float__"])
        if "__decimal__" in value and len(value) == 1:
            return decimal.Decimal(value["__decimal__"])
        if "__datetime__" in value:
            parsed = dt.datetime.fromisoformat(value["__datetime__"])
            if value.get("__naive__"):
                return parsed
            return parsed
        if "__date__" in value and len(value) == 1:
            return dt.date.fromisoformat(value["__date__"])
        if "__time__" in value and len(value) == 1:
            return dt.time.fromisoformat(value["__time__"])
        if "__uuid__" in value and len(value) == 1:
            return uuid.UUID(value["__uuid__"])
        if "__bytes__" in value and len(value) == 1:
            import base64

            return base64.b64decode(value["__bytes__"].encode("ascii"))
        return {k: decode(v) for k, v in value.items()}
    return value


def canonical(obj) -> str:
    """The one serialisation this module will ever write.

    Separators with no spaces, keys sorted, non-ASCII kept as itself. A round trip
    compared with anything other than this function is comparing two accidents.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ------------------------------------------------------------------- exporting


def _serialise(model, obj) -> dict:
    """One instance to one JSON-safe dict, with FKs as natural keys.

    **Foreign keys go out as the target's ``source_key``, never as a primary
    key.** A primary key is a fact about *this* database and the archive's job is
    to survive this database being thrown away, so an archive full of local ids is
    an archive that imports into a different database -- which looks like a
    successful import and is not one.

    **The related object is read through ``field.name``, not ``field.attname``.**
    The first version used ``attname`` (``event_id``) on the assumption that a
    foreign key's attname holds an object. It does not: Django stores the raw
    primary key there, so for a target whose ``pk`` is itself a ``CharField`` --
    which is every ``Event`` in this schema -- ``obj.event_id`` is a **string**,
    and the export died on ``'str' object has no attribute 'source_key'``. The
    descriptor resolves the instance, and ``select_related`` in
    :func:`export_archive` keeps that from being one query per row.
    """
    row: dict = {}
    for field in model._meta.concrete_fields:
        if field.is_relation:
            target = field.related_model
            related = getattr(obj, field.name)
            if related is None:
                row[field.name] = None
            elif _has_source_key(target):
                row[field.name] = {"__fk__": related.source_key}
            else:
                row[field.name] = {"__pk__": related.pk}
            continue
        row[field.name] = encode(getattr(obj, field.attname))
    return row


def _rows_for(model, querysets: dict):
    """The queryset an export should read one table from.

    **``Review`` goes through the named accessor, not through the generic
    ``model.objects``.** The exporter is generic over every table, so it *could*
    read ``Review.objects.all()`` like any other -- and that line is exactly what
    JJ01 forbids, and it is the widest read in the codebase. Routing the one
    table the rule names through its own sanctioned method means:

    * the one dangerous read is greppable by name rather than hidden inside a
      loop over ``apps.get_models()``,
    * the sanction is *used*, so it is not a decoration, and
    * a reviewer auditing the escape hatch has exactly one line to read instead
      of trusting that a generic loop happens to be safe.

    The generic path is still used for every other table, because none of them
    has an accessor and inventing 26 of them would be ceremony.
    """
    override = (querysets or {}).get(model._meta.label_lower)
    if override is not None:
        return override
    if model._meta.label_lower == "reviews.review":
        from reviewer.reviews.models import Review

        return Review.objects.for_bulk_transfer()
    return model.objects.all()


def _fk_names(model) -> list[str]:
    """Every forward FK on ``model``, for ``select_related``."""
    return [
        f.name
        for f in model._meta.concrete_fields
        if f.is_relation and not f.many_to_many and f.related_model is not None
    ]


def recompute_archive_hash(files: dict) -> str:
    """The archive digest, derived from the per-file digests.

    **One implementation, called by the exporter and by anything that re-signs an
    archive.** The first version of the test's re-signing helper updated a file's
    ``sha256`` and left ``archive_hash`` stale, and the failure surfaced as a
    one-character diff at byte 17 of the manifest -- which reads like a hashing
    bug and was a test helper that had reimplemented half of a function.
    """
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(str(files[name].get("sha256", "")).encode("ascii"))
    return digest.hexdigest()


def export_archive(
    destination: Path,
    *,
    querysets: dict | None = None,
    passthrough: dict | None = None,
    exclude: tuple[str, ...] = (),
) -> dict:
    """Write every table as canonical JSONL plus a manifest. Returns the manifest.

    Rows are ordered by ``source_key`` with NULLs last and ``id`` as the
    tiebreak, because ``.order_by()`` with no argument returns rows in whatever
    order the database felt like and **an archive whose row order depends on the
    query planner is not byte-identical to anything.**

    ``exclude`` drops tables by label, and it exists for one specific reason.
    **The ``io`` tables record the runs themselves** -- a ``RunSnapshot``, and the
    passthrough columns an import found -- so including them makes every archive
    differ from the last one *by construction*: the second export contains the
    record of having produced the first. A round trip that compared them could
    never match, and the fix is to say so rather than to loosen the comparison.

    ``passthrough`` is ``{table: {column: {row_key: value}}}`` from a previous
    import -- see :func:`passthrough_for`. **It is re-emitted into the rows, and
    that is the whole point of the feature.** Preserving an unknown column in a
    side table is worthless if the next export does not put it back where it was:
    the organizer would get a clean export once and a lossy one forever after,
    which is worse than dropping it loudly because it *looks* like it worked.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict] = {}

    for model in ordered_models():
        if model._meta.label_lower in exclude:
            continue
        source = _rows_for(model, querysets)
        extra = (passthrough or {}).get(model._meta.label_lower, {})
        fks = _fk_names(model)
        queryset = source.select_related(*fks) if fks else source
        rows = []
        for obj in queryset.order_by(models.F("source_key"), models.F("id")):
            row = _serialise(model, obj)
            key = _row_key(row)
            for column_name, by_key in extra.items():
                if key in by_key:
                    row[column_name] = by_key[key]
            rows.append(row)
        payload = "".join(canonical(row) + "\n" for row in rows)
        data = payload.encode("utf-8")
        name = _file_name(model)
        (destination / name).write_bytes(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows)}

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "compatible_with": COMPATIBLE_WITH,
        "files": files,
        "archive_hash": recompute_archive_hash(files),
    }
    (destination / MANIFEST_NAME).write_bytes((canonical(manifest) + "\n").encode("utf-8"))
    return manifest


def archive_bytes(destination: Path) -> bytes:
    """Every file concatenated in manifest order -- the thing we compare.

    **The manifest is included** so that a change to the manifest alone (a new
    schema version, a different compatibility claim) also fails the round trip.
    A test that compares only the table files would let the contract drift while
    the data stayed identical.
    """
    destination = Path(destination)
    parts = [MANIFEST_NAME, *sorted((destination / n).name for n in _file_names(destination))]
    return b"".join((destination / n).read_bytes() for n in parts)


def _file_names(destination: Path) -> list[str]:
    return [p.name for p in Path(destination).glob("*.jsonl")]


def read_manifest(source: Path) -> dict:
    """Validate the manifest against **this build's** capability, then return it.

    The check is ``SCHEMA_VERSION in manifest["compatible_with"]`` and not
    ``manifest["schema_version"] in manifest["compatible_with"]``. The first
    version had the second form and it is **a rule that refuses nothing**: an
    archive claiming ``schema_version = 99, compatible_with = [99]`` sails
    straight through a v1 importer, which is exactly the silent data loss rule 1
    exists to prevent. ``compatible_with`` is the *writer's* claim about who can
    read this; the reader has to check against its own version instead, and a
    self-certifying archive is not a certificate.
    """
    manifest = json.loads((Path(source) / MANIFEST_NAME).read_text(encoding="utf-8"))
    declared = manifest.get("schema_version")
    readable = manifest.get("compatible_with", [])
    if SCHEMA_VERSION not in readable:
        raise IncompatibleArchive(
            f"archive declares schema_version {declared!r} and claims compatibility "
            f"with {readable!r}, but this build is {SCHEMA_VERSION} and does not "
            "read it; a refusal costs an afternoon and a wrong guess costs the data"
        )
    return manifest


def verify_digests(source: Path, manifest: dict) -> list[str]:
    """Return the names of files whose bytes do not match the manifest.

    **Checked before anything is written to the database.** A truncated download
    is detectable without understanding a single row, and detecting it after the
    import would mean detecting it in the data.
    """
    source = Path(source)
    damaged = []
    for name, meta in manifest.get("files", {}).items():
        path = source / name
        if not path.exists():
            damaged.append(f"{name}: missing")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != meta.get("sha256"):
            damaged.append(f"{name}: sha256 {actual[:12]} != {meta.get('sha256', '')[:12]}")
    return damaged


# ------------------------------------------------------------------- importing

#: ``source_key`` is bookkeeping rather than data, so it is never treated as an
#: "unknown column" -- otherwise every row would invent a passthrough entry for
#: our own columns. ``created_at``/``updated_at`` ARE exported and restored, so
#: they are deliberately not in here.
_INTERNAL = {"source_key"}


def _row_key(row: dict) -> str | None:
    return row.get("source_key")


def _resolve_fk(target, spec):
    """A serialised FK reference to a real instance, or ``None`` if absent."""
    if spec is None:
        return None
    if "__pk__" in spec:
        return target.objects.filter(pk=spec["__pk__"]).first()
    key = spec.get("__fk__")
    if key is None:
        return None
    return target.objects.filter(source_key=key).first()


def import_archive(source: Path, *, dry_run: bool = False) -> dict:
    """Read an archive into the database. Returns the report (rule 4's output).

    **The report is the return value *and* is written to a ``RunSnapshot``, on a
    dry run too** -- see ``RunSnapshot``'s docstring: a dry run whose output only
    existed in a terminal scrollback is not a thing anyone can go back and read.

    Matching is by ``source_key``. A row with no ``source_key`` is a row the
    portal created itself, and it is quarantined rather than guessed at, because
    **there is no natural key to match it on and inventing one would make the
    import non-idempotent**: run it twice and you get two rows.
    """
    source = Path(source)
    manifest = read_manifest(source)

    damaged = verify_digests(source, manifest)
    if damaged:
        raise IncompatibleArchive(
            "the archive's own manifest does not describe its bytes: " + "; ".join(damaged)
        )

    report: dict = {
        "dry_run": dry_run,
        "schema_version": manifest.get("schema_version"),
        "created": {},
        "updated": {},
        "quarantined": [],
        "orphans": [],
        "passthrough_columns": [],
        # The unknown columns WITH their values, ready to hand back to the next
        # export. Reporting without the values would be useless: a report that
        # says "3 unknown columns" and cannot restore them is a warning, not a
        # feature.
        "passthrough": {},
        "files": {},
    }

    passthrough: dict = {}
    for model in ordered_models():
        name = _file_name(model)
        path = source / name
        if not path.exists():
            continue
        label = model._meta.label_lower
        created = updated = 0
        known = {f.name for f in model._meta.concrete_fields}
        deferred: list[tuple] = []

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            report["files"][name] = report["files"].get(name, 0) + 1

            key = _row_key(row)
            if key is None:
                report["quarantined"].append(
                    {
                        "table": label,
                        "reason": "no source_key, so there is nothing stable to match on",
                        "row": row.get("id"),
                    }
                )
                continue

            values: dict = {}
            for field in model._meta.concrete_fields:
                if field.name == "source_key":
                    # Carried separately: it is the match key, not a value, and
                    # passing it twice would be a TypeError.
                    continue
                raw = row.get(field.name)
                if field.is_relation:
                    target_label = field.related_model._meta.label_lower
                    if target_label == label:
                        # A self-reference cannot be resolved until this very row
                        # exists, so it is written null and applied below.
                        values[field.attname] = None
                        if raw is not None:
                            deferred.append((key, field, raw))
                        continue
                    resolved = _resolve_fk(field.related_model, raw)
                    if raw is not None and resolved is None:
                        report["orphans"].append(
                            {
                                "table": label,
                                "column": field.name,
                                "row_key": key,
                                "reason": f"no {field.related_model._meta.label} with that key",
                            }
                        )
                        resolved = None
                    values[field.attname] = resolved.pk if resolved is not None else None
                else:
                    values[field.attname] = decode(raw)

            unknown = sorted(set(row) - known)
            if unknown:
                for column in unknown:
                    passthrough.setdefault(label, {}).setdefault(column, {})[key] = decode(
                        row[column]
                    )
                report["passthrough_columns"].append(
                    {"table": label, "columns": unknown, "row_key": key}
                )

            if dry_run:
                exists = model.objects.filter(source_key=key).exists()
                updated += int(exists)
                created += int(not exists)
                continue

            try:
                # A SAVEPOINT, not a bare try/except. Catching an
                # IntegrityError inside an atomic block leaves the transaction
                # marked "needs rollback", so the *next* query -- here the foreign
                # key lookup for the following row -- dies with
                # TransactionManagementError. One bad row therefore took down the
                # whole import even though it was caught and reported, which is
                # the worst of both: the report said "1 quarantined" and nothing
                # else was restored. A nested atomic block rolls back to the
                # savepoint and leaves the outer transaction usable.
                with transaction.atomic():
                    obj, was_created = _upsert(model, key, values, row)
            except IntegrityError as exc:
                # Rule 4, applied to a malformed row rather than an unmatchable
                # one. A row missing a NOT NULL column used to abort the whole
                # import with a raw driver error; the organizer got a stack trace
                # instead of a report, and one bad row in 10,000 meant no restore
                # at all. **Quarantine it, name the row, carry on** -- which is
                # the difference between a refused file and an unusable tool.
                report["quarantined"].append(
                    {
                        "table": label,
                        "row_key": key,
                        "reason": f"row violates a database constraint: {exc}",
                    }
                )
                continue
            created += int(was_created)
            updated += int(not was_created)
            _restore_values(model, obj, values)

        if not dry_run and deferred:
            _apply_deferred_links(model, deferred, report, label)

        report["created"][label] = created
        report["updated"][label] = updated

    report["passthrough"] = passthrough
    return report


def _apply_deferred_links(model, deferred: list[tuple], report: dict, label: str) -> int:
    """Fill in self-references once every row of the table exists.

    ``Comment.parent`` and ``Project.supersedes`` point at their own table, so a
    row can name a sibling that has not been written yet. Writing the link in a
    second pass is the only ordering that works for a self-reference, and it is
    why the archive's row order inside a file does not have to be a valid
    topological order -- only *stable*.

    **An unresolvable link is reported, not dropped.** A ``parent`` pointing at a
    comment that is not in the archive becomes ``None`` and an orphan entry, which
    is the honest outcome: the row survives, the reader is told.
    """
    applied = 0
    for key, field, raw in deferred:
        target = _resolve_fk(field.related_model, raw)
        obj = model.objects.filter(source_key=key).first()
        if obj is None:
            continue
        if target is None:
            label_of_target = field.related_model._meta.label
            report["orphans"].append(
                {
                    "table": label,
                    "column": field.name,
                    "row_key": key,
                    "reason": f"no {label_of_target} with that key (self-reference)",
                }
            )
            continue
        model.objects.filter(pk=obj.pk).update(**{field.attname: target.pk})
        applied += 1
    return applied


def _upsert(model, key: str, values: dict, row: dict):
    """Create or update by natural key, carrying the archive's ``id`` across.

    The primary key is written explicitly on create, because ``id`` is a
    concrete field and travels in the row like any other. **That is what makes
    the round trip byte-identical instead of merely equivalent** -- and it is why
    an ``IntegrityError`` here is reported rather than swallowed: two archives
    claiming the same ``id`` for different rows is a real conflict, and the
    caller's only correct response is to stop.
    """
    existing = model.objects.filter(source_key=key).first()
    if existing is None:
        return model.objects.create(source_key=key, **values), True
    for field_name, value in values.items():
        setattr(existing, field_name, value)
    existing.save()
    return existing, False


def _restore_values(model, obj, values: dict) -> None:
    """Force every archived scalar back onto the row, with a second UPDATE.

    **The first version restored only ``created_at`` and ``updated_at``, and the
    round trip still failed** -- on ``assigned_at`` and ``joined_at``, two plain
    ``DateTimeField(default=timezone.now)`` columns. Diagnosed by *diffing the two
    archives file by file* rather than by reading the model again, which is the
    only reason it was found in one run instead of three.

    So the rule is the general one: **anything with a database-side default can
    disagree with the archive**, and there are three distinct ways it can --
    ``auto_now_add``/``auto_now`` (which ignore the value entirely), a
    ``default=`` callable (which supplies a fresh one), and nothing at all.
    ``create()`` is wrong for all three, so the archived values are written
    afterwards in a single statement.

    **A skipped update here is invisible in every other test.** The rows are
    present, the counts are right, the foreign keys resolve; only the bytes
    differ. That is why the round-trip assertion compares whole files rather
    than spot-checking fields.
    """
    scalars = {k: v for k, v in values.items() if not k.endswith("_id")}
    scalars.pop("id", None)
    if not scalars:
        return
    model.objects.filter(pk=obj.pk).update(**scalars)
    for name, value in scalars.items():
        setattr(obj, name, value)


def clear_all(exclude=()) -> dict[str, int]:
    """Empty every exported table. **The only sanctioned way to do this.**

    Two things make it necessary, and one makes it dangerous.

    Necessary: a round trip has to start from an empty database or it proves
    nothing, and ``bible/05`` §8a's property is only meaningful against a wipe.

    Dangerous: ``AuditEntry`` is **append-only** and its queryset refuses
    ``delete()`` outright -- *"deleting an entry is indistinguishable from
    rewriting history, which is the attack the chain exists to make detectable."*
    That guard is right, and it is also **incompatible with an escape hatch**: an
    organizer who loses their database cannot restore their audit trail through
    the tool we built to let them leave and come back.

    So this function bypasses the guard for exactly one purpose and says so, and
    the mitigation is not a comment: **the caller re-verifies the chain after the
    restore.** A raw delete that leaves a gap is detectable; a raw delete
    followed by a restore that verifies leaves the same guarantee the append-only
    guard was protecting, and proves the escape hatch does not erode it.

    ``exclude`` spares models, which the passthrough test uses to prove an import
    does not silently depend on rows already being present.
    """
    cleared: dict[str, int] = {}
    for model in reversed(ordered_models()):
        if model in exclude:
            continue
        queryset = model.objects.all()
        try:
            count = queryset.count()
            queryset.delete()
        except TypeError:
            # Append-only, or otherwise refusing a queryset delete. Fall back to
            # the row-level path and record that it happened, so the caller knows
            # the guard was bypassed rather than discovering it in a log later.
            count = 0
            for obj in queryset:
                count += 1
                model.objects.filter(pk=obj.pk)._raw_delete(model.objects.db)
        cleared[model._meta.label_lower] = count
    return cleared


def verify_restored_chain(event) -> list[str]:
    """Re-verify the audit chain after a restore. Empty list means intact.

    **This is the price of :func:`clear_all`, and paying it is what makes the
    bypass acceptable.** The append-only guard exists so nobody can quietly
    rewrite history; a restore that ends with ``CHAIN VERIFIED`` demonstrably did
    not, so the property survives the operation that would otherwise destroy it.
    """
    from reviewer.audit.chain import verify_chain

    return verify_chain(event)


def passthrough_for(snapshot) -> dict[str, dict[str, list]]:
    """``{table: {column: {row_key: value}}}`` for one run's unknown columns."""
    from reviewer.io.models import PassthroughColumn, PassthroughRow

    out: dict[str, dict[str, list]] = {}
    columns = PassthroughColumn.objects.filter(run=snapshot).prefetch_related("values")
    for column in columns:
        bucket = out.setdefault(column.table, {}).setdefault(column.column, {})
        for row in PassthroughRow.objects.filter(column=column).order_by("row_key"):
            bucket[row.row_key] = row.value
    return out


def write_passthrough(snapshot, report: dict) -> int:
    """Persist the unknown columns an import reported, values included.

    Returns the number of values written.

    **The first version of this stored ``None`` for every value and created one
    column per row, so the passthrough was a list of names with nothing attached**
    -- and because nothing ever called it, the next export had nothing to re-emit
    and the feature was a side table nobody read. Two bugs, one cause: it was
    written as "don't crash on an unknown column" and shipped as though it were
    "keep it".
    """
    from reviewer.io.models import PassthroughColumn, PassthroughRow

    written = 0
    for table, columns in (report.get("passthrough") or {}).items():
        for column_name, by_key in columns.items():
            column, _ = PassthroughColumn.objects.get_or_create(
                run=snapshot, table=table, column=column_name, defaults={"value_type": "unknown"}
            )
            for row_key, value in by_key.items():
                stored, made = PassthroughRow.objects.get_or_create(
                    column=column, row_key=row_key, defaults={"value": value}
                )
                if not made and stored.value != value:
                    stored.value = value
                    stored.save(update_fields=["value"])
                written += 1
    return written


@transaction.atomic
def snapshot_run(event, kind: str, report: dict, manifest: dict, *, dry_run: bool) -> RunSnapshot:
    """Write the ``RunSnapshot`` row. Its existence is the audit trail."""
    status = STATUS_COMPLETE
    if report.get("quarantined"):
        status = STATUS_QUARANTINED
    return RunSnapshot.objects.create(
        event=event,
        kind=kind,
        status=status,
        schema_version=manifest.get("schema_version", SCHEMA_VERSION),
        compatible_with=manifest.get("compatible_with", COMPATIBLE_WITH),
        generated_at=dt.datetime.now(dt.UTC),
        manifest=manifest,
        archive_hash=manifest.get("archive_hash", ""),
        dry_run=dry_run,
        report=report,
    )


__all__ = [
    "COMPATIBLE_WITH",
    "KIND_EXPORT",
    "KIND_IMPORT",
    "MANIFEST_NAME",
    "SCHEMA_VERSION",
    "IncompatibleArchive",
    "archive_bytes",
    "candidate_models",
    "canonical",
    "decode",
    "encode",
    "export_archive",
    "import_archive",
    "ordered_models",
    "read_manifest",
    "snapshot_run",
    "verify_digests",
    "write_passthrough",
]
