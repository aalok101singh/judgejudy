# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-05 — Isolation enforcement, dashboard, exports, event editor ☕

**8h** · **Phase E** · **Gate:** none (BREAK-2 is the next gate, tag
`v-t2-verified`)

### FEAT-04 is built and verified. The acceptance line passed on all three clauses.

`build-plan.md` Phase D, on a clean volume:

| Clause | Result |
|---|---|
| a feasible instance assigns | **pass** — 123 of 123, tightest capacity **6** found by search, not guessed |
| the capacity-5 instance reports infeasible with a **named min-cut** | **pass** — `trk_01` and `trk_08` each short by **3**, three bottleneck judges named each |
| the seeded tiebreak reproduces byte-for-byte | **pass** — two independent runs, identical SHA-256 over 123 pairs |

**Everything in `bible/06` §2.1a and §2.3 reproduced exactly** — the curve
(c=5 → 117/123, c=6 → 123/123), demand 123, mean load 4.10, and all six
remedies. **Two figures in §2.2 did not** (F-62).

### FEAT-05 scope

**Acceptance line, from `build-plan.md` Phase E — both, on a clean database:**
`run.py` passes T2-4 and T2-5; the T1/T2 `verified` ceiling is expected and
explained in the README.

That means the four T2 checks, which have been failing with real URLs since the
first commit:

| Check | Needs | Why it is still 404 |
|---|---|---|
| `judge sees own scores` | `GET /api/v1/judge/scores` → 200 as judge_a | the DRF surface does not exist |
| `judge cannot see peer scores` | 401/403 as judge_b, and 200 as judge_a to the same URL | same |
| `participant blocked` | 401/403 as participant | same |
| `csv export works` | `GET /api/v1/export.csv` → 200 as organizer | the export does not exist |

**This is the tier that matters and the trap is live again.** D-02 applies to
every one of them, and the acceptance gate already has the machinery to catch a
false pass: `tools/expected_checks.json` carries a precondition per check, and
`judge cannot see peer scores` already has `judge_scores_route_exists` waiting.
**Flipping an expectation to `pass` is only correct when the feature that owns it
is done AND its acceptance line has passed** — the file says so, and the
mutation harness is what enforces it.

**The export header is `functionality, quality, innovation`** — the fixture's
*key* order, not the order values appear in a row (F-04). Getting it backwards
transposes two columns in every export and nothing else catches it.

**Also in scope:** the judge and organizer dashboards, and the admin event
editor. And **F-51** lands here properly: the question of whether a judge who
*also* organises may read their own peers' scores is a product decision, the
accessor currently refuses, and FEAT-05 owns the routes that reach it.

### The two questions, and neither is mine to answer

- **F-51** — `for_actor_and_subject` refuses a judge-organizer asking about a
  peer, while `for_actor` alone hands that same user the whole event. **The code
  is kept and the docstring corrected**, because the strict reading is the safe
  one. The finding is deliberately left `fixed` rather than `closed` and
  **`fixed` blocks completion on purpose**: a repair is not done until a review
  has looked at the result. FEAT-05 builds the route, so FEAT-05 owns the
  decision.
- **D-12 scope** — the ballot-order and voting work is FEAT-06 and must not be
  pulled forward. If a T2 item looks like it needs it, it does not.

### Do not

- **Do not claim T2** until T2-4 and T2-5 actually pass. The report prints
  `claimed` against `verified` and the overclaim branch is mutation-tested.
- **Do not move `submissions_close`.** It is in the past because that is what
  makes the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**

### State

| | |
|---|---|
| **Status** | **FEAT-05 not started.** FEAT-04 built and verified; its acceptance line passed on all three clauses |
| **Started** | — |
| **Elapsed** | 0h of 8h (FEAT-05) |
| **Last touched** | FEAT-04, 2026-09-29 — `claimed T1, verified T1`, 340 tests, 18/18 gate mutations + 16/16 new, 68/68 spec, lint clean |
| **Next action** | read `bible/07` (the threat model) and `bible/05` §9 (the API surface), then build the scoped score endpoint first — it is the check everything else is judged against |
