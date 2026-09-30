# 08 · Delivery Plan

**Purpose:** a 69-hour solo plan that reaches T4 flagship without a broken
tier, with demotion gates that make honesty a scheduled decision rather than a
panic.

**Clock.** Kickoff Friday 25 Sep 2026 18:00 UTC was moved forward 24 hours, so
the working window is **69 hours** and freeze is **Monday 28 Sep 2026 18:00
UTC**. All times below are UTC and relative (`H+0` = kickoff).

**The plan's shape, and why:**

1. **T1 and the isolation primitive first.** Not "breadth first." The 40% is
   tier completion *with correctness*, T1 is a gate, and the isolation primitive
   is the thing everything else inherits. Building it before any feature exists
   to leak is worth several hours.
2. **A working acceptance run by H+12.** The checker takes ten seconds. Never
   discover a failure at H+67.
3. **Documentation interleaved, never deferred.** Five and a half hours of
   writing carries 35% plus the entire credibility surface. The documents in this
   bible *are* the drafts; the task at each block is editing them into the
   deliverables, not writing from scratch.
4. **The video at H+62, not "if there is time."** It is a required deliverable
   and it is the only artefact a judge watches.
5. **A hard freeze buffer of 6 hours.** The last six hours are for verification,
   the report, the video and the commit — not for features.

---

## 1. Hour map

**DECIDED, H+0. We build to T4 and we do not pre-emptively cut a tier.** The
build order is tier by tier, and **the tier claim is a decision made at a
scheduled break, not a promise made at kickoff.** See §1b for the protocol and
§1c for the residual budget.

| Block | Hours | Focus | Break at end of |
|---|---|---|---|
| **A** | H+0 → H+4 | Project skeleton, Docker, compose, healthcheck, `LICENSE` | — |
| **B** | H+4 → H+9 | **Schema + the isolation primitive + its proof harness** | — |
| **C** | H+9 → H+14 | Loader, seed identities, gallery, deadline guard | — |
| **—** | **H+14 → H+15** | **☕ BREAK 1 — T1.** Full verification, slippage ledger, honest claim | **T1** |
| **D** | H+15 → H+22 | Rubric, assignment, judge console, reviews | — |
| **E** | H+22 → H+30 | Isolation hardening, dashboard, exports, event editor | — |
| **—** | **H+30 → H+31** | **☕ BREAK 2 — T2.** Full T2 verification, **tag `v-t2-verified`** | **T2** |
| **F** | H+31 → H+40 | T3 public: voting, comments, results hiding, ballot order, **anti-abuse influence report** | — |
| **—** | **H+40 → H+41** | **☕ BREAK 3 — T3.** T3 gate, honest claim, slippage ledger | **T3** |
| **G** | H+41 → H+54 | T4: bulk IO, signed records, results hash, widget, OpenAPI | — |
| **—** | **H+54 → H+55** | **☕ BREAK 4 — T4.** T4 gate, honest claim, slippage ledger | **T4** |
| **H** | H+55 → H+62 | **Normalization engine + proof artefact** | — |
| **I** | H+62 → H+65 | **Demo video** | Video recorded |
| **J** | H+65 → H+69 | Docs finalisation, report, verification, commit | **Freeze — 4h protected** |

Documentation is written *inside* every block, not in a block of its own. See
§6. **The four breaks are not slack** — they are where the tier claims are
decided, and §1b is the protocol.

### What moved, and why

**The isolation *proof* work moved from Block E into Blocks B and C.** This is
the one structural change the second research pass forced, and it is not a
compromise — it is where that work belongs. `08` §3 already says *"Build the
scoped-accessor layer first, in the first six hours, before any feature exists
to leak."* The evidence that the layer works belongs with it, not twenty hours
later:

- **`isolation_proof` skeleton → Block B.** Against two hand-seeded judges it
  costs almost nothing and it is the earliest possible proof that the primitive
  is right.
- **The scope receipt → Block B.** One attribute and one template partial. It is
  part of the primitive's signature, not a feature bolted on afterwards.
- **Hypothesis invariants → end of Block C.** They need routes to exist, and C is
  where they do.

**Block E therefore becomes what it should have been:** isolation *enforcement*
across the full matrix, the dashboard, the exports and the event editor. That
was 12.5h of work in an 8h block, which was the real budget hole. It is now
about 8h in 8h, and Block B/C absorbed 3.5h of what had been queued behind it.

---

## 1b. The break protocol — what actually happens at H+14, H+30, H+40, H+54

**This is the mechanism the decision rests on, so it is written down rather than
assumed.** Each break is a fixed one-hour block with a fixed checklist. **The
break is not optional and it is not "if time permits."** An hour now costs less
than an honest demotion at H+54.

| Step | At every break |
|---|---|
| 1 | `docker compose down -v && up` from a clean state, **network off** |
| 2 | `python run.py .dogfood.toml` — real output, no editing |
| 3 | `python manage.py isolation_proof` — must exit 0 |
| 4 | Our extended suite, in full |
| 5 | **Update the slippage ledger** (§1c) with actual vs planned hours per block |
| 6 | **Decide the tier claim and write it down**, with the gap named in plain words |
| 7 | Tag: `v-t1-verified`, `v-t2-verified`, `v-t3-verified`, `v-t4-verified` |

**The rule at each break, and it is the same rule:** *if the tier in front of us
is not verified green, the claim in `.dogfood.toml` is the last verified tier,
and `README.md` names the gap in our own words.* No negotiation, no "it nearly
works," no shipping a claim we have not seen pass.

**What changes if T4 does not close.** The build order is unchanged — we still
build T4 features, in value order, in the order `08` §8 gives. What changes is
the **claim**. Gate 2 becomes "we built A, B and C of the five T4 items; here is
which, here is what each does, and here is what we would have needed." That is a
substantially better outcome than a T4 claim with two half-working endpoints,
and it is exactly the trade the brief tells us to make three times.

**A break that finds a tier green is not a wasted hour.** It is the only moment
where demoting is cheap.

---

## 1c. The residual budget, stated honestly

The second research pass added real value and it does not fit in 69 hours.
**The arithmetic, not a compressed estimate:**

| Block | was | now | Δ | What changed |
|---|---|---|---|---|
| B | 4.0 | **5.0** | +1.0 | `source_key` × 9 tables; `AuditEntry` chain columns; key volume; **`isolation_proof` skeleton + scope receipt moved in** |
| C | 6.0 | **5.0** | −1.0 | **Hypothesis invariants moved in** (+2.0), gallery polish moved to E (−1.0) |
| D | 8.0 | **7.0** | −1.0 | **Gallery polish + event editor moved out** to E (−1.5); min-cut certificate in (+1.5); max-min search offset by cutting two cost terms (−1.0) |
| E | 8.0 | **8.0** | 0.0 | **Everything proof-related moved out** (−3.5); matrix enforcement, dashboard, exports, editor, polish in (+3.5) |
| F | 10.0 | **10.0** | 0.0 | **Anti-abuse influence report in** (+1.0); ranked Borda ballot explicitly **out** (−1.0) |
| G | 12.0 | **11.0** | −1.0 | **Webhooks cut** (−2.0); certificates 1.5 → 0.5 (−1.0); `results_hash` in (+0.75); DSSE ≈ bespoke (0) |
| H | 6.0 | **7.0** | +1.0 | Detectability (1.0); candidate D (0.25); LORO harness (0.5); recovery experiment (0.5) − overlapping CSV work (−1.25) |
| | | | **+1.0** | |

