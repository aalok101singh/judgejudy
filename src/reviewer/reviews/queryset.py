"""``Review.objects.for_actor(actor)`` -- the only sanctioned way to read reviews.

This module is the architectural centrepiece of the project (``bible/05`` §6),
and it is four branches long, so the interesting part is not the code. It is the
four properties the code buys.

**1. Impossible to forget.** A view that writes ``Review.objects.all()`` is a
lint error (``tools/check_isolation.py``), not a security bug. The spec is
explicit that "hiding another judge's scores in your template is not refusing",
and a rule enforced by review is a rule that survives until hour 60.

**2. Refusal, not filtering.** An empty ``200`` FAILS the acceptance check. So
the *permission* layer raises a literal 403 with an empty body and no
``Location`` header (D-02), and the *queryset* layer -- this one -- constrains
and cannot raise. Two layers, failing in opposite directions (D-03). There is
deliberately no third layer: a third would be derived from one of the first two
and would be a second source of truth.

**3. Aggregate isolation falls out of the same place.** A leaderboard is
computed from ``Score`` joined to a scoped ``Review`` set, so a judge asking for
a ranking is asking over their own reviews and an organizer is asking over all
of them. One mechanism, two scopes.

**4. It is auditable.** Every call attaches a ``Scope`` describing the rule that
fired, which reaches the audit trail, the view and ``isolation_proof``.

**Why the track constraint is applied on top of the judge constraint.** A judge
sees ``judge = themselves``, and *also* only projects in the tracks they hold a
judge binding on. The second predicate is defence in depth, and it exists for a
specific reason: if a bad ``Assignment`` row ever put a judge on another track,
the first predicate alone would hand them that review. Both predicates fail
closed, and the receipt's sentence is generated from the list of predicates
rather than typed, so it cannot claim a constraint the filter does not apply.

**Why an event-wide judge binding is allowed at all.** A ``RoleBinding`` with
``role=judge, track=NULL`` is an organizer-declared grant across the whole
event; the track predicate is then omitted, and the receipt says so. The
alternative -- refusing -- would make the grant inexpressible and push
organizers toward granting organizer instead, which is a strictly larger
authority for what they meant as a judging role. The grant is explicit, stored
and reported; the misconfiguration it could not cause (a judge with no tracks
and no event-wide grant) yields nothing, because ``judge_track_ids`` is then
empty and the predicate matches no rows.
"""

from __future__ import annotations

from django.db import models

from reviewer.isolation.scope import (
    DECISION_ALLOW_ALL,
    DECISION_ALLOW_OWN,
    DECISION_DENY,
    Scope,
)
from reviewer.isolation.scoped import ScopedQuerySetMixin


