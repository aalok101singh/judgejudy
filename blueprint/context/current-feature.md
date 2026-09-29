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

### What THIS session did: a clean Phase 0, and four wrong numbers

**Every gate was green and four written figures were not.** That is the headline
and it is F-67's lesson paid in full: a number attached to a *command* is as
load-bearing as one attached to the fixture, and until this session no check
derived any of them. The application code did not change. The words around it did.

| Finding | What was wrong | Repair |
|---|---|---|
| **F-72** [P2] | `just check`'s **banner** and `AGENTS.md` said the spec gate has **67** checks; it prints **68/68** | number made **un-typable**; a new check asserts no artefact quotes it |
| **F-73** [P2] | the isolation proof's shipped footer pointed at `tests/test_results.py`, which does not exist | footer corrected; a new test asserts **every** `tests/*.py` the proof names exists |
| **F-74** [P2] | the findings tally's breakdown summed to **59** against a stated total of **71**; closed was really **60** | `48`→`60`; a new check asserts the breakdown **sums to its total** |
| **F-75** [P3] | cold start published as **12–20 s**, measured **11.8 s** — the floor was wrong | range widened to **11.8–20 s**; F-68's lesson, one session on |

**Two of the three new checks failed on their first run**, which is the evidence
they are real, and **each negative was then proved by breaking the document on
purpose** (`55 closed` fails the sum; re-typing `68/68 spec` fails the count).
Neither is self-referential: both assert a *property* (parts sum; no number
quoted), not an agreement with a value, so adding them could not break them.

**Nothing in the application changed and nothing needed to.** F-71's audit chain
reproduced **exactly** on a clean `just check` — 7 entries, sequence 1..7, head
`ba2931ab…`, CHAIN VERIFIED — which is the strongest confirmation in this
ledger that a *generated* number is reproducible and a typed one is not.

### FEAT-06 scope

**Acceptance line, from `build-plan.md` Phase F — on a clean database:**
a bias-attack harness shows the estimator is zero-mean under position bias; the
influence report renders for a synthetic attack.

### What is built so far, and what is not

**Done in FEAT-06 — the three `?` columns of the isolation matrix, the influence
report (increment 2), and now the bias-attack harness (increment 3).**

| Column | Now | How |
|---|---|---|
| `aggregate` | `41/126` organizer, **`refused`** for judge/participant/visitor | `results.results_visible_to(actor)` → `results.leaderboard(actor)`, at `/api/v1/results` |
| `export` | `126/126` organizer, **`refused`** for the rest | `actor.can_read_all_reviews` → `for_actor(actor)`, at `/api/v1/export.csv` |
| `audit` | `7 entries` organizer, **`refused`** for the rest | `audit.chain.for_actor(actor)`, at `/api/v1/audit` |

**A cell prints the word `refused`, never a zero.** `0/41` in the aggregate column
would read as *"verified, and there are no projects"* when there are 41 and this
actor may not see the ranking of them. That is the `UNPROVEN` constant's own
reason for existing, applied to the columns that now exist.

**The aggregate cell is the one the proof called "nobody tests and everybody
forgets", and it is now the sharpest statement in the matrix:** the shipped event
has `results_state = hidden`, so a judge, a participant and a visitor are all
refused a leaderboard while an organizer sees all 41. The ranking is a raw
weighted mean and **says so** in every row — normalization is FEAT-08.

**F-71, closed — and it is F-61 for the fourth time.** `AuditEntry` shipped at
FEAT-02 with the whole hash chain and **nothing ever wrote a row**. `reviewer/audit/chain.py`
is now the writer and verifier, `manage.py verify_audit` re-walks the hashes,
and the chain is populated by real traffic: **7 entries, sequence 1..7, CHAIN
VERIFIED** after a `just check` — reproduced in this session's Phase 0.

---

## Increment 2 — the influence report (D-13), the anti-abuse answer

**Built:** `ballots/influence.py`, `manage.py influence_report`, and
`GET /api/v1/influence` (organizer/admin only). Per project: distinct
identities, first-preference share, **vote-mass Gini**, and **identical-ballot
clusters**. `24 tests`, `9 new mutations`.

**The acceptance line's first clause — the bias-attack harness — is NOT built.**
One of the two clauses is done. The report went first *because* the harness needs
an attack to be visible, and building the detector after its own test would have
been the wrong order.

**Three decisions, and each is a sentence a reviewer can check:**

- **Not gated on `results_state`.** The leaderboard is refused while hidden; this
  is not, because the organizer has to see concentration *before* deciding to
  publish. Two tests pin the contrast.
- **No threshold anywhere.** Gini and cluster size are reported and ranked; the
  report never says "brigaded". Exact-match clustering needs no cut-off.
- **The caveat is in the output,** not the docstring. A report that shows a Gini
  without saying what it cannot conclude is a machine for accusing a table of
  friends.

**Two findings, and both are about verification, not logic:**

- **F-76** — the `lift` metric I invented is **structurally constant**: every
  voter casts one first preference, so a project's backers are its
  first-preferencers and the ratio is identically 1.0. The synthetic attack
  scored it at exactly 1.0. **Cut**, recorded with the arithmetic, and pinned by
  `TestTheDegenerateMetricStaysCut` so it cannot be re-derived from `bible/06`'s
  phrasing. D-04's lesson applied to abuse: a metric you cannot show
  *discriminates* is a tunable constant with a decimal point.
