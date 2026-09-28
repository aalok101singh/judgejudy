"""The scope receipt: the object that makes an access decision explain itself.

``bible/05`` §6a calls this the third "steal it" candidate and puts its cost at
about an hour. The argument is not that it is a nice UI. The argument is that it
converts isolation from *something our tests assert* into *something a reader can
verify without running anything*:

    Why you are seeing 3 of 126 reviews
    You are a judge on trk_04 (Security). Isolation shows you your own reviews
    only - 3 of the 126 in this event. Peers, other tracks, and aggregates are
    refused at the API with 403, not hidden on this page.

That is the third of the project's three isolation properties. The refusal is
correct (D-02), the queryset cannot be forgotten (D-01), and now the scope says
which rule fired and how many rows it let through.

**One object, three consumers** (`bible/05` §6a):

===========================  =========================================
consumer                     what it renders
===========================  =========================================
the judge's list view        the collapsible block above
the audit entry              the scope string, beside actor and action
``manage.py isolation_proof``  the "3 of 126" column, per actor
===========================  =========================================

**Why ``Scope`` and ``ScopeReason`` are two classes and not one.** ``for_actor()``
must stay lazy: it is called on the request path and adding an unconditional
``COUNT(*)` to it would put a query in front of every list view. So the
accessor attaches a ``Scope`` -- the *rule*, which is known at call time and
costs nothing -- and the counts arrive later, when a consumer that is actually
going to render them asks for a ``ScopeReason``. ``ScopeReason.with_counts()``
returns a new frozen instance, so a receipt with numbers cannot be confused with
a receipt without.

**Why the rule string is assembled from the constraints rather than typed per
branch.** A hand-written rule per branch is a claim about the code, and this
project has twelve findings of claims drifting from code. ``Scope.constrained()``
builds the sentence from the same constraint tuples that produced the filter, so
a constraint added to the filter and not to the sentence is a test failure
rather than a docstring nobody re-reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The three decisions a scope can make. `deny` is distinct from "allow nothing"
# on purpose: a judge legitimately sees zero rows when they have no reviews, and
# the receipt must not tell them their access was refused when it was not.
DECISION_ALLOW_ALL = "allow-all"
DECISION_ALLOW_OWN = "allow-own"
DECISION_DENY = "deny"


@dataclass(frozen=True)
class Scope:
    """The rule that fired, before anyone has counted anything.

    ``constraints`` is a tuple of ``(clause, explanation)`` pairs where ``clause``
    is the literal predicate that was applied to the queryset, rendered. It is
    the auditable half: it is what a reader compares against the SQL.
    """

    rule: str
    decision: str
    constraints: tuple[tuple[str, str], ...] = ()
    bindings: tuple[tuple[str, str], ...] = ()
    #: Machine-readable extras the accessor needed but did not want to turn into
    #: English. ``for_actor`` puts the event id here so the receipt's "of 126"
    #: denominator can be re-derived from the scope rather than re-queried from
    #: whatever queryset happened to be handed in. Excluded from comparison --
    #: two scopes that let through the same rows for the same reason are the
    #: same scope, whatever they carry.
    extras: dict = field(default_factory=dict, compare=False)

    @classmethod
    def constrained(cls, decision: str, constraints, bindings=(), extras=None) -> Scope:
        """Build a scope whose rule sentence is generated from its constraints.

        The sentence is deliberately mechanical -- "constrained by a, b and c" --
        rather than prose. A prose rule is a claim about the filter that nothing
        checks; a generated one cannot disagree with it.
        """
        constraints = tuple((str(c), str(w)) for c, w in constraints)
        bindings = tuple((str(k), str(v)) for k, v in bindings)
        joined = _join([c for c, _ in constraints])
        rule = f"{decision}: constrained by {joined}" if joined else decision
        return cls(
            rule=rule,
            decision=decision,
            constraints=constraints,
            bindings=bindings,
            extras=dict(extras or {}),
        )

    def with_counts(self, visible: int, total: int) -> ScopeReason:
        """Return the receipt for this scope, with the two row counts filled in."""
        return ScopeReason(
            rule=self.rule,
            decision=self.decision,
            constraints=self.constraints,
            bindings=self.bindings,
            visible=visible,
            total=total,
            extras=dict(self.extras),
        )


@dataclass(frozen=True)
class ScopeReason:
    """A scope plus the numbers a human needs to check it.

    ``visible`` and ``total`` are the whole point of the class and also its only
    awkwardness: a receipt saying "3 of 126" is only evidence if 126 was defined
    independently of the filter that produced 3. That is why ``for_actor``
    computes the total from the *event*, not from the queryset it was handed --
    see ``reviewer.reviews.queryset.ReviewQuerySet.for_actor``.
    """

    rule: str
    decision: str
    constraints: tuple[tuple[str, str], ...] = ()
    bindings: tuple[tuple[str, str], ...] = ()
    visible: int | None = None
    total: int | None = None
    extras: dict = field(default_factory=dict, compare=False)

    @property
    def withheld(self) -> int | None:
        """How many rows the scope kept out. ``None`` until counts are filled."""
        if self.visible is None or self.total is None:
            return None
        return self.total - self.visible

    @property
    def bindings_text(self) -> str:
        return _join([f"{k} {v}" for k, v in self.bindings])

    def summary(self) -> str:
        """The human-readable sentence, for the view and the audit trail."""
        if self.visible is None or self.total is None:
            return f"{self.rule} ({self.bindings_text or 'no bindings'})"
        head = f"You are seeing {self.visible} of {self.total} reviews"
        bindings = self.bindings_text
        if not bindings:
            return f"{head}. {self.rule}."
        return f"{head}. {self.rule}. Bound as {bindings}."

    def as_dict(self) -> dict:
        """The receipt as data, for the audit trail and the JSON export."""
        return {
            "rule": self.rule,
            "decision": self.decision,
            "constraints": [list(c) for c in self.constraints],
            "bindings": [list(b) for b in self.bindings],
            "visible": self.visible,
            "total": self.total,
            "withheld": self.withheld,
            "extras": dict(self.extras),
        }


def _join(items) -> str:
    """``a``, ``a and b``, ``a, b and c`` -- the only string work in here."""
    items = [i for i in items if i]
    if not items:
        return "nothing"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
