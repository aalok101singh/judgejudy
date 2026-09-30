"""Ed25519 signed judge records: signing, verification, and tamper rejection.

**This file closes F-97**, in which ``JudgeCredential`` and ``SignedRecord``
shipped at FEAT-02 with complete schemas and no writer anywhere in ``src/``.

The tests are arranged around the two directions that fail separately:

* **a judge can prove they did not change their work after signing**, and
* **an organizer cannot produce a record they did not sign**.

And around the two spec details that are *silently* wrong-able: DSSE's
length-prefixed PAE, and in-toto's ``subject`` shape. **Both are checked against
the spec rather than against this implementation**, because an implementation
that is consistently wrong agrees with itself forever.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from reviewer.credentials import in_toto, keys, signing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_keys(tmp_path, settings):
    """Every test gets its own key directory, outside the repo.

    **This is the arrangement the real deployment uses**, and it is why
    ``settings.KEYS_DIR`` is read at call time rather than captured at import:
    a module-level constant would make this fixture impossible and the tests would
    have to write real keys into the working tree.
    """
    directory = tmp_path / "keys"
    directory.mkdir(parents=True, exist_ok=True)
    settings.KEYS_DIR = directory
    return directory


@pytest.fixture
def raw_fixture():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture):
    from reviewer.events.models import Event
    from reviewer.importer import loader as loader_module

    loader_module.load(raw_fixture)
    return Event.objects.get(pk="evt_01")


@pytest.fixture
def judge(loaded):
    from reviewer.accounts.models import RoleBinding

    binding = (
        RoleBinding.objects.filter(event=loaded, role="judge")
        .select_related("user")
        .order_by("id")
        .first()
    )
    assert binding is not None, "the fixture ships judge bindings"
    return binding.user


# ------------------------------------------------------------------ the formats


class TestThePAEIsTheSpecBytes:
    """DSSE's pre-authentication encoding, which is one byte from being useless."""

    def test_it_matches_the_specification_worked_example(self):
        """``DSSEv1 26 0x<json> 19 <body>`` taken from the DSSE specification.

        **Hard-coded rather than computed, and that is the entire point.** A PAE
        built by the same code that verifies it agrees with itself perfectly. The
        only thing that catches a wrong PAE is a byte string the standard says is
        right, so the assertion is a literal from the spec.
        """
        payload_type = "http://example.com/HelloWorld"
        payload = b'{"hello":"world"}'
        expected = b"DSSEv1 29 http://example.com/HelloWorld 17 " + payload
        assert in_toto.pae(payload_type, payload) == expected, (
            "the PAE does not match the specification's worked example, so every "
            "signature we produce would verify against our own PAE and nothing else"
        )

    def test_the_lengths_are_byte_counts_not_character_counts(self):
        """The payload is UTF-8 JSON and the type is ASCII, so a character-count
        implementation gets the type right by luck and the payload wrong only
        when it contains a non-ASCII byte."""
        payload = "café".encode()
        assert len(payload) == 5, "4 characters, 5 bytes -- the difference the test needs"
        encoded = in_toto.pae("t", payload)
        assert b" 5 " in encoded
        assert b" 4 " not in encoded

    def test_the_prefix_is_exactly_dssev1_and_a_space(self):
        encoded = in_toto.pae("t", b"p")
        assert encoded.startswith(b"DSSEv1 ")
        assert encoded.count(b" ") == 4, (
            "DSSEv1, len(type), type, len(payload), payload -- four separators"
        )

    def test_the_lengths_are_bare_decimal_not_quoted(self):
        encoded = in_toto.pae("application/json", b"{}")
        assert b"DSSEv1 16 application/json 2 {}" == encoded


