"""Publication: the audit chain head, the results hash, and what a third party can check.

**The claim and the evidence, and why they are different things.** When an
organizer publishes results, this module writes two things:

* ``input_digest`` -- a hash over the **raw scores** that produced the ranking.
* ``results_hash`` -- a hash over the **ranking itself**, bound to that digest.

Neither is a secret and neither is trusted, because **the organizer's own
database is the thing we do not trust.** What makes them worth writing is that
both are **re-derivable by anyone holding the export**: the digest from the raw
scores, the ranking by running the published method. So:

> **An organizer who alters a result and leaves the hash alone has produced a
> mismatch any third party can detect with no access to our database.**

That upgrades the threat model's J-10 from *"detected"* to *"detectable by a
third party"*, and the difference between the two is the difference between a
claim and a control. A hash we computed and nobody can reproduce is a
fingerprint; a hash a stranger can recompute is evidence.

**And that is exactly what makes increment 1 load-bearing.** ``tests/
test_publication.py`` exports the database, wipes it, imports it, recomputes the
digest from the restored rows, and asserts it matches the published one. The
escape hatch and the publication claim are the same property viewed from two
sides: *if you can take the data away and bring it back, the numbers still
describe it.*

Why publication is a row and not a mutable singleton
---------------------------------------------------
``bible/05`` §9b and the model's own docstring: **publishing twice after fixing a
typo is a real workflow**, and overwriting the first hash would destroy exactly
the evidence this table exists to keep. So every publication is its own row and
the history is the audit trail. A reader who wants to know whether a result was
edited can count the publications before and after.

What D-09 replicates, and why it is not a Merkle tree
------------------------------------------------------
``audit_chain_head`` is copied into **every** signed judge record at publication
(``replicate_into_signed_records``). This project has no independent witness and
runs the container itself, so a Merkle root we compute ourselves would prove
internal consistency -- which the 30-line hash chain already proves, for three
times the code. What it would **not** do is let anyone else notice equivocation.
Putting the head in every signed record means **N judges who are not the
organizer each hold a copy**, so equivocation becomes detectable by a five-line
diff between any two of them. That is the actual value, and it is why this is
called out as replacing a transparency log rather than merely supplementing one.
"""

from __future__ import annotations

import hashlib

from django.db import transaction

from reviewer.io.bundle import canonical

#: The fields of a ranking row that go into the hash. **Explicit, not "the dict as
#: it came out of the function."** A hash over a dictionary serialises whatever
#: keys happen to exist, so adding a column would change every published hash and
#: breaking a column would too -- neither of which is a change to the *result*.
#: The hash has to mean "the ranking", so it means exactly these five values.
#:
#: Read off ``reviews/results.py``'s own row shape: ``project``, ``title``,
#: ``track``, ``weighted_total``, ``mean``, ``reviews_counted``,
#: ``normalization``, and ``rank`` -- which is the name that function actually
#: uses, not ``position``, which is what this tuple said for one commit. **A named
#: field the rows do not have contributes a constant ``None`` to every hash while
#: looking covered**, so the tuple is asserted against the real rows by
#: ``TestTheFieldListAndTheHashAgree`` and derived into the hash rather than
#: written out twice (F-98).
#:
#: ``title`` and ``track`` are deliberately **excluded** -- renaming a project does
#: not change where it ranked, and a hash that moved on a rename would be one more
#: reason for an organizer to avoid re-publishing.
RANKING_FIELDS = ("rank", "project", "mean", "reviews_counted", "normalization")


def input_digest(event, rubric=None) -> str:
    """SHA-256 over every raw score in the event, in a stable order.

    **Ordered by natural key, never by primary key and never by the database's
    own order.** An archive whose ordering depends on the query planner is not
    byte-identical to anything, and a digest with the same defect is worse --
    because it looks like a tamper signal. This is the same rule as the bulk
    exporter's, and for the same reason.

    Re-derivable from the export alone, which is the whole point: a stranger
    holding the archive recomputes this and compares.
    """
    from reviewer.reviews.models import Score

    scores = (
        Score.objects.filter(review__event=event)
        .select_related("review", "criterion")
        .order_by("review__source_key", "criterion__key")
    )
    parts = []
    for score in scores:
        parts.append(
            canonical(
                {
                    "review": score.review.source_key,
                    "criterion": score.criterion.key,
                    "value": score.value,
                    "weight_applied": str(score.weight_applied),
                }
            )
        )
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def ranking_for(event, actor) -> list[dict]:
    """The published rows, in the shape the results page renders.

    Delegates to ``reviews.results.leaderboard`` rather than recomputing a
    ranking. That is the same rule the ballot-order surface follows with
    ``presentation_order``: **the page and the published hash must come from one
    function**, because two implementations of "the ranking" is a class of defect
    this project has already paid for twice (F-84, F-89) -- in both cases two
    shipped artefacts answering one question differently.

    ``normalization`` is carried per row and is **always** the literal
    ``unnormalized-raw-weighted-mean`` today. It goes into the hash anyway,
    because a ranking that does not record *how* it was computed cannot be
    re-derived -- and the day a normalized estimator ships, the previous
    publication's hash would then mean something different from the same numbers.
    """
    from reviewer.reviews import results as results_module

    return results_module.leaderboard(actor)


