# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-07 — Bulk IO, signed records, `results_hash`, widget, OpenAPI

**11h** · **Phase G** · **Gate:** BREAK-4 ☕ (the T4 claim decision)

### FEAT-06 is complete and FEAT-08 is complete. T1 and T2 are CLAIMED.

All five REQ-T3 requirements ship and are tested (voting + identity budget +
tally, comments, results hidden on both surfaces, randomised ballot order, the
influence report). **And T3 is deliberately NOT claimed.** The T3 increment and the
normalization proof are archived:

| Feature | Archive |
|---|---|
| FEAT-06 | `history/features/06-public-results-page.md` (+ `-influence-report`, `-bias-attack-harness`) |
| FEAT-08 | `history/features/08-normalization-proof.md` |
| BREAK-3 | `history/features/break-3-t3-claim.md` |

**The T3 decision, decided by the human on 2026-09-29: built, not claimed.**

```
claimed: T1 T2 T3
claimed T1 T2 T3, verified T1 T2
note: claimed but not verified: T3
  GATE FAILED:
    - OVERCLAIM: .dogfood.toml claims T3 but the report verified T1 T2.
```

Proved by running it, then reverted. `.dogfood.toml` says `claimed = ["T1", "T2"]`.
The mechanism is arithmetic, not a gap: **`run.py` contains no T3 and no T4 checks
at all** — 3 T1 checks and 4 T2 checks, seven in total — so `verified` is
prefix-locked to `T1 T2` and any claim beyond T2 lands in the overclaim set.
`v-t3-verified` is therefore **not tagged**; tagging it while the gate prints
OVERCLAIM would assert the opposite of what the machine says.

> **This applies to T4 exactly as it does to T3.** BREAK-4 asks "how much of T4 is
> green?", and the answer will be *all of it or none of it* — a T4 claim cannot be
> partially verified, because there is no T4 check to fail or pass. **So FEAT-07 is
> worth building as a brief deliverable, not as a claimable tier.** The honest
> report line is that the organizers' program cannot verify T3 or T4, and we say so
> rather than working around it. Recorded as **F-91 [P1], accepted by decision**,
> and in `bible/08` §13 as a named cut with its regret.

### FEAT-08's finding, in one line

**No detectable judge-severity effect.** Between-judge variance `0.0217` sits
*below* the `0.0971` sampling-noise floor; permutation p = 0.227 (location) and
0.538 (dispersion). The estimator is built and **not applied**, because it would
move all 126 scores by ~0.57 rubric points for a measured null. Full generated
tables in `docs/REAL-FIXTURE-RESULTS.md`; **F-92 [P1]** records that two of
`bible/06`'s published numbers did not regenerate.

### FEAT-07 scope

**Acceptance line, from `build-plan.md` Phase G:** the round-trip test passes
byte-for-byte; signature and tamper rejection pass; the widget renders offline.

Five items, ordered by value-per-hour rather than by the plan's listing order:

| # | Item | Why this order |
|---|---|---|
| 1 | `export run` / `import run`, **byte-identical** including natural keys (`source_key`, D-11) | **Closes F-69, which is open right now.** `Review.source_key` is inherited from D-11 and **never written by the loader**, so the export's first column is 126 empty cells. FEAT-07 owns `source_key` and the round trip. Starting here because it discharges a live finding. |
| 2 | `results_hash` — audit chain head at publication, **replicated into every signed judge record** (D-09) | Small, and it is the load-bearing half of item 5 |
| 3 | OpenAPI 3.1 via `drf-spectacular` | Cheapest win in the block |
| 4 | Embeddable results widget, pure static HTML + JSON | Self-contained; renders offline |
| 5 | Ed25519 signed records, in-toto Statement v1 inside DSSE, **keys on their own volume** | The largest item. Built last so the round trip it signs is already proven |

### What is open and might bite

