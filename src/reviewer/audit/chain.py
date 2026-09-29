"""Writing the audit chain, and reading it back under an actor's authority.

**The chain exists; until this module nothing wrote to it.** `AuditEntry` shipped
at FEAT-02 with `seq`, `prev_hash`, `entry_hash` and `omitted_since_prev`, and
`manage.py isolation_proof` could already check that the chain is append-only --
but **`AuditEntry.objects.count()` was 0 on a fully seeded event.** The
isolation matrix's `audit` column therefore had nothing to report, and the two
available answers were both wrong:

* print `0`, and the column reads as *"verified, and the answer is none"* --
  which the `UNPROVEN` docstring in `isolation_proof.py` explicitly calls out as
  the misleading option; or
* print `?` forever, and the matrix never grows.

**This is F-61 for the fourth time**, and it is the clearest one yet: a
structurally valid audit trail containing nothing at all. The proof could check
that the trail was append-only without ever checking that it existed.

**Why the hash is over canonical JSON and not over the row.** The chain has to be
re-verifiable by a reader with a script, so the bytes being hashed must be
something they can reconstruct: sorted keys, no whitespace, UTF-8, and the
fields named explicitly. Hashing ``repr(instance)`` would bind the chain to
Django's model formatting and to this repository's field order, which is not a
property a third party can check.

**Why `omitted_since_prev` is a parameter and not an internal decision.** D-08:
the chain records what it did not record. Sampling decisions belong to the caller
that made them -- a rate limiter knows what it dropped and a blind writer does not
-- so the count is carried in and hashed. A writer that computed it would have to
lie about its own omissions.
"""

from __future__ import annotations

import hashlib
import json

from django.db import transaction

from reviewer.audit.models import AuditEntry

#: The fields the entry hash covers, in a fixed order. Named explicitly so that
#: adding a model field does not silently change what the chain commits to --
#: which would make every previously-written hash unverifiable against new code.
HASHED_FIELDS = (
    "event",
    "seq",
    "actor",
    "action",
    "object_type",
    "object_id",
    "before",
    "after",
    "ip_hash",
    "prev_hash",
    "omitted_since_prev",
)

#: Chain actions this module writes. A named vocabulary rather than free text,
#: because the audit view groups by it and a typo in an action string would be an
#: unreadable trail rather than a broken one.
ACTION_EXPORT_RUN = "export run"
ACTION_IMPORT_RUN = "import run"
ACTION_REVIEW_SUBMIT = "review submit"
ACTION_RESULTS_PUBLISH = "results publish"
ACTION_DENIED = "denied"


def canonical_payload(entry: AuditEntry) -> str:
    """The exact bytes ``entry_hash`` is computed over.

    **Exposed because a verifier has to re-derive it**, and a verifier that
    re-implements the serialisation is a second source of truth (F-62). One
    function, called by both the writer and `verify_chain`.
    """
    values = {}
    for field in HASHED_FIELDS:
        value = getattr(entry, field, None)
        if field == "event":
            value = entry.event_id
        elif field == "actor":
            value = entry.actor_id
        values[field] = value
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(entry: AuditEntry) -> str:
    """SHA-256 over :func:`canonical_payload`, hex, first 64 chars."""
    digest = hashlib.sha256(canonical_payload(entry).encode("utf-8")).hexdigest()
    return digest[:64]


def append(
    event,
    action: str,
    *,
    actor=None,
    object_type: str = "",
    object_id: str = "",
    before: dict | None = None,
    after: dict | None = None,
    ip_hash: str = "",
    scope_reason: dict | None = None,
    omitted_since_prev: int = 0,
) -> AuditEntry:
    """Append one link. The only supported way to create an ``AuditEntry``.

    ``transaction.atomic`` with a row lock on the head, because two concurrent
    appends would otherwise both read the same ``prev_hash`` and both claim the
    same ``seq`` -- which the ``UniqueConstraint`` turns into an
    ``IntegrityError`` on one of them. Locking first makes the second one wait and
    then chain correctly, so the trail never has a fork.

    The constraint is the backstop, not the mechanism: a constraint that fires is
    a failed write, and a failed write is a hole in a trail whose entire claim is
    that it has no holes.
    """
    with transaction.atomic():
        last = AuditEntry.objects.select_for_update().filter(event=event).order_by("-seq").first()
        seq = (last.seq + 1) if last is not None else 1
        prev_hash = last.entry_hash if last is not None else ""

        entry = AuditEntry(
            event=event,
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before or {},
            after=after or {},
            ip_hash=ip_hash,
            seq=seq,
            prev_hash=prev_hash,
            omitted_since_prev=omitted_since_prev,
            scope_reason=scope_reason or {},
        )
        entry.entry_hash = compute_hash(entry)
        entry.save()
        return entry


def verify_chain(event) -> list[str]:
    """Re-walk the chain and return a list of problems; empty means verified.

    **This is the check the FEAT-02 docstring said was waiting for a writer.** It
    is not a re-read of the stored hashes: it recomputes each one from the row's
    own contents, so an edit to `after` is caught even though `entry_hash` itself
    is untouched. The three failures it distinguishes are all different problems
    with different fixes:

    * a **sequence gap** -- an entry is missing;
    * a **broken link** -- ``prev_hash`` does not equal the previous
      ``entry_hash``, so an entry was inserted or reordered;
    * a **content mismatch** -- the row no longer hashes to its own recorded
      digest, so a field was edited in place.

    The last one is the only one a chain detects that a signed list would not, and
    it is the reason the hash covers the payload rather than being a pointer.
    """
    problems: list[str] = []
    previous: AuditEntry | None = None
    for entry in AuditEntry.objects.filter(event=event).order_by("seq"):
        expected_seq = (previous.seq + 1) if previous is not None else 1
        if entry.seq != expected_seq:
            problems.append(
                f"seq {entry.seq} follows {previous.seq if previous else 0}; "
                f"expected {expected_seq}. An entry is missing."
            )
        expected_prev = previous.entry_hash if previous is not None else ""
        if entry.prev_hash != expected_prev:
            problems.append(
                f"seq {entry.seq} prev_hash does not match the previous entry_hash. "
                "An entry was inserted or reordered."
            )
        recomputed = compute_hash(entry)
        if entry.entry_hash != recomputed:
            problems.append(
                f"seq {entry.seq} content does not hash to its recorded digest "
                f"(stored {entry.entry_hash[:12]}..., computed {recomputed[:12]}...). "
                "A field was edited in place."
            )
        previous = entry
    return problems


# ------------------------------------------------------------------- the accessor


def for_actor(actor) -> tuple[list[AuditEntry], bool]:
    """``(entries, permitted)`` -- the audit trail as this actor may see it.

    **Organizer and admin only, and the rule is that, not a scope.** An audit
    trail is a record of *what everyone did*, so there is no per-actor slice of it
    that is honest: a judge asking for "my history" would get a trail with the
    gaps where other people's actions were, and a gap in an audit trail is
    indistinguishable from a deletion -- which is the exact ambiguity
    ``omitted_since_prev`` exists to remove. So the choice is all or nothing.

    The second element is returned rather than raised, because the matrix's
    ``audit`` cell has to print **"refused"** and a 0 that reads as "verified, and
    the answer is none" is the misleading option this project keeps being bitten
    by. A refusal and an empty result are different answers.
    """
    if not actor.can_read_all_reviews:
        return [], False
    return (
        list(AuditEntry.objects.filter(event=actor.event).select_related("actor").order_by("seq")),
        True,
    )
