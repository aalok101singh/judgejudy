# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-06 — Public surface: voting, comments, ballot order, influence report ☕

**9h** · **Phase F** · **Gate:** none (BREAK-3 is the next gate, tag
`v-t3-verified`)

### FEAT-05 is built and verified. The acceptance line passed on both clauses.

`build-plan.md` Phase E, on a clean volume:

| Clause | Result |
|---|---|
| `run.py` passes T2-4 and T2-5 | **pass** — and in fact **7 of 7 checks pass**, `claimed T1, verified T1 T2` |
| the T1/T2 `verified` ceiling is expected and explained in the README | **pass** — explained as arithmetic in their checker, not as a gap |

**All four T2 checks, failing with real URLs since the first commit, now pass.**
Each passes with a **precondition**, so the pass means something: the peer URL is
probed with the checker's own credential and the refusal is required to *name*
the guard that produced it. Without that, a 403 from CSRF satisfies the check —
F-40, in the layer F-40's own repair was written for.

### What the previous session decided, and what carries forward

- **F-51 is closed, and it went against the interim code.** The guard is now
  `actor.is_judge and not actor.can_read_all_reviews`, so the two accessors agree.
  The reason matters: the strict reading was not the safe one, it was the
  **incoherent** one, because the organizer-scoped export contains every score
  and so the refusal protected nothing. **A judge-organizer can read every score
  today.** The rule that should stop that is FEAT-06's.
- **F-69 is a named gap for FEAT-07, not this feature.** `Review.source_key` is
  inherited from D-11 and **never written by the loader**, so the export's first
  column was 126 empty cells until a test that checks every cell caught it. The
  export falls back to the `(judge, project)` natural key. Populating the column
  belongs to FEAT-07, which owns `source_key` and the byte-identical round trip.
- **44/44 mutations**, 374 tests, 68/68 spec, lint clean.

### FEAT-06 scope

**Acceptance line, from `build-plan.md` Phase F — on a clean database:**
a bias-attack harness shows the estimator is zero-mean under position bias; the
influence report renders for a synthetic attack.

### The two questions, and neither is mine to answer

- **The leaderboard cell.** `isolation_proof` prints `?` for the aggregate,
  export and audit columns, and its own "STILL NOT PROVEN" list names *the
  aggregate cell nobody tests and everybody forgets*: **that a judge is refused
  the leaderboard while judging is open.** The export and the audit now have
  accessors and routes, so those cells can be filled; the aggregate is FEAT-06's,
  and it is the one that makes "isolation" mean something during judging rather
  than after it.
- **D-12 scope** — ballot order and voting are FEAT-06 and must not be pulled
  forward, and must not be overclaimed: randomisation makes bias zero-*mean*,
  not zero.

### Do not

- **Do not claim T2.** It is earned — all four checks pass — but **the claim is
  made at BREAK-2, in writing, by the human.** `.dogfood.toml` still says
  `claimed = ["T1"]` and that is correct until then. The report already prints
  `claimed T1, verified T1 T2`, which is the ceiling `run.py` can ever print.
- **Do not move `submissions_close`.** It is in the past because that is what
  makes the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**

### State

| | |
|---|---|
| **Status** | **FEAT-06 not started.** FEAT-05 built and verified; its acceptance line passed on both clauses |
| **Started** | — |
| **Elapsed** | 0h of 9h (FEAT-06) |
| **Last touched** | FEAT-05, 2026-09-29 — `claimed T1, verified T1 T2`, **7 of 7 checks**, 374 tests, 44/44 mutations, 68/68 spec, lint clean |
| **Next action** | fill the export and audit cells of the `isolation_proof` matrix — they now have accessors and routes and still print `?` — then build the leaderboard refusal that is the aggregate cell, then voting and the influence report |
