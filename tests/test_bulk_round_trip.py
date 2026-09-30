"""The bulk round trip -- ``export -> import -> export`` byte-identical.

``bible/05`` §8a, and this file is the whole reason the phrase includes
``including every source_key``. The earlier draft of the requirement said
"byte-identical modulo generated IDs", which removes the property: with ids
allowed to differ the assertion degrades to "the data is vaguely the same" and
**it passes while a column is silently dropped**, because a dropped column just
makes the second export shorter and nothing asserts the length.

Every test here is arranged so that it can fail. The last one exists purely to
prove that: it drops a column from the archive and asserts the round trip
notices. A round-trip test that has never been seen red is not evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reviewer.io import bundle
from reviewer.io.bundle import (
    IncompatibleArchive,
    archive_bytes,
    canonical,
    decode,
    encode,
    export_archive,
    import_archive,
    ordered_models,
)

pytestmark = pytest.mark.django_db

#: The ``io`` tables record the runs themselves, so a second export contains the
#: record of having produced the first and no round trip could ever match. Excluded
#: by label, and the reason is in `export_archive`'s docstring.
BOOKKEEPING = ("io.runsnapshot", "io.passthroughcolumn", "io.passthroughrow")


@pytest.fixture
def raw_fixture():
    import json as _json

    root = Path(__file__).resolve().parents[1]
    return _json.loads((root / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture):
    from reviewer.events.models import Event
    from reviewer.importer import loader as loader_module

    loader_module.load(raw_fixture)
    return Event.objects.get(pk="evt_01")


@pytest.fixture
def archive(tmp_path, loaded):
    destination = tmp_path / "run-1"
    export_archive(destination, exclude=BOOKKEEPING)
    return destination


def _wipe(keep_types=()) -> None:
    """Empty every exported table, so an import has to rebuild from the archive.

    Goes through :func:`bundle.clear_all` rather than ``.delete()`` because
    ``AuditEntry`` is append-only and refuses a queryset delete outright -- see
    ``clear_all``'s docstring for why that guard and an escape hatch are in
    genuine tension, and why the mitigation is re-verifying the chain rather than
    a comment. ``keep_types`` spares a model, which the passthrough test uses to
    prove an import does not silently depend on rows already being present.
    """
    bundle.clear_all(exclude=keep_types)


class TestTheRoundTripItself:
    def test_export_import_export_is_byte_identical(self, archive, tmp_path, loaded):
        """**The acceptance line.** Byte-for-byte, manifest included.

        **The empty-database precondition is asserted, not assumed, and that
        assertion was added because a mutation proved it was missing.** Making
        `clear_all` clear nothing -- so the "import" wrote no rows at all -- left
        this test **green**, because the importer's upsert re-writes the same
        values onto rows that never left. Byte-identical is therefore necessary
        but *not sufficient*: it cannot distinguish "restored correctly" from
        "never touched anything".

        So the test now states the three things that together make the round trip
        mean something: the tables were empty beforehand, the import reported
        rows **created** rather than updated, and the bytes match afterwards.
        """
        first = archive_bytes(archive)

        _wipe()
        assert _is_empty(), "the round trip did not start from an empty database"
        report = import_archive(archive)
        created = sum(report["created"].values())
        updated = sum(report["updated"].values())

        # Derived from the manifest, not typed. The first version hardcoded 760
        # from arithmetic and the real figure was 979 -- the same transcription
        # mistake this project has now made four times, in the one file whose
        # whole subject is not trusting a number you did not compute.
        expected = sum(
            meta["rows"]
            for name, meta in json.loads((archive / "manifest.json").read_text(encoding="utf-8"))[
                "files"
            ].items()
            if not name.startswith("io.")
        )
        assert created == expected, f"the import created {created} rows, expected {expected}"
        assert updated == 0, (
            f"the import UPDATED {updated} rows against an empty database, so it "
            "matched rows that should not have existed"
        )

        second_dir = tmp_path / "run-2"
        export_archive(second_dir, exclude=BOOKKEEPING)
        second = archive_bytes(second_dir)

        assert second == first, (
            "the second export differs from the first; the archive does not "
            "round-trip and the escape hatch is a one-way door"
        )

    def test_the_archive_holds_every_source_key_table(self, archive):
        """Every table named in the manifest, so a table cannot be forgotten."""
        manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            bundle._file_name(m) for m in ordered_models() if m._meta.label_lower not in BOOKKEEPING
        }
        assert set(manifest["files"]) == expected
        assert manifest["archive_hash"]

    def test_the_row_counts_are_126_reviews_and_not_a_handful(self, archive):
        """**The count is asserted, not assumed.** A truncated export that still
        verifies its own manifest would otherwise pass every other test here."""
        manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["files"]["reviews.review.jsonl"]["rows"] == 126

    def test_a_dropped_column_makes_the_round_trip_fail(self, archive, tmp_path, loaded):
        """**The negative, and the most important test in the file.**

        A column is removed from one row of the archive. The importer must
        restore *something*, so the second export cannot match -- and if it
        somehow did, this whole file would be asserting nothing.

        **The archive is re-signed after the edit, deliberately.** Without that the
        digest check refuses the import and the test would be asserting rule 3
        while claiming to assert the round trip. Getting to the branch under test
        means passing the guard that sits in front of it, which is the same
        technique the quarantine test uses and for the same reason.
        """
        victim = archive / "reviews.review.jsonl"
        lines = victim.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        removed = row.pop("status")
        lines[0] = canonical(row)
        payload = "".join(line + "\n" for line in lines).encode("utf-8")
        victim.write_bytes(payload)
        _repair_digest(archive, "reviews.review.jsonl", payload)

        _wipe()
        import_archive(archive)
        second = tmp_path / "dropped"
        export_archive(second, exclude=BOOKKEEPING)
        assert archive_bytes(second) != archive_bytes(archive), (
            f"a row lost its `{removed}` and the round trip still matched, so the "
            "byte-identical assertion cannot detect a dropped column"
        )

    def test_the_import_is_idempotent(self, archive, loaded):
        """Running it twice changes nothing, because matching is by natural key.

        Without this the escape hatch is a duplicate generator: every restore
        doubles the organizer's data and nothing errors.
        """
        _wipe()
        import_archive(archive)
        first = archive_bytes(archive)
        _wipe()
        import_archive(archive)
        import_archive(archive)
        second = tmp_path_for(archive) / "again"
        export_archive(second, exclude=BOOKKEEPING)
        assert archive_bytes(second) == first


class TestTheExportLabelFallbackStaysLoadBearing:
    """F-69's fallback, kept alive by a row built on purpose.

    **A mutation that removes this fallback stopped being detectable the moment
    FEAT-07 made the loader write ``Review.source_key``** -- the branch simply
    stopped executing, and the mutation reported itself equivalent. That is a
    warning about every test that only exercises the happy path, and the fix is a
    test that constructs the awkward case rather than waiting for the fixture to
    contain one.
    """

    def test_a_review_without_a_source_key_still_labels_itself(self, loaded):
        from reviewer.reviews.api import _review_label
        from reviewer.reviews.models import Review

        review = Review.objects.for_bulk_transfer().filter(source_key__isnull=False).first()
        assert _review_label(review) == review.source_key

        Review.objects.for_bulk_transfer().filter(pk=review.pk).update(source_key=None)
        blanked = Review.objects.for_bulk_transfer().get(pk=review.pk)

        assert _review_label(blanked) == (
            f"{blanked.judge.source_key}:{blanked.project.source_key}"
        ), "the natural-key fallback stopped working for a portal-created review"

    def test_every_loaded_review_now_has_a_real_label(self, loaded):
        """The cause is fixed, so this asserts the *absence* of F-69's symptom."""
        from reviewer.reviews.api import _review_label
        from reviewer.reviews.models import Review

        for review in Review.objects.for_bulk_transfer().all():
            assert _review_label(review), "an exported review label is empty"
            assert ":" in _review_label(review)