- **F-77** — the "organic control" in the tests **was itself a brigade of nine**,
  because every organic voter backed one project at weight 1 and so had a
  byte-identical vector. **24 tests were green and the control was broken.**
  Found by running the command in the container, not by pytest or mutation
  testing, because the code was right and the *scenario* was degenerate. This is
  F-41 from the other side: a **fixture** that cannot separate subject from
  control. The missing assertion now exists.

**Verified in the container on a clean volume:** a 12-voter brigade ranks first
with `clustered 12`, and every organic project reads `clustered 0`. The
full table is in `history/features/06-influence-report.md`.

## Increment 3 — the bias-attack harness, the acceptance line's FIRST clause

**Built:** `ballots/bias_attack.py` and `manage.py bias_attack`. **51 tests**,
**9 new mutations**. The harness takes three attempts, and the failures are the
interesting part.

| Arm | Reads | Means |
|---|---|---|
| **control** — no position bias | **exactly 0** | the instrument can see nothing when there is nothing |
| **`fixed`** — one project pinned to slot 1 | **+27.64 / +7.39, CI EXCLUDES zero** | **the attack is detected** |
| **`randomised`** — per-voter seeded permutation | **−0.53 / −0.26, CI spans zero, sd 9.9 / 14.6** | **zero-MEAN, not zero** |
| `balanced` — everyone in slot 1 equally often | spans zero | the null |

**Both acceptance clauses are now built.** The report renders for a synthetic
attack (increment 2); the harness shows the estimator is zero-mean under position
bias (increment 3). Observed in the container on a clean volume.

**The claim is stated exactly and the spread is reported beside the mean.** The
confidence interval spans zero; the standard deviation does not. A harness
reporting only the interval would let a reader conclude the bias was *removed*,
which `bible/06` §6.3 says is false and one citation refutes.

**Four findings, and every one is about verification, not logic:**

- **F-79 [P1]** — the first model of a position-biased voter promoted
  *whatever* was in slot 1, which measures **rank transfer**, not position: it
  read **−48 for the best project and +47 for the worst** under a *randomised*
  order, and would have "confirmed" D-12 for the wrong reason. **F-76 one level
  up.** Found by prototyping before writing the module.
- **F-80 [P2]** — a quality ladder of 1.0→0.12 left projects 5 and 7 in
  **nobody's** top two, so they were **structurally constant rows in a table of
  measurements**, and the harness measured exactly one project. **All 48 tests
  still passed with the ladder restored** — *a test that checks the attack fires
  does not check the field is contested.* Found by the mutation harness reporting
  its own mutation **NOT DETECTED**.
- **F-78 [P2]** — `bible/06` §6.3's power table does **not reproduce** from the
  formula it names (5.8× off, near-constant ratio). The error is conservative, so
  the conclusion survives, but the correction **narrows** it: 5 points needs 783
  comparisons, and §6.3's own range reaches 1,000. Now **generated** and pinned.
- **F-81 [P3]** — a mutation's description and detector were wired to each
  other's tuple, so the harness reported a **false failure**. Two other mutations
  were genuinely undetectable and now attack the property, each recording why.

**The control refused to pass, twice, and both refusals were right.** The first
version differenced a no-bias population against the pooled reference and read
`+0.051`; that is the *reference's* sampling noise, not the order's influence, and
the command said so. It is now an **exact** comparison — the same population under
three orders must score bit-identically.

**The full table is in `history/features/06-bias-attack-harness.md`.**

### What is NOT started

- **Randomized ballot order as a product path** — seeded per voter, stable across
  requests. **The function the harness attacks exists and is tested**
  (`presentation_order`), so the claim and the implementation are the same code;
  what is missing is the ballot surface that calls it.
- **Voting** with amplitude inside an identity budget, and mandatory attributable
  abstention.
- **Comments**, and results hiding as a *public* surface (the API is done; the
  public pages are not).

### The two questions, and neither is mine to answer

- **The leaderboard's published shape.** A published ranking is a page anyone can
  read, and the brief says results are hidden until the deadline. Whether
  publication shows *all* 41 projects or the top N is a product call with a
  fairness dimension, and it changes the widget in FEAT-07.
- **D-12 scope** — ballot order is FEAT-06 and must not be overclaimed:
  randomisation makes bias zero-*mean*, not zero.

### Do not

- **Do not claim T2.** It is earned and unclaimed, and the claim is made at
  BREAK-2, in writing, by the human. `.dogfood.toml` still says
  `claimed = ["T1"]`, which is correct.
- **Do not move `submissions_close`.** It is in the past because that is what
  makes the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**
- **Do not retype a gate's own check count.** Three places did it and all three
  rotted (F-72). `verify_spec` now fails if you do.

### State

| | |
|---|---|
| **Status** | **FEAT-06 in progress** — the three matrix columns, the audit chain, the influence report and the bias-attack harness are done. **Both acceptance clauses of the feature are now built.** Voting, randomised ballot order as a product path, comments and public result hiding are not started. The feature is NOT complete |
| **Started** | 2026-09-29 |
| **Last touched** | FEAT-06 increment 3 — **the bias-attack harness**, the acceptance line's first clause, with the claim stated as zero-**mean** and the spread reported beside it. Four findings, all about verification (F-78…F-81). `479 tests`, `68/68` mutations, spec green, lint clean, `just check` **GREEN** at 7 of 7 |
| **Next action** | **randomised ballot order as a product path** — `presentation_order` exists and is what the harness attacks, so the surface that calls it is all that is missing. Then voting, then comments |
