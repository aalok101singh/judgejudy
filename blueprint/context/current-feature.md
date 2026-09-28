# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-04 — Rubric, assignment + min-cut, judge console, reviews ☕

**7h** · **Phase D** · **Gate:** none (BREAK-2 is the next gate, tag
`v-t2-verified`)

### BREAK-1 is closed. The T1 claim is made and tagged.

Run at 2026-09-28 against a clean volume. The full Phase 0 pass reproduced
before anything was written down:

| | |
|---|---|
| `run.py` | **`claimed T1, verified T1`** — 3 of 3 T1 checks PASS, 4 of 4 T2 checks FAIL |
| Acceptance gate | `GATE OK: no regressions, no stale expectations, no false passes` |
| `just check` | **GATE GREEN** — re-run three times, identical each time |
| `just prove-offline` | **PASS** — healthy at **8.0 s** under `--network none` |
| `just mutation-test` | **18/18** |
| `tools/verify_spec.py` | **67/67** |
| Suite | **291 tests** (82 s) |
| Cold start | **11.8 s** against the 60 s budget |
| `acceptance-report.txt` | regenerates **byte-identical**; `git diff` empty |
| Recipe audit | every `just` recipe named in a document exists (F-59 is the finding that no check enforces this) |
| Tag | **`v-t1-verified`** |

**The claim and the gap, in the same breath.** T1 is earned: all three checks
pass, and they pass *for the right reason* — the acceptance gate re-sends the
checker's own request and requires `assert_open_for_submission` in the body, so
a CSRF rejection, a 404 or a 401 can no longer stand in for the deadline (F-40).
**T2 is four checks and none of them runs**; the judge console, the scoped score
endpoint and the CSV export are FEAT-04 and FEAT-05. `verified` is prefix-locked
and there are no T3 or T4 checks at all, so even a flawless build would print
`verified T1 T2` (`bible/03` §2).

### What BREAK-1 found, and one repair

Three findings, none blocking: **F-57** (the ledger's own *Open* section held a
closed finding and called it live), **F-58** (the cold start is the only
*instrument-measured* number in the project and the only one nothing regenerates
— documents said 11.6 s, it measures 11.8 s), and **F-59 open** (no check that a
documented `just` recipe exists; that gap has now cost F-47, F-48 and F-56).

**The repair, and it is the thing to carry into FEAT-04.** Writing
`claimed = ["T1"]` broke
`test_the_claimed_tier_list_is_still_empty`, which asserted `claimed == []`.
That test was pinning the **value**, not the **rule**, so it would have failed at
BREAK-2, BREAK-3 and BREAK-4 too — three times teaching a reader that the claim
is not allowed to change rather than that it has to be earned. It is now
`test_the_claim_names_only_tiers_the_gate_can_verify`: it parses the tier split
out of `run.py`, reads the expectations from `tools/expected_checks.json`, and
mirrors `run.py`'s prefix lock. **Verified by three deliberate corruptions**, each
caught with its specific reason: claiming T2, a check `run.py` declares that the
expectations file does not name, and a T1 check regressing to `fail`.

### FEAT-04 scope

**Acceptance line, from `build-plan.md` Phase D — all three, on a clean
database:** a feasible instance assigns; the capacity-5 instance reports
infeasible with a **named min-cut**; the seeded tiebreak reproduces
byte-for-byte.

Three things are already in place, so the feature starts from a populated
schema: the seeded `Rubric`/`Criterion` rows with **non-uniform weights**
(functionality 0.40, innovation 0.35, quality 0.25), the **126 synthesised
`Assignment` rows** the loader derives from the score rows, and
`Review.objects.for_actor()` with its scope receipt.

`ε = 0.5` is the legible normalization default and ships as such; the
empirical-Bayes `τ²` estimator is D-04's reported one. **Do not tune to the
published target** — `k = 0` scores better than the value we ship.

**Two questions land here:**

- **F-51** — should a judge who *also* organises be refused their own peers'
  scores? The accessor currently refuses (the safe reading), the docstring now
  says so, and the finding is deliberately left `fixed` rather than `closed`.
  FEAT-04 owns the console, so it owns the decision. **`fixed` blocks completion
  on purpose — it cannot be closed until a review has looked at the result.**
- **F-59** — the missing recipe-existence check, ~15 min, recommended here. It
  mechanically prevents a fourth instance of a defect class that has cost three
  findings.

### Do not

- **Do not claim T2** until T2-4 and T2-5 actually pass. The report prints
  `claimed` against `verified`, and the overclaim branch is mutation-tested.
- **Do not move `submissions_close`.** It is in the past because that is what
  makes the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**

### State

| | |
|---|---|
| **Status** | **FEAT-04 not started.** BREAK-1 closed: claim made, gate green, `v-t1-verified` tagged |
| **Started** | — |
| **Elapsed** | 1h of 1h (BREAK-1), 0h of 7h (FEAT-04) |
| **Last touched** | BREAK-1, 2026-09-28 — `claimed T1, verified T1`, 291 tests, 18/18 mutations, 67/67 spec, cold start 11.8 s, offline 8.0 s |
| **Next action** | read `bible/06` (assignment, min-cut, the seeded tiebreak) and `bible/05` §isolation, then build the assignment engine against the acceptance line above |