def _is_empty() -> bool:
    """True when every exported table really is empty.

    **This exists because a mutation caught what the byte-comparison could not.**
    ``export -> wipe -> import -> export`` matched byte-for-byte even with the
    wipe disabled, so the property under test was "the data is the same", not "the
    import rebuilt it". Asking the database is a different question from asking
    the bytes, and only one of them has an answer when nothing was deleted.
    """
    for model in ordered_models():
        if model._meta.label_lower in BOOKKEEPING:
            continue
        if model.objects.exists():
            return False
    return True


def tmp_path_for(archive: Path) -> Path:
    return archive.parent


class TestTheFourRules:
    """``bible/05`` §8c. Each is one behaviour and one refusal."""

    def test_an_unknown_schema_version_is_refused_not_guessed(self, archive):
        """Rule 1. A wrong guess silently drops data; a refusal costs an afternoon."""
        manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
        manifest["schema_version"] = 99
        manifest["compatible_with"] = [99]
        (archive / "manifest.json").write_bytes((canonical(manifest) + "\n").encode("utf-8"))
        with pytest.raises(IncompatibleArchive) as excinfo:
            import_archive(archive)
        assert "99" in str(excinfo.value)

    def test_a_version_we_claim_is_accepted(self, archive):
        """Rule 2: the list is explicit, so v1 is readable *because we say so*."""
        assert bundle.COMPATIBLE_WITH == [1]
        assert bundle.read_manifest(archive)["schema_version"] == 1

    def test_a_tampered_file_is_refused_before_anything_is_written(self, archive, loaded):
        """**A truncated download is detectable without reading a single row** --
        and it has to be detected *before* the import, not discovered in the data
        afterwards."""
        from reviewer.reviews.models import Review

        victim = archive / "reviews.review.jsonl"
        data = bytearray(victim.read_bytes())
        data[0:1] = b"X"
        victim.write_bytes(bytes(data))

        before = Review.objects.for_bulk_transfer().count()
        with pytest.raises(IncompatibleArchive) as excinfo:
            import_archive(archive)
        assert "sha256" in str(excinfo.value)
        assert Review.objects.for_bulk_transfer().count() == before

    def test_a_row_with_no_source_key_is_quarantined_with_a_reason(self, tmp_path, loaded):
        """Rule 4. A portal-created row has no external key, so there is nothing
        stable to match on -- and inventing one would make the import
        non-idempotent, running twice and doubling the data.

        **The table is ``accounts.user`` because those rows are the ones this test
        writes itself.** After FEAT-07 every row the loader creates carries a
        natural key -- including the demo identities, which got a generated
        ``demo:``-prefixed one -- so the only unkeyed rows are the synthetic one
        below. Testing a branch with a manufactured row is fine *provided the
        branch is real*, and it is pinned separately by
        ``TestEveryLoadedRowHasANaturalKey``.
        """
        source = tmp_path / "synthetic"
        export_archive(source, exclude=BOOKKEEPING)
        victim = source / "accounts.user.jsonl"
        lines = victim.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        row["source_key"] = None
        lines[0] = canonical(row)
        payload = "".join(line + "\n" for line in lines).encode("utf-8")
        victim.write_bytes(payload)
        _repair_digest(source, "accounts.user.jsonl", payload)

        report = import_archive(source, dry_run=True)
        quarantined = [q for q in report["quarantined"] if q["table"] == "accounts.user"]
        assert len(quarantined) == 1
        assert "source_key" in quarantined[0]["reason"]
        assert report["created"].get("accounts.user") == 0, (
            "a quarantined row was still counted as created, so the report "
            "understates what the import refused"
        )


