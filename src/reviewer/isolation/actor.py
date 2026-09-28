"""The actor: who is asking, in which event, and on what authority.

``bible/05`` §6 sketches ``for_actor(actor)`` against an object that answers
``is_admin``, ``is_organizer_for(event)`` and ``is_judge_for(event)``. This is
that object, and the reason it is a frozen dataclass resolved *once per request*
rather than a live wrapper around the request is a design decision worth
stating:

**Authority is a fact about a binding, and it is read once.** Every
authorization decision in this project is a ``RoleBinding`` lookup plus a
queryset scope (``bible/05`` §3). Resolving the bindings into an immutable value
means the rest of the request path cannot observe a different authority halfway
through -- a role added mid-request cannot widen a queryset that was already
scoped, and a role removed mid-request cannot narrow one that was not.

**Why the roles are resolved here rather than queried on demand.** The two
enforcement layers (D-03) fail in opposite directions, and the layer that fails
open is the queryset. If the queryset asked the database "is this a judge?"
itself, a typo in that subquery would be a *scope* that silently lets rows
through, and a scope failure is invisible -- there is no response to assert on.
Resolving first, then filtering on an in-memory value, means the only way to
leak is to construct the wrong ``Actor``, and constructing one is a visible,
testable act.

**``visitor`` is the absence of a binding, not a stored value** (``bible/05``
§3). Storing it would mean every anonymous request creates a ``User`` row. The
role *set* still has five members, because the tier requires five, and
``is_visitor`` is derived so no call site has to handle ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reviewer.core import ROLE_ADMIN, ROLE_JUDGE, ROLE_ORGANIZER, ROLE_PARTICIPANT, ROLE_VISITOR


@dataclass(frozen=True)
class Actor:
    """An immutable, already-resolved authority for one event."""

    event: object
    user: object | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    #: Track ids this actor holds a *judge* binding on. A judge binding with
    #: ``track = NULL`` is an organizer-declared event-wide grant, which is
    #: tracked separately below rather than being silently indistinguishable
    #: from "a judge on no tracks" (which would be a misconfiguration).
    judge_track_ids: frozenset[int] = field(default_factory=frozenset)
    event_wide_judge: bool = False
    is_authenticated: bool = False

    # ------------------------------------------------------------ construction

    @classmethod
    def anonymous(cls, event) -> Actor:
        """The visitor. A real role, expressed as the absence of any binding."""
        return cls(event=event, user=None, roles=frozenset(), is_authenticated=False)

    @classmethod
    def for_user(cls, event, user) -> Actor:
        """Resolve ``user``'s bindings in ``event`` into an immutable authority.

        This is the only place ``RoleBinding`` is read. Everything downstream
        reads the frozen result, so a reviewer can find the entire authorization
        surface by reading one class.
        """
        from reviewer.accounts.models import RoleBinding

        if user is None or not getattr(user, "is_authenticated", False):
            return cls.anonymous(event)

        bindings = list(RoleBinding.objects.filter(event=event, user=user))
        roles = {b.role for b in bindings}

        # `admin` is a Django-is_staff concept and `organizer` is a binding; the
        # union is what `can_read_all_reviews` needs. Neither implies the other
        # in the schema, and the receipt reports the real binding.
        if getattr(user, "is_staff", False):
            roles.add(ROLE_ADMIN)

        judge_tracks = {b.track_id for b in bindings if b.role == ROLE_JUDGE and b.track_id}
        event_wide = any(b.role == ROLE_JUDGE and b.track_id is None for b in bindings)

        return cls(
            event=event,
            user=user,
            roles=frozenset(roles),
            judge_track_ids=frozenset(judge_tracks),
            event_wide_judge=event_wide,
            is_authenticated=True,
        )

    @classmethod
    def for_request(cls, request, event) -> Actor:
        """Resolve the current request's user. The one call site a view needs."""
        return cls.for_user(event, getattr(request, "user", None))

    # ------------------------------------------------------------------ roles

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def is_admin(self) -> bool:
        return ROLE_ADMIN in self.roles

    @property
    def is_organizer(self) -> bool:
        return ROLE_ORGANIZER in self.roles

    @property
    def is_judge(self) -> bool:
        return ROLE_JUDGE in self.roles

    @property
    def is_participant(self) -> bool:
        return ROLE_PARTICIPANT in self.roles

    @property
    def is_visitor(self) -> bool:
        """True when the actor holds no stored binding at all."""
        return not (self.roles - {ROLE_ADMIN})

    @property
    def can_read_all_reviews(self) -> bool:
        """Organizer and admin see the whole event. The only branch that does."""
        return self.is_organizer or self.is_admin

    @property
    def label(self) -> str:
        """A stable name for the proof matrix and the audit trail."""
        if self.is_admin:
            return ROLE_ADMIN
        if self.is_organizer:
            return ROLE_ORGANIZER
        if self.is_judge:
            return ROLE_JUDGE
        if self.is_participant:
            return ROLE_PARTICIPANT
        return ROLE_VISITOR

    def track_ids(self) -> list[int]:
        """The judge's bound tracks, in a stable order for the receipt."""
        return sorted(self.judge_track_ids)
