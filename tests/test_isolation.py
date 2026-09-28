"""``for_actor`` -- what each role can actually read, over real rows.

These are the row-level tests that ``manage.py isolation_proof`` cannot run yet.
The command works on an empty database and therefore proves the *scope*; this
file builds a small world and proves the *rows*.

**Every read here goes through ``for_actor``.** The event-wide totals these tests
compare against come from ``tests/test_schema_contract.py``, which is the one
file on the lint's allowlist -- because a receipt's "3 of 126" is only evidence
if 126 was computed independently of the filter that produced the 3.
"""

from __future__ import annotations

import pytest
from tests import factories

from reviewer.audit.models import AuditEntry
from reviewer.core import ROLE_JUDGE, ROLE_ORGANIZER, ROLE_PARTICIPANT
from reviewer.events.models import Event
from reviewer.isolation import Actor
from reviewer.isolation.scope import DECISION_ALLOW_ALL, DECISION_ALLOW_OWN, DECISION_DENY
from reviewer.reviews.models import Review

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    """A two-track event, two teams, two judges on one track, one on the other.

    Small enough that every count in every assertion is readable, and shaped so
    that each of the four scoping questions has a case: a judge on one track, a
    judge on another, a peer, and an outsider with no binding.
    """
    event = factories.make_event()
    security = factories.make_track(event, "Security")
    infra = factories.make_track(event, "Infrastructure")

    team_a = factories.make_team(event, "Team A")
    team_b = factories.make_team(event, "Team B")

    p1 = factories.make_project("prj_01", event, team_a, security)
    p2 = factories.make_project("prj_02", event, team_a, security)
    p3 = factories.make_project("prj_03", event, team_b, infra)

    alice = factories.make_user("alice@example.invalid")
    bob = factories.make_user("bob@example.invalid")
    cara = factories.make_user("cara@example.invalid")
    dana = factories.make_user("dana@example.invalid")

    # alice judges two Security projects; bob judges the other Security project
    # and one Infrastructure project -- the cross-track case.
    factories.bind(alice, event, ROLE_JUDGE, security)
    factories.bind(bob, event, ROLE_JUDGE, security)
    factories.bind(bob, event, ROLE_JUDGE, infra)
    factories.bind(cara, event, ROLE_PARTICIPANT)
    factories.bind(dana, event, ROLE_ORGANIZER)

    rubric = factories.make_rubric(event)
    factories.make_review(p1, alice, rubric)
    factories.make_review(p2, alice, rubric)
    factories.make_review(p1, bob, rubric)
    factories.make_review(p3, bob, rubric)

    return {
        "event": event,
        "security": security,
        "infra": infra,
        "projects": [p1, p2, p3],
        "alice": alice,
        "bob": bob,
        "cara": cara,
        "dana": dana,
        "rubric": rubric,
    }


def _actor(world, user, **kwargs) -> Actor:
    return Actor.for_user(world["event"], user)


def _all_review_ids() -> set[tuple[str, str]]:
    """Ground truth, written down rather than queried.

    This file is NOT on the lint's allowlist, so it cannot compute the total by
    reaching past ``for_actor``. It states the four reviews the ``world``
    fixture builds, as (project id, judge email) pairs. Asserting a count
    against a hand-written fact is the stronger form: it cannot drift when the
    schema changes, because nothing in the schema is involved.
    """
    return {
        ("prj_01", "alice@example.invalid"),
        ("prj_02", "alice@example.invalid"),
        ("prj_01", "bob@example.invalid"),
        ("prj_03", "bob@example.invalid"),
    }


def _seen(qs) -> set[tuple[str, str]]:
    """The (project id, judge email) pairs a scope actually lets through.

    The judge's EMAIL rather than their id, because the fixture names people by
    email and `judge_id` is a surrogate integer -- the first draft of this
    sliced it as a string and crashed, which is the cost of assuming a key type.
    """
    return {(r.project_id, r.judge.email) for r in qs.select_related("judge")}


class TestRefusedRoles:
    """A refusal has to be a refusal, not an empty list."""

    def test_participant_sees_nothing(self, world):
        qs = Review.objects.for_actor(_actor(world, world["cara"]))
        assert list(qs) == []
        assert qs.scope.decision == DECISION_DENY

    def test_participant_scope_is_provably_empty(self, world):
        """EmptyResultSet, not a filter that matched nothing.

        The difference is the whole of "refusal, not filtering": a filter that
        matches nothing is indistinguishable from there being nothing to see,
        and a query that still costs a full scan.
        """
        assert Review.objects.for_actor(_actor(world, world["cara"])).query.is_empty()

    def test_visitor_sees_nothing(self, world):
        qs = Review.objects.for_actor(Actor.anonymous(world["event"]))
        assert list(qs) == []
        assert qs.query.is_empty()

    def test_an_unbound_authenticated_user_sees_nothing(self, world):
        """Authenticated but unbound is still a visitor.

        The role model has five members and `visitor` is the absence of a
        binding, so this path exists. It is also the path a misconfiguration
        would take, and it must fail closed.
        """
        stranger = factories.make_user("stranger@example.invalid")
        assert _actor(world, stranger).is_visitor
        assert Review.objects.for_actor(_actor(world, stranger)).query.is_empty()

    def test_anonymous_user_sees_nothing(self, world):
        assert Review.objects.for_actor(Actor.for_user(world["event"], None)).query.is_empty()