class TestEveryLoadedRowHasANaturalKey:
    """The check that would have found all four gaps at once.

    **This class exists because finding them was archaeology.** Four tables
    shipped with no ``source_key`` -- ``Review``, ``Score``, ``Assignment``,
    ``RoleBinding``, ``TeamMembership`` -- and each one was discovered by a
    *different* symptom: a quarantine report, a NOT NULL violation, a broken
    foreign key. The bug was always the same and the symptom never was.

    So the property is asserted directly: after a load, every row in every
    exported table carries a natural key, except the named exemptions below.
    **The exemption list is explicit, which is the whole point** -- a table whose
    rows legitimately have no external key has to be written down, so "we forgot
    one" and "we decided" cannot look the same.
    """

    #: Tables whose rows are created by this portal rather than imported. **Empty,
    #: and that is the finding.** It started with ``accounts.user`` exempted for
    #: the two demo identities -- and then the demo identities got generated
    #: ``demo:``-prefixed natural keys, because a NULL-keyed row cannot round-trip
    #: and our own escape hatch was silently dropping the demo logins. An
    #: exemption list is only worth having if shrinking it is easy; this one went
    #: to zero.
    EXEMPT: dict[str, str] = {}

    def test_no_loaded_table_is_missing_its_natural_key(self, loaded):
        offenders = {}
        for model in ordered_models():
            label = model._meta.label_lower
            if label in self.EXEMPT:
                continue
            nulls = model.objects.filter(source_key__isnull=True).count()
            if nulls:
                offenders[label] = f"{nulls}/{model.objects.count()}"
        assert offenders == {}, (
            f"these tables have rows with no natural key, so the bulk importer "
            f"quarantines them: {offenders}"
        )

    def test_the_exemption_list_stays_empty(self, loaded):
        """**The exemption is asserted to be empty, and the assertion says why.**

        An exemption is a licence to lose a table. When the demo users were
        exempted, the round trip quietly dropped two logins on every restore and
        this test would have passed. So the list is checked against being empty,
        and adding an entry now fails a test that names the cost.
        """
        assert self.EXEMPT == {}, (
            f"a table is exempted from the natural-key requirement: {self.EXEMPT}. "
            "Rows without a natural key are quarantined by the importer, so this "
            "means those rows do not survive an export/import round trip"
        )

    def test_the_demo_identities_carry_a_generated_key_that_cannot_collide(self, loaded):
        """They are portal-created, so no external system issued an identity --
        but the `demo:` prefix means a key we invented can never collide with one
        an organizer's system issued, which is the failure that would matter.
        """
        from reviewer.accounts.models import User

        demo_keys = list(
            User.objects.filter(source_key__startswith="demo:").values_list("source_key", flat=True)
        )
        assert demo_keys, "the demo identities should carry generated natural keys"
        assert len(demo_keys) == len(set(demo_keys))

    def test_the_natural_keys_are_unique(self, loaded):
        """``source_key`` is unique in the schema, so a duplicate is a database
        error rather than a silent merge. Asserted because a natural key that is
        only *mostly* unique is a key that merges two organizers' rows."""
        for model in ordered_models():
            keys = list(
                model.objects.exclude(source_key__isnull=True).values_list("source_key", flat=True)
            )
            assert len(keys) == len(set(keys)), f"{model._meta.label_lower} has duplicate keys"

    """The one place the escape hatch and a security property genuinely conflict."""

    def test_the_chain_verifies_after_a_full_wipe_and_restore(self, archive, loaded):
        """**`clear_all` deletes audit rows the queryset refuses to delete.** The
        justification for doing that is not a comment -- it is that the restored
        chain still verifies, so the operation demonstrably did not rewrite
        history. If this fails, the bypass is not justified and ``clear_all``
        should not exist.
        """
        assert bundle.verify_restored_chain(loaded) == [], "the fixture chain is already broken"

        _wipe()
        import_archive(archive)

        assert bundle.verify_restored_chain(loaded) == [], (
            "the audit chain did not verify after a wipe and restore; the escape "
            "hatch erodes the guarantee the chain exists to provide"
        )

    def test_the_chain_head_survives_the_round_trip(self, archive, loaded):
        """The head hash is what `results_hash` will be built from, so it has to
        come back identical rather than merely verify."""
        from reviewer.audit.chain import verify_chain

        before = verify_chain(loaded)
        head_before = _chain_head(loaded)
        _wipe()
        import_archive(archive)
        assert _chain_head(loaded) == head_before
        assert len(verify_chain(loaded)) == len(before)


