"""The assignment engine, against the organizers' data rather than ours.

This is the first feature since FEAT-03 whose subject matter is the published
fixture, and FEAT-03's rate was three P1s in one feature. The prior it earns is
carried here as a posture: **every expected number is re-derived from
``fixtures.json`` inside this module**, so a test fails because the engine and the
data disagree rather than because two transcriptions of the same figure drifted
apart. Where a figure appears in ``bible/06`` it is quoted in the test that
*contradicts* it, if it turns out to be wrong -- which it is, twice (F-61, F-62).

**The three acceptance clauses, in the order ``build-plan.md`` states them:**

1. a feasible instance assigns,
2. the capacity-5 instance reports infeasible with a named min-cut,
3. the seeded tiebreak reproduces byte-for-byte.

**And then the part that makes those three worth something:** four tests that
deliberately disable one layer each -- the cost function, the capacity search,
the jitter, the min-cut reading -- and assert the result *changes*. A test that
cannot fail is worse than no test, and FEAT-04's engine has four separate places
where a plausible-looking simplification would return a working, wrong answer.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from reviewer.assignment import graph as graph_module
from reviewer.assignment import planner as planner_module
from reviewer.assignment.flow import FlowNetwork
from reviewer.importer import loader as loader_module

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO / "fixtures.json"

#: `bible/06` §2.1a: the capacity at which the two zero-slack tracks become
#: provably impossible, and §2.3's certificate is measured at. This one number
#: is a *decision* recorded in the bible and it is the acceptance line's own
#: parameter, so it is named here rather than derived -- but everything the
#: certificate then claims about it is derived.
INFEASIBLE_CAPACITY = 5

#: The tracks the bible names as zero-slack. Quoted because they are the
#: *expectation*; the assertion below is that the engine independently finds
#: exactly these and no others.
ZERO_SLACK_TRACKS = ("trk_01", "trk_08")


@pytest.fixture(scope="module")
def raw_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture):
    loader_module.load(raw_fixture)


@pytest.fixture
def event(loaded):
    from reviewer.events.models import Event

    return Event.objects.get(pk="evt_01")


@pytest.fixture
def graph(event):
    return graph_module.build_graph(event, respect_in_flight=False)


@pytest.fixture
def plan(event):
    """The shipped plan: no organizer cap, so the search runs."""
    return _plan(event)


# ------------------------------------------------------- derived expectations


def expected_demand(raw_fixture: dict) -> int:
    """Total assignments to hit every track's target, derived from the fixture.

    The target is the event's ``reviews_per_project`` (3) and nothing in the
    fixture overrides it per track, so demand is ``3 x 41 = 123``. Computed from
    the file rather than written down, because a written-down 123 would pass even
    if the engine were asked to plan a different event.
    """
    projects = raw_fixture["projects"]
    return len(projects) * _event_target(raw_fixture)


def _event_target(raw_fixture: dict) -> int:
    """The review target, derived from the fixture's own MODE.

    **The mode, not the total, and not a constant.** ``bible/06`` §2.1 is
    emphatic that the totals do not identify the target (126 existing reviews vs
    123 at a target of 3 -- they do not agree) and that the evidence is that 26
    of 41 projects have exactly 3 reviews. The census module already computes
    that, so the expectation is read from the data rather than typed.
    """
    from reviewer.importer import census as census_module

    return census_module.census(raw_fixture).modal_reviews_per_project


def expected_edge_count(raw_fixture: dict) -> int:
    """Eligible judge-project pairs, derived independently of the engine.

    **Deliberately a second implementation.** ``build_graph`` reads the database
    with five exclusion rules; this walks ``fixtures.json`` with one of them (the
    submitting-team rule) and gets to the same number. If they agree, the engine
    read the panel correctly; if they disagree, one of them is wrong and the
    disagreement is a finding rather than a silent wrong answer.

    ``bible/06`` §2.2 quotes 77 for this figure. **That is wrong** -- see F-62 --
    and the assertion below is the one that survives.
    """
    judges = raw_fixture["judges"]
    teams = {t["id"]: set(t.get("members") or []) for t in raw_fixture["teams"]}
    judge_emails = {j["email"]: set(j.get("tracks") or []) for j in judges}

    total = 0
    for project in raw_fixture["projects"]:
        track = project["track"]
        team_members = teams.get(project["team"], set())
        for email, tracks in judge_emails.items():
            if track not in tracks or email in team_members:
                continue
            total += 1
    return total


def expected_track_demand(raw_fixture: dict) -> dict[str, int]:
    per_track: dict[str, int] = {}
    target = _event_target(raw_fixture)
    for project in raw_fixture["projects"]:
        per_track[project["track"]] = per_track.get(project["track"], 0) + target
    return per_track


# ------------------------------------------------------- 1. a feasible instance


class TestFeasibleInstance:
    def test_the_search_finds_the_tightest_capacity_not_a_guessed_one(self, plan, graph):
        """Acceptance clause 1, and the reason the search exists.

        **The number asserted is the shape of the answer, not a value.** The
        engine must find the *smallest* capacity that delivers full coverage, and
        that must be lower than the largest it would have accepted. A planner
        that simply used the largest capacity tried would pass a test asserting
        "the plan is feasible" and fail this one, which is the point: feasibility
        alone is a much weaker claim than "feasible, and nobody is asked to do
        more than they have to."
        """
        assert plan.feasible, "the shipped panel must reach full coverage"
        assert plan.curve, "the search must record the curve it swept"
        # Full coverage appears at exactly one capacity in the swept range, and
        # that one is the answer.
        full = [cap for cap, covered in plan.curve if covered == plan.demand]
        assert full == [plan.capacity], (
            f"coverage appears at more than one capacity: {full} -- the search "
            f"is not returning the tightest bound"
        )
        # And it is genuinely tight: the step below it fell short.
        below = [covered for cap, covered in plan.curve if cap < plan.capacity]
        assert below, "the search started already at full coverage; it proved nothing"
        assert max(below) < plan.demand, (
            "a smaller capacity also achieved full coverage, so the reported "
            "capacity is not the tightest"
        )

    def test_every_project_reaches_its_target_exactly(self, plan, graph):
        """Coverage is not "somewhere near the target"; it is the target."""
        by_project: dict[str, int] = {}
        for assignment in plan.assignments:
            by_project[assignment.project_id] = by_project.get(assignment.project_id, 0) + 1
        targets = {p.id: p.target for p in graph.projects}
        wrong = {
            pid: (count, targets[pid]) for pid, count in by_project.items() if count != targets[pid]
        }
        assert not wrong, f"projects not at their target: {wrong}"
        assert set(by_project) == set(targets), "some project got nobody at all"

    def test_no_judge_exceeds_the_capacity_the_search_found(self, plan):
        assert plan.max_load <= plan.capacity

    def test_the_total_matches_the_derived_demand(self, plan, raw_fixture):
        assert plan.demand == expected_demand(raw_fixture)
        assert len(plan.assignments) == plan.demand

    def test_the_graph_has_the_derived_edge_count(self, graph, raw_fixture):
        """The assertion `bible/06` §2.2 asks for, against a derived number.

        **This is where the bible is wrong.** It says 77 judge-project edges; the
        derived count is ``expected_edge_count`` and the engine agrees with it.
        77 is not reachable by any reading of the graph -- the per-track table in
        §2.1a of the same document implies 214 before exclusions. F-62 records it.
        """
        assert graph.edge_count == expected_edge_count(raw_fixture), (
            f"engine found {graph.edge_count} eligible pairs, the fixture implies "
            f"{expected_edge_count(raw_fixture)} -- one of them is reading the panel wrong"
        )

    def test_the_node_count_is_source_plus_sink_plus_the_entities(self, graph):
        assert graph.node_count == 2 + len(graph.tracks) + len(graph.projects) + len(graph.judges)

    def test_per_track_demand_uses_each_track_s_own_target(self, graph, raw_fixture):
        derived = expected_track_demand(raw_fixture)
        for track in graph.tracks:
            assert graph.demand_for(track) == derived[track.source_key], (
                f"{track.slug}: demand {graph.demand_for(track)} != "
            )

    def test_every_assignment_is_an_eligible_pair(self, plan, graph):
        """The plan may not invent a pair the eligibility rules forbid."""
        eligible = set(graph.pairs)
        for assignment in plan.assignments:
            key = (assignment.judge_user_id, assignment.project_id)
            assert key in eligible, f"assigned an ineligible pair: {key}"

    def test_no_judge_reviews_a_project_they_submitted(self, plan):
        """The one exclusion with a correctness consequence rather than a fairness one."""
        from reviewer.projects.models import Project
        from reviewer.teams.models import TeamMembership

        members = set(TeamMembership.objects.values_list("user_id", "team_id"))
        team_of = {p.id: p.team_id for p in Project.objects.all()}
        for assignment in plan.assignments:
            for user_id, team_id in members:
                if user_id == assignment.judge_user_id and team_id == team_of.get(
                    assignment.project_id
                ):
                    pytest.fail(
                        f"{assignment.judge_email} reviewed a project their own team submitted"
                    )


# --------------------------------------------- 2. infeasible, with a named cut


class TestInfeasibleInstance:
    @pytest.fixture
    def tight(self, event):
        return _plan(event, capacity=INFEASIBLE_CAPACITY)

    def test_it_reports_infeasible_rather_than_returning_a_short_plan(self, tight, event):
        assert not tight.feasible
        assert tight.assignments == [], (
            "an infeasible instance must not hand back a partial plan as if it "
            "were the answer -- that is the 'feasible and provably impossible are "
            "different answers' rule"
        )

    def test_the_named_tracks_are_exactly_the_zero_slack_ones(self, tight):
        found = {d.track_key for d in tight.deficiencies}
        assert found == set(ZERO_SLACK_TRACKS), (
            f"certificate names {sorted(found)}, expected {sorted(ZERO_SLACK_TRACKS)}"
        )

    def test_the_deficit_is_named_per_track(self, tight):
        """Not "6 short somewhere" -- per track, with the arithmetic."""
        for deficiency in tight.deficiencies:
            track = next(t for t in ZERO_SLACK_TRACKS if t == deficiency.track_key)
            projects = 6  # derived below, asserted against the graph
            assert deficiency.demand == deficiency.target * deficiency.project_count
            assert deficiency.project_count == projects
            assert deficiency.supply == len(deficiency.bottleneck_judges) * INFEASIBLE_CAPACITY
            assert deficiency.deficit == deficiency.demand - deficiency.supply
            assert deficiency.deficit > 0
            assert track

    def test_the_bottleneck_judges_are_named_not_counted(self, tight):
        """Three judges, by name, each at capacity. The whole value of the feature.

        `bible/06` §2.3 calls these "the sink side of the cut". On this network
        that set is **empty** -- see F-61 -- so a test that implemented the bible
        literally would assert `bottleneck_judges == ()` and pass while the feature
        did nothing. The judges are named, and each is at capacity, which is the
        claim the organizer acts on.
        """
        for deficiency in tight.deficiencies:
            assert deficiency.bottleneck_judges, (
                f"{deficiency.track_key}: a deficiency with no named judge is not a diagnosis"
            )
            assert all("AT CAPACITY" in d for d in deficiency.bottleneck_detail)

    def test_the_short_projects_are_named(self, tight):
        for deficiency in tight.deficiencies:
            assert deficiency.project_ids, "a deficiency must name the projects"
            assert len(deficiency.project_ids) < deficiency.project_count

    def test_three_remedies_each_with_sufficient_arithmetic(self, tight):
        """The remedy is arithmetic, and the flag is a test rather than prose."""
        for deficiency in tight.deficiencies:
            kinds = {r.kind for r in tight.remedies if r.track_slug == deficiency.track_slug}
            assert {"invite_judges", "raise_capacity", "lower_target"} <= kinds, (
                f"{deficiency.track_key}: only got {sorted(kinds)}"
            )
            for remedy in tight.remedies:
                if remedy.track_slug != deficiency.track_slug:
                    continue
                assert remedy.sufficient, f"{remedy.statement} is not sufficient"
                assert any(ch.isdigit() for ch in remedy.arithmetic), (
                    "a remedy with no number in it is an opinion"
                )

    def test_the_certificate_renders_and_names_the_shortfall(self, tight):
        text = tight.render()
        assert "INFEASIBLE" in text
        assert "MINIMUM CUT" in text
        for deficiency in tight.deficiencies:
            assert deficiency.track_key in text
            for judge in deficiency.bottleneck_judges:
                assert judge in text, f"{judge} missing from the rendered certificate"

    def test_it_is_a_minimum_cut_not_an_arbitrary_one(self, event, graph, tight):
        """The certificate's cut value must equal the max-flow value.

        A cut that is merely *a* cut proves nothing -- any partition has a
        capacity. By max-flow/min-cut the minimum cut equals the max flow, so
        asserting `cut == max_flow` is what makes this a *proof* of infeasibility
        rather than a report of a short plan. This test re-derives both sides.
        """
        index = planner_module._node_index(graph)
        network, _ = planner_module._build_network(
            graph, index, capacity=INFEASIBLE_CAPACITY, seed=0, costs=False
        )
        flow = network.max_flow(index["source"], index["sink"])
        assert flow == tight.covered
        assert flow < graph.demand(), "if flow met demand this instance is feasible"
        # Every arc out of the reachable set is saturated -- that is what makes
        # the reachable set a min cut's source side.
        reachable = network.residual_reachable(index["source"])
        crossing = 0
        for node in reachable:
            for edge in network.graph[node]:
                if edge.to not in reachable and edge.capacity:
                    crossing += 1
                    assert edge.cap == 0, (
                        "an unsaturated arc leaves the source side, so this is "
                        "not a cut boundary and the certificate is not tight"
                    )
        assert crossing > 0, "the source side had no boundary at all"


# ------------------------------------------------- 3. the seeded tiebreak, twice


class TestSeededTiebreak:
    def test_two_runs_are_byte_identical(self, event):
        """Acceptance clause 3.

        **A digest, not a count.** Two runs agreeing on how many assignments they
        produced would pass a count-based test while the *contents* drifted, which
        is the drift that matters: a judge who logs in tomorrow must see the same
        panel they saw yesterday.
        """
        first = _plan(event, seed=7)
        second = _plan(event, seed=7)
        assert _rows(first) == _rows(second)
        assert first.capacity == second.capacity

    def test_the_plan_survives_a_reordered_database(self, event, loaded):
        """Determinism must not be an accident of one query plan.

        The engine is handed ``graph.pairs`` sorted, so the jitter draw is in a
        fixed order regardless of what Django returned. Re-running after touching
        the rows (which changes nothing logically) must give the same answer; if
        the sort were missing, this is the test that would catch it.
        """
        from reviewer.projects.models import Project

        first = _plan(event, seed=3)
        list(Project.objects.order_by("-id")[:5])
        second = _plan(event, seed=3)
        assert _rows(first) == _rows(second)

    def test_a_different_seed_gives_a_different_plan(self, event):
        """**The seed must matter.** Without this, clause 3 passes for free.

        A planner that ignored its seed would satisfy "reproducible" perfectly and
        be deterministic in the way a lookup table is deterministic -- which is
        exactly the "check that cannot fail" defect. The tiebreak has to be
        *load-bearing* and this is the test that says so.
        """
        a = _plan(event, seed=1)
        b = _plan(event, seed=2)
        assert _rows(a) != _rows(b), (
            "two different seeds produced identical plans: the tiebreak is not "
            "doing anything, so the determinism guarantee is vacuous"
        )
        # ...and both are still valid plans.
        assert a.feasible and b.feasible
        assert len(a.assignments) == len(b.assignments) == a.demand

    def test_the_seed_is_read_from_the_event_when_not_given(self, event):
        """`bible/06` §2.2: the seed is stored on the event and shown to the organizer."""
        event.assignment_seed = 11
        event.save(update_fields=["assignment_seed"])
        plan = _plan(event)
        assert plan.seed == 11
        assert _rows(plan) == _rows(
            planner_module.plan_assignment(event, capacity=None, seed=11, respect_in_flight=False)
        )


def _rows(plan) -> list[tuple[int, str]]:
    return sorted((a.judge_user_id, a.project_id) for a in plan.assignments)


def _plan(event, **kwargs):
    """``plan_assignment`` with the honest default spelled out once.

    Every call in this module wants ``respect_in_flight=False`` -- the question
    is what the *panel* can cover, and the loader's 126 assignments are history.
    Writing it at each call site would be eight chances to forget it, and one
    forgotten ``True`` would quietly make every capacity assertion about a frozen
    panel instead of about the judges.
    """
    kwargs.setdefault("respect_in_flight", False)
    return planner_module.plan_assignment(event, **kwargs)


# ------------------------------------------- each layer, proven load-bearing


class TestLayersAreLoadBearing:
    """Four deliberate simplifications, each of which would look fine.

    Each test disables one mechanism and asserts the answer *changes*. This is
    the module's real content: the acceptance clauses above prove the engine
    produces a plan, and these prove the plan is produced **for the reasons the
    documentation claims**, rather than by a coincidence of arithmetic.
    """

    def test_the_cost_function_is_what_spreads_the_load(self, event, monkeypatch):
        """Without the load-imbalance cost, plain max-flow clusters the work.

        `bible/06` §2.2 measures this: max-flow at the right capacity gives loads
        of ``[0x8, 3x3, 6x19]``. The min-cost pass is what turns that into a
        balanced panel, and it is not decoration.
        """
        real = planner_module._build_network
        no_costs = lambda *a, **k: real(*a, **{**k, "costs": False})  # noqa: E731

        balanced = _plan(event, seed=5)
        monkeypatch.setattr(planner_module, "_build_network", no_costs)
        clustered = _plan(event, seed=5)

        assert balanced.max_load == clustered.max_load, (
            "the capacity search bounds the worst case in both; that is the point"
        )
        assert balanced.min_load > clustered.min_load, (
            f"min-cost pass did not improve the floor: "
            f"{balanced.min_load} vs plain max-flow {clustered.min_load}"
        )
        # And the quality measure that matters: deviation from the mean.
        assert _spread(balanced) < _spread(clustered)

    def test_the_capacity_search_is_what_finds_six(self, event, monkeypatch):
        """If the search is skipped and the largest capacity used, coverage holds
        and the *fairness claim* is false. Both plans are feasible -- which is
        why this is worth a test."""
        graph = graph_module.build_graph(event, respect_in_flight=False)
        low, high = planner_module._capacity_bounds(graph)
        assert (
            low
            < planner_module.plan_assignment(
                event, capacity=None, seed=0, respect_in_flight=False
            ).capacity
            <= high
        )

        greedy = planner_module.plan_assignment(
            event, capacity=high, seed=0, respect_in_flight=False
        )
        assert greedy.feasible
        assert (
            greedy.max_load
            > planner_module.plan_assignment(
                event, capacity=None, seed=0, respect_in_flight=False
            ).max_load
        ), "using the largest capacity did not cost anything -- the search is pointless"

    def test_without_a_max_flow_the_feasibility_answer_is_wrong(self, graph):
        """The certificate depends on a real max-flow, not on a count.

        Counting eligible pairs per project and comparing to the target would say
        ``trk_01`` is fine at capacity 5, because each of its six projects has
        three eligible judges. It is short anyway, because three judges at five
        each cannot cover six projects at three each. That gap between "each pair
        exists" and "the demand can be met" is the whole reason this is a flow
        problem.
        """
        from reviewer.assignment.graph import AssignmentGraph  # noqa: F401

        naive_ok = all(
            sum(1 for _j, p in graph.pairs if p == project.id) >= project.target
            for project in graph.projects
        )
        assert naive_ok, "the naive test would have failed, so this proves nothing"
        # The real answer at capacity 5.
        plan = planner_module.diagnose(graph, INFEASIBLE_CAPACITY)
        assert not plan.feasible, "capacity 5 is provably infeasible, and the naive test missed it"

    def test_the_sibling_rule_is_enforced_and_visible(self, event):
        """`prj_07` and `prj_41` are the same team and track, 13h28m apart.

        A judge on both is not independent evidence, so the plan must not contain
        both -- and because the rule is a post-pass rather than a network
        constraint, the test also checks the collision was *reported* rather than
        silently accepted.
        """
        plan = _plan(event)
        from reviewer.projects.models import Project

        siblings = set()
        for project in Project.objects.all():
            if project.supersedes_id:
                siblings.add(frozenset({project.pk, project.supersedes_id}))
        assert siblings, "the fixture's supersede pair is gone -- the rule is untested"

        by_judge: dict[int, set[str]] = {}
        for assignment in plan.assignments:
            by_judge.setdefault(assignment.judge_user_id, set()).add(assignment.project_id)
        for group in siblings:
            for judge, held in by_judge.items():
                both = held & set(group)
                assert len(both) < 2, (
                    f"judge {judge} holds both {sorted(both)}: not independent evidence"
                )

    def test_the_exclusion_reasons_are_reachable(self, graph):
        """Which rules the fixture can reach, and -- more useful -- which it cannot.

        **The fixture never exercises the conflict-of-interest rule.** Measured:
        not one of the fixture's 30 judges is a member of any of its 40 teams, so
        ``submitting_team_member`` is *unreachable* on shipped data. That is not
        a reason to delete the rule -- it is a conflict of interest, and judges
        submit at hackathons -- but it does mean a test that asserted "the
        exclusion rules are covered" by the fixture would be lying, and the rule
        would ship untested. So the honest split is asserted here and the
        unreachable rule gets its own synthetic test below.
        """
        reasons = set(graph.excluded.values())
        assert "no_track_binding" in reasons, "the track rule is the fixture's main filter"
        assert "submitting_team_member" not in reasons, (
            "if this now fires, the fixture changed and the synthetic test below "
            "is no longer the only coverage -- update F-64"
        )
        assert reasons <= {
            "no_track_binding",
            "submitting_team_member",
            "already_in_flight",
            "sibling_already_in_flight",
        }

    def test_a_judge_cannot_review_their_own_teams_project(self, event, graph):
        """The conflict rule, on a world the fixture does not contain.

        Built synthetically on purpose, per the measurement above: add one team
        member who is also a judge on that project's track, and assert the pair
        disappears from the graph with the right reason. This is the test that
        stops the rule being dead code.
        """
        from reviewer.accounts.models import RoleBinding
        from reviewer.projects.models import Project
        from reviewer.teams.models import TeamMembership

        project = Project.objects.select_related("team").order_by("id").first()
        judge = RoleBinding.objects.filter(role="judge", track=project.track).first()
        assert judge is not None, "no judge on that track to conflict with"
        TeamMembership.objects.get_or_create(
            team=project.team, user=judge.user, defaults={"role_in_team": "member"}
        )

        rebuilt = graph_module.build_graph(event, respect_in_flight=False)
        key = (judge.user_id, project.pk)
        assert key not in set(rebuilt.pairs), (
            "a judge bound to a track was allowed to review their own team's "
            "project -- the conflict rule did not fire"
        )
        assert rebuilt.excluded.get(key) == "submitting_team_member", (
            f"excluded for the wrong reason: {rebuilt.excluded.get(key)!r}"
        )

    def test_a_single_eligible_judge_is_reported_as_a_single_point_of_failure(self, graph):
        """ "This judge is your only cover for trk_01."

        ``bible/06`` §2.3 calls this the highest-value line in the dashboard, and
        it is the one line an organizer needs *before* the invitation email.

        Two directions, because either alone is half a test: the shipped fixture
        has 3+ judges on every track so nothing may be flagged, and a track
        reduced to one judge must be flagged **by name**. The first direction is
        what stops the rule from firing on everything; the second is what stops it
        from being decorative.
        """
        # -- direction 1: nothing on the shipped fixture is a sole cover ------
        from reviewer.events.models import Event

        shipped = planner_module.plan_assignment(
            Event.objects.get(pk="evt_01"), capacity=None, seed=0, respect_in_flight=False
        )
        assert shipped.sole_covers == [], (
            f"unexpected sole covers on the fixture: "
            f"{[(c.track_slug, c.judge_email) for c in shipped.sole_covers]}"
        )
        assert all(len(t.judge_user_ids) >= 2 for t in graph.tracks), (
            "the fixture no longer has 3+ judges per track; this test's premise "
            "has changed and the sole-cover rule is now untested in the clear case"
        )

        # -- direction 2: reduce one track to a single judge, and it is named --
        track = next(t for t in graph.tracks if len(t.judge_user_ids) >= 2)
        keeper = track.judge_user_ids[0]
        judge = next(j for j in graph.judges if j.user_id == keeper)
        thinned = planner_module.AssignmentPlan(
            event_id=graph.event_id, seed=0, capacity=0, demand=0, covered=0, feasible=False
        )
        planner_module._sole_covers(
            graph_module.AssignmentGraph(
                event_id=graph.event_id,
                tracks=[
                    graph_module.TrackNode(
                        id=track.id,
                        name=track.name,
                        slug=track.slug,
                        source_key=track.source_key,
                        target=track.target,
                        project_ids=track.project_ids,
                        judge_user_ids=(keeper,),
                    )
                ],
                judges=graph.judges,
                projects=graph.projects,
                pairs=graph.pairs,
            ),
            thinned,
        )
        assert len(thinned.sole_covers) == 1, (
            f"a track with one eligible judge produced {len(thinned.sole_covers)} "
            f"warnings -- the rule did not fire"
        )
        cover = thinned.sole_covers[0]
        assert cover.judge_email == judge.email, (
            f"named the wrong judge: {cover.judge_email} != {judge.email}"
        )
        assert cover.track_slug == track.slug, "the warning names the wrong track"

        # -- and two judges on the same track is NOT a sole cover --------------
        two = planner_module.AssignmentPlan(
            event_id=graph.event_id, seed=0, capacity=0, demand=0, covered=0, feasible=False
        )
        planner_module._sole_covers(
            graph_module.AssignmentGraph(
                event_id=graph.event_id,
                tracks=[
                    graph_module.TrackNode(
                        id=track.id,
                        name=track.name,
                        slug=track.slug,
                        source_key=track.source_key,
                        target=track.target,
                        project_ids=track.project_ids,
                        judge_user_ids=tuple(track.judge_user_ids[:2]),
                    )
                ],
                judges=graph.judges,
                projects=graph.projects,
                pairs=graph.pairs,
            ),
            two,
        )
        assert two.sole_covers == [], "two eligible judges is not a single point of failure"


def _spread(plan) -> float:
    """Sum of squared deviation from the mean -- the measure the cost minimises."""
    if not plan.loads:
        return 0.0
    mean = plan.mean_load
    return sum((load - mean) ** 2 for load in plan.loads.values())


# ------------------------------------------------------------- the solver alone


class TestTheSolver:
    """The flow solver, isolated from judging.

    ``bible/06`` §2.2's whole argument for hand-rolling is that this network is
    small enough not to need scipy. That argument only holds if the hand-rolled
    version is *right*, so it gets tested against the properties it claims rather
    than through the planner.
    """

    def test_max_flow_and_the_min_cut_agree(self):
        """Max-flow/min-cut, checked rather than cited."""
        network = FlowNetwork(4)
        network.add_edge(0, 1, 2)
        network.add_edge(1, 3, 2)
        network.add_edge(0, 2, 3)
        network.add_edge(2, 3, 1)
        assert network.max_flow(0, 3) == 3
        reachable = network.residual_reachable(0)
        # Every arc leaving the reachable set is saturated, and the cut's
        # capacity equals the flow.
        cut = sum(
            e.capacity
            for u in reachable
            for e in network.graph[u]
            if e.to not in reachable and e.capacity
        )
        assert cut == 3
        assert all(
            e.cap == 0
            for u in reachable
            for e in network.graph[u]
            if e.to not in reachable and e.capacity
        )

    def test_negative_marginal_costs_give_the_minimum_cost_flow(self):
        """The load term is *negative* below the target, so this path is live.

        Zero-initialised potentials would return a feasible flow that is not
        minimum-cost here, and it would look correct (F-60).
        """
        network = FlowNetwork(6)
        for project in (1, 2, 3):
            network.add_edge(0, project, 1)
            network.add_edge(project, 4, 1)
        target = 1
        for level in range(1, 4):
            network.add_edge(4, 5, 1, 2 * (level - 1 - target) + 1)
        flow, cost = network.min_cost_max_flow(0, 5)
        assert (flow, cost) == (3, 3), "marginals -1,+1,+3 must sum to 3"

    def test_a_self_loop_is_refused(self):
        with pytest.raises(ValueError):
            FlowNetwork(2).add_edge(0, 0, 1)