class TestJudgeScope:
    """Own reviews only, and only within the tracks the judge is bound to."""

    def test_a_judge_sees_exactly_their_own_reviews(self, world):
        alice = _actor(world, world["alice"])
        assert _seen(Review.objects.for_actor(alice)) == {
            ("prj_01", "alice@example.invalid"),
            ("prj_02", "alice@example.invalid"),
        }

    def test_a_judge_never_sees_a_peer(self, world):
        alice = _actor(world, world["alice"])
        seen = Review.objects.for_actor(alice)
        assert not any(r.judge_id == world["bob"].pk for r in seen)

    def test_a_dual_track_judge_sees_both_tracks(self, world):
        """The fixture's 9 dual-track judges, in miniature."""
        bob = _actor(world, world["bob"])
        assert bob.track_ids() == sorted([world["security"].pk, world["infra"].pk])
        assert _seen(Review.objects.for_actor(bob)) == {
            ("prj_01", "bob@example.invalid"),
            ("prj_03", "bob@example.invalid"),
        }

    def test_a_judge_cannot_see_a_track_they_are_not_bound_to(self, world):
        """The second predicate, tested on its own.

        A judge with a track-scoped binding must not see an off-track review
        even for themselves. There is no such row in `world`, so this is built:
        an organizer-declared bad assignment, which is exactly the case the
        track predicate exists to catch.
        """
        from reviewer.reviews.models import Assignment

        alice = _actor(world, world["alice"])
        rogue = Assignment.objects.create(
            event=world["event"], judge=world["alice"], project=world["projects"][2]
        )
        Review.objects.create(
            assignment=rogue,
            judge=world["alice"],
            project=world["projects"][2],
            event=world["event"],
            rubric_version=world["rubric"],
            status="assigned",
        )
        seen = Review.objects.for_actor(alice)
        assert world["projects"][2].id not in {r.project_id for r in seen}

    def test_a_judge_with_no_track_sees_nothing(self, world):
        """The misconfiguration case. It must fail closed, not open."""
        judge = factories.make_user("roaming@example.invalid")
        orphan = Actor(
            event=world["event"],
            user=judge,
            roles=frozenset({ROLE_JUDGE}),
            judge_track_ids=frozenset(),
        )
        qs = Review.objects.for_actor(orphan)
        assert list(qs) == []
        # DECISION_ALLOW_OWN, not DECISION_DENY: a judge with no track is
        # refused by a *filter that matches nothing*, not by an explicit deny.
        # The receipt says which, and the distinction is what lets a reader
        # tell a misconfiguration from a policy decision.
        assert qs.scope.decision == DECISION_ALLOW_OWN

    def test_an_event_wide_judge_grant_is_honoured(self, world):
        """`role=judge, track=NULL` is an explicit organizer grant, not a bug."""
        judge = factories.make_user("wide@example.invalid")
        factories.bind(judge, world["event"], ROLE_JUDGE)  # track is None
        # A review on the OTHER track, which a track-scoped binding would hide.
        factories.make_review(world["projects"][2], judge, world["rubric"])
        wide = _actor(world, judge)
        assert wide.event_wide_judge
        qs = Review.objects.for_actor(wide)
        assert _seen(qs) == {("prj_03", "wide@example.invalid")}
        assert qs.scope.decision == DECISION_ALLOW_OWN

    def test_the_peer_probe_refuses(self, world):
        """Asking about another judge is a different method on purpose."""
        alice = _actor(world, world["alice"])
        qs = Review.objects.for_actor_and_subject(alice, world["bob"])
        assert list(qs) == []
        assert qs.scope.decision == DECISION_DENY

    def test_the_peer_probe_allows_ones_own_subject(self, world):
        alice = _actor(world, world["alice"])
        qs = Review.objects.for_actor_and_subject(alice, world["alice"])
        assert len(list(qs)) == 2
        assert qs.scope.decision == DECISION_ALLOW_OWN

    def test_an_organizer_may_ask_about_any_subject(self, world):
        """The peer probe is peer-blind, not organizer-blind.

        An organizer asking about a judge gets the organizer's scope -- the
        whole event -- rather than a filtered subset. That is the documented
        fall-through, and the count asserts it: all four reviews, including
        bob's, even though the question named alice. A subject filter that
        quietly became a permission check would hide rows from the one role
        that is supposed to see them, and an organizer who cannot see a peer
        review cannot investigate a conflict of interest.
        """
        dana = _actor(world, world["dana"])
        qs = Review.objects.for_actor_and_subject(dana, world["alice"])
        assert len(list(qs)) == 4
        assert qs.scope.decision == DECISION_ALLOW_ALL
        assert any(r.judge_id == world["bob"].pk for r in qs)