class TestTheWidestAccessorStaysInOneModule:
    """``for_bulk_transfer`` is the widest read in the codebase, so it gets a test.

    **Sanctioning an accessor is not the same as trusting it.** ``for_actor`` and
    ``for_cross_judge_analysis`` are safe because every caller is visible in a
    diff. This one is unfiltered and has no actor, so the property that keeps it
    safe is a *negative* -- that only the escape hatch calls it -- and a negative
    property cannot be reviewed by reading the call site. It has to be asserted.
    """

    def test_only_the_escape_hatch_calls_it(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "src"
        callers = [
            str(path.relative_to(root))
            for path in root.rglob("*.py")
            if "for_bulk_transfer" in path.read_text(encoding="utf-8")
            and path.name != "queryset.py"  # its own definition
        ]
        assert callers == [str(pathlib.Path("reviewer/io/bundle.py"))], (
            f"the widest unscoped Review read in the codebase is called from "
            f"{callers}. Every one of those is a place a future edit could turn "
            "into a page that renders every review."
        )

    def test_it_is_sanctioned_as_a_method_and_not_by_allowlisting_a_file(self):
        """The distinction is the whole point of the design, so it is pinned."""
        source = (Path(__file__).resolve().parents[1] / "tools" / "check_isolation.py").read_text(
            encoding="utf-8"
        )
        assert '"for_bulk_transfer"' in source, "the accessor must be named in the rule"
        assert "normalization/loader.py" not in source, (
            "the rule must not exempt a file by path; an allowlist entry exempts a "
            "whole module's future edits, a sanctioned method exempts one call"
        )

    def test_it_returns_everything_which_is_why_the_name_says_so(self, loaded):
        from reviewer.reviews.models import Review

        # The count is a literal rather than a comparison against
        # `Review.objects.count()`, because that second call is precisely the
        # unscoped read this rule exists to forbid -- JJ01 caught it here, the
        # same way it caught the loader in FEAT-08.
        assert Review.objects.for_bulk_transfer().count() == 126


def _chain_head(event):
    from reviewer.audit.models import AuditEntry

    last = AuditEntry.objects.order_by("seq").last()
    return last.entry_hash if last is not None else None


def _repair_digest(destination: Path, name: str, payload: bytes) -> None:
    """Re-sign a hand-edited file so the test reaches the rule it means to test.

    Editing an archive breaks its manifest, which is rule 3 working correctly.
    A test about quarantining has to get past the digest check to observe
    quarantining, so it re-signs -- and re-signing is deliberately a separate,
    named helper so it is obvious that this test bypasses the integrity check on
    purpose.
    """
    import hashlib

    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][name] = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "rows": len(payload.decode("utf-8").strip().splitlines()),
    }
    # The archive hash too. Leaving it stale produced a one-character diff at
    # byte 17 of the manifest, which reads exactly like a hashing bug and was
    # this helper reimplementing half of `recompute_archive_hash`.
    manifest["archive_hash"] = bundle.recompute_archive_hash(manifest["files"])
    (destination / "manifest.json").write_bytes((canonical(manifest) + "\n").encode("utf-8"))


