"""Signing a judge's participation record, and verifying one without any trust in us.

**This module is what closes F-97.** ``JudgeCredential`` and ``SignedRecord``
shipped at FEAT-02 with complete schemas and no writer anywhere in ``src/``; after
a full load the database held zero of each. D-09's replication was correct, tested,
and running against nothing.

The claim being made here, and it is narrower than "we sign things":

> **A judge can prove they did not change their work after signing, and an
> organizer cannot produce a record they did not sign.**

Both directions matter and they fail differently. A record nobody can verify is
decoration. A record only the organizer's own code can verify is a claim.

What is committed to, and what is deliberately not
--------------------------------------------------
The subject of the statement is **the judge's reviews, by natural key, committed
by digest**. Not their scores. :func:`review_digests_for` hashes a review's
rubric, status, comment and per-criterion values into one digest, so the record
proves *"these reviews exist and are these reviews"* without naming a single score.

**That restriction is what makes replication possible.** D-09 puts the chain head
and the results hash into every signed record so N judges who are not the
organizer each hold a copy. An organizer can then be caught equivocating by
comparing two judges' copies. **A record that leaked the scores would not be
shareable with a judge who was not the organizer**, and an unshareable record
replicates nothing -- so the privacy property is not a courtesy, it is the
mechanism.

The review digest is re-derivable
---------------------------------
:meth:`JudgeCredential.digest_of_review` takes the review object, so a verifier
holding the export can recompute every digest and check them against the statement.
**That is the same property the publication hash rests on**, and for the same
reason: a signature over bytes only a stranger cannot reproduce is a claim, not a
proof.

What a signature is NOT used for here
-------------------------------------
**There is no Merkle tree and no transparency log**, and ``requirements.txt``
records why: we run the container, so a root we compute proves internal
consistency, which the audit chain already proves, for three times the code. What
the signature buys is the one thing that needs no witness: **a second party's
verdict**, which they compute themselves.
"""

from __future__ import annotations

import datetime as dt

from reviewer.credentials import in_toto, keys
from reviewer.io.bundle import canonical


def review_digest(review) -> str:
    """One review committed to by digest. Re-derivable from the export alone.

    **Ordered by criterion key and containing nothing the reviewer did not write.**
    The per-criterion values and the weight applied to each are included, because
    "I submitted these reviews" is a much weaker claim than "these are the exact
    numbers I submitted", and the second is the one a judge would want to make.
    The ordering is by criterion key rather than by position so a rubric reordering
    does not invalidate a signature -- a reordering is not a change of content.
    """
    scores = [
        {
            "criterion": score.criterion.key,
            "value": score.value,
            "weight_applied": str(score.weight_applied),
        }
        for score in review.scores.select_related("criterion").order_by("criterion__key")
    ]
    payload = canonical(
        {
            "review": review.source_key,
            "project": review.project.source_key,
            "rubric_version": review.rubric_version.source_key,
            "status": review.status,
            "overall_comment": review.overall_comment or "",
            "scores": scores,
        }
    )
    return in_toto.sha256_hex(payload.encode("utf-8"))


def review_digests_for(event, judge) -> list[tuple[str, str]]:
    """``[(review_source_key, digest)]`` for one judge's submitted work, in key order.

    Ordered by natural key so the statement is byte-identical across runs. **A
    statement whose subject order came from a database would sign differently every
    time**, and a signature that changes when nothing did teaches every verifier to
    ignore signature failures -- which is the same failure mode as an
    always-valid signature.
    """
    from reviewer.reviews.models import REVIEW_SUBMITTED, Review

    reviews = (
        Review.objects.for_judge_signing(event.pk, judge)
        .filter(status=REVIEW_SUBMITTED)
        .select_related("project", "rubric_version")
        .order_by("source_key")
    )
    return [(review.source_key, review_digest(review)) for review in reviews]


def audit_range_for(event, judge) -> tuple[int, int]:
    """The audit chain sequence range this judge's work occupies.

    ``(0, 0)`` when the judge has no audit entries, which is honest rather than
    convenient: a range that starts and ends at the same entry would imply a
    one-link chain that does not exist.
    """
    from reviewer.audit.models import AuditEntry

    entries = AuditEntry.objects.filter(event=event, actor=judge).order_by("seq")
    if not entries.exists():
        return 0, 0
    return entries.first().seq, entries.last().seq


def issue_credential(event, judge):
    """Ensure the judge has a key and a ``JudgeCredential``, and return it.

    **A new key is never generated for a judge who already has one** --
    ``keys.generate`` refuses to overwrite, and this is the second guard: silently
    re-keying would orphan every record the old key signed, and those records would
    still *look* valid, because each carries its own public key and nothing in the
    schema notices that a different key now answers to the same judge.
    """
    from reviewer.credentials.models import JudgeCredential

    existing = JudgeCredential.objects.filter(event=event, judge=judge).first()
    if existing is not None:
        return existing

    keys.generate(judge.source_key or judge.email)
    public = keys.public_key_bytes(judge.source_key or judge.email)
    return JudgeCredential.objects.create(
        event=event,
        judge=judge,
        public_key=public.hex(),
        signature="",
        record_hash="",
    )