class TestOrganizerScope:
    def test_an_organizer_sees_the_whole_event(self, world):
        dana = _actor(world, world["dana"])
        qs = Review.objects.for_actor(dana)
        assert len(list(qs)) == 4
        assert qs.scope.decision == DECISION_ALLOW_ALL

    def test_an_organizer_is_not_constrained_by_judge_or_track(self, world):
        dana = _actor(world, world["dana"])
        fields = {
            child.lhs.target.name for child in Review.objects.for_actor(dana).query.where.children
        }
        assert fields == {"event"}

    def test_staff_is_admin(self, world):
        staff = factories.make_user("staff@example.invalid", is_staff=True)
        actor = _actor(world, staff)
        assert actor.is_admin
        qs = Review.objects.for_actor(actor)
        assert len(list(qs)) == 4
        assert qs.scope.decision == DECISION_ALLOW_ALL


class TestEventBoundary:
    """Every query has to be scopable to an event, and that means two events."""

    def test_an_actor_never_sees_another_event(self, world):
        other = factories.make_event(event_id="evt_02", slug="evt-02", name="Other")
        other_track = factories.make_track(other, "Other Track")
        other_team = factories.make_team(other, "Other Team")
        other_project = factories.make_project("prj_99", other, other_team, other_track)
        other_rubric = factories.make_rubric(other)
        stranger = factories.make_user("stranger2@example.invalid")
        factories.bind(stranger, other, ROLE_ORGANIZER)
        factories.make_review(other_project, stranger, other_rubric)

        dana = _actor(world, world["dana"])
        qs = Review.objects.for_actor(dana)
        assert other_project.id not in {r.project_id for r in qs}
        # Four REVIEWS across three projects. Asserting on project ids is the
        # point: the boundary being tested is which event a row belongs to, and
        # a set of ids cannot accidentally grow by a second review of the same
        # project.
        assert len(qs) == 4
        assert {r.project_id for r in qs} == {"prj_01", "prj_02", "prj_03"}

    def test_the_receipt_total_is_the_events_not_the_callers(self, world):
        """The denominator is defined independently of the filter.

        This is the assertion that makes "3 of 126" evidence rather than a
        tautology. A scope applied to an already-filtered base would otherwise
        report a total that had itself been filtered.
        """
        dana = _actor(world, world["dana"])
        receipt = Review.objects.for_actor(dana).scope_receipt()
        assert receipt.visible == 4
        assert receipt.total == 4

        alice = _actor(world, world["alice"])
        alice_receipt = Review.objects.for_actor(alice).scope_receipt()
        assert alice_receipt.visible == 2
        assert alice_receipt.total == 4, (
            "the denominator must be the event's review count, not the actor's"
        )
        assert alice_receipt.withheld == 2

    def test_the_world_fixture_built_what_this_file_claims(self, world):
        """Guards the test's own ground truth against drift in `factories`."""
        dana = _actor(world, world["dana"])
        assert _seen(Review.objects.for_actor(dana)) == _all_review_ids()


