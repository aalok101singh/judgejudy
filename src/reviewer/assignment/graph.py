"""Who *may* review what, as an explicit graph, derived from the database.

``bible/06`` §2.1 lists the five conditions for an edge. Each one is a hard
constraint and each one is a place where a plausible-looking shortcut returns a
wrong answer, so this module's job is to make all five visible and separately
countable.

**The number this module exists to get right is the edge count.** ``bible/06``
§2.2 records a real bug: building this graph from a track-keyed map and reading
it as judge-keyed produced 38 edges instead of 77 and returned a **silently
wrong answer rather than an error**. A solver handed 38 edges will happily return
a plan for a smaller event. So the builder returns the graph *and* a count, and
``manage.py verify_assignment`` asserts the count against the fixture -- asserted
on the derived number, never on a transcribed one.

**Eligibility is read from the database, not from ``fixtures.json``.** The engine
is an application feature the organizer runs against whatever the event actually
contains; the fixture is only the data we happen to ship. A planner that read the
fixture would be a fixture re-serializer wearing a solver's clothes.

**Siblings are a *pair* exclusion, not a project exclusion.** ``prj_07`` and
``prj_41`` are the same team, track, title and repo, submitted 13h28m apart. A
judge who reviews both is not providing independent evidence, so once a judge is
assigned to one, the other is not offered to the same judge. This is the fixture
teaching us something about judging, and it is a rule we would want with no
fixture at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: ``bible/06`` §2.2's seed-noise amplitude, scaled to integer cost units so the
#: whole cost function stays exact. 0.4 * ``_JITTER_SCALE`` == 400.
JITTER_SCALE = 1000

#: Pairs whose status is real work in flight. A planner may not shuffle these.
#: `assigned` is deliberately absent: an assignment nobody has opened is a
#: proposal, and reshuffling proposals is the whole point of re-planning.
IN_FLIGHT_STATUSES = ("in_progress", "submitted")


@dataclass(frozen=True)
class JudgeNode:
    """A judge on this event, with the tracks they are bound to."""

    user_id: int
    email: str
    display_name: str
    track_ids: frozenset[int]
    event_wide: bool

    @property
    def label(self) -> str:
        return self.display_name or self.email


@dataclass(frozen=True)
class ProjectNode:
    """A project to be assigned, with the constraints that apply to it."""

    id: str
    title: str
    team_name: str
    team_id: int
    track_id: int
    track_name: str
    track_slug: str
    target: int
    #: Projects by the same team in the same track -- the supersede chain plus
    #: any other same-team/same-track sibling, because the rule is about
    #: independence of evidence and not about which row won.
    sibling_ids: frozenset[str]


@dataclass(frozen=True)
class TrackNode:
    id: int
    name: str
    slug: str
    #: The fixture's own track identifier, e.g. ``trk_01``. ``Track.id`` is a
    #: surrogate integer, and a certificate that names ``3`` instead of
    #: ``trk_01`` cannot be checked against ``fixtures.json`` by string
    #: comparison -- which is the whole point of D-11 keeping source keys.
    source_key: str
    target: int
    project_ids: tuple[str, ...]
    judge_user_ids: tuple[int, ...]


@dataclass
class AssignmentGraph:
    """The eligibility structure, with the counts that make it checkable."""

    event_id: str
    tracks: list[TrackNode]
    judges: list[JudgeNode]
    projects: list[ProjectNode]
    #: ``(judge_user_id, project_id)`` pairs that are eligible. Sorted, so
    #: anything derived from it -- including the seeded jitter -- is stable.
    pairs: list[tuple[int, str]] = field(default_factory=list)
    #: Why each excluded pair was excluded, for the organizer's screen. Keyed
    #: ``(judge_user_id, project_id)`` -> reason slug. Diagnostic only: the
    #: solver never reads it, and it is deliberately allowed to be empty.
    excluded: dict[tuple[int, str], str] = field(default_factory=dict)

    # ----------------------------------------------------------------- counts

    @property
    def edge_count(self) -> int:
        """The number ``bible/06`` §2.2 says a test must pin."""
        return len(self.pairs)

    @property
    def judge_count(self) -> int:
        return len(self.judges)

    @property
    def project_count(self) -> int:
        return len(self.projects)

    @property
    def node_count(self) -> int:
        """Flow-graph nodes: source, one per track, one per project, one per
        judge, sink."""
        return 2 + len(self.tracks) + len(self.projects) + len(self.judges)

    def demand(self) -> int:
        """Total assignments required to hit every track's target."""
        return sum(track.target * len(track.project_ids) for track in self.tracks)

    def demand_for(self, track: TrackNode) -> int:
        return track.target * len(track.project_ids)

    def by_track(self) -> dict[int, TrackNode]:
        return {track.id: track for track in self.tracks}


# --------------------------------------------------------------------- builder


