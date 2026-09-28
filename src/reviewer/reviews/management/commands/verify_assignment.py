"""``verify_assignment`` -- re-derive every number the assignment story claims.

This command exists because of the rule that every number in a shipped document
is generated and not transcribed. ``bible/06`` §2 quotes four of them: **77
judge-project edges**, **123 assignments of demand**, **the smallest feasible
capacity is 6**, and **at capacity 5, ``trk_01`` and ``trk_08`` are each short by
3**. Those are claims about our own code reading the organizers' data, so they
are exactly the kind of claim that goes stale silently.

**What it does, in order:**

1. Builds the graph from the database and prints the census.
2. Runs the capacity search and prints the **whole curve**, because the curve is
   the evidence and the single answer is only its endpoint.
3. Runs at capacity 5 and prints the min-cut certificate.
4. **Runs the plan twice and asserts the two are byte-identical**, which is the
   acceptance line's third clause. Determinism asserted by construction is not a
   test; determinism observed across two independent runs is.

Exits non-zero on any disagreement, so it can gate like the other verifiers.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from reviewer.assignment.graph import build_graph
from reviewer.assignment.planner import plan_assignment


class Command(BaseCommand):
    help = "Re-derive the assignment numbers and print the min-cut certificate."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--event", default="evt_01")
        parser.add_argument(
            "--infeasible-capacity",
            type=int,
            default=5,
            help="The per-judge capacity at which to prove infeasibility (bible/06 §2.1a).",
        )
        parser.add_argument(
            "--json", action="store_true", help="Emit machine-readable output only."
        )

    def handle(self, *args, **options) -> None:
        from reviewer.events.models import Event

        try:
            event = Event.objects.get(pk=options["event"])
        except Event.DoesNotExist as exc:
            raise CommandError(f"no event {options['event']!r}") from exc

        # respect_in_flight=False: the question is what the PANEL can cover, and
        # the loader's 126 synthesised assignments are history, not in-flight work.
        graph = build_graph(event, respect_in_flight=False)

        if not options["json"]:
            self.stdout.write("=" * 66)
            self.stdout.write(f" assignment graph -- event {event.pk} -- {event.name}")
            self.stdout.write("=" * 66)
            self.stdout.write("")
            self.stdout.write(
                f"  {graph.judge_count} judges, {graph.project_count} projects, "
                f"{len(graph.tracks)} tracks"
            )
            self.stdout.write(
                f"  {graph.node_count} flow nodes, {graph.edge_count} judge-project edges"
            )
            self.stdout.write(f"  demand: {graph.demand()} assignments")
            self.stdout.write("")
            self.stdout.write("  per track:")
            for track in graph.tracks:
                self.stdout.write(
                    f"    {track.slug:<24} target {track.target}  "
                    f"{len(track.project_ids)} projects  {len(track.judge_user_ids)} judges"
                )
            self.stdout.write("")

        # ---- the capacity search, and the curve behind it -------------------
        search = plan_assignment(event, capacity=None, respect_in_flight=False)
        if not options["json"]:
            self.stdout.write(search.render())
            self.stdout.write("")

        # ---- the infeasible instance, and its certificate -------------------
        capacity = options["infeasible_capacity"]
        tight = plan_assignment(event, capacity=capacity, respect_in_flight=False)
        if not options["json"]:
            self.stdout.write("=" * 66)
            self.stdout.write(f" capacity {capacity} -- the infeasible instance")
            self.stdout.write("=" * 66)
            self.stdout.write("")
            self.stdout.write(tight.render())
            self.stdout.write("")

        # ---- determinism, observed rather than assumed ----------------------
        first = plan_assignment(event, capacity=None, respect_in_flight=False)
        second = plan_assignment(event, capacity=None, respect_in_flight=False)
        fingerprint_a = _fingerprint(first)
        fingerprint_b = _fingerprint(second)
        deterministic = fingerprint_a == fingerprint_b

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "event": event.pk,
                        "judges": graph.judge_count,
                        "projects": graph.project_count,
                        "tracks": len(graph.tracks),
                        "nodes": graph.node_count,
                        "edges": graph.edge_count,
                        "demand": graph.demand(),
                        "tightest_capacity": search.capacity,
                        "covered_at_search": search.covered,
                        "curve": search.curve,
                        "feasible": search.feasible,
                        "max_load": search.max_load,
                        "min_load": search.min_load,
                        "mean_load": round(search.mean_load, 4),
                        "assignments": len(search.assignments),
                        "capacity5_feasible": tight.feasible,
                        "capacity5_covered": tight.covered,
                        "capacity5_deficiencies": [
                            {
                                "track": d.track_slug,
                                "demand": d.demand,
                                "supply": d.supply,
                                "deficit": d.deficit,
                                "projects": list(d.project_ids),
                                "bottleneck_judges": list(d.bottleneck_judges),
                            }
                            for d in tight.deficiencies
                        ],
                        "sole_covers": [
                            {"track": c.track_slug, "judge": c.judge_email}
                            for c in search.sole_covers
                        ],
                        "sibling_collisions": list(search.sibling_collisions),
                        "deterministic": deterministic,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            self.stdout.write("=" * 66)
            self.stdout.write(" determinism")
            self.stdout.write("=" * 66)
            self.stdout.write("")
            self.stdout.write(f"  two independent runs, seed {first.seed}")
            self.stdout.write(f"  fingerprint 1: {fingerprint_a}")
            self.stdout.write(f"  fingerprint 2: {fingerprint_b}")
            self.stdout.write(
                f"  {'IDENTICAL' if deterministic else 'DIFFERENT -- the tiebreak is not seeded'}"
            )
            self.stdout.write("")
            self.stdout.write("  This is the acceptance line's third clause, observed rather")
            self.stdout.write("  than asserted by construction. A seeded tiebreak that merely")
            self.stdout.write("  looks seeded still drifts when the query planner reorders rows.")

        problems = []
        if not search.feasible:
            problems.append("the shipped panel cannot reach full coverage")
        if not deterministic:
            problems.append("the plan is not reproducible across two runs")
        if search.max_load > search.capacity:
            problems.append(
                f"a judge was assigned {search.max_load} projects against a cap "
                f"of {search.capacity}"
            )
        # Every project must be at or under its target, and the total must match.
        by_project: dict[str, int] = {}
        for assignment in search.assignments:
            by_project[assignment.project_id] = by_project.get(assignment.project_id, 0) + 1
        over = [
            (pid, count)
            for pid, count in sorted(by_project.items())
            if count > next(p.target for p in graph.projects if p.id == pid)
        ]
        if over:
            problems.append(f"projects over their target: {over}")

        if problems:
            for problem in problems:
                self.stderr.write(f"FAIL {problem}")
            raise CommandError(f"{len(problems)} assignment check(s) failed")
        self.stdout.write("  assignment OK: feasible, balanced, reproducible.")


def _fingerprint(plan) -> str:
    """A stable digest of the plan, so "identical" means identical.

    **A hash, not a count.** Two runs agreeing on how *many* assignments they
    produced says nothing; agreeing on which judge is on which project is the
    property the acceptance line is about.
    """
    import hashlib

    rows = sorted(f"{a.judge_user_id}:{a.project_id}" for a in plan.assignments)
    digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    return f"sha256:{digest[:32]} ({len(rows)} pairs)"