**After moving work to where it belongs and cutting webhooks and certificates,
the plan closes at +1.0 hour against a 4-hour freeze buffer.** That is the
residual, and the four breaks absorb it.

**Two things this table is quietly saying, which are worth stating out loud:**

1. **The original plan's E block was 12.5h of work in an 8h block.** The overrun
   was never "we added features" — it was "the isolation proof work was queued
   behind the dashboard, where it did not belong." Moving it fixed the budget
   *and* the ordering. That is the cheapest hour in this document.
2. **We still might not make it, and the breaks are how we find out at H+40
   rather than at H+66.** T4 is a build order, not a promise. If Break 4 arrives
   with two T4 items outstanding, we claim T3 and say exactly which two.

### The slippage ledger — fill this in at every break

The Write Up Quest's "what we got wrong" material, and the thing that makes the
break protocol real rather than ceremonial.

| Block | Planned | Actual | Δ | Why |
|---|---|---|---|---|
| A | 4.0 | ~4 | ≈0 | Skeleton, image, compose, healthcheck. On plan. `compose up` served in 6.2 s, and the two costs that would have overrun it did not happen: a 1.9 s seed and a PATH problem that was not a missing install (F-13/F-34) |
| B | 5.0 | ~5 | ≈0 | Schema, 24 models / 12 apps, `for_actor()`, scope receipt, hash-chained audit, the JJ01 lint rule. On plan, and the scope receipt landed in the estimate rather than on top of it |
| C | 5.0 | ~6 | **+1** | **The first block to meet the organizers' data instead of ours, and it cost the hour.** Eight findings, three of them P1 (F-49, F-50, F-55), every one a value that agreed with what we expected and disagreed with what the file said. F-40 was also discharged here: two of the seven checks had been passing for the wrong reason, and the fix was a new *kind* of precondition, not a patch |
| D | 7.0 | ~7 | ≈0 | Rubric, the assignment engine with its min-cut certificate, the judge console. `FEAT-04` recorded `Actual: ~7h` when it was written. The min-cut certificate was the whole point of the block and it landed inside the estimate, which the §1c table said it would because it was already priced in at +1.5 |
| E | 8.0 | ~8 | ≈0 | The three isolation columns, the scoped score endpoint, the CSV export, the refusal primitive. **No `Actual:` line was written in the FEAT-05 archive, so this is a retrospective estimate and is marked as one** — see the note below |
| F | 10.0 | **~13** | **+3** | **COMPLETE — seven increments, and it ran OVER.** The three matrix columns, the audit chain's missing writer, the influence report, the bias-attack harness, **the randomised ballot as a product surface, voting with its identity budget, comments, and the public results page.** All five REQ-T3 requirements ship. The overrun is real and it is *not* padding: **F-84 [P1] was a P1** (an abstention silently counted as a vote), and four more findings (F-83, F-85, F-86, F-87, F-88, F-89, F-90) were each found only after a deliberate sabotage proved the tests load-bearing. **The two most expensive things in this block were the verification, not the features** | **Yes.** +3 against plan, and the honest reading is that the *tests* cost more than the code. Would do it again — F-84 was a correctness bug in the mechanism the brief asks for by name |
| G | 11.0 | | | |
| H | 7.0 | | | |

> **Fill it in honestly, including the blocks that went fast.** A ledger where
> every row is negative teaches the reader nothing, and the most useful entry in
> the whole write-up will be the block where something took two hours instead of
> one and we found out at a break.

**BREAK-1, 2026-09-28 — first entry, so the format is set here.** Three
concessions, stated up front because they weaken the table above:

1. **The actuals are estimates, not a stopwatch.** A, B and C are the
   `**Actual:**` figures each feature archive recorded when it was written
   (`~4h`, `~5h`, `~6h`). They are honest judgements written after the fact, not
   measurements. A reader should treat the ± as "within the hour", not as a
   figure to the tenth. **Nothing in this project has ever been timed against a
   clock; the one number we *do* measure mechanically is the cold start, and it
   is measured by `tools/coldstart.py`.**
2. **Three rows of zeros is a suspicious shape**, and the rule below exists
   because of it. Blocks A and B going to plan is the *expected* result, not
   evidence that the estimates are good; the first honest test of the estimating
   is block C, and block C ran over. One over in three is not a trend.
3. **Δ is against the plan, not against the budget.** The 69 hours do not move
   because block C overran; they move because blocks D–H are still unstarted, so
   the overrun is absorbed by the ~1.5 h × 4 breaks already budgeted, or it is
   not absorbed at all. Which of those is true is decided at BREAK-2, not here.

**BREAK-2, 2026-09-29.** The first three concessions still stand, and the second
of them bit. Adding rows D, E and F:

1. **Block E has no `Actual:` in its archive, and that is now a gap in this
   ledger's own source rather than a judgement call.** `FEAT-01`…`FEAT-04` each
   recorded `Actual: ~Nh` when the archive was written; `FEAT-05` did not, so its
   `~8` above is a **retrospective estimate made at the break**, and it is marked
   as one. The rule the next session should keep is the boring one: **write the
   `Actual:` line into the archive when you write the archive**, because the
   slippage ledger is only as good as the figures it reads.
2. **Block F is under plan and the feature is unfinished, and those two facts are
   the same fact.** `~7` against a planned 10.0 is not efficiency — the ballot
   order, voting and comments are simply not built yet. **A negative Δ on an
   incomplete block is not a saving**, and reading it as one is how a slippage
   ledger starts lying.
3. **The two zero-Δ rows that were expected to be non-zero were not.** D and E
   both landed on plan, which is a real result and not a rounding: the two blocks
   that met the organizers' *requirements* rather than their *data* both
   estimated correctly. C, the one block that met the fixture, ran +1. **Three
   blocks is not a trend, but it is the only signal the ledger has produced and
   it points the same way every time.**

### The one hour BREAK-2 actually cost, and what it verified

Not an hour of building. The block spent itself on **verification and on
finding that a document had rotted under it**:

| | |
|---|---|
| **Green, measured** | spec **72/72** · acceptance **7 of 7 PASS**, `claimed T1, verified T1 T2` · suite **479** · mutations **68/68** · lint clean · `prove-offline` passes · `isolation_proof` **exit 0** on a clean volume |
| **Found at the break** | **F-82** — the README's route count was wrong, its repair was *also* wrong, and the second repair invented a breakdown that did not sum over its own table. Fixed by making the count **derived from `urls.py`** rather than retyped, and proved negative |
| **Concession, stated because the brief rewards it** | **`verified` cannot exceed T2 on a flawless build.** There are no T3 or T4 checks in the organizers' program and `verified` is prefix-locked, so the ceiling is arithmetic. The report ships printing `verified T1 T2`, and the README explains why in full rather than the report being edited to say otherwise |

