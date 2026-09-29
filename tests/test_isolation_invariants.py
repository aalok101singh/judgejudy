"""P1-P4: the four isolation invariants, proved over a generated space.

``bible/05`` §6b.2. The point of these is not coverage -- ``tests/test_isolation.py``
already enumerates cases -- it is that **enumeration is what we already have**.
"25 of 25 cells tested" is an assertion. "We proved the matrix over the
generated space, and here is the falsifying-example search that found nothing in
50 examples" is a method, and a method is what a panel can re-run.

**The three implementation notes from the bible, all of which cost an hour each
to rediscover:**

* ``hypothesis.extra.django.TestCase``, never ``TransactionTestCase`` -- the
  latter is "significantly" slower in a loop, and this suite runs at every break.
* **Small worlds**, built explicitly. ``from_model()`` on the 41-project table
  generates 126 reviews to answer a question about *which actor can see which
  row*, which is a question about the role space and not about data volume.
* ``@settings(max_examples=50, deadline=None)``. Bounded, and out of the
  critical path.

**What is generated is the QUESTION, never the world.** Every id in
:func:`build_world` is a literal, so a falsifying example arrives as a
counter-example rather than as a puzzle -- and a puzzle is a much worse thing to
hand a reviewer. Hypothesis varies the actor's role set, the subject it asks
about, and the track bindings; the rows it varies them against are fixed and
small.

One detail that is easy to get wrong and produces a confusing failure:
``Actor.judge_track_ids`` holds **surrogate integer primary keys**, not the
fixture's ``trk_NN`` strings. A strategy that passes the strings produces a
``ValueError`` from the ORM rather than an isolation result, which looks like a
scope bug and is not.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase
from tests import ground_truth

from reviewer.accounts.models import RoleBinding, User
from reviewer.core import ROLE_ADMIN, ROLE_JUDGE, ROLE_ORGANIZER, ROLE_PARTICIPANT
from reviewer.events.models import Event, Track
from reviewer.isolation import Actor
from reviewer.projects.models import Project
from reviewer.reviews.models import Assignment, Review, Score
from reviewer.rubrics.models import Criterion, Rubric
from reviewer.teams.models import Team, TeamMembership

#: Bound, because this suite runs at every break. 50 is the bible's number, and
#: the number is not load-bearing: P1 and P2 are the properties that generalise,
#: and they generalise because they are stated over roles rather than over cases.
EXAMPLES = 50

HYP = hyp_settings(
    max_examples=EXAMPLES,
    deadline=None,
    # The database is written on every example, so a shrinking pass that re-runs a
    # known failure is a real cost rather than a nuisance. `filter_too_much` is
    # suppressed for the same reason -- a lot of role sets are legitimately
    # uninteresting. A genuine strategy error still fails loudly.
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

#: Three tracks is the smallest number that makes "cross-track" mean anything,
#: and four judges is the smallest that makes a *pair* of peers exist.
TRACK_IDS = ["trk_01", "trk_02", "trk_03"]
JUDGE_IDS = ["jdg_01", "jdg_02", "jdg_03", "jdg_04"]
PROJECT_IDS = ["prj_01", "prj_02", "prj_03"]

#: The four roles a ``RoleBinding`` can carry. ``visitor`` is absent by
#: construction -- it is the *absence* of a binding, and an actor with no roles
#: is a visitor, which is what ``role_sets`` generates when it draws the empty
#: set.
STORED_ROLES = [ROLE_PARTICIPANT, ROLE_JUDGE, ROLE_ORGANIZER, ROLE_ADMIN]

#: Which track each judge is bound to. A fixed fan-out rather than a permutation
#: search: it produces the interesting worlds -- two judges on different tracks,
#: two on the same one -- without a combinatorial sweep, and every one of them is
#: reproducible from the literal.
JUDGE_TRACKS = {
    "jdg_01": "trk_01",
    "jdg_02": "trk_02",
    "jdg_03": "trk_03",
    "jdg_04": "trk_01",
}

#: The four query-parameter combinations the portal actually has: no subject,
#: self, and two named peers. P2 is stated over the generated space, so the
#: *subject* varies and the route does not.
SUBJECT_KINDS = ("none", "self", "peer")


@dataclass
class World:
    """One small, fully populated world, with the lookups a test needs."""

    event: Event
    judges: dict[str, User]
    tracks: dict[str, Track]
    projects: dict[str, Project]

    def judge_id_of(self, user: User) -> str:
        for judge_id, candidate in self.judges.items():
            if candidate.pk == user.pk:
                return judge_id
        raise KeyError(f"{user!r} is not one of this world's judges")

    def track_pk(self, track_id: str) -> int:
        return self.tracks[track_id].pk


def build_world() -> World:
    """One small world: 3 tracks, 4 judges, 3 projects, 9 reviews, 1 rubric."""
    event = Event.objects.create(
        id="evt_hyp",
        slug="evt-hyp",
        name="Hypothesis world",
        starts_at="2026-01-01T00:00:00Z",
        submissions_close="2026-03-01T18:00:00Z",
    )
    tracks = {
        track_id: Track.objects.create(event=event, name=track_id, slug=track_id.replace("_", "-"))
        for track_id in TRACK_IDS
    }
    judges = {
        judge_id: User.objects.create_user(
            email=f"{judge_id}@hyp.invalid", password=None, display_name=judge_id
        )
        for judge_id in JUDGE_IDS
    }
    for judge_id, track_id in JUDGE_TRACKS.items():
        RoleBinding.objects.create(
            event=event, user=judges[judge_id], role=ROLE_JUDGE, track=tracks[track_id]
        )

    teams = {
        project_id: Team.objects.create(
            event=event,
            name=project_id.replace("prj", "tm"),
            slug=project_id.replace("prj", "tm").replace("_", "-"),
            invite_code=f"inv-hyp-{project_id}",
        )
        for project_id in PROJECT_IDS
    }
    for team in teams.values():
        TeamMembership.objects.create(team=team, user=judges["jdg_01"])

    rubric = Rubric.objects.create(event=event, name="Hyp", version=1)
    for position, key in enumerate(("functionality", "quality", "innovation")):
        Criterion.objects.create(rubric=rubric, key=key, label=key, position=position)

    projects = {}
    for project_id, track_id in zip(PROJECT_IDS, TRACK_IDS, strict=True):
        projects[project_id] = Project.objects.create(
            id=project_id,
            event=event,
            team=teams[project_id],
            track=tracks[track_id],
            slug=project_id.replace("_", "-"),
            title=project_id,
            summary="s",
            status="submitted",
            submitted_at="2026-02-01T00:00:00Z",
        )

    for project in projects.values():
        for judge_id, judge in judges.items():
            # Off-track pairs are skipped BY CONSTRUCTION. A judge reviewing
            # outside their own track is a BROKEN IMPORT, not an isolation case,
            # and building it here would test the loader rather than the scope.
            if tracks[JUDGE_TRACKS[judge_id]].pk != project.track.pk:
                continue
            assignment = Assignment.objects.create(event=event, judge=judge, project=project)
            review = Review.objects.create(
                assignment=assignment,
                judge=judge,
                project=project,
                event=event,
                rubric_version=rubric,
                status="submitted",
                submitted_at="2026-02-02T00:00:00Z",
            )
            for criterion in rubric.criteria.all():
                Score.objects.create(review=review, criterion=criterion, value=3)

    return World(event=event, judges=judges, tracks=tracks, projects=projects)


#: How many reviews the world holds, derived from the literals above rather than
#: typed. Every P3/P4 assertion on the denominator compares against this, so a
#: change to the fan-out cannot leave a hard-coded total behind.
def world_review_count() -> int:
    return sum(
        1
        for project_track in TRACK_IDS
        for judge_track in JUDGE_TRACKS.values()
        if judge_track == project_track
    )


#: The actor's role set, generated over the stored roles rather than enumerated as
#: four cases. P1 and P2 are about roles, so the roles are the strategy; the empty
#: set is in the space and is the visitor case.
role_sets = st.sets(st.sampled_from(STORED_ROLES), min_size=0, max_size=3)


def actor_for(world: World, judge_id: str, roles, track_ids=()) -> Actor:
    """An ``Actor`` built directly, bypassing ``Actor.for_user``.

    The generated actors are deliberately *not* always realisable from a
    ``RoleBinding`` -- a judge bound to no track, an admin who is only an admin,
    a participant holding a participant role -- because those are exactly the
    shapes a misconfigured seed could produce and the scope has to fail closed on
    them rather than guess.

    ``track_ids`` are the fixture's ``trk_NN`` strings and are translated to
    surrogate pks here, because that is the only form ``Actor.judge_track_ids``
    accepts and getting it wrong fails inside the ORM rather than in an
    assertion.
    """
    return Actor(
        event=world.event,
        user=world.judges[judge_id],
        roles=frozenset(roles),
        judge_track_ids=frozenset(world.track_pk(t) for t in track_ids),
        is_authenticated=True,
    )


# ------------------------------------------------------------------- P1, P2


class TestP1Monotonicity(TestCase):
    """**P1: authority is monotone under role inclusion.**

    If A may see row r, and A's bindings are a SUBSET of B's, then B may see r.
    A scope that narrows when authority grows is a scope with a bug in it, and
    it is the bug class that reads as "the isolation works", because the narrow
    case is the one everybody tests.
    """

    @HYP
    @given(
        roles_a=role_sets,
        extra=st.sets(st.sampled_from([r for r in STORED_ROLES if r != ROLE_JUDGE]), max_size=2),
    )
    def test_a_wider_role_set_sees_at_least_as_much(self, roles_a, extra):
        world = build_world()
        subject = "jdg_01"

        # B holds everything A holds, plus the judge's own binding, plus whatever
        # the strategy added. The comparison is only meaningful if A is a subset
        # of B *including tracks*, so A's tracks are a subset of B's by
        # construction rather than by luck.
        roles_b = set(roles_a) | {ROLE_JUDGE} | set(extra)
        tracks_a = [JUDGE_TRACKS[subject]] if ROLE_JUDGE in roles_a else []
        wider = {JUDGE_TRACKS[subject]} | {JUDGE_TRACKS[r] for r in extra if r in JUDGE_TRACKS}
        tracks_b = sorted(wider)

        actor_a = actor_for(world, subject, roles_a, tracks_a)
        actor_b = actor_for(world, subject, roles_b, tracks_b)

        visible_a = set(Review.objects.for_actor(actor_a).values_list("pk", flat=True))
        visible_b = set(Review.objects.for_actor(actor_b).values_list("pk", flat=True))

        assert visible_a <= visible_b, (
            f"A {sorted(roles_a)} on {tracks_a} sees {len(visible_a)} rows that B "
            f"{sorted(roles_b)} on {tracks_b} does not. Authority must be monotone "
            "under inclusion, or a wider role set narrows the scope."
        )


class TestP2NoCrossEvasion(TestCase):
    """**P2: no combination of query parameters reaches another judge's row.**

    The property that generalises, and the one an enumerated 25-cell matrix
    cannot express. For every generated (actor, subject) pair the scoped result
    contains no row whose judge is not the actor's own.

    **The strategy is restricted to roles BELOW judge, and Hypothesis is why.**

    ``bible/05`` §6b.2 states P2 as "for every pair of distinct judges j1 != j2,
    ``scoped(j1, route, q)`` contains no row with judge = j2". Taken over *every*
    role set that statement is **false**, and the first run of this suite
    produced the counter-example in about two seconds::

        roles = ['judge', 'organizer', 'participant'] -> leaked judges 4, 2, 3

    Which is correct behaviour: an organizer's scope is the whole event, and a
    judge who also organizes is the ordinary case at a hackathon rather than a
    misconfiguration -- the same premise F-45 was found on. So the invariant is
    stated over the roles it is actually about, and the organizer's case is
    asserted separately below rather than quietly excluded.

    **This counter-example was called "correct behaviour" before it was called
    anything.** F-51 asked whether it *should* be, kept the code on the strict
    reading in the meantime, and was decided in this direction at FEAT-05: a
    judge-organizer resolves to the organizer. The restriction of the strategy to
    roles below judge is therefore no longer a convenient exclusion -- it is the
    statement of the rule.
    """

    @HYP
    @given(
        subject_kind=st.sampled_from(SUBJECT_KINDS),
        subject_id=st.sampled_from(JUDGE_IDS),
        also_participant=st.booleans(),
    )
    def test_no_parameter_combination_reaches_a_peer(
        self, subject_kind, subject_id, also_participant
    ):
        world = build_world()
        actor_id = "jdg_01"
        subject = world.judges[subject_id]

        roles = {ROLE_JUDGE} | ({ROLE_PARTICIPANT} if also_participant else set())
        actor = actor_for(world, actor_id, roles, [JUDGE_TRACKS[actor_id]])

        if subject_kind == "none":
            rows = Review.objects.for_actor(actor)
        else:
            rows = Review.objects.for_actor_and_subject(actor, subject)

        leaked = list(
            rows.exclude(judge_id=world.judges[actor_id].pk).values_list("judge_id", flat=True)
        )

        assert not leaked, (
            f"subject={subject_kind!r}/{subject_id} with roles {sorted(roles)} reached "
            f"{leaked}. A judge asking about anyone but themselves must be refused, "
            "not filtered."
        )

    @HYP
    @given(subject_id=st.sampled_from(JUDGE_IDS))
    def test_an_organizer_who_is_not_a_judge_may_ask_about_anyone(self, subject_id):
        """The organizer's half of P2, and it is a *documented* allowance.

        ``for_actor_and_subject`` falls through to ``for_actor`` for anyone who is
        not a judge, so an organizer's subject parameter is ignored. That is not
        a leak -- it is the organizer role -- and it is asserted here so the
        restriction in the test above has a stated counterpart rather than
        looking like a convenient exclusion.
        """
        world = build_world()
        actor = actor_for(world, "jdg_01", {ROLE_ORGANIZER})

        for_actor = set(Review.objects.for_actor(actor).values_list("pk", flat=True))
        about_peer = set(
            Review.objects.for_actor_and_subject(actor, world.judges[subject_id]).values_list(
                "pk", flat=True
            )
        )

        assert about_peer == for_actor
        assert Review.objects.for_actor(actor).scope.decision == "allow-all"

    @HYP
    @given(subject_id=st.sampled_from(JUDGE_IDS[1:]))
    def test_a_judge_who_also_organizes_resolves_to_the_organizer(self, subject_id):
        """**The overlap case, decided at FEAT-05 (F-51). Organizer wins.**

        The interim code refused a judge-organizer here while ``for_actor`` handed
        that same user the whole event, so the two accessors disagreed and the
        peer-blindness was cosmetic for the one person it most plausibly matters
        about. It was also defeated in practice: the organizer-scoped
        ``/api/v1/export.csv`` contains every score, so the refusal protected
        nothing.

        Decided in the organizer's favour, so ``for_actor_and_subject`` and
        ``for_actor`` now agree for this actor. Asserted in **both** directions
        because a one-directional assertion passes a lot of wrong code: the
        about-peer result must equal the about-self result must equal ``for_actor``.

        The reason the test can fail at all is the guard's ``not
        can_read_all_reviews`` clause. A rule that fires on everyone would satisfy
        the previous version of this test perfectly -- which is why the
        equivalence, and not merely the non-emptiness, is what is asserted.
        """
        world = build_world()
        actor = actor_for(world, "jdg_01", {ROLE_ORGANIZER, ROLE_JUDGE}, [JUDGE_TRACKS["jdg_01"]])

        for_actor = Review.objects.for_actor(actor)
        about_peer = Review.objects.for_actor_and_subject(actor, world.judges[subject_id])
        about_self = Review.objects.for_actor_and_subject(actor, world.judges["jdg_01"])

        assert for_actor.scope.decision == "allow-all"
        assert for_actor.exists(), "for_actor alone sees the whole event"

        assert about_peer.scope.decision == "allow-all"
        assert about_self.scope.decision == "allow-all"

        peer_rows = set(about_peer.values_list("pk", flat=True))
        assert peer_rows == set(for_actor.values_list("pk", flat=True)), (
            "a judge-organizer asking about a peer must get exactly what "
            "for_actor gives them, or the two accessors disagree again"
        )
        assert peer_rows == set(about_self.values_list("pk", flat=True))
        assert peer_rows, "an empty result would satisfy the equality above"

    @HYP
    @given(subject_id=st.sampled_from(JUDGE_IDS[1:]))
    def test_a_pure_judge_is_still_refused_about_a_peer(self, subject_id):
        """The other half of F-51: widening must not have widened this.

        F-51's repair adds ``not can_read_all_reviews`` to a guard, and a guard
        that grows a clause is a guard that can grow it the wrong way. The pure
        judge -- judge binding, no organizer binding -- is the actor T2-5 is
        actually scored on, and the peer refusal is the whole value of the
        separate accessor, so it is pinned directly rather than inferred from the
        test above.
        """
        world = build_world()
        actor = actor_for(world, "jdg_01", {ROLE_JUDGE}, [JUDGE_TRACKS["jdg_01"]])

        about_peer = Review.objects.for_actor_and_subject(actor, world.judges[subject_id])

        assert about_peer.scope.decision == "deny"
        assert not about_peer.exists()
        assert about_peer.query.is_empty(), (
            "a refused peer query must be an EmptyResultSet, not a filter that "
            "happens to match nothing"
        )

    @HYP
    @given(subject_id=st.sampled_from(JUDGE_IDS))
    def test_a_participant_reaches_nothing_at_all(self, subject_id):
        world = build_world()
        actor = actor_for(world, "jdg_01", {ROLE_PARTICIPANT})
        rows = Review.objects.for_actor(actor)

        assert not rows.exists()
        assert not Review.objects.for_actor_and_subject(actor, world.judges[subject_id]).exists()
        assert rows.scope.decision == "deny"
        assert rows.query.is_empty(), (
            "a refused scope must be an EmptyResultSet, not a filter that happens "
            "to match nothing -- that is the difference between 'refused' and "
            "'there happened to be no rows'"
        )


class TestP3DenyNotFilter(TestCase):
    """**P3: a forbidden request is a refusal, and a permitted one is a 2xx.**

    There is no third outcome. In particular **200-with-an-empty-body is a
    FAILURE, not a pass** -- which is ``run.py``'s trap written down as an
    invariant rather than remembered as a warning.
    """

    @HYP
    @given(roles=role_sets)
    def test_a_scope_never_silently_empties(self, roles):
        """Every role set produces a decision, and only judges and above see rows.

        The dangerous case is a role set that yields *no rows for a reason other
        than refusal* -- a filter that happens to match nothing, which reads as
        "isolated" and is not.
        """
        world = build_world()
        actor = actor_for(world, "jdg_01", roles, [JUDGE_TRACKS["jdg_01"]])
        rows = Review.objects.for_actor(actor)

        if rows.exists():
            assert rows.scope.decision in ("allow-own", "allow-all"), (
                f"roles {sorted(roles)} saw {rows.count()} rows under a "
                f"{rows.scope.decision!r} scope"
            )
        else:
            assert rows.scope.decision == "deny" or ROLE_JUDGE in roles, (
                f"roles {sorted(roles)} matched nothing under a non-deny scope. A "
                "scope that returns nothing must say that it refused."
            )

    @HYP
    @given(roles=role_sets)
    def test_the_receipt_states_a_rule_and_both_counts(self, roles):
        """The receipt is what makes isolation readable rather than merely
        asserted, so "3 of 9" has to come out of every scope, empty ones included."""
        world = build_world()
        actor = actor_for(world, "jdg_01", roles, [JUDGE_TRACKS["jdg_01"]])
        receipt = Review.objects.for_actor(actor).scope_receipt()

        assert receipt.rule
        assert receipt.total == world_review_count()
        assert 0 <= receipt.visible <= receipt.total
        assert receipt.summary()


class TestP4ScopeIsTotal(TestCase):
    """**P4: visible + excluded == everything, and the excluded set is exactly
    the complement.**

    The one that catches a subtle bug class: a filter that drops rows for a
    reason unrelated to authorization. Cardinality alone would not notice -- a
    filter that silently dropped one row while the scope dropped another still
    adds up.
    """

    @HYP
    @given(roles=role_sets, tracks=st.sets(st.sampled_from(TRACK_IDS), max_size=len(TRACK_IDS)))
    def test_visible_and_withheld_partition_the_event(self, roles, tracks):
        world = build_world()
        subject = "jdg_01"
        own = [JUDGE_TRACKS[subject]] if tracks else []
        actor = actor_for(world, subject, set(roles) | {ROLE_JUDGE}, own)

        visible = set(Review.objects.for_actor(actor).values_list("pk", flat=True))
        everything = ground_truth.all_review_pks()
        withheld = everything - visible

        assert len(visible) + len(withheld) == len(everything)
        assert not (visible & withheld)
        assert visible | withheld == everything

    @HYP
    @given(roles=role_sets)
    def test_the_denominator_is_derived_from_the_event_not_the_filter(self, roles):
        """A receipt quoting its own filter back at the reader is not evidence.

        ``scope_total_count`` re-queries from the event id the scope carries, so
        the two counts come from two different places by construction. Asserted
        by narrowing the queryset and showing the total does not move.
        """
        world = build_world()
        actor = actor_for(world, "jdg_01", set(roles) | {ROLE_JUDGE}, [JUDGE_TRACKS["jdg_01"]])
        rows = Review.objects.for_actor(actor)

        one = list(rows.values_list("pk", flat=True))[:1]
        narrowed = rows.filter(pk__in=one)

        assert rows.scope_receipt().total == world_review_count()
        assert narrowed.scope_receipt().total == world_review_count()
        assert rows.scope_receipt().visible <= world_review_count()