class ReviewQuerySet(ScopedQuerySetMixin, models.QuerySet):
    """Reviews, plus the scope that decides who may read which of them."""

    def for_actor(self, actor):
        """The only sanctioned entry point to a ``Review`` queryset.

        ``actor`` is a ``reviewer.isolation.actor.Actor`` -- an already-resolved,
        immutable authority for one event. It is not a request and not a user,
        because both of those can be re-read mid-request and this is the layer
        that must not widen halfway through.
        """
        event_id = actor.event.pk
        base = self.filter(event_id=event_id)
        event_constraint = ("event", "the actor's event")

        if actor.can_read_all_reviews:
            # Organizer and admin. Note that `base` is the WHOLE event, not a
            # track slice: an organizer who could not see a track's reviews
            # could not staff it, and the acceptance matrix has one organizer
            # row, not one per track.
            return base._attach_scope(
                Scope.constrained(
                    DECISION_ALLOW_ALL,
                    [event_constraint],
                    bindings=self._actor_bindings(actor),
                    extras={"event_id": event_id},
                )
            )

        if actor.is_judge and actor.user is not None:
            constraints = [event_constraint, ("judge", "the actor's own user id")]
            qs = base.filter(judge_id=actor.user.pk)
            if not actor.event_wide_judge:
                constraints.append(("project.track", "the tracks the judge is bound to"))
                qs = qs.filter(project__track_id__in=actor.track_ids())
            return qs._attach_scope(
                Scope.constrained(
                    DECISION_ALLOW_OWN,
                    constraints,
                    bindings=self._actor_bindings(actor),
                    extras={"event_id": event_id, "judge_id": actor.user.pk},
                )
            )

        # Visitor and participant: nothing. `.none()` rather than an empty
        # filter result so the SQL is optimised away entirely -- but the SCOPE is
        # still attached, because the receipt is what tells a reader the
        # difference between "you may not see this" and "there is nothing here".
        return base.none()._attach_scope(
            Scope.constrained(
                DECISION_DENY,
                [event_constraint, ("role", f"{actor.label} has no review authority")],
                bindings=self._actor_bindings(actor),
                extras={"event_id": event_id},
            )
        )

    def for_actor_and_subject(self, actor, subject):
        """A judge asking about another judge is refused, not filtered (``bible/05`` §6).

        This is a *separate, explicitly peer-blind* accessor rather than a
        ``judge=`` parameter on the one above, and the separation is the point.
        The acceptance checker hits a peer URL and requires a 403; if
        ``for_actor`` took a subject, the natural implementation would return an
        empty queryset -- a 200 with nothing in it, which is the failure the
        brief names. Making the peer case a differently-named method means the
        call site has to say out loud that it is asking about someone else.

        Organizers and admins legitimately ask about any subject, so this falls
        through to ``for_actor`` for them.
        """
        if actor.is_judge and subject is not None and subject.pk != getattr(actor.user, "pk", None):
            return (
                self.filter(event_id=actor.event.pk)
                .none()
                ._attach_scope(
                    Scope.constrained(
                        DECISION_DENY,
                        [
                            ("event", "the actor's event"),
                            ("subject", "a subject the actor is not"),
                        ],
                        bindings=self._actor_bindings(actor),
                        extras={"event_id": actor.event.pk, "subject_id": subject.pk},
                    )
                )
            )
        return self.for_actor(actor)

    # ------------------------------------------------------------------ receipt

    def scope_total_count(self) -> int:
        """The event-wide review count, computed from the event and not from us.

        This is the denominator of the receipt's "3 of 126". Defining it here
        rather than as ``self.unscoped().count()`` is deliberate: a scope applied
        to an already-filtered base would otherwise report a total that had
        itself been filtered, and the receipt would be quoting its own filter
        back at the reader as independent evidence.
        """
        event_id = (self._scope.extras or {}).get("event_id")
        if event_id is None:
            raise ValueError(
                "scope_total_count() needs the event the scope was applied to. "
                "Only a queryset produced by for_actor() carries one."
            )
        # `self.model` rather than a module-level `Review` reference: queryset.py
        # is imported BY models.py to build the manager, so a top-level import of
        # Review here is a cycle that Python resolves by accident. `self.model`
        # is the model class by construction and has no import at all.
        return self.model._default_manager.filter(event_id=event_id).count()

    @staticmethod
    def _actor_bindings(actor) -> tuple[tuple[str, str], ...]:
        """The ``RoleBinding`` rows that justified this scope, as readable pairs.

        Not the raw relation: a receipt that prints foreign keys teaches the
        reader nothing, and the point of the object is that a person can check
        it. The one exception is a judge with many tracks, which would produce a
        paragraph; that is collapsed with a count.
        """
        from reviewer.core import ROLE_ADMIN, ROLE_ORGANIZER

        if actor.is_admin:
            return [("role", ROLE_ADMIN)]
        if actor.is_organizer:
            return [("role", ROLE_ORGANIZER)]
        if not actor.is_judge:
            return []
        tracks = actor.track_ids()
        if actor.event_wide_judge:
            return [("role", "judge, event-wide")]
        if not tracks:
            return [("role", "judge, bound to no track")]
        shown = ", ".join(str(t) for t in tracks[:3])
        if len(tracks) > 3:
            shown += f" and {len(tracks) - 3} more"
        return [("role", "judge"), ("tracks", shown)]