### BREAK-3, 2026-09-29 — T2 claimed, and the T3 claim becomes available

The same seven steps, run again, on a clean volume with the network off. The
whole block was spent **applying the T2 claim and proving the thing it rests on**,
which is the point of a break and not an administrative formality.

| | |
|---|---|
| 1 | clean `down -v`, `up` **network off** — volume removed and recreated, healthy |
| 2 | `run.py` against `.dogfood.toml` — **7 of 7 PASS**, and the report header now reads **`claimed: T1 T2`** with the summary **`claimed T1 T2, verified T1 T2`** |
| 3 | `isolation_proof` — **exit 0**; matrix: visitor `0/126` refused everywhere, participant `0/126` refused, **judge `5/126`** and refused the aggregate, organizer `126/126` and `41/126` on the aggregate |
| 4 | full extended suite — **green**, `575 tests` |
| 5 | this ledger |
| 6 | **the tier claim, written down** in `blueprint/history/features/break-3-t3-claim.md` |
| 7 | tag `v-t3-verified` |

**The interesting sentence in the report is the one that did not change.**
`claimed T1 T2, verified T1 T2` — and `verified` is the machine's word, not ours.
It could not have said T3, because `run.py` contains **no T3 checks at all**. A
panelist reading that line should conclude "they claimed T2 and the machine
confirmed T2, and there is no machine check for T3" — which is the honest
situation, and is why the T3 claim in step 6 is a **human judgement against a
rubric** and the part of this break that is not machine-verifiable.

**What the hour actually bought**, same as BREAK-2: not features. The T2 claim sat
earned and unclaimed for **five features** after FEAT-05, and the reason it sat
is the rule working. Applying it changed **one line** in `.dogfood.toml` and
regenerated a report. Everything else this break did was check that the claim
still held on a volume that had just been destroyed.

---

## 2. Block A · H+0 → H+4 · Skeleton and one command

**The only goal: `docker compose up` gives a serving portal.** Everything else
is downstream of that and the organizers' rule 02 is the first thing they test.

- Django project, `dockerfile`, `docker-compose.yml`: one service, one image,
  gunicorn + whitenoise, SQLite volume, healthcheck against `/healthz`.
- `manage.py migrate` in the entrypoint; **seeding completes before gunicorn
  binds** (per `03` §4.7).
- `LICENSE` = MIT. `.gitignore`. Public repo created. `README.md` stub with the
  run instructions, so the repo is never in a state where nobody can start it.
- A `make` or `just` target wrapping the three commands we will run constantly:
  `up`, `down`, `check`.

**Definition of done:** from a clean clone, `docker compose up` → serving page
in under 60 seconds, no required environment variables, no outbound calls.

**Watch for:** the image build is the longest single step in the whole project.
Start it first and let it run while writing models. Do not discover at H+3 that
the base image is 1.4 GB.

---

## 3. Block B · H+4 → H+9 · Schema, the isolation primitive, and its proof harness

**This is the most important five hours in the plan, and it is not building
features.** It is building the thing that makes T2-5 impossible to fail, and
then proving it. The second research pass moved the *evidence* for the primitive
in here from Block E, and that is the single change that made the budget close
(`§1c`) — the proof of a primitive belongs next to the primitive, not twenty
hours later.

Order:

0. **`tools/verify_census.py`** — the script that re-derives every number in
   `04` and `06` from `fixtures.json` and asserts the two invariants (`04` §2.1).
   It is the first thing written and it takes fifteen minutes, because six
   errors in our own census were found by exactly this check and we are not
   repeating them in code. It becomes the loader's self-check in Block C.
   **Amendment after the second research pass:** the six census errors included
   two in the table the normalization argument rests on (`06` §4.1a), found
   *after* the correction log in `README.md` had been written. So the script
   also **prints the row count of every table it generates**, and a table whose
   row count does not match its stated population is a boot failure.
1. Migrations for everything in `05` §1–§5. All of it, now, while nothing depends
   on it. Schema changes get exponentially more expensive after features exist.
   **Two amendments from the second pass, both cheap now and expensive later:**
   - **`source_key` on every importable table** (`05` §8a). Without it the
     round-trip property in `05` §8 is not *testable* — "byte-identical modulo
     generated IDs" lets a dropped column pass. One nullable column × nine
     tables, free in the initial migration, 3 hours if retrofitted.
   - **`seq` / `prev_hash` / `entry_hash` / `omitted_since_prev` on
     `AuditEntry`** (`06` §5.2). Four columns, and they are the difference
     between "append-only, we promise" and "append-only, go and check."
2. `User`, `RoleBinding`, `Session` (DB backend). Signup, signin, signout.
   **`JudgeCredential` key directory on its own named volume, not the database
   volume** (`05` §9) — our own hour-66 checklist runs `down -v` twice, and keys
   there would invalidate every record in the README.
3. **`ReviewQuerySet.for_actor()` and `for_actor_and_subject()`** — `05` §6,
   verbatim — plus the DRF permission classes, **and the `ScopeReason` object**
   that both the receipt and the audit entry consume (`05` §6a). ~1h for the
   receipt: one attribute on the queryset, one template partial, one call site.
4. The denial path: **`403`, never a redirect** (`03` §4.1).
5. The lint rule forbidding `Review.objects.all()` outside the manager.
6. `Track.target_reviews_per_project` (`05` §2) — it is one nullable integer
   **now** and a migration touching the assignment solver, the progress
   denominators and the infeasibility report in Block D if it arrives late.
7. **`manage.py isolation_proof`, complete enough to run** (`05` §6b.1) —
   against the two hand-seeded judges this is nearly free, and it is the earliest
   possible proof that the primitive is right. Just the matrix walk, the
   status-code-per-cell printing, the 403/empty-body/no-`Location` assertions
   and the visible-of-total counts. The `curl` transcript and the full route
   coverage come in Block E when the routes exist. ~0.5h here.

**Definition of done:** with two judges seeded by hand, judge B's `curl` at
judge A's scores returns 403, **`manage.py isolation_proof` prints a matrix with
status codes and exits 0**, and the judge's list view renders its scope reason.
Captured as a transcript in the repo from the first hour, and kept up to date as
a test.

**Why this order and not features first:** the primitive is only cheap to build
before there is anything to leak. Add it later and it is a retrofit across every
view, under time pressure, which is exactly how projects end up with a
template-level check. The brief calls that failure "the most common way a good
looking project loses points."

---

## 4. Block C · H+9 → H+14 · Loader, gallery, deadline, and the isolation invariants

- The fixture loader: idempotent, lossless, anomaly-reporting, IDs preserved
  (`04` §6). Print the anomaly summary on boot, **including both `04` §2.1
  invariants and the row count of every census table** — six errors in our own
  census came from not doing this, two of them after we had already written a
  correction log about it.
- The five seed identities with stable, **printed** session values.
- Gallery: server-rendered, first page in fixture order, search (FTS5 with an
  `icontains` fallback), filters by track and tag. **No client-side-only fetch**
  (`03` §4.2). **Polish deferred to Block E** to pay for the invariants below.
