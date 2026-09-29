# Feature History

> One file per completed feature, in order. This is the durable record of **what
> was built, how, and what it cost** — the material the Write Up Quest is built
> on, and the first thing a new session reads to work out where the project
> actually is.
>
> Template: `_TEMPLATE.md`. A feature is archived when its acceptance line in
> `../../build-plan.md` passes on a clean database — not when the code exists.

| # | Feature | Completed | Planned | Actual | Gate |
|---|---|---|---|---|---|
| 00 | [Specification and environment](00-specification.md) | 2026-09-27 | pre-window | pre-window | — |
| 01 | [Skeleton and container](01-skeleton-and-container.md) | 2026-09-28 | 4h | ~4h | — |
| 02 | [Schema and the isolation primitive](02-schema-and-isolation.md) | 2026-09-28 | 5h | ~5h | — |
| 03 | [Loader, identities, gallery, deadline guard](03-loader-gallery-deadline-guard.md) | 2026-09-28 | 5h | ~5h | **BREAK-1** |
| 04 | [Assignment and the judge console](04-assignment-and-judge-console.md) | 2026-09-28 | 7h | ~7h | — |
| 05 | [The T2 surface and the export](05-t2-surface-and-export.md) | 2026-09-29 | 8h | ~8h | **BREAK-2** |
| 06a | [The influence report (D-13)](06-influence-report.md) | 2026-09-29 | — | increment 2 | — |
| 06b | [The bias-attack harness](06-bias-attack-harness.md) | 2026-09-29 | — | increment 3 | — |
| 06 | *in flight* — **both acceptance clauses built**; randomised ballot order, voting, comments and public result hiding remain | | 9h | | **BREAK-3** |

**FEAT-06 is archived in two files** because it is 9h of work and its two
acceptance clauses are separable: the report (increment 2) and the harness
(increment 3). **The feature itself is NOT complete** — the line at the bottom is
the one that matters, and it is the reason the row is not a link.

> **This table said "03 in flight" while FEAT-06 was running** — three features
> stale, on the same class as F-57 and F-66, and `verify_spec` does not check this
> file. Repaired 2026-09-29 at FEAT-06 increment 3. **A staleness check that is not
> mechanical is a note in a document, and a note rots.**

**A note on the ledger.** These archives record *what shipped*. What broke, what
we chose not to fix, and what is still open lives in
[`../../context/findings.md`](../../context/findings.md) — a different file for a
different job. A finding that only exists in a chat transcript has no ID, no
status, and nothing that notices it was reported and never repaired.