class TestTheStatementIsInTotoV1:
    def test_the_shape_is_what_the_spec_says(self, loaded, judge):
        record = signing.sign(loaded, judge)
        statement = record.statement

        assert statement["_type"] == "https://in-toto.io/Statement/v1"
        assert isinstance(statement["subject"], list), "subject is a LIST in in-toto v1"
        for entry in statement["subject"]:
            assert set(entry) == {"name", "digest"}
            assert set(entry["digest"]) == {"sha256"}
            assert len(entry["digest"]["sha256"]) == 64, "hex, not base64"
        assert statement["predicateType"].startswith("https://")

    def test_the_payload_type_is_the_in_toto_one(self, loaded, judge):
        record = signing.sign(loaded, judge)
        assert in_toto.envelope_payload_bytes(record.envelope)[0] == (
            "application/vnd.in-toto+json"
        )

    def test_it_commits_to_no_score_values(self, loaded, judge):
        """**The privacy restriction is the mechanism, not a courtesy.**

        D-09 replicates the results hash into every signed record so N judges who
        are not the organizer each hold a copy -- and an organizer equivocating
        becomes a five-line diff between two judges. A record carrying scores would
        not be shareable with a judge who was not the organizer, so it would
        replicate nothing.
        """
        record = signing.sign(loaded, judge)
        payload = json.dumps(record.statement)
        assert '"value"' not in payload, (
            "the statement carries per-criterion values; that is a score and the "
            "record would stop being shareable with other judges"
        )


# --------------------------------------------------------------- key management


class TestKeysLiveOnTheirOwnVolume:
    def test_a_key_is_written_inside_the_key_directory(self, judge):
        path = keys.generate(judge.source_key)
        assert path.parent == keys.keys_dir().resolve()
        assert path.read_bytes() != b""

    def test_generation_refuses_to_overwrite(self, judge):
        """Silently re-keying would orphan every record the old key signed, and
        those records would still LOOK valid -- each carries its own public key."""
        path = keys.generate(judge.source_key)
        original = path.read_bytes()
        keys.generate(judge.source_key)
        assert path.read_bytes() == original, "the key was replaced without being asked"

    def test_a_key_outside_the_key_directory_is_refused(self, tmp_path, judge):
        """The rule that keeps a private key out of the image and out of git."""
        outside = tmp_path / "leaked.ed25519"
        outside.write_bytes(b"x" * 32)
        with pytest.raises(keys.KeyMaterialError):
            keys._assert_inside_keys_dir(outside)

    def test_a_symlink_out_of_the_key_directory_is_refused(self, tmp_path, judge):
        """The path is resolved *before* the comparison, which is the only reason
        this check is worth having -- a symlink is otherwise a way around it."""
        outside = tmp_path / "leaked.ed25519"
        outside.write_bytes(b"x" * 32)
        link = keys.keys_dir() / "sneaky.ed25519"
        try:
            link.symlink_to(outside)
        except OSError:  # pragma: no cover - Windows without developer mode
            pytest.skip("symlinks unavailable on this platform")
        with pytest.raises(keys.KeyMaterialError):
            keys._assert_inside_keys_dir(link)

    def test_a_missing_key_says_what_to_do(self, judge):
        with pytest.raises(keys.KeyMaterialError) as excinfo:
            keys.load_private("nobody@example.org")
        assert "issue_keys" in str(excinfo.value) or "sign_records" in str(excinfo.value)

    def test_a_truncated_seed_says_what_it_is(self, judge):
        path = keys.generate(judge.source_key)
        path.write_bytes(b"short")
        with pytest.raises(keys.KeyMaterialError) as excinfo:
            keys.load_private(judge.source_key)
        assert "32" in str(excinfo.value)


class TestF97IsClosed:
    def test_the_loader_still_creates_nothing_and_the_signer_creates_everything(self, loaded):
        """**The finding, restated as an executable assertion.**

        Before this increment: zero credentials, zero signed records, and no code
        that could make either. Now: signing creates them. The count is derived
        from the fixture's own judges rather than typed.
        """
        from reviewer.accounts.models import RoleBinding
        from reviewer.credentials.models import JudgeCredential, SignedRecord

        assert JudgeCredential.objects.count() == 0, "the loader creates no credentials"
        assert SignedRecord.objects.count() == 0, "the loader creates no signed records"

        records = signing.sign_all(loaded)
        judges = (
            RoleBinding.objects.filter(event=loaded, role="judge")
            .values("user_id")
            .distinct()
            .count()
        )
        assert JudgeCredential.objects.count() == judges
        assert len(records) == judges
        assert SignedRecord.objects.count() == judges