- Teams, invites, project create/edit, draft/submit.
- **The deadline guard** as a service function (`05` §4). The seeded event is
  born closed; the guard is exercised by tests in both directions.
- **The four Hypothesis invariants** (`05` §6b.2): monotonicity under role
  inclusion, no cross-evasion across generated actor/query pairs,
  decline-not-filter, and scope-is-total. **~2h, here rather than in Block E,
  because the routes they exercise now exist.** Use
  `hypothesis.extra.django.TestCase`, **never `TransactionTestCase`** (the docs
  warn it is significantly slower in a loop), bound `max_examples=50`, and build
  small worlds with `st.just`/`st.builds` rather than `from_model` on the big
  tables.

**Acceptance run #1 at H+13. Expect T1 green. T2 will fail until judge endpoints
exist** — that is fine and expected at this point. **Record the output anyway**,
because watching the report fill in over the weekend is the point.

---

## 4a. ☕ BREAK 1 · H+14 → H+15 · T1

**Run the `§1b` protocol. Seven steps, one hour, not optional.**

The decision at this break: **is T1 green?** If yes, tag `v-t1-verified` and
start Block D. If no, we have a gate problem and 54 hours to fix it — which is
the entire reason this break exists rather than a `curl` at H+29.

Update the slippage ledger (`§1c`) with A, B and C actuals. **Honest numbers,
including the blocks that went fast.**

---

## 5. Block D · H+15 → H+22 · Judging

- Rubric and criterion editing with weights; the lock.
- Assignment: eligibility, **one flow over all tracks** (`06` §2.1b — dual-track
  judges couple the tracks, so per-track flows are wrong), the **min-max
  capacity search** (§2.2, ~20 lines on top of the flow), **load imbalance +
  seeded tiebreak only** as the cost function (§2.2 — two terms cut on
  measurement, one moved from cost to eligibility), the **min-cut
  infeasibility certificate with its three arithmetic remedies** (§2.3, ~1.5h),
  and manual override. **Reconstruct assignments from the 126 fixture score
  rows** so the dashboard is real from the first minute.
- Judge console: assigned list, per-project rubric form, save-as-you-go, submit,
  decline.
- `Review` + `Score` writes with `weight_applied` snapshotted.
- `/api/judge/scores` — own scores, scoped. The peer-scoped sibling exists and
  is refused.

**No `scipy`, no `networkx`** (§2.2). Hand-rolled successive-shortest-path with
Johnson potentials; measured at sub-millisecond on a 40-node graph. **Assert
the edge count in a test** — building this graph from a track-keyed map read as
judge-keyed yields 38 edges instead of 77 and a silently wrong answer rather
than an error. That is a real bug we hit while designing it.

**Acceptance run #2 at H+21.** T1 + T2-4 green. T2-5 should now pass; if it does
not, **stop and fix it before writing another feature.** This is the gate that
protects 40% and 25% simultaneously.

**Watch for:** the CSV export and the progress dashboard are T2 items. They are
in Block E — but **do not let that become an excuse to skip them**, because T2 is
the highest-value tier we have and Break 2 is at H+30, not H+45.

---

## 5a. ☕ BREAK 2 · H+30 → H+31 · T2

**Run the `§1b` protocol. Tag `v-t2-verified` if green — this is the fallback
state if everything after H+31 goes badly, and it is the single most valuable
tag in the repo.**

The decision: **is T2 green, all six demands, not just the four the checker
tests?** If yes, `.dogfood.toml` claims T1–T2 and we proceed to T3. If no, we
stop here and fix T2, because everything we have added since H+0 sits on top of
it.

**This is the break where honest reporting is most likely to save us.** The
brief says a clean T2 beats a broken T4, and this is the last cheap moment to
act on that.

---

## 6. Block E · H+22 → H+30 · Isolation enforcement, dashboard, exports

- Full FIG. 02 matrix enforced, **including the three cells the checker never
  tests**: cross-track, aggregate-while-open, export-as-judge.
- **`manage.py isolation_proof`, complete** (`05` §6b.1): the matrix with a
  status code per cell, the 403/empty-body/no-`Location` assertions, the
  visible-of-total row counts with scope reasons, and the raw `curl` equivalent
  of the peer probe. Nonzero exit on mismatch. **This is the evidence artefact
  for the 25% and it is a table that matches a published figure, which a list of
  test names is not.** *(The command itself is built in Block B; what is
  completed here is route coverage and the transcript, now that every route
  exists.)*
- **The scope receipt in the UI** — built in Block B; wire it into the remaining
  list views here.
- Progress dashboard **in the `06` §5.1 order**: unfixable projects and
  sole-cover judges first, long tail, per-judge, the severity panel **with its
  permutation p-value and detection floor beside the bars**, completion
  percentage last.
- CSV exports: all seven, streamed, comma-bearing header row first. Plus the
  canonical JSON export and the signed archive (`05` §8b).
- Event editor: dates, tracks, prizes, voting mode, results state.
- **Gallery search/filter polish, deferred from Block C.**

**Acceptance run #3 at H+29. Full T2 green. This is the point of maximum
vulnerability and the point at which the project is genuinely submittable.**

**Why this block is now ~8h of work in 8h, when the original 8h block held
12.5h.** The isolation proof work moved to Blocks B and C, which is where it
belongs (`§1c`). Do not move it back.

---

## 7. Block F · H+31 → H+40 · T3 public

*Starts immediately after Break 2. The old 4-hour buffer at H+30 is now Break 2
plus the moved work — see `§1c` for where it went.*

- Voting with three access modes; quadratic weighting stored on `Vote`.
- Randomised ballot order, stable per voter, seeded and reconstructable.
- Comments with moderation state.
- Results hidden during the voting window, enforced on every endpoint.
- Rate limits, duplicate detection, the flagging queue.
- **The anti-abuse influence report** (`06` §6.2) — ~1h, and **this is the
  "mechanism against people trying to cheat," decided in and it is the
  deliverable.** Per project, before results are announced: distinct verified
  identities, first-preference share, **vote-mass Gini**, and identities flagged
  by the clustering detector. The table in `06` §6.2 shows the shape, including
  the `prj_14` case that is winning on concentration — 20% of first preferences
  from 14% of voters, Gini 0.71. **A brigaded vote, visible, before publication.**
  No incumbent produces this and it is worth more than any voting mechanism,
  because the brief asks for *"an answer to people trying to cheat it"* and an
  answer is a report.
- **The ranked Borda ballot is explicitly OUT** (`06` §6.2). Not because it is
  bad — the Schwartzian transform is the unique linear rank aggregator
  satisfying the Condorcet criterion (Fishburn 1973) — but because it *changes
  the outcome* while the report *explains* it, and the report is what the brief
  asked for. It is a candidate at Break 4 if G finishes early and F's half hour
  is already spent.

---

## 7a. ☕ BREAK 3 · H+40 → H+41 · T3

**Run the `§1b` protocol. This is the break that decides the T4 claim's
starting point, and the second most important one after Break 2.**

The decision: **is T3 green on our own suite?** Six demands, none of which the
checker verifies. If yes, claim T1–T3 and start G. If no, claim T2, name the gap
in plain words, and start G anyway — because the build order does not change,
only the claim does.