def results_hash(rows, digest: str) -> str:
    """SHA-256 over the ranking, bound to the digest of the scores behind it.

    **The digest is mixed in**, so a hash cannot be reused across two different
    sets of scores that happen to produce the same ranking -- and, more usefully,
    so an organizer cannot present a hash from one publication as the hash of
    another.
    """
    payload = canonical({"input_digest": digest, "ranking": [_hashable(row) for row in rows]})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hashable(row: dict) -> dict:
    """Reduce a row to exactly ``RANKING_FIELDS``.

    Anything not in that tuple is deliberately dropped rather than hashed, so a
    cosmetic change to the page does not invalidate a published result -- and a
    change to a *score* does, because the value is one of the five.

    **Derived from the tuple rather than written out again, and that is F-98's
    whole repair.** The first version listed the five keys by hand, and when
    ``RANKING_FIELDS`` was corrected the two drifted apart: the function still
    hashed a ``judges`` key that no row has -- so it contributed a constant
    ``None`` to every hash -- and **stopped hashing ``reviews_counted``**, which is
    a number a reader would reasonably expect to be covered. The docstring claimed
    "exactly ``RANKING_FIELDS``" and was false, and nothing could catch it because a
    consistently-wrong hash is indistinguishable from a right one by any test that
    only checks that hashes agree.

    It was found because the mutation harness **skipped** its mutation: the
    two-line replacement string no longer matched the source. A skip is a finding
    about the harness, and this time the finding was about the code.
    """
    return {name: row.get(name) for name in RANKING_FIELDS}


def chain_head(event) -> str:
    """The audit chain's current head, or ``""`` when the chain is empty."""
    from reviewer.audit.models import AuditEntry

    last = AuditEntry.objects.filter(event=event).order_by("seq").last()
    return last.entry_hash if last is not None else ""


@transaction.atomic
def publish(event, actor, *, published_at=None) -> object:
    """Publish the ranking. Returns the ``ResultPublication`` row.

    **A new row every time, never an update.** See this module's docstring: the
    history of publications *is* the tamper evidence, and an overwrite destroys it.
    """
    import datetime as dt

    from reviewer.audit.models import ResultPublication
    from reviewer.reviews import results as results_module

    if not results_module.results_visible_to(actor):
        raise PermissionError(
            f"{actor!r} may not publish results for {event.pk}; publication is an "
            "organizer action and the check lives at the one place it can be read"
        )

    digest = input_digest(event)
    rows = ranking_for(event, actor)
    head = chain_head(event)

    rubric = event.rubrics.order_by("-version").first()
    if rubric is None:
        raise ValueError(f"{event.pk} has no rubric, so there is nothing to publish")

    publication = ResultPublication.objects.create(
        event=event,
        published_at=published_at or dt.datetime.now(dt.UTC),
        rubric_version=rubric,
        input_digest=digest,
        ranking=rows,
        results_hash=results_hash(rows, digest),
        audit_chain_head=head,
        published_by=getattr(actor, "user", None),
    )
    replicate_into_signed_records(event, publication)
    return publication


def replicate_into_signed_records(event, publication) -> int:
    """Copy ``results_hash`` and ``audit_chain_head`` into every signed record.

    **D-09.** Returns the number of records stamped.

    The copy lands inside each record's ``statement`` -- the signed payload -- so
    the values cannot be edited afterwards without invalidating that judge's own
    signature. **That is the reason to put them here rather than in a column we
    own:** a column would be ours to rewrite, and a rewritten column is invisible.

    A record with no ``results_hash`` key yet is stamped; one that already
    carries a *different* hash is left alone and reported, because
    **overwriting it would destroy the only evidence that the result changed
    after a judge signed.** The count of untouched records is returned by
    :func:`replication_report` rather than swallowed here.
    """
    from reviewer.credentials.models import SignedRecord

    stamped = 0
    for record in SignedRecord.objects.filter(event=event):
        statement = dict(record.statement or {})
        if statement.get("results_hash") not in (None, publication.results_hash):
            continue
        statement["results_hash"] = publication.results_hash
        statement["audit_chain_head"] = publication.audit_chain_head
        statement.setdefault("results_hash_at_issue", statement["results_hash"])
        record.statement = statement
        record.save(update_fields=["statement"])
        stamped += 1
    return stamped


def replication_report(event, publication) -> dict:
    """How many signed records agree with this publication, and how many differ."""
    from reviewer.credentials.models import SignedRecord

    agreeing = disagreeing = absent = 0
    for record in SignedRecord.objects.filter(event=event):
        current = (record.statement or {}).get("results_hash")
        if current is None:
            absent += 1
        elif current == publication.results_hash:
            agreeing += 1
        else:
            disagreeing += 1
    return {
        "agrees": agreeing,
        "disagrees": disagreeing,
        "no_results_hash": absent,
        "total": SignedRecord.objects.filter(event=event).count(),
    }
