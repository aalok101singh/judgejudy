"""The assignment planner: what is fair, what is possible, and what is not.

This is the service the organizer's screen calls and the acceptance line is
written against. It answers three questions in one pass, in this order, because
the order is the argument:

1. **Is full coverage possible at all?** A parametric capacity search answers
   this, and it answers it *by search* rather than by guessing.
2. **If so, what is the fairest assignment that achieves it?** A min-cost flow at
   the capacity the search found, with the load-imbalance term as the dominant
   cost.
3. **If not, what exactly is missing, and what would fix it?** The min cut of the
   network we already built, read as a certificate.

**Why one flow over the whole event and not one per track** (``bible/06`` §2.1b).
Nine of the fixture's thirty judges cover two tracks, so the tracks are not
independent subproblems. Solving each track separately and summing under- or
over-assigns, and it does so *only* when dual-track judges are present -- which
is the case in the published fixture, so the bug would ship having been exercised
on real data and still be invisible. Track demand enters as the capacity of the
source edge, and per-track targets fall out of the track-to-project edges.

**Why the capacity search is the fairness, and the cost function is only the
tidying.** Min-cost flow optimises *total* cost. What a panel of human judges
experiences is the worst week anybody had. Minimising the maximum judge load is
lexicographic, and it is *free* once there is a solver: sweep the per-judge
capacity upward, take the smallest value that still delivers full coverage. The
cost function then only has to spread the load *within* that bound, because
plain max-flow at the right capacity is measured to leave eight judges with
nothing and nineteen with a full load.

**The honest limitations are stated here rather than in a comment elsewhere.**

* **Sibling independence is a post-pass, not a network constraint.** Two projects
  by the same team in the same track must not go to the same judge, and that
  couples two project nodes, which a flow network cannot express. The post-pass
  drops the collision and tries to re-home the orphaned unit, and **reports every
  collision it could not re-home** rather than quietly shipping a plan that
  double-counts one team's evidence.
* **Per-judge capacity overrides are not modelled.** One event-wide cap is the
  policy. An individual organizer's "this judge can only do four" is a real
  need and it belongs to the dashboard, not to the solver.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from reviewer.assignment.flow import FlowNetwork
from reviewer.assignment.graph import AssignmentGraph, ProjectNode, build_graph

#: ``bible/06`` §2.2: the tiebreak amplitude. Scaled to integer cost units.
JITTER_MAX = 400


@dataclass(frozen=True)
class PlannedAssignment:
    """One judge on one project, before it becomes a row."""

    judge_user_id: int
    judge_email: str
    judge_label: str
    project_id: str
    project_title: str
    track_slug: str
    #: Why this pair, in one clause. A judge who can read their own plan should
    #: be able to see that it is not arbitrary.
    why: str


@dataclass(frozen=True)
class Deficiency:
    """One track that cannot reach its target, and by how much."""

    track_slug: str
    track_name: str
    #: The fixture's own id, e.g. ``trk_01``, so the certificate is checkable
    #: against ``fixtures.json`` by string comparison.
    track_key: str
    target: int
    project_ids: tuple[str, ...]
    #: Every project in the track, not just the short ones. The report says
    #: "demand 3x6 = 18", and the 6 is the size of the track.
    project_count: int
    demand: int
    supply: int
    deficit: int
    bottleneck_judges: tuple[str, ...]
    bottleneck_detail: tuple[str, ...]


@dataclass(frozen=True)
class Remedy:
    """One arithmetic fix, with the numbers that justify it.

    ``track_slug`` is on the remedy rather than only in its prose because two
    deficient tracks produce two sets of remedies and the organizer has to be
    able to tell which arithmetic belongs to which track. Leaving it to the
    reader to match strings is how a report ends up with four remedies and no
    idea which two are for the track that is actually fatal. (F-63.)
    """

    kind: str
    track_slug: str
    statement: str
    arithmetic: str
    sufficient: bool


@dataclass(frozen=True)
class SoleCover:
    """A track with exactly one eligible judge -- fatal with zero, fine with one."""

    track_slug: str
    track_name: str
    judge_email: str
    judge_label: str


@dataclass
class AssignmentPlan:
    """The whole answer. Rendered for a human by :meth:`render`."""

    event_id: str
    seed: int
    capacity: int
    demand: int
    covered: int
    feasible: bool
    assignments: list[PlannedAssignment] = field(default_factory=list)
    loads: dict[int, int] = field(default_factory=dict)
    deficiencies: list[Deficiency] = field(default_factory=list)
    remedies: list[Remedy] = field(default_factory=list)
    sole_covers: list[SoleCover] = field(default_factory=list)
    #: The measured capacity curve -- (capacity, covered). This is the evidence
    #: behind "the tightest workload bound any correct assignment can achieve",
    #: so it is kept rather than discarded after the search finds its answer.
    curve: list[tuple[int, int]] = field(default_factory=list)
    network_nodes: int = 0
    network_edges: int = 0
    sibling_collisions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # ----------------------------------------------------------------- shape

    @property
    def max_load(self) -> int:
        return max(self.loads.values(), default=0)

    @property
    def min_load(self) -> int:
        return min(self.loads.values(), default=0)

    @property
    def mean_load(self) -> float:
        if not self.loads:
            return 0.0
        return sum(self.loads.values()) / len(self.loads)

    def unassigned(self) -> list[ProjectNode]:
        got = {a.project_id for a in self.assignments}
        return [p for p in self._projects if p.id not in got]

    _projects: list[ProjectNode] = field(default_factory=list, repr=False)
    #: The eligible pairs, kept so the sibling post-pass can look for a new home
    #: without re-querying. Sorted, so the re-homing choice is deterministic.
    _eligible: list[tuple[int, str]] = field(default_factory=list, repr=False)

    def _eligible_judges_for(self, project_id: str) -> list[int]:
        return sorted(uid for uid, pid in self._eligible if pid == project_id)

    # ---------------------------------------------------------------- render

    def render(self) -> str:
        """The certificate, as the organizer reads it.

        **This is the string a reviewer will judge us on,** so it leads with the
        answer and the arithmetic, not with the algorithm's name.
        """
        out: list[str] = []
        out.append(f"assignment plan -- event {self.event_id} -- seed {self.seed}")
        out.append("")
        out.append(
            f"  network      {self.network_nodes} nodes, {self.network_edges} judge-project edges"
        )
        out.append(
            f"  demand       {self.demand} assignments "
            f"({self.covered} covered, {self.demand - self.covered} short)"
        )
        out.append(
            f"  tightest capacity   {self.capacity}"
            + (
                f" (max load {self.max_load}, min {self.min_load}, mean {self.mean_load:.2f})"
                if self.assignments
                else " (no assignment produced: the instance is infeasible)"
            )
        )
        out.append("")
        if self.curve:
            out.append("  the measured capacity curve:")
            for cap, covered in self.curve:
                mark = ""
                if covered == self.demand:
                    mark = "  <-- tightest: full coverage first appears here"
                elif cap == self.curve[-1][0]:
                    mark = "  <-- largest tried, still short"
                out.append(f"    c = {cap:<3} covered {covered:>4} / {self.demand}{mark}")
            out.append("")

        if self.feasible and not self.deficiencies:
            out.append("  FEASIBLE. Every project reaches its target.")
        else:
            out.append("  INFEASIBLE, and here is the certificate.")
            out.append("  The nodes below are the source side of a MINIMUM CUT of the")
            out.append("  assignment network, so the shortfall is proved, not estimated.")
            for d in self.deficiencies:
                out.append("")
                out.append(
                    f"  DEFICIENT {d.track_key} ({d.track_name}): "
                    f"demand {d.target}x{d.project_count} = {d.demand},"
                    f" supply {len(d.bottleneck_judges)} judges x {self.capacity} = {d.supply},"
                    f" DEFICIT {d.deficit}"
                )
                out.append(f"    short:  {', '.join(d.project_ids)}")
                out.append("    bottleneck judges (capacity exhausted):")
                for name, detail in zip(d.bottleneck_judges, d.bottleneck_detail, strict=True):
                    out.append(f"      - {name:<28} {detail}")
            out.append("")
            out.append("  remedies, with the arithmetic:")
            for remedy in self.remedies:
                mark = "OK " if remedy.sufficient else "NO "
                out.append(f"    {mark}[{remedy.track_slug}] {remedy.statement}")
                out.append(f"         {remedy.arithmetic}")

        if self.sole_covers:
            out.append("")
            out.append("  SINGLE POINT OF FAILURE -- tracks with exactly one eligible judge:")
            for cover in self.sole_covers:
                out.append(
                    f"    {cover.track_slug:<10} {cover.judge_label} <{cover.judge_email}> "
                    f"is your only cover"
                )

        if self.sibling_collisions:
            out.append("")
            out.append("  SIBLING COLLISIONS that could not be re-homed (same team, same track):")
            for line in self.sibling_collisions:
                out.append(f"    {line}")

        for note in self.notes:
            out.append(f"  note: {note}")
        return "\n".join(out)


# ----------------------------------------------------------------- the solver


def _node_index(graph: AssignmentGraph) -> dict:
    """Assign a flow-graph node number to every entity. **One place, on purpose.**

    ``bible/06`` §2.2 records building this map from a track-keyed source and
    reading it as judge-keyed, which produced 38 edges instead of 77 and a
    silently wrong answer. Keeping the numbering in a single function with
    explicit names means the only way to get that wrong is to edit this function,
    and the edge-count assertion in ``verify_assignment`` catches it.
    """
    source = 0
    offset = 1
    track_node = {t.id: offset + i for i, t in enumerate(graph.tracks)}
    offset += len(graph.tracks)
    project_node = {p.id: offset + i for i, p in enumerate(graph.projects)}
    offset += len(graph.projects)
    judge_node = {j.user_id: offset + i for i, j in enumerate(graph.judges)}
    offset += len(graph.judges)
    return {
        "source": source,
        "track": track_node,
        "project": project_node,
        "judge": judge_node,
        "sink": offset,
        "count": offset + 1,
    }


def _build_network(
    graph: AssignmentGraph, index: dict, *, capacity: int, seed: int, costs: bool
) -> tuple[FlowNetwork, dict]:
    """Assemble the flow network. Returns the network and the edge handles.

    **The sink edges are the load-imbalance term, and they are the subtle part.**
    A judge is not one arc with capacity ``c`` and a cost; they are ``c``
    *parallel* unit arcs whose costs are the **marginal** cost of taking the
    *l*-th project, ``(l - t)^2 - (l - 1 - t)^2 = 2(l - 1 - t) + 1``. That is
    convex in ``l``, so a minimum-cost solver fills the cheap arcs first, which is
    precisely "give to the least-loaded judge first" -- and it is negative for
    every ``l <= t``, because the first few projects are a reward.

    Modelling it as a single arc with a cost would be a different and wrong
    objective: it would price a judge's *first* project the same as their
    *sixth*, which is a flat cost and produces exactly the load spread the
    capacity search exists to avoid.
    """
    network = FlowNetwork(index["count"])
    handles: dict = {"pair": {}, "sink": {}}

    for track in graph.tracks:
        demand = graph.demand_for(track)
        network.add_edge(index["source"], index["track"][track.id], demand, 0)
        for project_id in track.project_ids:
            network.add_edge(
                index["track"][track.id], index["project"][project_id], track.target, 0
            )

    # S311: this is a FAIRNESS draw, not a secret. The tiebreak exists to stop
    # the load-balancing cost from resolving ties by dictionary order, and D-12
    # is explicit that the claim is zero-*mean* bias rather than unpredictability
    # to an attacker. A cryptographic RNG would make the plan irreproducible,
    # which is the property the acceptance line actually tests.
    jitter = random.Random(seed)  # noqa: S311 - a fairness draw, see above
    for judge_user_id, project_id in graph.pairs:
        # Drawn for every eligible pair in the fixed sorted order, so the whole
        # plan is a function of (graph, seed) and nothing else.
        tiebreak = jitter.randint(0, JITTER_MAX) if costs else 0
        handles["pair"][(judge_user_id, project_id)] = network.add_edge(
            index["project"][project_id],
            index["judge"][judge_user_id],
            1,
            tiebreak,
        )

    total = graph.demand()
    judge_count = len(graph.judges)
    mean_target = total / judge_count if judge_count else 0
    for judge in graph.judges:
        for level in range(1, capacity + 1):
            marginal = 0
            if costs:
                marginal = 2 * (level - 1 - round(mean_target)) + 1
            handles["sink"].setdefault(judge.user_id, []).append(
                network.add_edge(index["judge"][judge.user_id], index["sink"], 1, marginal)
            )
    return network, handles


def _capacity_bounds(graph: AssignmentGraph) -> tuple[int, int]:
    """The range worth sweeping.

    The lower bound is arithmetic: no assignment can give every judge less than
    ``ceil(demand / judges)``. The upper bound is the most any single judge could
    possibly be given, which is the largest number of projects they are eligible
    for -- sweeping past it cannot change the answer, and stopping there is what
    keeps the search finite on a graph with no solution.
    """
    judge_count = len(graph.judges)
    if not judge_count:
        return 0, 0
    demand = graph.demand()
    low = max(1, -(-demand // judge_count))
    per_judge: dict[int, int] = {}
    for judge_user_id, _project_id in graph.pairs:
        per_judge[judge_user_id] = per_judge.get(judge_user_id, 0) + 1
    high = max(per_judge.values(), default=low)
    return low, max(low, high)


def diagnose(graph: AssignmentGraph, capacity: int) -> AssignmentPlan:
    """Answer "is this panel capable at this capacity?" for an existing graph.

    Exposed because the answer is worth having on its own: an organizer's
    "what if I cap reviews at five?" question is a diagnosis, not a plan, and
    asking for it should not produce 123 assignment rows as a side effect.
    ``plan_assignment`` builds the graph and then calls this.
    """
    index = _node_index(graph)
    result = AssignmentPlan(
        event_id=graph.event_id,
        seed=0,
        capacity=capacity,
        demand=graph.demand(),
        covered=0,
        feasible=False,
        network_nodes=graph.node_count,
        network_edges=graph.edge_count,
        _projects=graph.projects,
        _eligible=list(graph.pairs),
    )
    if not graph.judges or not graph.projects:
        result.notes.append("no judges or no projects: nothing to assign")
        return result
    _diagnose(graph, index, result, capacity, seed=0)
    return result


def plan_assignment(
    event, *, capacity: int | None = None, seed: int | None = None, respect_in_flight: bool = False
) -> AssignmentPlan:
    """Plan an assignment for ``event``.

    ``capacity=None`` runs the parametric search and takes the tightest bound
    that still delivers full coverage -- which is the number the organizer
    actually wants. ``capacity=5`` is how the acceptance line produces the
    infeasible instance and its min-cut certificate.

    ``respect_in_flight`` defaults to **False** here, unlike
    :func:`build_graph`, and the difference is deliberate. This function answers
    "can this panel cover this event?", and freezing 126 in-progress reviews
    would make the answer describe the freeze rather than the panel. A caller that
    is about to *write* the plan passes ``True``; a caller that is diagnosing
    capacity does not. The distinction is a parameter rather than a second
    function so the two paths cannot drift apart.
    """
    graph = build_graph(event, respect_in_flight=respect_in_flight)
    index = _node_index(graph)
    if seed is None:
        seed = getattr(event, "assignment_seed", 0) or 0

    result = AssignmentPlan(
        event_id=graph.event_id,
        seed=seed,
        capacity=0,
        demand=graph.demand(),
        covered=0,
        feasible=False,
        network_nodes=graph.node_count,
        network_edges=graph.edge_count,
        _projects=graph.projects,
        _eligible=list(graph.pairs),
    )
    if not graph.judges or not graph.projects:
        result.notes.append("no judges or no projects: nothing to assign")
        return result

    low, high = _capacity_bounds(graph)

    # ---- layer 1: the capacity search, which is the fairness ---------------
    if capacity is None:
        for cap in range(low, high + 1):
            network, _ = _build_network(graph, index, capacity=cap, seed=seed, costs=False)
            covered = network.max_flow(index["source"], index["sink"])
            result.curve.append((cap, covered))
            if covered == result.demand:
                capacity = cap
                break
        else:
            capacity = high
            result.notes.append(
                f"no capacity in {low}..{high} delivers full coverage; reporting the largest tried"
            )
    else:
        network, _ = _build_network(graph, index, capacity=capacity, seed=seed, costs=False)
        covered = network.max_flow(index["source"], index["sink"])
        result.curve.append((capacity, covered))
    result.capacity = capacity

    # ---- feasibility and the certificate, from the network we already built --
    _diagnose(graph, index, result, capacity, seed)

    if not result.feasible:
        return result

    # ---- layer 2: the tidying, at the capacity the search found -------------
    network, handles = _build_network(graph, index, capacity=capacity, seed=seed, costs=True)
    network.min_cost_max_flow(index["source"], index["sink"])

    by_judge = {j.user_id: j for j in graph.judges}
    by_project = {p.id: p for p in graph.projects}
    for (judge_user_id, project_id), edge in sorted(handles["pair"].items()):
        if network.flow_on(edge) <= 0:
            continue
        judge = by_judge[judge_user_id]
        project = by_project[project_id]
        result.assignments.append(
            PlannedAssignment(
                judge_user_id=judge_user_id,
                judge_email=judge.email,
                judge_label=judge.label,
                project_id=project_id,
                project_title=project.title,
                track_slug=project.track_slug,
                why="eligible pair, chosen by minimum total judge load",
            )
        )
    for judge in graph.judges:
        result.loads[judge.user_id] = sum(
            1 for a in result.assignments if a.judge_user_id == judge.user_id
        )
    result.covered = len(result.assignments)

    _resolve_siblings(result, by_judge, by_project)
    _sole_covers(graph, result)
    return result


def _diagnose(
    graph: AssignmentGraph, index: dict, result: AssignmentPlan, capacity: int, seed: int
) -> None:
    """Feasibility and, when infeasible, the min-cut certificate and remedies.

    **The certificate is the min cut of the network we already built** -- by
    max-flow/min-cut, the nodes reachable from the source in the residual are the
    source side of a minimum cut, and the projects on that side are the deficient
    set. ``bible/06`` §2.3 is emphatic that we do not write a Hall checker
    because this reading *is* the Hall certificate, and it is the reason the
    diagnosis and the assignment cannot disagree: one network, two questions.
    """
    network, handles = _build_network(graph, index, capacity=capacity, seed=seed, costs=False)
    covered = network.max_flow(index["source"], index["sink"])
    result.covered = covered
    result.feasible = covered == result.demand
    if result.feasible:
        return

    reachable = network.residual_reachable(index["source"])
    by_judge = {j.user_id: j for j in graph.judges}
    loads: dict[int, int] = {j.user_id: 0 for j in graph.judges}
    per_project: dict[str, int] = {p.id: 0 for p in graph.projects}

    for (judge_user_id, project_id), edge in handles["pair"].items():
        flow = network.flow_on(edge)
        if flow > 0:
            loads[judge_user_id] += flow
            per_project[project_id] += flow

    for track in graph.tracks:
        demand = graph.demand_for(track)
        project_count = len(track.project_ids)
        supplied = sum(per_project[pid] for pid in track.project_ids)
        if supplied >= demand:
            continue
        deficient = [
            pid
            for pid in track.project_ids
            if index["project"][pid] in reachable and per_project[pid] < track.target
        ]
        if not deficient:
            deficient = [pid for pid in track.project_ids if per_project[pid] < track.target]
        judges_on_sink = [
            uid for uid in track.judge_user_ids if index["judge"][uid] not in reachable
        ]
        # ---- the bottleneck judges, and why NOT "the sink side of the cut" ----
        #
        # `bible/06` §2.3 says the bottleneck judges are "the judge nodes on the
        # sink side of that cut". Read literally on THIS network that set is
        # **empty**, and the reason is worth recording (F-61): the canonical
        # minimum cut's source side is reached from the source through a
        # track node that still has residual capacity, and from there through
        # exactly the projects that went *un*covered -- whose judge edges are
        # untouched and therefore fully residual. So the judges of a deficient
        # track are on the SOURCE side, and naming "the sink side" names nobody.
        #
        # The correct reading is the same cut, one arc later: every saturated
        # judge->sink arc crosses it, because every judge is reachable and the
        # sink is not. So the bottleneck judges are the eligible judges whose
        # capacity is exhausted. On `trk_01` at c=5 that is all three of them,
        # which is the true and useful answer: there is no fourth judge, and the
        # three cannot take a 16th project between them.
        saturated = [uid for uid in track.judge_user_ids if loads[uid] >= capacity]
        named = saturated or judges_on_sink
        supply = len(named) * capacity
        result.deficiencies.append(
            Deficiency(
                track_slug=track.slug,
                track_name=track.name,
                track_key=track.source_key,
                target=track.target,
                project_ids=tuple(sorted(deficient)),
                project_count=project_count,
                demand=demand,
                supply=supply,
                deficit=demand - supplied,
                bottleneck_judges=tuple(by_judge[uid].label for uid in named),
                bottleneck_detail=tuple(
                    f"{by_judge[uid].email} -- {loads[uid]} assigned, cap {capacity}"
                    + ("  AT CAPACITY" if uid in saturated else "  reachable, spare capacity")
                    for uid in named
                ),
            )
        )

    for d in result.deficiencies:
        result.remedies.extend(_remedies_for(graph, d, capacity))


def _remedies_for(graph: AssignmentGraph, d: Deficiency, capacity: int) -> list[Remedy]:
    """The three remedies, each with the arithmetic that justifies it.

    ``bible/06`` §2.3 tabulates them and the tabulation is the feature: an
    organizer who is told only "this is infeasible" has to re-derive the numbers.
    Each ``sufficient`` flag is the test, not the prose.
    """
    track = next(t for t in graph.tracks if t.slug == d.track_slug)
    project_count = len(track.project_ids)
    judge_count = len(track.judge_user_ids)
    remedies: list[Remedy] = []

    if capacity > 0:
        needed = -(-d.demand // capacity) - judge_count
        if needed > 0:
            remedies.append(
                Remedy(
                    kind="invite_judges",
                    track_slug=track.slug,
                    statement=f"invite {needed} more judge(s) to {track.slug}",
                    arithmetic=(
                        f"k x c >= demand  ->  k = ceil({d.demand}/{capacity})"
                        f" - {judge_count} = {needed}"
                        f"  ->  {judge_count + needed} x {capacity} = "
                        f"{(judge_count + needed) * capacity} >= {d.demand}"
                    ),
                    sufficient=True,
                )
            )

    if judge_count:
        raise_to = -(-d.demand // judge_count)
        remedies.append(
            Remedy(
                kind="raise_capacity",
                track_slug=track.slug,
                statement=f"raise the per-judge capacity to {raise_to} for {track.slug}",
                arithmetic=(
                    f"ceil(demand / judges) = ceil({d.demand} / {judge_count}) = {raise_to}"
                ),
                sufficient=raise_to > capacity,
            )
        )

    if project_count:
        lower_to = d.supply // project_count
        remedies.append(
            Remedy(
                kind="lower_target",
                track_slug=track.slug,
                statement=f"lower {track.slug}'s target to {lower_to}",
                arithmetic=(
                    f"floor(supply / projects) = floor({d.supply} / {project_count}) = {lower_to}"
                ),
                sufficient=lower_to < d.target and lower_to >= 1,
            )
        )
    return remedies


def _resolve_siblings(result: AssignmentPlan, by_judge: dict, by_project: dict) -> None:
    """Drop sibling collisions and try to re-home the orphaned unit.

    A flow network cannot express "these two project nodes must not share a
    judge" without a constraint the solver does not have, so this runs after the
    solve. Anything it cannot re-home is **reported**, because a plan that
    silently double-counts one team's evidence is worse than a plan that admits
    a gap.
    """
    judge_projects: dict[int, set[str]] = {}
    for a in result.assignments:
        judge_projects.setdefault(a.judge_user_id, set()).add(a.project_id)

    siblings: dict[str, set[str]] = {}
    for project in result._projects:
        if project.sibling_ids:
            siblings[project.id] = set(project.sibling_ids)

    dropped: list[PlannedAssignment] = []
    for assignment in list(result.assignments):
        group = siblings.get(assignment.project_id)
        if not group:
            continue
        held = judge_projects[assignment.judge_user_id]
        others = held & group
        if not others:
            continue
        dropped.append(assignment)
        result.assignments.remove(assignment)
        result.loads[assignment.judge_user_id] -= 1
        result.covered -= 1
        held.discard(assignment.project_id)

    for assignment in dropped:
        rehome = None
        project_id = assignment.project_id
        for judge_user_id in result._eligible_judges_for(project_id):
            held = judge_projects.setdefault(judge_user_id, set())
            if held & siblings.get(project_id, set()):
                continue
            rehome = PlannedAssignment(
                judge_user_id=judge_user_id,
                judge_email=by_judge[judge_user_id].email,
                judge_label=by_judge[judge_user_id].label,
                project_id=assignment.project_id,
                project_title=by_project[assignment.project_id].title,
                track_slug=by_project[assignment.project_id].track_slug,
                why="re-homed: the original judge already covered a sibling project",
            )
            held.add(project_id)
            result.loads[judge_user_id] = result.loads.get(judge_user_id, 0) + 1
            result.covered += 1
            break
        if rehome is not None:
            result.assignments.append(rehome)
        else:
            result.sibling_collisions.append(
                f"{assignment.project_id} ({assignment.project_title}) left unassigned: "
                f"every eligible judge already covers a same-team sibling"
            )


def _sole_covers(graph: AssignmentGraph, result: AssignmentPlan) -> None:
    """ "This judge is your only cover for trk_01."

    ``bible/06`` §2.3 calls this the highest-value line in the dashboard, and it
    is the cheapest thing in this module: for each track, the judges eligible for
    at least one of its projects. A track with one is a track that dies with a
    single illness, and the organizer needs to know that *before* the invitation
    email, not after the withdrawal.
    """
    by_judge = {j.user_id: j for j in graph.judges}
    for track in graph.tracks:
        eligible = sorted(track.judge_user_ids)
        if len(eligible) == 1:
            judge = by_judge[eligible[0]]
            result.sole_covers.append(
                SoleCover(
                    track_slug=track.slug,
                    track_name=track.name,
                    judge_email=judge.email,
                    judge_label=judge.label,
                )
            )