**This gate is where most teams inflate, and inflation is the one documented way
to lose points for free.** `run.py` prints `claimed` against `verified` and
flags the difference, the panel runs the identical program, and the brief states
three separate times that honest reporting is rewarded and inflation is
penalised.

Update the slippage ledger. **Write down the F actual now** — this is the block
most likely to overrun, and knowing it at H+40 rather than H+54 is the whole
point of the break.

Cheapest-first ordering within T3, because the visible-per-minute ratio matters:
randomised order (20 min, very visible in the video) → results hiding (30 min,
security-flattering) → comments (1h, easy) → voting modes (2h) → quadratic (1h)
→ rate limits and detection (2h) → **influence report (1h)**.

---

## 8. Block G · H+41 → H+54 · T4

**We build T4. The claim is decided at Break 4, not here.** In value order, not
difficulty order:

1. **Bulk import and export** (REQ-T4-05) — the escape hatch, the sentence about
   a platform you cannot leave. **The round-trip property test is the product**,
   not a test: `manage.py verify_archive` re-imports into a scratch DB and
   asserts byte-identity **including `source_key`** (`05` §8a), with a Hypothesis
   `world()` strategy rather than a hand-written fixture. ~4h. **Do it first in
   this block even though it is the least glamorous item in it.**
2. **Signed judge participation records** (REQ-T4-03) — **in-toto Statement v1
   inside a DSSE envelope** (`05` §9b), not a bespoke signed blob: it signs
   bytes so no third party has to agree with us about canonicalisation, and it is
   verifiable with tooling that already exists. Ed25519 (RFC 8032) via
   `cryptography`, keys on their own volume, public verification endpoint,
   offline CLI verifier, **exposing no scores**. ~3h. Best "steal it" candidate
   in T4, and the cheapest in the block.
   **Two traps that produce records which verify against our own verifier and
   against nothing else:** PAE's `len()` is in **bytes**, not characters; and
   test against one hardcoded vector from the DSSE spec.
3. **`results_hash` + the chain head in the signed record** (`05` §9, §9c).
   ~45min on top of item 2, and it is the answer to the one attack we previously
   could only "detect": a malicious organizer. **One column. Do not skip it for
   a shinier feature.**
4. **Certificates** (REQ-T4-02) — cut to "render the existing signed record as a
   PDF," ~30min, free marginal cost once the signing primitive exists.
5. **Embeddable gallery widget** (REQ-T4-04) — one `<script>` tag, no consumer
   build step. ~1.5h.
6. **OpenAPI spec** — `drf-spectacular`, ~1h, and it doubles as the API First
   bonus. Cheap because the architecture already did the work.
7. ~~**Webhooks**~~ — **CUT at H+0, decisively. Not "last", not "if time
   permits": cut.** 2h, **zero points on all four criteria**, and P-8 (SSRF via
   webhook URL — DNS resolution against private ranges, redirect limits, scheme
   allowlist) is a real bug class written from scratch under time pressure.
   `01` §9 already files it as "Nice." **What ships instead:** a documented
   `WebhookEndpoint` model, a stub view returning 501, and an `export run` /
   `import run` audit entry — so the schema is there when someone extends it, and
   `README.md` says plainly that delivery, retries and signature verification
   are not implemented. **In the cut ledger with "Yes, slightly."**

**The API First discipline, enforced throughout:** no UI action exists that is
not also a viewset action. If a form posts somewhere bespoke, that is a bug.

---

## 8a. ☕ BREAK 4 · H+54 → H+55 · T4

**Run the `§1b` protocol. This is the last scheduled decision point before the
freeze, and the one the whole break structure exists to make cheap.**

The decision: **how much of T4 is actually verified green?**

| If | Then |
|---|---|
| All five T4 demands verified | `claimed = ["T1","T2","T3","T4"]`, tag `v-t4-verified` |
| Four of five | `claimed = ["T1","T2","T3"]` and **`README.md` names the missing one precisely** — a T3 claim plus a T4 item is honest and reads as competence |
| Three or fewer | `claimed = ["T1","T2","T3"]` with a T4 section in the README describing what was built, what is not finished, and what the next event's fork would need |

**In every case, `run.py`'s real output ships and `.dogfood.toml` matches it.**
Note from `03` §2.4 that `verified` is prefix-locked and only T1/T2 have checks
implemented, so a flawless build still prints `verified T1 T2` and
`note: claimed but not verified: T3 T4`. **The README explains that in our own
words** (Q8 in `DISCORD-QUESTIONS.md` asks whether that ceiling is final).

**A claim of T4 with three half-working endpoints scores worse than an honest T3
with a clear list of what was not finished**, and the brief says so twice. The
build order does not change at this break — only the claim does.

**Update the slippage ledger one final time.** G's actual is the number that
decides H. Write it down honestly, and if we overran, the write-up gets the
real figure rather than the plan's.

---

## 9. Block H · H+55 → H+62 · Normalization

**Protected time. Do not let features displace it.** This is 25% of the score
plus the $100 prize, and the work is analysis on data we already have rather
than new product surface.

**Order, and the order is the argument:**

1. **The detectability analysis first** (`06` §4.1b): the variance
   decomposition, the permutation test, the power analysis. One hour, and it
   determines what the rest of the block is for. **If we do not have this, we do
   not have a proof, we have a subtraction.**
2. **Implement `06` §4.3C** — robust location and scale, shrinkage by review
   count — **with the §4.2a fix**: `robust_scale()` returns `None` below `n = 2`,
   so "constant because inconsistent" and "constant because unmeasured" are
   different branches. Today the shipped answer is right by coincidence and
   §4.3C's "handled by construction" claim is false until this is fixed.
3. **Implement candidate D**, empirical-Bayes offsets, 12 lines (§4.3). No
   constant, better held-out RMSE, better recovery. **Keep C as the default for
   legibility; report D's numbers as the headline; expose both as a config flag.**
4. **The held-out harness** (§4.4a): leave-one-review-out, 126 fits, plus the
   paired bootstrap. This is the proof, and it is ~40 lines.
   **Do not attempt leave-one-judge-out** — the parameter is unidentified without
   that judge's own data, and we tried it. Say so in the document.
5. **The recovery experiment** (§4.4a): 200 synthetic panels on the fixture's own
   graph with a known injected severity, snapped to the real 0.05 lattice.
   ~1h. **This is the part that establishes correctness rather than absence of
   harm.**
6. **The `k` and `ε` sweeps** (§4.4b) and the disclosure paragraph. **Do not
   adopt the winning values.** Publishing the curve and saying plainly that we
   did not take the better number is the highest-leverage paragraph in the
   project.
7. **Generate the artefacts**: `normalization-proof.md` (generated, never
   typed), `normalization-proof.csv`, `feasibility-report.md`, `sensitivity.csv`.
8. **The worked example**: one project, its reviews, raw composite, judge
   severities, shrunk severities, normalized rank, rank delta, arithmetic shown.

**Gate 3 at H+62 — the bonus decision.** In order:

| If | Then |
|---|---|
| T4 verified, ≥2h spare | Ship normalization proof + threat model + API First. **Stop there.** |
| T4 verified, ≥5h spare after that | Add pairwise mode (`06` §7), best video in the category |
| T3 or T2 only | Normalization proof only. It is the highest-value-per-hour item in the entire project |

**And the one-line framing for the whole block, which is what the demo video
needs to say out loud:** *we measured whether there was anything to fix. On this
panel there was almost nothing, and here is how we know, and here is how much it
would have taken for us to be wrong — and here is proof that our method recovers
a real effect when one exists.*

---

## 10. Block I · H+62 → H+65 · Demo video

**Recorded, not planned.** Storyboard from `01` §8:

| Time | Content | Proves |
|---|---|---|
| 0:00–0:30 | `docker compose up`, clean clone, network off, ending on the seeded portal and printed credentials | 20% in thirty seconds |
| 0:30–1:30 | Create an event, tracks, prizes, a **visibly weighted** rubric; change a weight and show results move | T1 + the market leader's missing feature |
| 1:30–2:30 | Team, invite link, draft, edit, **and the deadline refusal** | T1-06, shown deliberately |
| 2:30–4:00 | A judge scores — then **we `curl` judge B against judge A on camera and show the 403** | **The money shot** |
| 4:00–5:00 | Normalization proof on real data: raw σ, normalized σ, rank deltas. Then publish, export CSV, show the audit trail | 25% + 20% |

**Rules for the recording:** a real terminal for the `curl`, not a screenshot. No
editing that implies functionality we do not have. If a step is half-built, do
not show it — cut it and say so in the README instead. Five minutes is a ceiling;
four and a half minutes of honest content beats five of padded.

**Record at H+62 precisely because at H+68 it will not happen.**

---

## 11. Block J · H+65 → H+69 · Freeze (4 hours, protected)

- Finalise `README.md` (what it does, how to run, **honest limits**), from
  `01` §9 plus the cut ledger below.
- `ARCHITECTURE.md` from `01` §6 + `05` + `07` §6.
- `DATA-MODEL.md` from `05`, lightly edited.
- `JUDGING.md` from `06` §9's checklist.
- **Final verification pass**, `03` §6 in full:
  - `docker compose down -v` → clean clone → `up`, **network off**.
  - `python3 run.py .dogfood.toml > acceptance-report.txt` — real output, once.
  - All five `curl` controls from `07` §7, re-run against the final build.
  - `git diff` on `acceptance-report.txt` after a second run: must be empty.
  - **`.dogfood.toml` claims exactly what the report verifies.** Last check, no
    negotiation.
- Commit, tag, push, make the repo public, add the contact address.
- Confirm the write-up quest draft exists (`§7`).

---

## 12. Test strategy

`tests/` is not in the 40% — the brief says outright that the checker "does not
look at your HTML, your framework, your database, your file layout or your commit
history" and does not grade test counts. Tests are for **us**, and they earn
their hours in exactly three places:

1. **The isolation matrix** (`05` §6b). `manage.py isolation_proof` as a
   command, and the four Hypothesis invariants as tests — monotonicity, no
   cross-evasion, decline-not-filter, scope-is-total. **This is not hygiene, it
   is the evidence for 25%,** and the property-based version is what makes it a
   method rather than a checklist.
2. **The loader and the round-trip** (`05` §8b). Load fixtures, export,
   re-import, assert byte-identity **including `source_key`**, driven by a
   Hypothesis `world()` strategy. This is what makes the escape-hatch claim
   true rather than aspirational.
3. **The normalization edge cases and the proof harness** (`06` §4.2a, §4.4a):
   `robust_scale` returning `None` at `n < 2`, the held-out LORO RMSE matching
   the published number, the recovery experiment's RMSE bounds, and the
   sensitivity curves matching `sensitivity.csv`. **The proof's numbers should
   be asserted in CI, so a refactor that silently changes the method fails a
   test instead of quietly weakening the document.**

Beyond that, target the places where a bug is expensive and invisible: the
assignment network's **edge count** (`06` §2.2 — 38 vs 77 is a silent wrong
answer, not an error), the deadline guard in both directions, ballot-order
stability, and the hash-chain verifier against a deliberately tampered chain.

Target: **roughly 5 hours total** (was 3h; the second research pass added the
Hypothesis invariants and the proof-harness assertions), spent almost entirely
in blocks B, E, G and H. **Do not write tests for CRUD.**

**Two disciplines that will save us time, from the research pass:**

- **Keep the Hypothesis suite out of the hour-60 verification run.**
  `hypothesis.extra.django.TestCase`, `max_examples=50`, small worlds. It is a
  verification asset, not a critical-path one.
- **The `tools/verify_census.py` self-check is folded into the loader's boot
  output, not a separate script** (`04` §6 already says this). One artefact, and
  it prints its own row counts so a 26-row table over a 30-row population cannot
  ship.

---

## 13. The cut ledger

Kept during the build, published in `README.md`. It is the Write Up Quest's
central question — *"the feature you cut and do not regret"* — answered
honestly, and it is free credibility on the 15% Code Quality criterion.

**Rows 1–9 are pre-populated from the second research pass and are DECISIONS,
not notes.** Each was evaluated and rejected on measurement or on cost, not on
taste. They are written here *before* kickoff so that at H+40, when the
ambition arrives, the answer is already on paper.