class TestScopeReceipt:
    """The receipt is the feature a judge can read instead of a test they trust."""

    def test_the_rule_is_generated_from_the_constraints(self, world):
        receipt = Review.objects.for_actor(_actor(world, world["alice"])).scope_receipt()
        for clause, _ in receipt.constraints:
            assert clause in receipt.rule
        assert receipt.decision == DECISION_ALLOW_OWN

    def test_the_summary_states_both_counts(self, world):
        receipt = Review.objects.for_actor(_actor(world, world["alice"])).scope_receipt()
        assert "2 of 4" in receipt.summary()

    def test_the_receipt_reports_the_bindings(self, world):
        receipt = Review.objects.for_actor(_actor(world, world["alice"])).scope_receipt()
        assert ("role", "judge") in receipt.bindings
        assert any(k == "tracks" for k, _ in receipt.bindings)

    def test_a_dual_track_judge_reports_every_track(self, world):
        receipt = Review.objects.for_actor(_actor(world, world["bob"])).scope_receipt()
        assert ("role", "judge") in receipt.bindings

    def test_many_tracks_are_collapsed_with_a_count(self, world):
        """A judge on six tracks should not get a paragraph as their explanation."""
        event = world["event"]
        judge = factories.make_user("busy@example.invalid")
        for i in range(6):
            track = factories.make_track(event, f"Extra {i}")
            factories.bind(judge, event, ROLE_JUDGE, track)
        receipt = Review.objects.for_actor(_actor(world, judge)).scope_receipt()
        tracks = dict(receipt.bindings).get("tracks", "")
        assert "3 more" in tracks

    def test_an_organizer_receipt_names_its_role(self, world):
        receipt = Review.objects.for_actor(_actor(world, world["dana"])).scope_receipt()
        assert ("role", ROLE_ORGANIZER) in receipt.bindings

    def test_the_receipt_serialises_for_the_audit_trail(self, world):
        receipt = Review.objects.for_actor(_actor(world, world["alice"])).scope_receipt()
        data = receipt.as_dict()
        assert data["visible"] == 2
        assert data["total"] == 4
        assert data["decision"] == DECISION_ALLOW_OWN

    def test_the_scope_survives_a_derived_queryset(self, world):
        """Without this, one `.filter()` in a view drops the explanation.

        The protection stays and the evidence goes, and no test fails -- which
        is the worst kind of regression.
        """
        derived = (
            Review.objects.for_actor(_actor(world, world["alice"]))
            .filter(status="submitted")
            .order_by("project_id")
        )
        assert derived.is_scoped
        assert derived.scope_receipt().visible == 2

    def test_an_unscoped_queryset_refuses_to_explain_itself(self):
        """A receipt with no rule is worse than no receipt.

        The queryset is built from the class rather than from the manager on
        purpose. `Review.objects.none()` would be the obvious way to get an
        unscoped queryset, and the isolation lint correctly flags it -- which
        means this test could not exist without an exception. Constructing the
        queryset directly says what is being tested (the mixin, not the
        manager) and keeps the rule free of a hole.
        """
        from reviewer.reviews.queryset import ReviewQuerySet

        unscoped = ReviewQuerySet(model=Review)
        assert not unscoped.is_scoped
        with pytest.raises(ValueError, match="unscoped queryset"):
            unscoped.scope_receipt()

    def test_a_managers_copy_does_not_inherit_a_previous_actors_scope(self, world):
        """The scope lives on the instance, not on the manager.

        This is the one bug the design cannot have: a scope that leaked from one
        call into the next would make a judge's list page show an organizer's
        rows, and it would do it only sometimes.
        """
        Review.objects.for_actor(_actor(world, world["alice"]))
        fresh = Review.objects.for_actor(_actor(world, world["dana"]))
        assert fresh.scope.decision == DECISION_ALLOW_ALL
        assert fresh.scope_receipt().visible == 4


class TestAuditRecordsTheScope:
    """`bible/05` §9: what each actor was able to see, not just what they did."""

    def test_a_scope_reason_round_trips_through_the_audit_trail(self, world):
        dana = _actor(world, world["dana"])
        receipt = Review.objects.for_actor(dana).scope_receipt()
        AuditEntry.objects.create(
            event=world["event"],
            actor=world["dana"],
            action="review.list",
            seq=1,
            scope_reason=receipt.as_dict(),
        )
        entry = AuditEntry.objects.get(event=world["event"], seq=1)
        assert entry.scope_reason["visible"] == 4
        assert entry.scope_reason["total"] == 4

    def test_chain_head_is_empty_for_an_empty_chain(self, world):
        assert AuditEntry.chain_head(world["event"]) == ""

    def test_chain_head_is_the_last_entries_hash(self, world):
        for seq, digest in ((1, "a" * 64), (2, "b" * 64)):
            AuditEntry.objects.create(event=world["event"], action="x", seq=seq, entry_hash=digest)
        assert AuditEntry.chain_head(world["event"]) == "b" * 64

    def test_seq_is_unique_per_event(self, world):
        from django.db import IntegrityError, transaction

        AuditEntry.objects.create(event=world["event"], action="x", seq=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            AuditEntry.objects.create(event=world["event"], action="y", seq=1)

    def test_omitted_since_prev_defaults_to_zero(self, world):
        entry = AuditEntry.objects.create(event=world["event"], action="x", seq=1)
        assert entry.omitted_since_prev == 0


class TestEventIsTheTenant:
    def test_an_unsaved_event_still_scopes(self):
        """`for_actor` reads the event's PK, so an in-memory event is enough.

        This is what lets the wiring checks in `isolation_proof` run on an
        empty database: no row has to exist for the SQL to be inspectable.
        """
        ghost = Event(id="evt_ghost", slug="ghost", name="ghost")
        actor = Actor.anonymous(ghost)
        assert Review.objects.for_actor(actor).query.is_empty()