class TestThePassthroughIsReal:
    """The column the portal has never heard of must come back."""

    def test_an_unknown_column_survives_the_round_trip(self, archive, tmp_path, loaded):
        """**Rule 3, and the single highest-value importer behaviour here.**

        An organizer's custom field goes in, is unknown, and comes back in the
        same column of the same rows. Not dropped, not rejected, and -- the part
        that is easy to get wrong -- **not preserved in a side table while the
        next export quietly drops it again.**
        """
        _add_unknown_column(archive, "reviews.review", "legacy_flag", True)

        _wipe()
        report = import_archive(archive)
        run = bundle.snapshot_run(
            loaded, bundle.KIND_IMPORT, report, bundle.read_manifest(archive), dry_run=False
        )
        written = bundle.write_passthrough(run, report)
        assert written == 126, "every affected row's value should be kept, not just its name"

        second = tmp_path / "passthrough"
        export_archive(second, passthrough=bundle.passthrough_for(run), exclude=BOOKKEEPING)

        assert archive_bytes(second) == archive_bytes(archive), (
            "an unknown column did not survive the round trip; the organizer would "
            "get one clean export and lossy ones forever after"
        )

    def test_the_column_is_reported_rather_than_hidden(self, archive, tmp_path, loaded):
        """The organizer is told which columns we did not understand.

        **The first version of this test asserted the *absence* of a report on a
        clean archive**, which passes whether or not the passthrough works -- a
        tautology dressed as a check. It now adds the unknown column first, so a
        reporter that silently swallowed it fails.
        """
        _add_unknown_column(archive, "reviews.review", "legacy_flag", True)
        report = import_archive(archive, dry_run=True)
        entries = [e for e in report["passthrough_columns"] if e["table"] == "reviews.review"]
        assert entries, "the importer read an unknown column and did not report it"
        assert all("legacy_flag" in e["columns"] for e in entries)
        assert len(entries) == 126, "one report per affected row, not per file"

    def test_a_clean_archive_reports_no_passthrough_at_all(self, archive, loaded):
        """The other half: bookkeeping columns are never mistaken for unknown
        ones. If ``source_key`` counted as unknown, every row would invent a
        passthrough entry and the table would fill with our own columns."""
        report = import_archive(archive, dry_run=True)
        assert report["passthrough_columns"] == []

    def test_a_passthrough_row_is_keyed_by_natural_key_not_primary_key(self, archive, loaded):
        """A primary key is a fact about *this* database, and surviving the
        database being replaced is the entire point.

        **It creates its own snapshot rather than skipping when none exists.** The
        first version skipped, which is the one thing a test in this file must not
        do: a skip is a hole exactly the shape of the defects this suite hunts,
        because the assertion simply never runs and the count still looks fine.
        """
        from reviewer.io.models import PassthroughColumn, PassthroughRow

        report = bundle.import_archive(archive, dry_run=True)
        run = bundle.snapshot_run(
            loaded, bundle.KIND_IMPORT, report, bundle.read_manifest(archive), dry_run=True
        )
        column = PassthroughColumn(run=run, table="t", column="c", value_type="bool")
        column.save()
        PassthroughRow.objects.create(column=column, row_key="evt_01:review:1", value=True)

        stored = PassthroughRow.objects.get(column=column)
        assert stored.row_key == "evt_01:review:1"
        assert stored.column.run_id == run.pk
        assert not str(stored.row_key).isdigit(), (
            "a row_key that looks like a primary key will not survive the database "
            "being replaced, which is the whole reason this column exists"
        )