def sign(event, judge, *, issued_at=None, overwrite=False):
    """Sign one judge's participation and store the ``SignedRecord``.

    **The credential is issued as part of signing**, because a record whose
    credential does not exist is a record no third party can check -- the verifier
    needs the public key, and the public key lives on the credential.
    """
    from reviewer.credentials.models import SignedRecord

    existing = SignedRecord.objects.filter(event=event, judge=judge).first()
    if existing is not None and not overwrite:
        return existing

    credential = issue_credential(event, judge)
    judge_key = judge.source_key or judge.email
    private = keys.load_private(judge_key)

    digests = review_digests_for(event, judge)
    if not digests:
        return None

    seq_from, seq_to = audit_range_for(event, judge)
    statement = in_toto.build_statement(
        event_key=event.pk,
        judge_key=judge_key,
        rubric_source_key=event.rubrics.order_by("-version").first().source_key,
        review_digests=digests,
        audit_seq_from=seq_from,
        audit_seq_to=seq_to,
        issued_at=issued_at or dt.datetime.now(dt.UTC),
    )
    payload = in_toto.statement_bytes(statement)
    signature = private.sign(in_toto.pae(in_toto.DSSE_PAYLOAD_TYPE, payload))
    envelope = in_toto.build_envelope(statement, signature)
    record_hash = in_toto.sha256_hex(payload)

    if existing is not None:
        existing.statement = statement
        existing.envelope = envelope
        existing.record_hash = record_hash
        existing.credential = credential
        existing.save()
        return existing

    return SignedRecord.objects.create(
        event=event,
        judge=judge,
        credential=credential,
        statement=statement,
        envelope=envelope,
        record_hash=record_hash,
    )


def sign_all(event, *, issued_at=None, overwrite=False) -> list:
    """Sign every judge with submitted work. Returns the records written.

    **Iterates distinct USERS, not role bindings.** The shipped fixture has **39
    judge bindings and 30 judges** -- a judge holds one binding per track they
    cover -- so iterating bindings signs the same person three or four times. That
    is harmless for correctness (``sign`` is idempotent and returns the existing
    record) and wrong for everything a human reads: the command would report "39
    judges signed" over 30 signatures, and the count is the only number the
    operator gets.

    **A judge with nothing submitted is skipped and returns nothing**, rather than
    signing a record with an empty subject list. An empty-subject statement is
    valid in-toto and proves nothing: it says the judge signed, about no work,
    which is worse than no record because it looks like coverage.
    """
    from reviewer.accounts.models import RoleBinding, User

    judge_ids = sorted(
        set(RoleBinding.objects.filter(event=event, role="judge").values_list("user_id", flat=True))
    )
    records = []
    for judge_id in judge_ids:
        record = sign(
            event, User.objects.get(pk=judge_id), issued_at=issued_at, overwrite=overwrite
        )
        if record is not None:
            records.append(record)
    return records


def verify_record(record) -> tuple[bool, str]:
    """``(ok, why)`` for one stored record, using only the credential's public key.

    **Three checks, and the order matters.** The envelope is checked first (did
    this key sign these bytes?), then the statement's shape, then whether the
    digests still match the reviews in the database. **A record whose signature
    verifies but whose digests no longer match is the interesting case** -- it means
    the work changed after signing, which is exactly what the record exists to
    make detectable -- so it is reported distinctly rather than as a plain failure.
    """
    try:
        public = bytes.fromhex(record.credential.public_key)
    except ValueError:
        return False, f"the credential's public key is not hex: {record.credential.public_key!r}"

    if not in_toto.verify_envelope(record.envelope, public):
        return False, "the signature does not verify against the credential's public key"

    try:
        statement = in_toto.envelope_statement(record.envelope)
    except (ValueError, KeyError) as exc:
        return False, f"the envelope does not contain a readable statement: {exc}"

    if statement.get("_type") != in_toto.STATEMENT_TYPE:
        return False, f"statement _type is {statement.get('_type')!r}, not in-toto v1"

    claimed = statement.get("predicate", {}).get("review_digests", {})
    if not claimed:
        return False, "the statement commits to no reviews, which proves nothing"

    current = dict(review_digests_for(record.event, record.judge))
    if claimed == current:
        return True, f"signature valid and {len(claimed)} review digests unchanged"
    changed = sorted(set(claimed) ^ set(current)) or [
        k for k in claimed if current.get(k) != claimed[k]
    ]
    return False, f"signature valid but the work changed after signing: {changed[:5]}"


def verify_event(event) -> dict:
    """Verify every signed record for an event, and summarise."""
    from reviewer.credentials.models import SignedRecord

    results = [
        (record, *verify_record(record)) for record in SignedRecord.objects.filter(event=event)
    ]
    return {
        "total": len(results),
        "ok": sum(1 for _r, ok, _w in results if ok),
        "bad": sum(1 for _r, ok, _w in results if not ok),
        "details": [{"record": r.pk, "ok": ok, "why": why} for r, ok, why in results],
    }