- **F-69** — `source_key` is never written on import. Item 1's whole job.
- **`verify_census` and the `isolation_proof` already depend on the export
  shape.** Changing the export to add a populated first column must not move a
  check's meaning; `run.py` reads `/api/v1/export.csv`? **It does not** — it reads
  `/`, the scoped score endpoint, and the peer-refusal endpoints — so adding a
  column is additive, but **verify this rather than assuming it.**
- **F-51 stands**: a judge-organizer can read every score today. Item 1 must not
  widen that; a bulk export is exactly the surface that would.

### FEAT-07 increment 1 is DONE: the byte-identical round trip

`reviewer/io/bundle.py`, `manage.py export_run`, `manage.py import_run`,
`Review.objects.for_bulk_transfer()`, and **five natural keys written by the
loader**. **31 tests, 5 mutations.** Archive:
`history/features/07-bulk-io-round-trip.md`.

**Four findings, and not one was found by reading the code** — three by the
escape hatch refusing to do its job, one by the mutation harness:

- **F-93 [P1]** — `Review`, `Score`, `Assignment`, `RoleBinding` and
  `TeamMembership` all had `source_key = NULL`, so **our own escape hatch
  quarantined the data it existed to restore.** It arrived in four disguises
  (a quarantine report, two NOT NULL violations, and a census miscount), each
  reading as somebody else's bug. The demo logins were the sixth symptom and
  the one that mattered: a restore dropped them and **the demo stopped working
  on the second boot.** The repair is `TestEveryLoadedRowHasANaturalKey`, whose
  exemption list is asserted to be **empty**.
- **F-94 [P1]** — **the acceptance line passed with the importer writing
  nothing.** Byte-identical cannot distinguish "restored correctly" from "never
  touched anything"; the empty-database and created-not-updated assertions are
  what give it meaning.
- **F-95 [P2]** — rule 1 refused nothing: it checked the archive's **own**
  compatibility claim. A self-certifying archive is not a certificate.
- **F-96 [P2]** — quarantining a malformed row left the transaction poisoned, so
  one bad row in 10,000 restored **nothing**. Fixed with a savepoint.

### The next four items, in the order they earn their place

| # | Item | Note |
|---|---|---|
| 2 | `results_hash` — audit chain head at publication, **replicated into every signed judge record** (D-09) | Small, and it is the load-bearing half of item 5. The chain head already survives the round trip, asserted |
| 3 | OpenAPI 3.1 via `drf-spectacular` | Cheapest win in the block |
| 4 | Embeddable results widget, pure static HTML + JSON, renders offline | Self-contained |
| 5 | Ed25519 signed records, in-toto Statement v1 in DSSE, **keys on their own volume** | Largest. Last, so the round trip it signs is already proven |

### Do not

- **Do not claim T3 or T4.** It turns the gate red. Proved twice; reverted twice.
- **Do not move `submissions_close`.** It is in the past because that is what makes
  the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**
- **Do not retype a gate's own check count.** `verify_spec` fails if you do (F-72).
- **Do not type a count from arithmetic.** I typed "91 mutations" into the FEAT-08
  archive and the run printed 90 — F-72 happening to me, in a commit about not
  transcribing numbers. **Measure, then write.**

### State

| | |
|---|---|
| **Status** | FEAT-07 increment 1 done (the byte-identical round trip); items 2-5 not started. FEAT-01..FEAT-06 and FEAT-08 built, verified, committed |
| **Started** | 2026-09-29 |
| **Last touched** | FEAT-08 committed as `8116125`: **636** tests, `95/95` mutations, spec `72/72`, lint clean, `just check` **GREEN** at 7 of 7, acceptance-report diff empty |
| **Claim** | `claimed = ["T1", "T2"]`. T3 fully built and **unclaimed** (F-91, accepted by decision). `v-t3-verified` untagged, deliberately |
| **Next action** | **FEAT-07 item 2: `results_hash` at publication, replicated into every signed judge record (D-09).** Then OpenAPI, then the widget, then DSSE. Item 1 is done and F-93 closed five tables with no natural key. |
| **Tag** | `v-t1-verified` (BREAK-1), `v-t2-verified` (BREAK-2) |
