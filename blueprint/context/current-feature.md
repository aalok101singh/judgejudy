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

### FEAT-07 increment 2 is built: `results_hash` and the D-09 replication

`reviewer/audit/publication.py`, `manage.py publish_results`, and **18 tests**.
**The claim is that a stranger can recompute it**, and the centrepiece test proves
it: export, wipe, import, recompute the digest from the restored rows, and it
matches. **The escape hatch and the publication claim are the same property viewed
from two sides** -- if you can take the data away and bring it back, the numbers
still describe it.

`results_hash` covers five named fields, so a rename does not invalidate a
publication and a changed score does. The digest is mixed in, so a hash from one
set of scores cannot be presented as the hash of another. An **empty** audit chain
publishes an empty head rather than a placeholder, which would otherwise look like
a chain head and mismatch forever after.

### F-97 [P1, OPEN] -- the signed-records half of T4 has no data path

Grepping `src/` for `JudgeCredential.objects` returns **one hit: the model
definition.** A loaded database holds **zero** `JudgeCredential` and **zero**
`SignedRecord` rows. **F-71 again, one app over** -- `AuditEntry` shipped with a
complete chain and no writer, and `JudgeCredential`/`SignedRecord` ship with
complete schemas and no writer.

So the D-09 replication is **correct, tested, and running against nothing.** The
signing increment is what makes that sentence untrue, and until it is, "D-09 is
implemented" means the replication exists and there is nothing to replicate into.
**The spec layer now reports 1 open blocking finding, which correctly stops
FEAT-07 being marked done.**

### FEAT-07 increment 3 is DONE: Ed25519, in-toto v1, DSSE. F-97 is CLOSED.

`credentials/keys.py`, `in_toto.py`, `signing.py`, `manage.py sign_records`, and a
**second named Docker volume for the keys**. **27 tests, 6 mutations.**
Archive: `history/features/07-signed-records-dsse.md`.

**0 open blocking findings.** The T4 signed-records data path is real for the first
time: every table in that half of the schema now has a writer, and D-09's
replication finally has something to replicate into.

Three things that had to be right, each because a plausible version is silently
wrong:

- **The DSSE PAE is length-prefixed, and a wrong one still looks like a valid
  string.** Character-counting instead of byte-counting is correct for the *type*
  (ASCII) and wrong for the *payload* (UTF-8 JSON), so it passes everything until a
  judge has an accent in their name. **The test asserts the specification's own
  worked example, not this implementation's output** — a PAE built by the same
  code that verifies it agrees with itself forever.
- **Verification never compares a stored hash to a stored hash.** It recomputes
  the PAE and asks whether the key signs *these bytes*.
- **The record commits to digests, never to scores** — and that is the mechanism,
  not a courtesy: a record carrying scores is not shareable with a judge who was
  not the organizer, so it would replicate nothing.

**Keys on their own volume because `down -v` is how we reset.** Share a volume with
the database and every reset destroys every signature, taking the evidence with it.
A backup of the data volume is then safe to hand to somebody, which you cannot
retrofit.

### Two more things the gates caught in my own new code

- **The blast-radius test on `for_bulk_transfer` failed**, because the signer had
  started calling the widest read in the codebase. The fix was **not** a second
  allowlist entry — it is `for_judge_signing(event_id, judge)`, genuinely narrower,
  so the guarantee on the wide accessor still says "one caller".
- **The one-payload guard had a docstring and no test**, and the mutation harness
  proved it by reporting the mutation that removes it NOT DETECTED. Two tests now
  cover it. *A docstring asserting a behaviour is not a test of it.*

### FEAT-07 increment 4 is DONE: OpenAPI 3.1, and the README is now written for the product

`reviewer/api/documents.py` (the declarations), `reviewer/api/schema.py` (the
assembler), `manage.py build_openapi`, a committed **`openapi.yaml`**, and **15
tests**. Plus a **README rewrite**: 23 KB organised around tiers → 17 KB organised
around an organizer's week, with the reviewer material condensed into one section.

**F-99 [P2]** — `just schema` ran `manage.py spectacular`, which enumerates **DRF
views**. This API is plain Django functions *on purpose*, so the introspector found
nothing and wrote `paths: {}`: **a valid, committed, authoritative document
describing zero endpoints, from a command that exited 0.** F-61's shape with a
`paths:` key. The fix is a table plus a generator that **raises rather than emitting
a partial document** — for an undocumented route *and* for a declaration whose
route is gone. Wrapping the views in `@api_view` to satisfy the introspector would
have put the false-pass risk straight back.

**F-100 [P2]** — a predicate tested, and the refusal it drives not. `stale_declarations()`
had a test; the `raise` two lines below it did not. **Second time this session, and
the identical shape as the DSSE one-payload guard.** A predicate is worth testing
for what it *causes*.

Also fixed: an empty map emitted as the quoted string `"{}"` — so every refusal's
`content` told a client generator to parse a body that does not exist — and a
pre-existing test that asserted one of `run_acceptance.py`'s two unreachable
wordings, which passed standalone and failed under `just check`.

**FEAT-07 has one item left.**

| # | Item | Note |
|---|---|---|
| 5 | Embeddable results widget, pure static HTML + JSON, renders offline | Self-contained. **Must render with no network** — the same constraint the container boot is proved against |

### Do not

| # | Item | Note |
|---|---|---|
| 4 | OpenAPI 3.1 via `drf-spectacular` | Cheapest win in the block |
| 5 | Embeddable results widget, pure static HTML + JSON, renders offline | Self-contained |

### Do not

| # | Item | Note |
|---|---|---|
| 3 | **Ed25519 signed records, in-toto Statement v1 in DSSE, keys on their own volume** | **Moved up from 5. It is the only thing that closes F-97**, and F-97 is a P1 that blocks the feature being done. Building the widget while a P1 stands open would be the wrong order. |
| 4 | OpenAPI 3.1 via `drf-spectacular` | Cheapest win |
| 5 | Embeddable results widget, pure static HTML + JSON, renders offline | Self-contained |

### FEAT-09 is written

`history/features/09-video-script.md` -- a **3-minute structure with our own
material in it**, timed, with the two failure sections marked as the parts worth
rehearsing. Nothing to decide at the recording session.

### Do not

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
| **Status** | **BUILD COMPLETE — FEAT-01 … FEAT-08 and FEAT-10 all shipped and verified.** FEAT-09 is scripted and timed; recording it needs a human and a voice |
| **Started** | 2026-09-29 |
| **Last touched** | FEAT-10 committed and tagged `v-submission`: **721** tests passing (1 skipped), `113/113` mutations, spec `75/75`, lint clean, `just check` **GREEN** at 7 of 7 with `claimed T1 T2, verified T1 T2`, `just prove-offline` **PROVED** with the widget rendering 41 rows and no external reference, acceptance-report diff empty, and a **clean clone → fresh image → `run.py` at 7 of 7 PASS** |
| **Claim** | `claimed = ["T1", "T2"]`. T3 fully built and **unclaimed** (F-91, accepted by decision). `v-t3-verified` untagged, deliberately |
| **Next action** | **Nothing in software.** FEAT-09's recording needs a human, and the T2-only claim is an arithmetic fact about the organizers' program rather than an open question. `break-3-t3-claim.md` holds the arithmetic if the field is ever revisited |
| **Tag** | `v-t1-verified` (BREAK-1), `v-t2-verified` (BREAK-2), `v-submission` |
