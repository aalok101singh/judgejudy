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

### BREAK-2 is done. The T2 claim is EARNED and the human has not yet applied it.

All seven steps of `bible/08` §1b ran, on a clean volume with the network off.
The full record is `history/features/break-2-t2-claim.md`.

| Step | Measured |
|---|---|
| spec | **72/72** |
| acceptance | **7 of 7 PASS**, `claimed T1, verified T1 T2` — parsed from the **body**; `run.py` always exits 0 (F-32) |
| `isolation_proof` | **exit 0** |
| suite | **479** |
| mutations | **68/68** |
| `prove-offline` | passes |
| lint | clean |

**F-82 was found at the break, and it is the reason one number is now derived
rather than corrected.** The README's route count was wrong; so was the repair's
("Eleven routes"), because the table omitted `/judge/review/<id>/` and the prose
apportioning the eleven did not sum over the table's own rows. A repair that
swaps a wrong number for a right one has not fixed anything a check could catch,
so a new `verify_spec` check now derives the routes from `urls.py` and asserts
the README names every one. **Proved negative** — deleting the row turns it red
and names the route.

**The `verified T1 T2` ceiling is arithmetic, not a gap,** and it is stated in
the claim record, the README and the shipped report. There are no T3 or T4 checks
in the organizers' program; `verified` is prefix-locked.

#### THE DIFF FOR THE HUMAN TO APPLY — not applied on initiative

`.dogfood.toml` line 49 is **correct as it stands**: `claimed = ["T1"]`. T2 is
earned but the claim is the human's. Two edits, and no credential values in
either:

1. Line 49:

   ```toml
   claimed = ["T1", "T2"]
   ```

2. The stale paragraph at lines 36-38, which now says the opposite of the truth —
   *"**T2 is deliberately NOT claimed.** It is four checks and none of them runs:
   the judge console, the scoped score endpoint and the CSV export arrive in
   FEAT-04 and FEAT-05"*. All three shipped; all four checks pass. Replace it
   with the BREAK-2 reason: T2 is claimed because all four checks pass and each
   passes *with a precondition*, so a wrong-reason refusal cannot stand in.

Then `just report` and `git diff acceptance-report.txt`. The header must read
`claimed: T1 T2` and the summary `claimed T1 T2, verified T1 T2`.

**Do not** edit the report by hand to make the two lines agree.

## Increment 4 — randomised ballot order as a PRODUCT path (REQ-T3-04)

**Built:** `ballots/order.py`, `ballots/views.py`, `/vote/`, `src/templates/ballots/ballot.html`. **24 tests**, **4 new mutations**.

**The constraint that shaped the increment: the surface must CALL
`presentation_order`, not reimplement it.** The harness attacks that function, so
a second copy of the seed formula is a second thing that can drift — and the
drift would be *invisible*, because the harness would keep reporting zero-mean
against a permutation the product stopped using. A test
(`test_the_surface_calls_presentation_order`) monkeypatches the symbol and
asserts it was called, so a re-implementation is caught rather than assumed away.

**The decision worth arguing about: the order is stored, and it did not have to
be.** `presentation_order` is a pure function of the identity, so stateless is
possible and simpler — no row, no constraint, no migration. Rejected because the
guarantee D-12 rests on is that a voter **cannot re-roll by refreshing**, and a
pure function of a *cookie* is only stable while the cookie survives.
`Ballot`'s `UniqueConstraint(event, voter_key)` is the enforcement; the seed is
stored beside the order so it is reproducible rather than merely asserted to have
existed. In the cut ledger, with two more entries beside it.

**`/vote/` renders the order and does not accept a ranking.** Disclosed, not
hidden — the cut ledger says so and `README.md` names it. Shipping the ranking
would have meant shipping the aggregation, which is REQ-T3-01.

### F-83 — a permutation keyed on a NULLABLE column

The permutation was first keyed on `Project.source_key`: D-11's portable natural
key, and **`NULL` for every project the portal created itself**
(`SourceKeyMixin` says so in its own docstring). So a self-submitted project
would have put a `None` into the order — structurally valid, renders, satisfies
every shape assertion, **ranks nothing**. The sixth appearance of F-80's class.

Caught by the tests on their first run, and **by luck**: one test sorts the
order and `[None] < [None]` raises. The shape assertions would all have passed.
The test that pins the class asserts `None not in order` **and** that the
self-submitted project is present — a fix that dropped the project instead of
re-keying it would pass the first and fail the second.

### The sabotage run, and why the second one matters

| Sabotage | Red |
|---|---|
| replace the permutation with the base order | **17 of 24** |
| **make the seed a constant** | **3 of 24** |

The second is the one that matters. **A constant order is perfectly stable per
voter**, so every "the same voter gets the same order twice" test stayed green
and only the *discrimination* tests went red. That is F-80's shape exactly — "does
the guarantee hold" is half the question — and it is why
`TestTheOrderActuallyVariesAcrossVoters` exists, asserts **counts** rather than
pairwise inequality, and carries its own slot-1 control. Both sabotages are now
mutations, so a re-introduction is caught by name.

### What is NOT started

- **Voting** with amplitude inside an identity budget, and mandatory attributable
  abstention. `Vote` ships with its constraints and indexes; nothing writes one.
- **Comments** on gallery projects (the model and its constraints ship; the
  surface does not).
- **Results hiding as a *public* surface** — the API refusal is built and tested;
  the public pages are not.
- **Rate limiting and a signed ballot cookie**, both cut and disclosed in `bible/08` §13.

### The two questions, and neither is mine to answer

- **The leaderboard's published shape.** A published ranking is a page anyone can
  read, and the brief says results are hidden until the deadline. Whether
  publication shows *all* 41 projects or the top N is a product call with a
  fairness dimension, and it changes the widget in FEAT-07.
- **D-12 scope** — ballot order is FEAT-06 and must not be overclaimed:
  randomisation makes bias zero-*mean*, not zero.

### Do not

- **Do not claim T2 without the human.** It is earned, BREAK-2 is done, and the
  exact `.dogfood.toml` diff is in this file — but the claim is applied by the
  human, not on initiative. `.dogfood.toml` still says `claimed = ["T1"]`.
- **Do not move `submissions_close`.** It is in the past because that is what
  makes the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**
- **Do not retype a gate's own check count.** Three places did it and all three
  rotted (F-72). `verify_spec` now fails if you do.

### State

| | |
|---|---|
| **Status** | **FEAT-06 in progress** — the three matrix columns, the audit chain, the influence report, the bias-attack harness and **the randomised ballot as a product path** are done. **Both acceptance clauses are built and REQ-T3-04 is now real.** Voting, comments and public result hiding are not started. The feature is NOT complete |
| **Started** | 2026-09-29 |
| **Last touched** | FEAT-06 increment 4 — **the randomised ballot as a product path**, `/vote/`, calling the function the harness attacks so the claim and the code cannot drift. **F-83** (a permutation keyed on a nullable column) and the constant-seed sabotage, which stayed green on every stability test. `503 tests`, `72/72` mutations, spec 72/72, lint clean, `just check` **GREEN** at 7 of 7 |
| **Next action** | **voting** — `Vote` ships with its constraints and the per-voter budget index, and the Borda estimator the harness attacks is `schwartzian`, so what is missing is the write path and the ranking. Then comments, then public result hiding |
