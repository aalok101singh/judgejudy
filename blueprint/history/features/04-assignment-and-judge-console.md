# FEAT-04 — Assignment engine, min-cut certificate, judge console

**Completed:** 2026-09-29 · **Planned:** 7h · **Actual:** ~7h · **Gate:** none
(next gate is BREAK-2, tag `v-t2-verified`)

## The acceptance line, and whether it passed

`build-plan.md` Phase D, all three clauses, on a clean database:

| Clause | Result |
|---|---|
| a feasible instance assigns | **pass** — 123 of 123, tightest capacity **6** found by search |
| the capacity-5 instance reports infeasible with a **named min-cut** | **pass** — `trk_01` and `trk_08` each short by **3**, three bottleneck judges named each, both at capacity |
| the seeded tiebreak reproduces byte-for-byte | **pass** — two independent runs, identical SHA-256 over 123 pairs |

**And every number in `bible/06` §2.1a and §2.3 reproduced exactly**, which is the
part worth saying out loud, because two figures in the same section did not
(F-62). Confirmed: the curve (c=5 → 117/123, c=6 → 123/123), demand 123, mean
load 4.10, and all six remedies — `k=1 → 4×5=20 ≥ 18`, `⌈18/3⌉ = 6`,
`⌊15/6⌋ = 2`.

## What was built

- **`reviewer/assignment/`** — a package, not an app, like `isolation` and
  `importer`: no model, so `INSTALLED_APPS` would add a migration that creates
  nothing. Three modules split by *what has to be true* rather than by size.
  - `flow.py` — min-cost max-flow, **pure Python**. Dinic's for the capacity
    search, SSP with Johnson potentials for the tidying. **No scipy, no
    networkx**, and the measured cost of that decision is 0.15 ms per solve.
  - `graph.py` — the five eligibility rules, read from the database, with the
    edge count exposed so it can be pinned.
  - `planner.py` — capacity search, min-cost tidying, min-cut diagnosis, remedies,
    sole-cover detection, the sibling post-pass.
- **`manage.py verify_assignment`** — re-derives every number and prints the
  certificate. **Now inside `just check`**, so a reviewer gets it from the one
  command. Exits non-zero.
- **`reviewer/reviews/console.py`** — the judge console: assignments, the rubric,
  draft and submit; plus the organizer's plan screen.
- **Two migrations' worth of schema** — `Event.assignment_seed` and
  `Event.judge_capacity`, both nullable or defaulted, plus a check constraint that
  a capacity of zero is impossible and that NULL means "no organizer cap".
- **49 new tests** (291 → 340) in two modules.

## The decision that mattered most: the certificate, and F-61

`bible/06` §2.3 says the diagnosis should name "the judge nodes on the sink side
of that cut". **Implemented literally, that set is empty**, and the certificate
printed a deficiency with nobody on it — which is not a diagnosis, and which
looks exactly like a feature that works.

The reason is a property of the canonical minimum cut: its source side is reached
through a track node that still has residual capacity, and from there through
exactly the projects that went **un**covered, whose judge edges are untouched and
therefore fully residual. **The judges of a deficient track are on the source
side.** Naming the sink side names nobody.

The correct reading is the same cut one arc later — every saturated
`judge → sink` arc crosses it — so the bottleneck judges are the eligible judges
**whose capacity is exhausted**. On `trk_01` at c=5 that is all three, by name,
each marked `AT CAPACITY`, which is the sentence an organizer acts on: *there is
no fourth judge, and these three cannot take a 16th project between them.*

The general point is the one this project keeps paying for: **a feature that
returns structurally valid output containing nothing is indistinguishable from a
feature that works.** A test asserting `bottleneck_judges == ()` would have
passed forever.

## The other three that mattered

**F-60 (P1) — the solver was wrong and never said so.** The textbook
successive-shortest-path updates its Johnson potentials incrementally, and that is
wrong: a node that drops out of reachability keeps a stale potential, an arc from
it into a reached node gets a negative reduced cost, and Dijkstra then returns a
path that is not shortest. The result is a **feasible** flow with a slightly worse
total cost — a slightly worse spread of judge workloads, on the feature whose
whole claim is that the spread is as fair as it can be.

Found by **testing the solver against a second, independently written algorithm**
(plain Bellman-Ford SSP, no potentials) over 1,500 random instances of the
planner's exact network shape. Now 1,500/1,500 agree. The repair recomputes
potentials from Bellman-Ford on every augmentation: at 81 nodes that is 0.15 ms,
so **correctness was worth more than the asymptotics, and the asymptotics are
exactly where this bug lives.**

**F-62 (P2) — the bible's edge count is wrong.** §2.2 says "40 nodes and 77
edges" and builds its `assert network.nnz == expected` instruction on it. Built
and counted, the network is **81 nodes and 199 edges**. 77 is unreachable by any
reading: §2.1a's own table implies 214 before exclusions. So §2.1a and §2.2
disagree inside one file, and the assertion §2.2 asks for **would have pinned the
wrong number and passed.**

**F-64 (P2) — the fixture never exercises the conflict rule.** Not one of the 30
fixture judges is a member of any of the 40 teams, so
`submitting_team_member` is *unreachable on shipped data*. A test asserting "the
exclusion rules are covered" would have been lying, and the rule would have
shipped untested behind a green gate. It now has a synthetic test, and the
reachable/unreachable split is asserted explicitly so the gap stays visible.

## How it was verified

| | |
|---|---|
| Acceptance line | **all three clauses pass** on a clean volume |
| `just check` | **GATE GREEN**, now including `verify_assignment` |
| Suite | **340** (291 → 340; 31 engine + 18 console) |
| Mutations, new modules | **16/16** — 8 against the engine, 8 against the console, each naming the test that must notice |
| Mutations, existing gates | **18/18** re-run after `ruff format` (F-46) |
| `tools/verify_spec.py` | **68/68** (67 → 68: F-59's recipe check) |
| Lint | clean — and the isolation rule caught **two unscoped `Review` reads I wrote in the test helpers**, which is D-01 working |
| Migrations | `makemigrations --check` clean |
| Solver vs independent oracle | **1,500/1,500** random instances agree |
| Cold start | re-measured below |

## What I would tell the next session

**`reviewer/assignment/` is a package and its management command is not in it.**
`verify_assignment` lives in `reviewer/reviews/management/commands/` because a
package's commands are not discoverable — I lost a cycle to that. It matches the
existing convention (`isolation_proof` is in `reviews`).

**Two limitations are documented in the code, not hidden.** Sibling independence
is a post-pass rather than a network constraint, because a flow network cannot
express "these two project nodes must not share a judge"; anything the post-pass
cannot re-home is *reported*. And per-judge capacity overrides are not modelled —
one event-wide cap is the policy, and the individual "this judge can only do
four" belongs to the dashboard.

**F-51 is still `fixed`, and `fixed` blocks completion on purpose.** It is a
product decision — should a judge who *also* organises read their own peers'
scores? — and the accessor currently refuses, which is the safe reading. FEAT-05
owns the routes that reach it.

**The next feature should expect the organizers' data to have one more gap in
it.** FEAT-03 found three P1s in its first contact with the fixture; FEAT-04
found **none**, because the data was already loaded and verified twice. The rate
is a function of how much genuinely *new* input meets our code, and FEAT-05 is
mostly new code over old data. Expect F-64 to be the template for what to look
for: **a rule the fixture cannot reach is a rule with no coverage, and the suite
must say so out loud rather than let a green gate imply otherwise.**