# ------------------------------------------------------------ sign and verify


class TestSignAndVerify:
    def test_a_freshly_signed_record_verifies(self, loaded, judge):
        record = signing.sign(loaded, judge)
        ok, why = signing.verify_record(record)
        assert ok, why
        assert "unchanged" in why

    def test_verification_needs_no_trust_in_our_code(self, loaded, judge):
        """**The signature is checked with the public key from the credential, by
        recomputing the PAE** -- not by comparing a stored hash to a stored hash,
        which would only prove two things the signer produced agree with each
        other."""
        record = signing.sign(loaded, judge)
        public = bytes.fromhex(record.credential.public_key)
        assert in_toto.verify_envelope(record.envelope, public)

    def test_editing_a_review_breaks_the_digest_but_not_the_signature(self, loaded, judge):
        """**The interesting case, and the one the record exists for.**

        The signature is still valid -- the statement was not altered. What changed
        is the *work*, so the recomputed digest no longer matches. A verifier that
        only checked signatures would call this fine.
        """
        from reviewer.reviews.models import Review

        record = signing.sign(loaded, judge)
        review = (
            Review.objects.for_bulk_transfer()
            .filter(event=loaded, judge=judge)
            .order_by("source_key")
            .first()
        )
        score = review.scores.filter(value__isnull=False).order_by("criterion__key").first()
        original = score.value
        score.value = 5 if original != 5 else 4
        score.save(update_fields=["value"])

        ok, why = signing.verify_record(record)
        assert not ok
        assert "changed after signing" in why, why

    def test_a_tampered_payload_fails_verification(self, loaded, judge):
        """The classic attack: rewrite the statement, keep the signature."""
        record = signing.sign(loaded, judge)
        statement = json.loads(in_toto.unb64(record.envelope["payloads"][0]))
        statement["predicate"]["reviews_signed"] = 9999
        record.envelope = {
            **record.envelope,
            "payloads": [in_toto.b64(in_toto.statement_bytes(statement))],
        }
        record.save()
        ok, why = signing.verify_record(record)
        assert not ok
        assert "signature does not verify" in why

    def test_a_signature_from_another_judge_fails(self, loaded):
        """An organizer's real capability: forge a record signed by the wrong key."""
        from reviewer.accounts.models import RoleBinding

        first, second = list(
            RoleBinding.objects.filter(event=loaded, role="judge")
            .select_related("user")
            .order_by("id")[:2]
        )
        record = signing.sign(loaded, first.user)
        signing.issue_credential(loaded, second.user)
        impostor_public = keys.public_key_bytes(second.user.source_key)
        assert not in_toto.verify_envelope(record.envelope, impostor_public)

    def test_signing_is_idempotent_and_will_not_rekey(self, loaded, judge):
        record = signing.sign(loaded, judge)
        again = signing.sign(loaded, judge)
        assert record.pk == again.pk, "signing twice created a second record"

    def test_a_judge_with_no_submitted_work_gets_no_record(self, loaded):
        """An empty-subject statement is valid in-toto and proves nothing: it says
        the judge signed, about no work. Worse than no record, because it looks
        like coverage."""
        from reviewer.credentials.models import SignedRecord
        from reviewer.reviews.models import REVIEW_SUBMITTED, Review

        submitting = set(
            Review.objects.for_bulk_transfer()
            .filter(event=loaded, status=REVIEW_SUBMITTED)
            .values_list("judge_id", flat=True)
        )
        outsider = _a_user_with_no_reviews(loaded, submitting)
        assert outsider is not None, "the fixture has no judge who submitted nothing"

        assert signing.sign(loaded, outsider) is None
        assert not SignedRecord.objects.filter(judge=outsider).exists()

    def test_an_envelope_with_two_payloads_is_refused(self, loaded, judge):
        """**The one-payload guard had no test, and the mutation harness proved it
        by reporting the mutation that removes it NOT DETECTED.**

        DSSE permits several payloads, so a verifier that quietly takes the first
        one is validating *a* payload rather than *the* payload -- and "which one
        did the signer mean" is exactly the ambiguity the PAE exists to remove.

        The guard is in ``envelope_payload_bytes`` and its own docstring says the
        refusal is explicit, so the docstring and the test coverage were both
        written and only one of them was real. **A docstring asserting a behaviour
        is not a test of it**, which is the same lesson as F-98's field list.
        """
        record = signing.sign(loaded, judge)
        doubled = {
            **record.envelope,
            "payloads": [record.envelope["payloads"][0], record.envelope["payloads"][0]],
        }
        with pytest.raises(ValueError) as excinfo:
            in_toto.envelope_payload_bytes(doubled)
        assert "exactly one payload" in str(excinfo.value)

        assert (
            in_toto.verify_envelope(doubled, bytes.fromhex(record.credential.public_key)) is False
        )

    def test_an_envelope_with_no_payloads_is_refused(self, loaded, judge):
        record = signing.sign(loaded, judge)
        empty = {**record.envelope, "payloads": []}
        with pytest.raises(ValueError):
            in_toto.envelope_payload_bytes(empty)
        assert in_toto.verify_envelope(empty, bytes.fromhex(record.credential.public_key)) is False

    def test_the_statement_is_byte_identical_across_runs(self, loaded, judge):
        """A statement whose subject order came from a database would sign
        differently every time, and a signature that changes when nothing did
        teaches every verifier to ignore signature failures."""
        import datetime as dt

        moment = dt.datetime.now(dt.UTC)
        first = signing.sign(loaded, judge, issued_at=moment)
        second = signing.sign(loaded, judge, issued_at=moment, overwrite=True)
        assert in_toto.statement_bytes(first.statement) == in_toto.statement_bytes(second.statement)


