"""The product surface for randomised ballot order (D-12, REQ-T3-04).

**The one thing this module must not do is reimplement the shuffle.** The
harness in `bias_attack.py` attacks `presentation_order`, and the *entire* value
of the claim is that the function the product ships is the function the harness
measured. A second copy of the seed formula -- even an identical one -- is a
second thing that can drift, and the drift would be invisible: the harness would
keep reporting zero-mean against a function nothing calls any more.

So `ballot_order()` below is a thin, auditable wrapper: derive an identity, hand
it to `presentation_order`, persist the answer. Every decision worth arguing
about is in the docstring below; the arithmetic is not repeated anywhere.

**Why a stored row and not a computed one.** `presentation_order` is a pure
function, so it *could* be recomputed on every request. It is persisted anyway,
because the guarantee D-12 rests on is that a voter **cannot re-roll by
refreshing**, and a pure function of a *cookie* is only stable while the cookie
survives. `Ballot` carries a `UniqueConstraint(event, voter_key)`, so the second
request finds the first request's row rather than minting a new order. The stored
row is the enforcement; the pure function is only how the first one was made.

**Why the identity is hashed and salted before it is a seed.** `voter_key` is
the deduplication identity and the models docstring is explicit that it is hashed
for all three voting modes. A seed derived from a raw IP address would be
reversible by brute force over the whole IPv4 space in seconds, and the seed is
printed in the ballot. The HMAC key is `settings.SECRET_KEY`, which the
entrypoint generates onto the instance volume and gitignores -- so the seed is
not reproducible from the repository, which is the point.

**What this does NOT do, and the two omissions are decisions rather than gaps.**
It does not cast votes (that is `Vote`, REQ-T3-01, and it is not started), and
it does not rank. What it ships is the ordering guarantee and the row that
proves it, which is the whole of REQ-T3-04 and the part the harness can attack.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings

from reviewer.ballots.bias_attack import presentation_order
from reviewer.ballots.models import Ballot
from reviewer.events.models import VOTING_AUTHENTICATED, VOTING_EMAIL_GATED, VOTING_OPEN_LINK

#: The only design this surface ships. `randomised` is the shipped mechanism and
#: the one the harness reports zero-mean for; `balanced` and `fixed` exist to give
#: the harness a null and an attack, and neither is a thing a user should ever be
#: shown. Naming it as a constant makes "did someone re-point the product at the
#: attack arm?" a one-line diff to read rather than a question to answer.
DESIGN = "randomised"

#: Bytes of the identity digest we keep, and so the exact width of the stored
#: seed. 8 hex characters is 32 bits: ample for separating 41 slots across a few
#: hundred voters, and short enough that the seed column stays readable in a
#: database browser. **This is not a security parameter** -- the seed is public by
#: design, it is in the ballot row -- it is a collision parameter, and the honest
#: statement is that it was chosen because the number is legible, not because it
#: was measured to be safe.
SEED_HEX_CHARS = 8


def _event_salt(event) -> bytes:
    """A per-event salt, so one event's seeds mean nothing in another.

    Derived from ``SECRET_KEY`` rather than stored, because a column that has to
    be rotated is a column that will not be. ``SECRET_KEY`` is generated onto the
    instance volume and gitignored, so this cannot be reproduced from the
    repository.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        event.pk.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _digest(event, *parts: str) -> str:
    """Hex digest over the identity parts, keyed by the event salt."""
    payload = "\x1f".join(parts).encode("utf-8")
    return hmac.new(_event_salt(event), payload, hashlib.sha256).hexdigest()