def _add_unknown_column(destination: Path, stem: str, column: str, value) -> None:
    name = f"{stem}.jsonl"
    path = destination / name
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        row = json.loads(line)
        row[column] = value
        out.append(canonical(row))
    payload = "".join(line + "\n" for line in out).encode("utf-8")
    path.write_bytes(payload)
    _repair_digest(destination, name, payload)


def _latest_import(event):
    from reviewer.io.models import RunSnapshot

    return RunSnapshot.objects.filter(event=event, kind=bundle.KIND_IMPORT).first()


class TestTheTrapsInTheSerialisation:
    def test_a_decimal_survives_exactly_rather_than_through_a_float(self):
        """``0.1`` is not recoverable from a float, and a bulk importer that
        rounds a number is a bulk importer nobody trusts with money."""
        import decimal

        original = decimal.Decimal("1.0050000000000000000000001")
        assert decode(encode(original)) == original
        assert json.loads(canonical(encode(original)))["__decimal__"] == str(original)

    def test_the_encode_decode_pair_is_the_inverse_of_itself(self):
        import datetime as dt
        import decimal
        import uuid

        for value in [
            None,
            "",
            "text",
            0,
            -17,
            True,
            1.5,
            decimal.Decimal("-0.0000001"),
            dt.datetime(2026, 9, 29, 12, 30, tzinfo=dt.UTC),
            dt.datetime(2026, 9, 29, 12, 30),
            dt.date(2026, 9, 29),
            dt.time(23, 59, 59),
            uuid.UUID("12345678-1234-5678-1234-567812345678"),
            b"\x00\x01\x02",
            [1, "a", None],
            {"nested": {"deep": [1, 2]}},
        ]:
            assert decode(encode(value)) == value, f"{value!r} did not survive"

    def test_a_naive_datetime_stays_naive(self):
        """Coercing it to UTC would invent a timezone the database never had, and
        the round trip would still 'pass' while shifting every timestamp."""
        import datetime as dt

        naive = dt.datetime(2026, 9, 29, 12, 30)
        assert decode(encode(naive)) == naive
        assert decode(encode(naive)).tzinfo is None

    def test_timestamps_are_restored_not_replaced_by_now(self, archive, loaded):
        """``created_at``/``updated_at`` are ``auto_now_add``/``auto_now``, so the
        obvious importer writes *now* and the second export differs in two columns
        per row for no reason connected to the data."""
        from reviewer.reviews.models import Review

        original = Review.objects.for_bulk_transfer().filter(source_key__isnull=False).first()
        before = (original.created_at, original.updated_at)
        _wipe()
        import_archive(archive)
        restored = Review.objects.for_bulk_transfer().get(pk=original.pk)
        assert (restored.created_at, restored.updated_at) == before

    def test_foreign_keys_travel_as_natural_keys(self, archive, tmp_path):
        """An archive full of local primary keys imports into a *different*
        database and looks like it worked."""
        lines = (archive / "reviews.review.jsonl").read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        assert "__fk__" in row["judge"], "the judge FK did not travel as a natural key"
        assert "__fk__" in row["project"]


class TestDryRunAndReporting:
    def test_a_dry_run_writes_nothing(self, archive, loaded):
        from reviewer.reviews.models import Review

        before = Review.objects.for_bulk_transfer().count()
        report = import_archive(archive, dry_run=True)
        assert report["dry_run"] is True
        assert Review.objects.for_bulk_transfer().count() == before
        assert report["created"], "a dry run should report what it would do"

    def test_the_report_survives_as_a_row_and_not_only_on_stdout(self, archive, tmp_path, loaded):
        """A dry run whose output only existed in a terminal scrollback is not a
        thing anyone can go back and read."""
        from reviewer.io.models import RunSnapshot

        report = import_archive(archive, dry_run=True)
        run = bundle.snapshot_run(
            loaded, bundle.KIND_IMPORT, report, bundle.read_manifest(archive), dry_run=True
        )
        assert RunSnapshot.objects.filter(pk=run.pk).exists()
        assert run.report["dry_run"] is True
        assert run.archive_hash
