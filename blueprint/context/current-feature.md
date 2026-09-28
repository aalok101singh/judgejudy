# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-04 — gated on BREAK-1, the T1 claim ☕

**1h of break, then 7h of feature** · **Phase D** · **Gate:** a tier claim made
in writing against what is actually green, then `v-t1-verified`

### BREAK-1 first. FEAT-04 does not start until the tag exists.

The brief is explicit that the claim is decided at a break and not in advance,
and `AGENTS.md` repeats it. **Everything BREAK-1 needs is already measured** —
the numbers are in the FEAT-03 archive and the run below reproduces them. What
is left is judgement, and judgement is the human's.

### Protocol — one hour, fixed

1. **Clean `down -v` → `up`, network off.** `just check` does this itself, so
   step 1 is *already done* by running it. Do not skip it on a warm volume.
2. **`just check`** — the gate. It is currently green.
3. **`just prove-offline`** and **`just mutation-test`** — outside the gate, run
   at every break.
4. **Update the slippage ledger** (`bible/08` §1c). This is the first entry, so
   the format is being set here.
5. **Decide the claim and write it down.** `claimed = ["T1"]` in
   `.dogfood.toml`, with the reason beside it.
6. **Tag `v-t1-verified`** and push.

### The evidence, as measured

| | |
|---|---|
| `run.py` | `claimed nothing, verified T1` — **3 of 3 T1 checks PASS** |
| Acceptance gate | `GATE OK: no regressions, no stale expectations, no false passes` |
| `just check` | green end to end, clean volume, network-independent build |
| `just prove-offline` | PASS — boots under `--network none`, healthy at **8.0 s** |
| `just mutation-test` | **18/18** deliberate corruptions caught |
| `tools/verify_spec.py` | **67/67** |
| Suite | **291 tests** |
| Cold start | **11.6 s** to a serving page against the 60 s budget |
| `verify_census` | 14 tables match the fixture, both invariants on both sides |
| `isolation_proof --require-data` | the real matrix, no `?` in the three decidable columns |

### The claim to make, and the gap to name with it

**T1 is earned.** All three checks pass, and — this is the part that matters —
they pass *for the right reason*. The `closed event refuses submissions` check
used to pass on a 404; the gate now re-sends the checker's own request and
requires `assert_open_for_submission` in the response body, so a CSRF rejection
or a 401 can no longer stand in for the deadline.

**Name the gap in the same breath:** T2 is four checks and **none of them runs**.
The judge console, the scoped score endpoint and the CSV export arrive in
FEAT-04 and FEAT-05, and until they do, `run.py` prints their failures with real
URLs. `verified` is prefix-locked and there are no T3 or T4 checks at all, so
even a flawless build would print `verified T1 T2` (`bible/03` §2).

### Do not

- **Do not claim T2.** Nothing about T2 is green.
- **Do not edit `acceptance-report.txt` by hand.** It is generated; `just
  report` produces it, and the panel runs the identical program.
- **Do not move `submissions_close`.** It is in the past because that is what
  makes the deadline check meaningful.

### State

| | |
|---|---|
| **Status** | **BREAK-1 ready** — every input the break needs is measured and green. FEAT-04 unblocked the moment the tag exists |
| **Started** | — |
| **Elapsed** | 0h of 1h (break), then 0h of 7h (FEAT-04) |
| **Last touched** | FEAT-03 verified and committed; `just check` green, `verified T1`, 291 tests, 18/18 mutations, 67/67 spec, cold start 11.6 s (`../history/features/03-loader-gallery-deadline-guard.md`) |
| **Next action** | run the six steps above, and the sixth one is the one that matters: **write the claim down** |

---

## FEAT-04, once the break is tagged

**Rubric, assignment + min-cut, judge console, reviews** — 7h. Scope and
acceptance line in `build-plan.md` Phase D.

Three things are already in place and the feature starts from a populated
schema: the seeded `Rubric`/`Criterion` rows with **non-uniform weights**
(functionality 0.40, innovation 0.35, quality 0.25), the **126 synthesised
`Assignment` rows** the loader derives from the score rows, and the
`Review.objects.for_actor()` accessor with its scope receipt.

**One deferred question lands here:** **F-51** — should a judge who *also*
organises be refused their own peers' scores? The accessor currently refuses
(the safe reading), the docstring now says so, and the finding is deliberately
left `fixed` rather than `closed`. FEAT-04/05 own the console and the route
that would reach it, so they own the decision.
