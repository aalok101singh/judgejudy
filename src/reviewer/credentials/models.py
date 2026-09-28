"""Judge credentials and the signed participation record.

**Ed25519** (RFC 8032 §3.1, Edwards-curve DSA over Curve25519) because it is
deterministic, 64-byte signatures, 32-byte keys, no parameter selection and no
nonce management -- and because it is already in the image as a transitive
dependency of `cryptography`, so it adds nothing to the build.

**What the credential is for.** One keypair per judge per event, generated at
first boot. The judge's *participation record* is signed with it, and that record
lets a judge prove they served and lets an organizer prove the panel was
staffed -- **without publishing a single score** (``bible/05`` §9b). The record
carries ``reviews_submitted: 3`` and a digest of what they submitted. Nothing
confidential leaves the portal.

**Keys live on their own Docker volume, not the database volume.** This is a
fifteen-minute decision that prevents a self-inflicted wound at hour 66: our own
verification checklist runs ``docker compose down -v && up`` twice, and keys on
the database volume would wipe every previously issued record -- including ones
quoted in the README and the demo video. The database therefore stores the
*public* key only, which is exactly what a verifier needs.

**Why DSSE and in-toto Statement v1 rather than "a signature over canonical
JSON".** The DSSE spec is explicit that an implementation should avoid
depending on canonicalisation for security and should not require the verifier to
parse the payload before verifying: the signature covers a PAE (Pre-Authentication
Encoding) of the payload *bytes*. So a verifier never has to agree with us about
key ordering, number formatting or Unicode normalisation. That removes an entire
class of interoperability bug for about the same amount of code, and anyone with
`cosign` or an in-toto verifier can check our records with tools that already
exist. Hand-rolling a canonical form would mean every third party who wanted to
verify a record had to reimplement our serialisation, and would get it subtly
wrong -- silently, which is the failure mode that matters.

**The known trap, written down so nobody re-derives it:** ``len()`` in the PAE is
in **bytes**, not characters. The payload is base64 so it happens to be safe, but
``payloadType`` is not base64, and getting it wrong produces a record that
verifies against our own verifier and against nothing else.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

#: The predicate type for a judge's participation record. Versioned in the URL
#: because the envelope is meant to be readable by someone who has never seen
#: this repository.
PREDICATE_TYPE = "https://dogfoodhack.com/attestation/judge-service/v1"

#: The DSSE payload type. Also a URI, also stable, also not ours to change.
PAYLOAD_TYPE = "application/vnd.in-toto+json"


class JudgeCredential(SourceKeyMixin, TimeStampedModel, models.Model):
    """One Ed25519 public key per judge per event. The private half never lands here."""

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="judge_credentials"
    )
    judge = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="judge_credentials"
    )
    #: Base64 Ed25519 public key, 32 bytes. Public by definition.
    public_key = models.CharField(max_length=128)
    issued_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    #: The keypair's self-signature, so a downloaded credential file can be
    #: checked without trusting the portal that served it.
    signature = models.TextField(blank=True)
    record_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "credentials_judgecredential"
        ordering = ["event_id", "judge_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "judge"], name="credentials_cred_event_judge_uniq"
            ),
        ]

    def __str__(self) -> str:
        return f"credential {self.judge_id}@{self.event_id}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class SignedRecord(SourceKeyMixin, TimeStampedModel, models.Model):
    """An in-toto Statement v1 inside a DSSE envelope, signed by one judge.

    **The record exposes no scores and that is still the point.** It carries the
    event, the judge, the rubric version, how many reviews they submitted, a
    digest of those submissions, the audit sequence range their work occupies,
    the audit chain head at publication, and the results hash. Every field is
    either public or a digest.

    **``audit_chain_head`` replicated here is what replaces a Merkle transparency
    log** (``bible/05`` §9c, D-09). Certificate transparency's value is
    *witnessing* -- an independent party holding a copy to detect equivocation --
    and this project has no witness: the organizer runs the container. A Merkle
    root we compute ourselves proves internal consistency, which the 30-line hash
    chain already proves, for three times the code. Putting the head in every
    signed record instead means **N people who are not the organizer each hold a
    copy**, so equivocation becomes detectable by a five-line diff between any
    two record holders. For one column, that is strictly stronger.
    """

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="signed_records"
    )
    judge = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="signed_records"
    )
    credential = models.ForeignKey(
        JudgeCredential, on_delete=models.PROTECT, related_name="signed_records"
    )
    #: The in-toto Statement v1 document, verbatim. Stored whole rather than
    #: shredded into columns, because the document is the artefact a verifier
    #: consumes and a reconstruction is one more thing to get wrong.
    statement = models.JSONField()
    #: The DSSE envelope: {payloadType, payload, signatures}. `payload` is
    #: base64 of the statement's bytes.
    envelope = models.JSONField()
    issued_at = models.DateTimeField(auto_now_add=True)
    #: SHA-256 over the statement bytes. Lets a record be referenced by one
    #: short string in a README or a video.
    record_hash = models.CharField(max_length=64)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "credentials_signedrecord"
        ordering = ["event_id", "judge_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "judge"], name="credentials_record_event_judge_uniq"
            ),
            models.CheckConstraint(
                condition=~models.Q(record_hash=""),
                name="credentials_record_hash_present",
                violation_error_message="A signed record with no hash cannot be referenced.",
            ),
        ]
        indexes = [
            models.Index(fields=["event", "judge"], name="credentials_rec_ev_judge_idx"),
        ]

    def __str__(self) -> str:
        return f"signed record {self.judge_id}@{self.event_id}"
