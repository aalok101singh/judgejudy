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
from django.db.models import Count

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

        **Who falls through, and why a judge who also organises now does too
        (F-51).** The guard is ``actor.is_judge and not actor.can_read_all_reviews``:

        * a visitor, a participant, an organizer or an admin who is **not** also
          a judge falls through to ``for_actor`` -- an organizer's subject
          parameter is ignored, which is the organizer role working;
        * a **judge who is also an organizer now falls through too.** It did not
          until FEAT-05 decided F-51, and the decision went the other way from
          the interim code.

        **Why the overlap resolves in the organizer's favour, and it is not
        "widen it to match the comment".** The interim code refused a
        judge-organizer here while ``for_actor`` handed that same user all 126
        reviews -- so the peer-blindness was real for a pure judge and *cosmetic*
        for the one person it most plausibly matters about. Worse, the refusal
        protected nothing: the organizer-scoped ``/api/v1/export.csv`` contains
        every score in the event, so a judge-organizer read all of them anyway by
        a documented route. **A rule that the export already defeats is not a
        security control, it is a sentence in a docstring.**

        The alternative -- narrowing so that organizers cannot read peer scores --
        was the only reading under which the refusal means anything, and it was
        rejected because it costs more than the sentence: it forces
        ``can_read_all_reviews`` to split into "may read all scores" against "may
        staff this event", and it has to restrict the export too, which is the
        route T2-7 scores. Decided at FEAT-05, by the human, in writing. A judge
        who organises is the ordinary case at a hackathon, not a misconfiguration
        -- the premise F-45 and F-51 were both found on -- and the organizer's
        authority is event-wide *by design*: an organizer who cannot read a peer's
        review cannot investigate a conflict of interest.

        The consequence to be honest about: **a judge-organizer is not a peer-
        blind actor, and this accessor is not what makes them one.** They are
        refused the leaderboard *while judging is open* by a different rule
        (FEAT-06), and until that rule exists they can read every score. Stating
        that here is the point of recording F-51 rather than closing it quietly.
        The tests that pin both halves are
        ``tests/test_isolation_invariants.py::TestP2NoCrossEvasion``.
        """
        if (
            actor.is_judge
            and not actor.can_read_all_reviews
            and subject is not None
            and subject.pk != getattr(actor.user, "pk", None)
        ):
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

    # ------------------------------------------------------------- whole-event read

    def for_cross_judge_analysis(self, event_id) -> ReviewQuerySet:
        """EVERY review in an event, for the normalization proof. No actor.

        **This is the one sanctioned whole-event row read, and it is added at
        FEAT-08.** The alternative was an allowlist entry for
        `normalization/loader.py`, and the existing `public_review_counts` comment
        already says why that is the weaker choice: *an allowlist entry exempts a
        whole file, whereas a sanctioned method exempts one method in every file,
        so the rule keeps applying to the rest of the line.*

        **Why the proof needs it, stated plainly, because "it needs everything" is
        the sentence that has produced every scope bug in this project.** A
        variance decomposition measures the *variance between judges*, so reading
        one judge's reviews produces a number and no finding. Scoping the analysis
        to an actor is not a security decision here, it is a category error: there
        is no actor, because the unit of analysis is the panel.

        **Which is exactly why it must be named rather than merely allowed.** A
        whole-event read behind a neutral name is the shape of every future leak;
        behind *this* name it is greppable, and the sentence next to it says what
        it is for. `tests/test_normalization.py` asserts the loader uses this
        accessor, and `tools/check_isolation.py` still fails on every other
        unscoped read in the codebase including in this module.
        """
        return self.filter(event_id=event_id)

    def for_judge_signing(self, event_id, judge) -> ReviewQuerySet:
        """Every review ONE judge wrote in one event, for signing their own record.

        **Narrower than ``for_bulk_transfer`` on purpose, and the distinction is
        the point.** Signing a judge's participation record needs that judge's work
        and nothing else -- not the whole event -- so this takes an explicit judge
        and filters on them.

        It exists because the blast-radius test on ``for_bulk_transfer`` **caught
        the signer using it.** That is the test working: the widest read in the
        codebase was being called from a second module, and the fix that keeps the
        guarantee strong is a narrower accessor rather than a second entry in the
        allowlist. **An allowlist that grows is a rule that stops meaning anything**,
        and a second sanctioned method costs one small method instead.

        Not a request path. Signing is an operator action against a record the
        organizer is attesting to, so there is no request actor -- but unlike
        ``for_bulk_transfer`` the scope is still fully determined by the arguments,
        which is why it can be this narrow.
        """
        return self.filter(event_id=event_id, judge=judge)

    def for_bulk_transfer(self) -> ReviewQuerySet:
        """EVERY review, unfiltered -- the bulk escape hatch, and nothing else.

        **This is the widest read in the codebase and the one that most needs a
        name.** FEAT-07's importer and exporter cannot scope to an actor: an
        organizer restoring a lost database is not one of the 30 judges, and a
        restore that quietly skipped the rows it could not attribute would be a
        tool that reports success and loses data -- the F-61 shape at the largest
        possible scale.

        The reasons it is acceptable, in order of how much they matter:

        1. **No request path can reach it.** It is only called from
           `reviewer/io/bundle.py`, and `tests/test_bulk_round_trip.py` asserts
           that -- so the accessor's blast radius is one module, greppable, and
           pinned by a test rather than by a convention.
        2. **The output leaves the isolation boundary by design.** An archive is
           the organizer's own data being handed back to the organizer; that is
           the feature, not a leak.
        3. **It is not a rendering primitive.** Nothing formats a review with it,
           so it cannot leak into a page by accident the way
           `for_cross_judge_analysis` could.

        **It still requires the operator to be an organizer**, which is enforced
        where the command is, not here. A queryset method has no idea who is
        asking, and pretending otherwise would be a worse failure than the one it
        prevents.
        """
        return self

    # ------------------------------------------------------------- public read

    def public_review_counts(self, event_id, project_ids) -> dict:
        """``{project_id: how many reviews it has}`` -- counts, never rows.

        **This is the gallery's one unscoped read, and it lives here rather than
        in the view for two reasons.**

        First, the isolation lint. ``Review.objects.filter(...)`` in a view is
        JJ01's forbidden form, and the honest responses to that are "write a
        scoped accessor" or "put the module on the allowlist". The first is right
        and the second is a habit. This is a third option that is better than
        both: a method whose *name* says what it exposes. There is no way to
        reach a review row through it, so it is not a leak even though it is not
        scoped -- it is a count, and a count is the public fact the gallery is
        supposed to show.

        Second, and this is the part that matters: a count with no actor on it
        belongs next to the accessor that *does* require one, so a reader
        comparing the two sees the difference rather than inferring it. The
        gallery's card shows "3 reviews" while judging is open, which is
        deliberately a count and never a score.

        ``public_`` is the whole contract. Renaming it to something neutral would
        be a security-relevant change and the lint rule would not notice.
        """
        ids = [str(i) for i in project_ids]
        if not ids:
            return {}
        rows = (
            self.model._default_manager.filter(event_id=event_id, project_id__in=ids)
            .values("project_id")
            .annotate(n=Count("id"))
        )
        return {row["project_id"]: row["n"] for row in rows}

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
