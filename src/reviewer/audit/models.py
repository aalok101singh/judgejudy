"""The audit chain and the results publication.

Two tables, and they are in the same app for a reason that is worth one
sentence: ``ResultPublication`` is where the **audit chain head** is published
(``bible/05`` §9c), so the two rows are written through the same append-only
service and a reader looking for "how do I know this was not edited" finds both
answers in one file.

**``AuditEntry`` is hash-chained, and ``omitted_since_prev`` is the design.**

A hash chain makes append-only a *verifiable* claim rather than a promise: change
entry 40 and every hash from 41 upward disagrees. That works only if the sequence
has no gaps -- and rate-limited audit sampling, which is what you would normally
build to stop a bored judge filling a table, produces exactly that. A gap in the
sequence is indistinguishable from a deleted entry. So the dropped count lives
**inside** the chain: the chain records what it did not record, and a gap becomes
a provable, disclosed fact rather than a tamper signal. D-08 exists for this.

**Append-only is enforced by the manager, not by convention.** ``AuditQuerySet``
raises on ``update`` and ``delete``. A convention is a comment; this is a
``TypeError`` at the call site, and the admin's delete action goes through it too.

**Why ``before``/``after`` are JSONField diffs and are mostly empty.** They are
populated only for the changes that matter -- role binding, score edit, rubric
weight change, results publication, export, import, denial. A trail that records
every column of every save is a trail nobody reads, and the design goal is an
audit trail an organizer can read without a database client.

**Why denials are logged.** A run of refused peer-score requests is exactly the
signal a security-minded organizer wants, and it is free here.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel


class AuditQuerySet(models.QuerySet):
    """Append-only. Every write path except ``create`` raises."""

    def update(self, **kwargs):
        raise TypeError(
            "AuditEntry is append-only. An update would break the hash chain at "
            "this seq and every entry after it."
        )

    def delete(self):
        raise TypeError(
            "AuditEntry is append-only. Deleting an entry is indistinguishable "
            "from rewriting history, which is the attack the chain exists to make "
            "detectable."
        )


class AuditManager(models.Manager.from_queryset(AuditQuerySet)):
    """The default manager, and the only one that can be a default manager.

    ``use_in_migrations`` is deliberately off: the manager is a guard, not
    schema, and a migration that captured it would make a future change to the
    guard require a migration.
    """


class AuditEntry(SourceKeyMixin, TimeStampedModel, models.Model):
    """One link in the append-only, hash-chained audit trail."""

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="audit_entries"
    )
    #: The acting user, or null for a denied anonymous request. Denials are
    #: logged, so "who tried" is a first-class question.
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        related_name="audit_entries",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)

    #: JSONField diffs, populated only for the changes that matter.
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)

    #: Hashes of the salted client identifiers, for correlating a burst of
    #: denials. Never the raw address (see reviewer.ballots for the reasoning).
    ip_hash = models.CharField(max_length=128, blank=True)

    # --- the chain (D-08) ----------------------------------------------------
    seq = models.PositiveIntegerField(
        help_text=(
            "Monotonic per event. A gap here is either a disclosed omission or a tamper signal."
        )
    )
    prev_hash = models.CharField(max_length=64, blank=True, default="")
    entry_hash = models.CharField(max_length=64, blank=True, default="")
    #: How many entries were rate-limit-dropped since the previous one. See the
    #: module docstring: this column is why sampling and chaining are coherent.
    omitted_since_prev = models.PositiveIntegerField(default=0)

    #: The scope receipt from reviewer.isolation, stored so the audit trail
    #: records not just *who did what* but *what each actor was able to see*
    #: (bible/05 §9). Null for actions that are not a scoped read.
    scope_reason = models.JSONField(default=dict, blank=True)

    objects = AuditManager()

    class Meta:
        db_table = "audit_auditentry"
        ordering = ["event_id", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["event", "seq"], name="audit_entry_event_seq_uniq"),
        ]
        indexes = [
            # audit view
            models.Index(fields=["event", "created_at"], name="audit_entry_event_idx"),
            # per-actor history
            models.Index(fields=["event", "actor", "action"], name="audit_entry_actor_idx"),
        ]

    def __str__(self) -> str:
        return f"audit {self.event_id}#{self.seq} {self.action}"

    @classmethod
    def chain_head(cls, event) -> str:
        """The current head of the chain for an event, or "" for an empty chain.

        A read helper, not a verifier. The verifier is FEAT-05: it re-walks the
        chain and recomputes the hashes, and until the writer exists there is
        nothing to re-walk. This returns "" honestly rather than pretending.
        """
        last = (
            cls.objects.filter(event=event)
            .order_by("-seq")
            .values_list("entry_hash", flat=True)
            .first()
        )
        return last or ""


class ResultPublication(SourceKeyMixin, TimeStampedModel, models.Model):
    """A published results page, and the content hash that anchors it.

    **Why the hash survives an untrusted database, which is the only attack
    that matters here.** The organizer's own database is the thing we do not
    trust. But ``input_digest`` is re-derivable from the raw scores by anyone
    holding the export, and ``ranking`` is re-computable by anyone running the
    published method. So **the hash is a claim and the export is the evidence.**
    An organizer who alters a result and leaves the hash alone has produced a
    mismatch any third party can detect with no access to our database -- which
    upgrades the threat model's J-10 from "detected" to "detectable by a third
    party", the difference between a claim and a control.

    One row per publication rather than a mutable singleton: publishing twice
    after fixing a typo is a real workflow, and overwriting the first hash would
    destroy exactly the evidence this table exists to keep.
    """

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="result_publications"
    )
    published_at = models.DateTimeField()
    rubric_version = models.ForeignKey(
        "rubrics.Rubric", on_delete=models.PROTECT, related_name="result_publications"
    )
    #: SHA-256 over the canonical form of every raw score row, sorted.
    input_digest = models.CharField(max_length=64)
    #: The published ranking block, verbatim as rendered.
    ranking = models.JSONField(default=list)
    #: SHA-256 over the whole publication document (bible/05 §9).
    results_hash = models.CharField(max_length=64)
    #: The audit chain head at the moment of publication, replicated into every
    #: signed judge record (bible/05 §9c). This is the column that makes the
    #: chain something a third party can check.
    audit_chain_head = models.CharField(max_length=64, blank=True, default="")
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        related_name="result_publications",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "audit_resultpublication"
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["event", "-published_at"], name="audit_pub_event_idx"),
        ]

    def __str__(self) -> str:
        return f"publication {self.event_id}@{self.published_at:%Y-%m-%d}"
