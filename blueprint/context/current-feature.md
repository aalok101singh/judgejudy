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

## Increment 6 — public comments (REQ-T3-02)

**Built:** `comments/views.py`, `/projects/<id>/comments/`,
`templates/comments/thread.html`. **25 tests**, **4 new mutations**.

**Four controls, and the one that does not ship is named in our own threat
model.** `bible/07` V-8 lists: escaped output, no raw HTML, `pending` queue,
rate limits, length caps. **Three ship and are tested; rate limiting does not**,
and it is in the cut ledger, the README, and the module docstring — disclosed
three times rather than quietly missing.

**Comments are deliberately NOT on the gallery.** `run.py` reads `projects[:3]`
positionally from `/`, so the gallery markup is a page the T1 checks read. A
separate route is additive and cannot move the ordering. The gallery carries
only a link.

### F-86 [P2] — the moderation queue rendered bodies unescaped, and every escaping test was green

The sabotage put the safe filter on the **queue's** copy of `comment.body`, not
the public thread's, and **all four rendering tests stayed green** — they read the
page as a *visitor*, and the queue renders only for an organizer.

**The queue is the highest-privilege rendering of user-controlled text in the
whole feature**, and a hostile comment that is *never approved* never reaches the
public thread, so those tests were structurally incapable of catching it. Stored
XSS against the person whose job is to review the content, triggered by the
content itself.

> **Escaping is a property of every render path, not of the data.** A test that
> proves a payload is escaped on page A has proved nothing about page B. The
> number that matters is the **count of places user-controlled text reaches HTML**,
> and the assertion has to be enumerated over that count.

Pinned by `test_the_moderation_queue_escapes_too`, which reads the page *as an
organizer* — plus a companion that proves the queue is non-empty, so the first
cannot pass vacuously.

### F-87 [P2] — approving a comment updated the row and re-rendered the stale page

`_moderate` rebuilt only the queue, re-rendering the public thread from a context
built **before** the write. So the organizer pressed "Approve" and the page said
it had not happened. F-85's shape one module over.

**Found immediately, unlike F-85, because the moderation tests re-render the page
after acting.** That is the whole difference between the two, and it is a habit
worth naming: **a write test that re-reads the page is a test about the product;
one that asserts on the database is a test about storage.**

### A test that was wrong before it was right

The first escaping test asserted the string `"onerror"` is absent from the page.
It failed — against **correctly escaped output**, where `onerror` is inert text
inside a `<p>`. A test that asserts a *substring* is absent is asserting a proxy.
What a browser acts on is an **element**, so the assertion is now on the tag.

### The two things, neither mine to answer

## Increment 7 — the public results page (REQ-T3-03). The last named T3 gap.

**Built:** `reviews/results_view.py`, `/results/`, `templates/reviews/results.html`. **17 tests**, **3 new mutations**.

`results_visible_to` and `leaderboard` both existed and were both tested — for
`/api/v1/results`. **A reviewer opening a browser never asks for JSON**, so for
nine hours the brief's most carefully worded capability was enforced only on a
surface nobody would have visited.

**One predicate, one aggregate, two renderings**, and `TestThePageAndTheApiAgree`
asserts the HTML and the JSON produce the same rows in the same order with the
same means. Two renderings of one ranking is a liability — and it is exactly what
caused F-84's second-order bug, where `voters` meant one thing in the tally and
another in the influence report. **The reason that happened is that nobody
compared the two.**

### F-89 [P2] — a published event served the public an empty board

`leaderboard` computed every row from `for_actor(actor)`, and for a participant
or visitor that is **empty** — they hold no reviews. So a published page returned
**200 with a board of nothing**: structurally valid, renders, passes every
status-code assertion, ranks zero projects. F-80's shape, on the capability the
brief is most careful about.

FEAT-05's decision is deliberate and **kept** — "publishing opens the endpoint, it
does not widen the scope." What that did not consider: **scoping is protective,
not decorative.** It exists so a judge cannot infer peers' scores, and a visitor
has nothing of their own to protect, so narrowing is vacuous for them.

> **Narrow the board only when narrowing protects somebody.**

The branch is `elif _has_any_review(actor)` — an `EXISTS` against the accessor,
**not** `actor.is_judge`, because a judge with no assigned reviews is in the same
position as a visitor. It stays a **scoped query**: the wider board is reached by
building a real `Actor` and passing it to `for_actor`, not by an unscoped read,
which is what D-01 and the JJ01 lint rule forbid — and `just lint` is in the gate.

**Proved negative by a test that predates this feature by two increments.**
Removing the narrowing is caught by FEAT-05's
`test_a_judge_published_still_sees_a_ranking_over_a_scoped_set`. The
security-relevant half of F-89 was already pinned, and the sabotage found it
immediately instead of needing a new assertion.