| Feature cut | Why | Do we regret it? |
|---|---|---|
| **IRT / MFRM / any joint project-difficulty model** | **Measured to lose.** Held-out RMSE 0.9097 vs 0.7099 for candidate C — *worse than predicting the panel mean.* Parameter-recovery RMSE 0.5414 vs 0.2809. At 3 reviews per project the item facet costs more variance than it recovers (`06` §4.3e). 4 hours to ship something measurably worse | **No.** Naming what we rejected and why earns more than the model. The vocabulary (severity as a *facet*) and the `infit`/`outfit` standardised statistic are both free, and we kept both |
| **MCMC / HMC hierarchical Bayes** | Statistically the right instrument for rater severity (Uto & Ueno 2020) and it would need a sampler, an R̂/ESS convergence diagnostic, and a prior-sensitivity analysis — all of which would then need defending. The method-of-moments τ² gets 90% of the benefit in 12 inspectable lines and **has no constant to defend at all** | **No.** Goes in "what we would do with more time," where it impresses for free |
| **TrueSkill** | A win/loss online rating with a *dynamic* skill parameter: order-of-arrival and skill drift. Our data is static ordinal rubric scores. Adopting it means abandoning the rubric, and the rubric is what T2 asks for | **No** |
| **A Merkle transparency log (CT / RFC 6962 / Sigsum-style)** | CT's value is **witnessing** and we have no witness; a Merkle root we compute ourselves proves only internal consistency, which the 30-line hash chain already proves. Sigsum's actual model also requires a network and a witness quorum, both forbidden. 4 hours for a *strictly weaker* guarantee | **No.** We took the strictly better 80%: publish one chain head and replicate it into every signed judge record |
| **Postgres Row-Level Security as the isolation primitive** | Postgres-specific; needs `SET LOCAL` per transaction with real pool-leakage hazards; **views bypass it by default**; recursive policies fail. Breaks the single-service single-file story carrying 20%. And it would express "judge on trk_04" as a correlated subquery per row where our scoped accessor is one index scan | **No.** The scoped-accessor layer is the portable equivalent and is stronger here |
| **Casbin / OPA** | Our best architectural claim is "exactly one place where the rules live." A policy model file is a **second schema in a DSL** that can drift from the ORM. Our policy is 5 roles × 6 resources and already lives in the ORM | **No.** Trading a single source of truth for a policy engine is a bad trade |
| **The `+50` project-coverage and `+1` track-novelty cost terms** | **Measured to be doing nothing:** plain max-flow at the right capacity delivers 123/123 with no cost function at all. Coverage is already maximum, so a term rewarding maximum coverage cannot change the optimum. They were arguments to defend with zero measurable effect | **No.** Fewer terms is a *better* argument than more terms |
| **Ranked-choice (IRV) and a "jury of the top-voted" for T3** | Both are **more** brigadable than a broad vote under a fixed budget; IRV is materially harder to explain in one sentence. **Decided in:** the **anti-abuse influence report** (`06` §6.2, 1h) ships, and the **ranked Borda ballot does not** — it *changes* the outcome while the report *explains* it, and the brief asks for "an answer to people trying to cheat it", and an answer is a report. Borda is a Break 4 candidate if G finishes early | **No.** A defended rejection plus a better artefact beats an undefended mechanism |
| **`scipy` / `networkx` in the container** | Measured: scipy's Dinic on the real 40-node/77-edge graph takes **0.25 ms**. A hand-rolled successive-shortest-path is the same order and ~80 readable lines. The 60 MB wheel is an install-time failure mode we do not need, and "smaller image, fewer moving parts" is part of the 20% we already win | **No** |
| **Webhooks — CUT at H+0** | **Decided, not deferred.** 2h, **zero points on all four criteria**, and P-8 (SSRF via webhook URL — DNS resolution against private ranges, redirect limits, scheme allowlist) is a real bug class written from scratch under time pressure. `01` §9 already files it as "Nice." **What ships instead:** the `WebhookEndpoint` / `WebhookDelivery` models, a stub view returning 501, and the `export run` / `import run` audit entries — so the schema is there for whoever extends it, and `README.md` says plainly that delivery, retries and signature verification are **not** implemented | **Yes, slightly.** The one cut on this list a panel might notice missing. Mitigated by the stub plus an honest note |
| **Pairwise Bradley-Terry** | Already last on our own list. **New reason, measured:** the fixture's comparison graph is **one connected component, 71 nodes**, and all eight per-track graphs are connected — so the disconnected-graph caveat in `06` §7.3 **will not fire and cannot be demonstrated on the published data.** Do not spend hours hardening a path with no demo | **Only if we had spare hours at Break 4 (H+54).** It is the best five minutes of video in the category, so it stays on the board as pure upside |
| **Certificates as a designed artefact** | 1.5h → **30min**: "render the existing signed record as a PDF." Free marginal cost once the signing primitive exists, and near-zero scored value | **No** |
| **Re-deriving the ballot order instead of storing it — CUT at BREAK-2 + 3h** | `presentation_order` is a **pure function of the identity**, so a stateless implementation is possible and simpler: no `Ballot` row, no unique constraint, no migration. **It was rejected because the guarantee D-12 rests on is that a voter cannot re-roll by refreshing**, and a pure function of a *cookie* is only stable while the cookie survives. The stored row is the enforcement, and the seed is stored beside it so the order is reproducible rather than merely asserted to have existed. Cost of the decision: one table read per request and the F-83 bug below | **No.** A cheaper implementation that holds only under the conditions we control is not a cheaper implementation |
| **Ballot cookies / rate limiting — CUT at BREAK-2** | The open-link mode derives `voter_key` from IP + user agent and hashes both. A signed cookie would make the identity survive an IP change, and a per-IP rate limit would blunt a single-household brigade. **Neither is built**: the cookie is a second identity to get wrong, and the rate limit is a threshold in a project whose stated anti-abuse answer is the influence report, not a gate (D-13). **This is disclosed rather than hidden** — `README.md` names open-link mode as the weakest of the three, and the influence report is the artefact that addresses it | **Yes, slightly.** A determined operator can mint ballots by changing networks, and we would rather say so than imply the identity is stronger than it is. The report is the mitigation we chose, and the report does not stop anything either — it *explains* |
| **Casting votes and ranking on the ballot — CUT at BREAK-2, deferred, not dropped** | `/vote/` renders the order and **does not accept a ranking**. `Vote` and `Ballot` ship with their constraints, indexes and the per-voter budget the schema docstring describes, and the Borda estimator the harness attacks is `bias_attack.schwartzian`. So the order ships **complete** while the vote is unstarted. The reason is the one the whole project is built on: **a permutation nobody can reproduce is a mechanism nobody can check**, and shipping the ranking would have meant shipping the aggregation too, which is REQ-T3-01 and FEAT-06's remaining scope. **Superseded at increment 5: the ranking, the budget and the tally now ship.** The cut that stands is *quadratic* voting — see the next row | **Yes, slightly.** The page a judge reaches is not yet one they can act on, and a reviewer clicking `/vote/` sees an ordering rather than a ballot. Naming that plainly in the README is cheaper than the alternative |
| **Quadratic voting (1, 4, 9, …) — CUT at increment 5, decided not deferred** | It is the classic answer to concentrated voting and it is **already decided twice**: D-13 puts the anti-abuse answer in the *published influence report* rather than a fancier ballot, and the cut ledger's own row on ranked-choice says the same thing. Weight is capped at **3** inside a budget equal to the ballot size, so a voter can concentrate but not compound. Quadratic also changes the *meaning* of the Borda estimator the harness measures, which would leave the harness attacking a function the product stopped using — the drift claim and the mechanism out of step, which is the failure this project treats as disqualifying | **No.** A defended rejection plus a report beats an undefended mechanism, and the cap that ships is the part a reviewer can reason about |
| **Results weighting by *rank* rather than by *weight*** — CUT at increment 5 | The submission is a fixed ballot order plus a per-project weight, so the server never accepts a free-text ranking. A rank-only form would let a voter submit an order they were never shown by reordering the page, which is the one thing the randomised order exists to make awkward | **No.** The stronger property is free once the ballot is stored |
| **Comment rate limiting — CUT at increment 6, and the one control we DID name in the threat model** | `bible/07` V-8 lists four controls for comment spam/XSS: **escaped output, no raw HTML, `pending` moderation queue, rate limits, length caps.** Three ship and are tested; **rate limiting is the one that does not**, and it is the one V-8 names. Not built because it needs per-identity state we deliberately do not keep (the same reason there is no signed ballot cookie), and because this project's stated anti-abuse answer is the **influence report**, not a gate (D-13). **The page and this ledger both say so in plain words** rather than the surface implying a control that is not there | **Yes, slightly.** This is the only place we have written a control down in our own threat model and then not shipped it, which is worse than never having written it — a reader of `07` would reasonably expect all four. Mitigation: it is named in the README, in the cut ledger, and in the module docstring, so it is disclosed three times rather than quietly missing |
| **Comment threading / replies — CUT at increment 6** | `Comment.parent` exists in the schema (nullable, with a CHECK against self-parenting) and nothing writes one. Threading invites flame-threads that a moderation queue with no rate limit cannot keep up with, and REQ-T3-02 asks only for "Comment model, moderation affordance". The column ships so a fork has somewhere to put it | **No.** The schema is already right and the moderation surface is where the work would be |
| **Applying the cross-judge estimator to the published leaderboard — CUT at FEAT-08, decided on measurement** | The estimator is **built, tested and shipped** (`reviewer/normalization/`), along with the proof that decides whether it is needed. It is **not applied** to `/results/`, because that proof measured this panel and found **no severity effect to correct** — between-judge variance `0.0217` against a `0.0971` sampling-noise floor, permutation p = 0.227 — while applying it **moves all 126 scores by ~0.57 rubric points, up to 1.44**. Shipping the transformation would have changed every published number to achieve a measured null, and the page's `unnormalized-raw-weighted-mean` label would have stopped being a disclosure and started being a claim | **Yes, slightly.** A panel that *expects* corrected scores will read a raw mean as a bug, and the honest answer lives in a document rather than on the page. Mitigated by measuring the cost, publishing it, and shipping the sensitivity curve showing the metric's own optimum is `k=12, ε=0.75` — not anything we would have chosen |
| **Reporting the empirical-Bayes estimator's held-out numbers instead of the constant-free one — CUT at FEAT-08** | `bible/06` §4 D is the better estimator (no tunable constant at all, and EB measured ~4.9% better held-out RMSE). It is **not** the one whose numbers we publish, because a *reported* estimator that a reviewer cannot re-derive by hand is worth less than a legible one they can. C's two constants are each defensible in a sentence and the full sensitivity curve is published beside them | **No.** The constant-free estimator remains the strongest argument in the plan and is the first thing to build if this is ever extended |