def _a_user_with_no_reviews(event, submitting_ids):
    """A real user bound to the event who submitted nothing, or ``None``.

    **Promoted to a role first if necessary**, so the test does not depend on the
    fixture containing an idle judge -- the branch under test is "no submitted
    work", and how such a user arises is not what it is checking.
    """
    from reviewer.accounts.models import RoleBinding

    binding = (
        RoleBinding.objects.filter(event=event)
        .exclude(user_id__in=submitting_ids)
        .select_related("user")
        .first()
    )
    if binding is not None:
        return binding.user
    for binding in RoleBinding.objects.filter(event=event).select_related("user"):
        RoleBinding.objects.get_or_create(
            event=event, user=binding.user, role="judge", defaults={"track": None}
        )
        return binding.user
    return None


class TestTheCommands:
    def test_sign_records_writes_and_verifies(self, loaded, capsys):
        from django.core.management import call_command

        call_command("sign_records")
        out = capsys.readouterr().out
        assert "SIGNED" in out
        assert "VERIFY:" in out
        assert "0 signed record(s) did not verify" not in out

    def test_verify_only_does_not_sign(self, loaded, capsys):
        from django.core.management import call_command

        from reviewer.credentials.models import SignedRecord

        call_command("sign_records", "--verify-only")
        assert SignedRecord.objects.count() == 0
        assert "VERIFY: 0 of 0" in capsys.readouterr().out

    def test_base64_is_standard_alphabet_with_padding(self, loaded, judge):
        """DSSE requires standard base64. URL-safe is the other alphabet, and a
        verifier handed the wrong one fails with a mismatch that reads like
        tampering."""
        record = signing.sign(loaded, judge)
        payload = record.envelope["payloads"][0]
        assert base64.b64encode(base64.b64decode(payload)).decode() == payload