def voter_identity(event, request, *, user=None) -> str | None:
    """The deduplication identity for this request, or ``None`` if there is none.

    **Three modes, three identities, and the choice is the event's rather than
    the caller's** (`bible/05` §7), because a surface that let the request pick
    would let a requester pick the weakest one:

    * ``open_link``  -- salted digest of IP + user agent. No cookie, deliberately:
      this is the "no account needed" mode and adding a cookie would be a
      different product.
    * ``email_gated`` -- the authenticated user's normalised email. Gated means
      authenticated, so there is no anonymous branch.
    * ``authenticated`` -- the user id.

    ``None`` means *refuse*, never *anonymous*. A ballot with no identity cannot
    be deduplicated, and an undeduplicated ballot is the free-for-all the open
    link mode is documented as being (REQ-T3-01's stated risk). **"I could not
    tell who you are" is a refusal, not a blank ballot.**
    """
    mode = event.voting_mode
    if mode == VOTING_OPEN_LINK:
        ip = request.META.get("REMOTE_ADDR", "")
        agent = request.META.get("HTTP_USER_AGENT", "")
        if not ip:
            # No REMOTE_ADDR means no identity, not an identity of "". Behind a
            # proxy this is normal; on a bare socket it means the request did not
            # come through the stack we expect. Either way, refusing is honest.
            return None
        return _digest(event, "open_link", ip, agent)
    if mode == VOTING_EMAIL_GATED:
        email = getattr(user, "email", None)
        if not email:
            return None
        return _digest(event, "email_gated", email.strip().lower())
    if mode == VOTING_AUTHENTICATED:
        user_id = getattr(user, "id", None)
        if not user_id:
            return None
        return _digest(event, "authenticated", str(user_id))
    return None


def ballot_order(event, voter_key: str, projects) -> Ballot:
    """This voter's ballot for this event, creating it on first request.

    ``projects`` is the list the order permutes, and **it is the base order that
    the permutation applies to** -- which is why it is passed in rather than
    queried here. The permutation is a list of *positions*; if the base order
    were not deterministic the seed would not determine what a voter sees, and
    the whole "stable across requests" property would be an accident of the
    database's row order. Callers sort explicitly and this function says so.

    **F-83, and it is F-80 one level down: the order is keyed on `Project.id`,
    not on `source_key`.** The first version of this function used
    ``source_key``, which is the obvious choice for a portable natural key and is
    `NULL` for every project the portal created itself -- `SourceKeyMixin`'s
    docstring says so outright ("Null for rows this portal created"). So a
    self-submitted project would have put a `None` in the permutation, and a
    ballot of `None`s is **structurally valid and contains nothing**: it renders,
    it stores, it passes every shape check, and it ranks no project at all. The
    tests caught it because one of them sorts the order, and `[None] < [None]`
    raises. **A field that is nullable in the schema is nullable in the
    permutation too, and a permutation needs a total order.**

    `Project.id` is the primary key, so it is present for fixture rows and
    portal-created rows alike. It is also what the gallery and the console already
    print, so a reader can match a ballot entry to a project without a second
    lookup.
    """
    keys = [p.pk for p in projects]
    n = len(keys)

    existing = Ballot.objects.filter(event=event, voter_key=voter_key).first()
    if existing is not None:
        return existing

    seed = _digest(event, "order", voter_key)[:SEED_HEX_CHARS]
    # `voter` and `replication` are 0 because the product has exactly one ballot
    # per identity and no replication loop. The identity lives entirely in
    # `seed`, so the order is a pure function of who is asking -- which is the
    # property the claim rests on, and the reason a refresh cannot move it.
    positions = presentation_order(
        DESIGN,
        seed=int(seed, 16),
        voter=0,
        replication=0,
        n_projects=n,
    )
    order = [keys[i] for i in positions]
    ballot, _created = Ballot.objects.get_or_create(
        event=event,
        voter_key=voter_key,
        defaults={"seed": seed, "order": order},
    )
    return ballot


def ordered_projects(ballot: Ballot, projects_by_pk) -> list:
    """The projects in this ballot's order.

    A dict rather than a queryset lookup so the caller controls the mapping and
    this function cannot accidentally widen it. Projects the ballot names but the
    event no longer has are skipped silently: a ballot cast against a field that
    has since changed is history, and dropping the row would be a lie.
    """
    return [projects_by_pk[k] for k in ballot.order if k in projects_by_pk]