### The refusal is asserted four ways

Status, empty body, no `Location`, **and no project title in the bytes** — the
last is the one a shape check cannot make. A page rendering a board of zeros
satisfies "the page has a table" and fails "the reader learned nothing."

### What the page always says

`unnormalized-raw-weighted-mean` on every 200 (a ranking that doesn't say whether
it's corrected is one a reader must guess about), and whether the board is scoped
— a published *judge* is told in words that they are seeing their own reviews
only, and that "a published ranking over your own scores is not a result."

### What is NOT started

- **Comments** on gallery projects (the model and its constraints ship; the
  surface does not).
- **Results hiding as a *public* surface** — the API refusal is built and tested;
  the public pages are not. **This is the last named REQ-T3 gap.**
- **Comment rate limiting**, cut and disclosed three times (`bible/08` §13, the
  README, and `comments/views.py`'s docstring). `bible/07` V-8 names it and we
  did not ship it, which is the one place our own threat model promises
  something the code does not deliver.
- **Comment threading.** `Comment.parent` ships unused; REQ-T3-02 does not ask
  for it.

## Increment 5 — voting, the identity budget, and the tally (REQ-T3-01)

**Built:** `ballots/tally.py`, the POST cast path on `/vote/`, and the weighting
form. **25 tests**, **5 new mutations**.

**The budget is one sentence: weight 1 on every project exactly exhausts it.**
D-12 says voting claims cost *amplification inside an identity budget, not Sybil
resistance*, so the cap is on total weight per `voter_key` and equals the ballot
size. The consequence is the point — a voter who wants weight 3 on a favourite
must give another project up or leave it unvoted, which makes the ballot
**constant-sum**, and constant-sum is exactly what `schwartzian`'s docstring relies
on when it says drift is "a genuine redistribution" with "no room for a uniform
inflation to hide inside."

**A budget of `3 x n` was the first design and it was rejected as decoration**: it
permits weight 3 on *every* project, so the cap never binds. It is now the first
mutation, and the sabotage proved five tests catch it.

**`schwartzian` is called, not reimplemented** — the same rule as
`presentation_order`. The harness measures drift on *this* function.

### F-84 [P1] — an abstention silently became a VOTE

`tally` ranked every `Ballot`, and `ranking_of` returned the unvoted projects in
ballot order — so a voter who cast **nothing** came back with a full ranking equal
to their raw ballot order and was scored as though they had voted for it.
**The surface had a button labelled "Abstain" that recorded the abstention and
then voted the ballot anyway.** The defect does not corrupt a number; it inverts
the meaning of a control the brief explicitly asks for, and a reader would have
found the correct model and a contradicting tally in the same commit.

**Found by the cheapest possible assertion.** A test created a third ballot to
break a tie and asserted the two were equal — they were not. The instinct was
"the tie test is wrong"; the third ballot had moved the numbers. **A test
asserting a negative caught a positive-valued defect.**

**A second-order bug in the same function**: `voters` counted "rankings that
mention this project", so a project ranked **last** by everyone reported **full
support** — contradicting the influence report's distinct-identities count on the
same data. Two shipped artefacts answering one question differently is worse than
either being wrong alone. One definition now, read from the `Vote` rows.

### A property worth saying out loud

**Two perfectly opposite ballots cancel exactly** (4+3 and 3+4), and a test now
pins it. It is the constant-sum property, and its consequence is real: **a
perfectly symmetric brigade cancels**, so brigading has to be *asymmetric* to move
anything. The tie test alone would pass against a tally that always returns equal
points, so the *opposite* is asserted too — a third asymmetric voter must break
the tie.

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
| **Status** | **FEAT-06 is DONE as far as the five named REQ-T3 requirements go.** T1, T2, T3-01 (voting + budget + tally), T3-02 (comments), T3-03 (results hidden, BOTH surfaces), T3-04 (randomised ballot order) and T3-05 (influence report) all ship and are tested. **That is the whole of REQ-T3, so the T3 claim is now a genuine question for BREAK-3 rather than a formality** - and the cut ledger names three things cut inside it |
| **Started** | 2026-09-29 |
| **Last touched** | FEAT-06 increment 7 - **the public results page**, the last named T3 gap. **F-89**: a published event served the public an empty board, so publication published nothing. `575 tests`, `86/86` mutations, spec 72/72, lint clean, `just check` **GREEN** at 7 of 7 |
| **Next action** | **BREAK-3.** The claim is now *available*, which has not been true before: all five T3 requirements are built. Per `bible/08` 1b that means the seven steps again, and the decision is the human's. The gap to name: three controls are cut and disclosed (comment rate limiting, ballot cookies/rate limiting, quadratic voting), and the published leaderboard is an **unnormalized** raw mean because FEAT-08 is not built |