**Rules for the ledger:**

- Cut on the criterion in `01` §9: anything below the line is worth less than
  anything above it.
- A cut feature is either removed cleanly or honestly documented as partial.
  **Never shipped broken and never claimed.** A half-built feature that is
  disclosed costs us almost nothing; the same feature claimed and broken costs
  the credibility of everything else we say.
- Write the regret column honestly, including the ones we do regret. That column
  is the most convincing part of the whole thing.
- **The regret column is the deliverable.** A cut list where every row says "no"
  reads as a list of things we were afraid of. The two "yes, slightly" rows are
  what make the other ten credible.

---

## 14. Write Up Quest

Worth $100 × 4, closes **5 Oct 18:00 UTC**, judged on insight and substance
rather than reach. It does not affect the main score, so it is pure upside and it
is **not** something to do at H+68.

**Draft the skeleton during Block E (H+26), when the isolation work is fresh and
there is genuinely something to say.** Five sections, each of which we will
actually have material for:

1. **The isolation bug we did not have, and the one we nearly had.** Building the
   scoped-accessor layer in the first four hours specifically so this could not
   happen — and the moment in testing when we realised what it would have cost
   to retrofit. This is the strongest section available and it is true.
2. **Normalization: the maths that fought back.** `σ→0` on `jdg_07`, `n=1` on
   two judges, the difference between "inconsistent" and "unmeasured," and why
   the honest σ is the one we publish.
3. **The schema we would redo.** `05` §12, written when it is cheap. Custom
   questions as `JSONField` and the state-machine columns.
4. **One command, honestly.** What it cost to keep to a single service, and what
   we gave up by not using Postgres.
5. **The cut list**, from §13.
6. **The numbers we got wrong** — new, and it is the section with the most
   material already written. Four census errors in our own planning documents,
   two of them arithmetically impossible (a project histogram implying 128 score
   rows in a 126-row file, and a judge histogram summing to 29 judges in a
   30-judge file), and three named judges who turned out to be *kind* rather than
   severe. The generalisable lesson is the two invariants, and the specific
   lesson is that **every number in a document aimed at senior reviewers should
   be generated, not transcribed** — which is the same argument we make for the
   normalization proof, arriving from the opposite direction. This is exactly
   the "benchmark that disappointed you" and "the design you abandoned" material
   the Write Up Quest asks for, and it is free: it already happened.

Where to publish: our own blog is best, because judges can read the whole argument
without a character limit and a dev.to or LinkedIn post truncates the maths. Tag
Hackathon Raptors, post a link to the repo. A 200-follower account writing
something genuinely useful beats a viral thread that says nothing — the brief
says so, and in this case that is literally the advice.

---

## 15. The five decision points, restated

The whole plan reduces to five decisions made with data instead of adrenaline.
**The first four are the four breaks in `§1b`; the fifth is the freeze.**

| # | When | Decision |
|---|---|---|
| **1** | **H+14 · Break 1** | T1 green? Tag `v-t1-verified` and start D. If not, we have 54 hours to fix a gate — which is the entire reason this break exists. |
| **2** | **H+30 · Break 2** | T2 green, all six demands and not just the four the checker tests? Tag `v-t2-verified`. **This is the fallback state if everything after H+31 goes badly, and the most valuable tag in the repo.** If not, stop and fix T2 — everything since H+0 sits on it. |
| **3** | **H+40 · Break 3** | T3 green? Claim T3, start G. If not, claim T2, name the gap, start G anyway. **The build order does not change; only the claim does.** This is where most teams inflate, and inflation is the one documented way to lose points for free. |
| **4** | **H+54 · Break 4** | How much of T4 is verified green? Claim T4, T3+one, or T3 with a precise list. **The last scheduled decision before the freeze.** |
| **5** | **H+68** | Does `.dogfood.toml` match `acceptance-report.txt`? **If not, the report wins.** |

**At decision 5 there is no negotiation available.** The checker prints
`claimed …, verified …` and flags the difference, the panel runs the identical
program, and the brief states three separate times that honest reporting is
rewarded and inflation is penalised. If the report says T2, we claim T2 and put
the gap in the README in our own words.

**At every one of the first four, the slippage ledger (`§1c`) is updated before
the claim is decided** — because a claim made without knowing what it cost is
not a decision, it a hope.

**And the version of this plan that wins is not "we shipped everything."** The
brief says a clean T2 beats a broken T4, and it says it three times, by people
who have watched thirty-five events decide that way.

**We are going for T4, and that decision is now made.** What has changed since
`§1` was first written is *where the claim is decided*: not at kickoff, but at
four scheduled one-hour breaks, each with a fixed seven-step protocol, each one
tagged, each one preceded by an honest slippage figure. **T4 is our build
order. The claim is whatever is green when we get there, and we find out at
H+40 and H+54 instead of at H+66** — with four hours of protected freeze behind
it either way.

That discipline is itself scored. `01` §5: *"Honest gap reporting is rewarded,
inflated claims are penalised."* An organizer who forks this in 2027 inherits a
plan that tells them what to do at the top of every hour, and a README that
tells them what is not finished. That is worth more to them than a sixth
half-working endpoint.