def build_graph(event, *, respect_in_flight: bool = True) -> AssignmentGraph:
    """Derive the eligibility graph for ``event`` from the database.

    ``respect_in_flight`` is the continuity rule, and it is a parameter rather
    than a constant because the two callers want opposite things:

    * **The organizer's screen** passes ``True``. A judge who has opened a
      project keeps it. Disrupting in-flight judging is not a tidying decision.
    * **The feasibility check** passes ``False``. The question being answered is
      "is this panel capable of covering this event at all?", and a panel that
      already has 126 reviews in progress does not become more or less capable
      because we froze them. Holding in-flight work in the graph would report a
      shortfall that is an artefact of the freeze rather than a property of the
      panel -- which is exactly the "a refusal must name its real cause" rule,
      applied to a diagnosis.
    """
    from reviewer.accounts.models import RoleBinding
    from reviewer.projects.models import Project
    from reviewer.reviews.models import Assignment
    from reviewer.teams.models import TeamMembership

    tracks = list(event.tracks.all())
    projects = list(Project.objects.filter(event=event).order_by("id"))

    # -- judges: one per user holding a judge binding, with their track set ----
    bindings = list(
        RoleBinding.objects.filter(event=event, role="judge").select_related("user", "track")
    )
    by_user: dict[int, dict] = {}
    for binding in bindings:
        entry = by_user.setdefault(
            binding.user_id,
            {"tracks": set(), "event_wide": False, "user": binding.user},
        )
        if binding.track_id is None:
            entry["event_wide"] = True
        else:
            entry["tracks"].add(binding.track_id)

    judges = [
        JudgeNode(
            user_id=user_id,
            email=entry["user"].email,
            display_name=entry["user"].display_name,
            track_ids=frozenset(entry["tracks"]),
            event_wide=entry["event_wide"],
        )
        for user_id, entry in sorted(by_user.items())
    ]

    # -- the submitting team of every project, for the membership exclusion ----
    team_members: dict[int, set[int]] = {}
    for membership in TeamMembership.objects.filter(team__event=event).values_list(
        "team_id", "user_id"
    ):
        team_members.setdefault(membership[0], set()).add(membership[1])

    # -- siblings: same team AND same track -----------------------------------
    by_team_track: dict[tuple[int, int], list[str]] = {}
    for project in projects:
        by_team_track.setdefault((project.team_id, project.track_id), []).append(project.id)

    project_nodes: list[ProjectNode] = []
    for project in projects:
        track = next(t for t in tracks if t.id == project.track_id)
        project_nodes.append(
            ProjectNode(
                id=project.id,
                title=project.title,
                team_name=project.team.name,
                team_id=project.team_id,
                track_id=project.track_id,
                track_name=track.name,
                track_slug=track.slug,
                target=track.effective_target(),
                sibling_ids=frozenset(
                    pid
                    for pid in by_team_track[(project.team_id, project.track_id)]
                    if pid != project.id
                ),
            )
        )

    # -- pairs already in flight, for continuity ------------------------------
    in_flight: set[tuple[int, str]] = set()
    if respect_in_flight:
        in_flight = set(
            Assignment.objects.filter(event=event, status__in=IN_FLIGHT_STATUSES).values_list(
                "judge_id", "project_id"
            )
        )

    pairs: list[tuple[int, str]] = []
    excluded: dict[tuple[int, str], str] = {}
    for judge in judges:
        for project in project_nodes:
            reason = _ineligible(judge, project, team_members, in_flight)
            if reason is None:
                pairs.append((judge.user_id, project.id))
            else:
                excluded[(judge.user_id, project.id)] = reason

    track_nodes = [
        TrackNode(
            id=track.id,
            name=track.name,
            slug=track.slug,
            source_key=track.source_key,
            target=track.effective_target(),
            project_ids=tuple(p.id for p in project_nodes if p.track_id == track.id),
            judge_user_ids=tuple(
                j.user_id for j in judges if j.event_wide or track.id in j.track_ids
            ),
        )
        for track in tracks
    ]

    return AssignmentGraph(
        event_id=str(event.pk),
        tracks=track_nodes,
        judges=judges,
        projects=project_nodes,
        # Sorted so the jitter draw -- and therefore the whole plan -- is stable
        # regardless of the order Django happened to return rows in.
        pairs=sorted(pairs),
        excluded=excluded,
    )


def _ineligible(
    judge: JudgeNode,
    project: ProjectNode,
    team_members: dict[int, set[int]],
    in_flight: set[tuple[int, str]],
) -> str | None:
    """The reason this pair cannot be assigned, or ``None`` if it can.

    **Order matters and is not arbitrary.** The cheapest, most decisive checks
    run first so the diagnostic reasons a reader sees are the *primary* ones. A
    judge on the wrong track is reported as ``no_track_binding`` even if they are
    also on the submitting team, because "not bound to this track" is the fact
    that explains the missing edge and the other is a coincidence of the fixture.
    """
    if not judge.event_wide and project.track_id not in judge.track_ids:
        return "no_track_binding"
    if judge.user_id in team_members.get(project.team_id, ()):
        return "submitting_team_member"
    if (judge.user_id, project.id) in in_flight:
        return "already_in_flight"
    # Siblings: if this judge is already on one member of a same-team/same-track
    # group, the other is not offered. Checked against the in-flight set rather
    # than against the whole plan, because within one plan the solver's per-pair
    # capacity of 1 plus the sibling rule would need a second pass to enforce
    # properly -- and the honest thing is to enforce the part that is decidable
    # now and say so, rather than pretend.
    for sibling in project.sibling_ids:
        if (judge.user_id, sibling) in in_flight:
            return "sibling_already_in_flight"
    return None
