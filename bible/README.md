# DOGFOOD 2026 · Foundation Bible

**Read this first. Then read `01`. Then start building.**

This folder is not documentation. It is the decoded demand — the complete
specification of what winning DOGFOOD 2026 actually requires, extracted from
three sources that disagree with each other in small, expensive ways:

1. `https://dogfoodhack.com/` — the brief, tiers, scoring, prizes, rules
2. `https://dogfoodhack.com/spec` (+ local `spec.md`, `context.txt`) — the four files
3. `run.py` — **the actual scorer.** 268 lines. It does not care what we write
   in our README, and it is the same program for all ~40 teams.

Everything here was verified by reading those sources line by line and by
analysing `fixtures.json` directly. Numbers in this folder are measured, not
recalled from the marketing page. Where the website and the checker disagree,
**the checker wins** and the discrepancy is called out.

---

## The one-paragraph thesis

Raptors does not want a demo. They want the thing they fork on Monday and run
for a decade. The scoring function is not a rubric we satisfy — it is a set of
failure modes we must avoid. 40% of the score is tier completion *verified by a
program*, and the program only tests seven things, one of which (peer-score
isolation) is the single most common way a beautiful project loses. 25% is a
judging engine that defends itself in writing, which almost nobody will attempt
properly. The remaining 35% is won by being the submission a stranger can run
and a senior reviewer can respect. **Nobody in this category is going to ship a
correct, documented, *measured* normalization engine. That is the whole
opening** — and after the second research pass the opening is wider than we
thought, because the honest version of the claim is stronger than the
flattering one: we can show that the published fixture contains almost nothing to
correct, prove we are not fooling ourselves, and prove our method recovers a
real effect when one exists.

### What we are building, and for how long

**This is not a weekend submission. It is the judging engine the organizers
intend to fork and run for a decade.** That framing changes three things and
should be stated once, here, so every later decision has something to be
measured against:

1. **The public dataset is a regression suite, not a demo fixture.** Every
   number in `04` is asserted by `tools/verify_census.py` at boot. An organizer
   who upgrades the portal and points it at a *new* dataset gets the same
   treatment: census printed, invariants checked, anomalies reported, and the
   normalisation engine refusing to claim an effect it cannot measure.
2. **The engine is the product, not the portal.** The normalisation method, the
   assignment certificate, the isolation proof and the signed records are the
   parts that outlive any one event's UI. They are the parts we spend the extra
   hours on, and they are the parts `JUDGING.md` and `DATA-MODEL.md` exist to
   defend.
3. **Every "we cannot guarantee" in `07` is a documented constraint on future
   work, not an apology.** A decade of organizers will hit the same walls. Our
   job is to have written down where the walls are.

---

## Document map

| File | What it settles | Feeds deliverable |
|---|---|---|
| `README.md` | How to use this folder | — |
| **`ENVIRONMENT.md`** | **What is installed, pinned, and actually verified** — plus the two claims that turned out to be false and the Docker blocker | `08` §2, `01` §6 |
| **`DISCORD-QUESTIONS.md`** | **14 paste-ready messages** for the spec ambiguities, priority-ordered, with the evidence already attached | `02` §10 |
| `01-MISSION-AND-WIN-CONDITIONS.md` | Why we win or lose. Scoring function → tactics. The nine ways to score zero. T4 risk register and demotion gates. | `README.md`, demo video narrative |
| `02-REQUIREMENTS-TRACEABILITY.md` | Every demand in the brief as an ID, with acceptance check, intent, evidence, risk. The "nothing was missed" proof. | all four `.md` deliverables |
| `03-ACCEPTANCE-CONTRACT.md` | Line-referenced reverse engineering of `run.py`. The seven checks on the wire. Seven silent-failure traps. Pre-submission checklist. | `acceptance-report.txt`, `.dogfood.toml` |
| `04-FIXTURES-DATASET-BIBLE.md` | Measured census of `fixtures.json`. The eight deliberate edge cases, what each punishes, and the seed behaviour they force. | `DATA-MODEL.md` |
| `05-DOMAIN-MODEL.md` | The schema. Constraints, indexes, isolation-scoped access, and the escape hatch. | `DATA-MODEL.md`, `ARCHITECTURE.md` |
| `06-JUDGING-ENGINE.md` | Assignment, isolation, normalization, pairwise. Three normalization candidates with defences. The bonus options matrix. | `JUDGING.md` |
| `07-SECURITY-AND-THREAT-MODEL.md` | Attacks stopped and attacks not stopped. The audit trail. | `JUDGING.md`, `ARCHITECTURE.md` |
| `08-DELIVERY-PLAN.md` | Hour-by-hour against a 69-hour clock. Freeze buffer. Demotion gates. Cut ledger. | `README.md`, Write Up Quest |

---

## Verification status

**Every measured number in `04` and `06` was re-derived directly from
`fixtures.json` and `run.py` rather than trusted, and every claim about how a
library behaves has been executed against the installed stack rather than
recalled.** Eleven errors were found. All are listed here rather than quietly
corrected, because a planning document that silently fixes its own numbers is
one you stop trusting, and because *"the benchmark that disappointed you"* is
material for the Write Up Quest.

| # | Was | Now | Where | How it was caught |
|---|---|---|---|---|
| 1 | Projects by review count `8 / 22 / 9 / 2` | `8 / **26** / **3** / **4**` | `04` §2 | **Invariant 2.** The old figures imply `8·2+22·3+9·4+2·5 = 128` score rows. The file has 126. A distribution of 128 rows is not a distribution of 126 rows, whatever the bucket counts sum to. |
| 2 | Judges by review count `2/7/5/4/3/5/1/1/1` | `2/**6**/**7**/4/3/5/1/1/1` | `04` §2 | **Invariant 1.** The old counts sum to **29 judges**. The file has 30 — one judge had vanished, which is why it survived a casual read. |
| 3 | `jdg_24`, `jdg_26`, `jdg_29` named as the severe judges | `jdg_01` (2.0000, n=1) is harshest; all three named IDs are at or **above** the panel mean | `06` §4.1 | Recomputing per-judge means. Two of the three guesses were wrong *in direction*. Never put a guessed ID in `JUDGING.md`. |
| 4 | Criteria listed as `functionality, innovation, quality` in all 126 records | The key **set** is stable; the key **order** in the file is `functionality, quality, innovation` | `04` §1 | Inspecting key order rather than key identity. Harmless until a CSV writer derives column order from the first row it sees, at which point it transposes two columns in every export. |
| 5 | The per-judge severity table in `06` §4.1a listed `jdg_07` as the **7th most generous** of 30 | **4th most generous.** `jdg_02` 4.2167, `jdg_30` 4.0375, `jdg_15` 4.0083, **`jdg_07` 4.0000** | `06` §4.1a | Sorting the 30 means. The prose also contradicted its own table, which filed `jdg_07` in a middle column and so broke its own sort order. **The argument got stronger, not weaker — 4th of 30 is a more striking fact than 7th.** |
| 6 | The same table listed **26 rows for a 30-judge population** | `jdg_21` (3.6750, n=4) and `jdg_22` (3.7300, n=5) restored; table now 30 rows, sorted, with its row count printed | `06` §4.1a | **Invariant 1 again.** A 26-row table over 30 judges fails the cardinality check — which is precisely the check that caught errors 1 and 2. **Found on a second pass, after this correction log had already been written.** |
| 7 | *"Two of eight tracks are **structurally infeasible**" at a target of 3 | They are **zero-slack**: 18 needed, 18 available, so a perfect matching **exists**. They become **provably infeasible at per-judge capacity 5** (max-flow delivers 117/123 and the min-cut names `trk_01` and `trk_08`, deficit 3 each) | `06` §2.1a | Building the assignment network and running max-flow. **The claim was false and falsifiable in five minutes by hand.** The corrected version is a *better* claim, which is the only reason it is a correction and not a retraction. |
| 8 | *"The organizers' own data missed the target in both"* those tracks | **Three** tracks missed: `trk_01` −2, `trk_06` −1, `trk_08` −1. Five over-covered by +7, netting +3 — **so the event looks fine on a global completion bar while three local targets failed.** That is the actual argument for per-track reporting | `06` §2.1a | Per-track review counts. The row was in the table ("slack 3, but 1 short"); the prose said two. |
| 9 | *"41 projects → 123 assignments against 126 existing score rows. Close enough to confirm the target is 3"* | **Withdrawn as an inference.** The totals disagree, and per-track it is 3 short and 5 over. The real evidence is the **mode: 26 of 41 projects have exactly 3 reviews** | `06` §2.1 | Noticing the inference does not hold. A net surplus of three is consistent with a wide range of targets; a mode of 26/41 is not. |
| 10 | `MAD` for a single-review judge | `median(|x − med|)` over one element is **0 for a structural reason**, identical to the number `jdg_07` produces for an *evidential* one. The shipped answer was right by coincidence | `06` §4.2a | Reading the formula against §4.2's own insistence that "constant because inconsistent" and "constant because unmeasured" must not be conflated. **The code contradicted the document it implements.** |
| 11 | *"`03` §3.2: exempt DRF's `SessionAuthentication` from CSRF (**DRF does this by default for session auth**)"* | **It does not.** `hasattr(SessionAuthentication, "enforce_csrf")` is `True` and `SessionAuthentication.enforce_csrf is None` is `False`. DRF defines `enforce_csrf()` and calls it from `authenticate()`; the check runs for unsafe methods only | `03` §3.2, `07` P-1 | **Executing the installed library.** The widest class of the eleven, and the most expensive: `run.py` POSTs as `participant` expecting any 4xx, **a CSRF 403 is a 4xx, so T1-3 would have passed without the deadline ever being tested.** Now carries the verified behaviour, a per-check table, the `enforce_csrf = None` subclass and four compensating controls |
| 12 | Seeding the fixture's 121 people | 121 distinct people × ~400 ms per `pbkdf2_sha256` hash (Django 5.2 default, 1,000,000 iterations) = **~48 s, which is 4.8× `run.py`'s 10-second timeout**, and the loader runs before gunicorn binds. **Only the 5 seeded test identities get real hashes; the other ~116 get `UNUSABLE_PASSWORD`** | `04` §5.2, `03` §4.7 | **Timing the installed hasher.** A schema decision, so it belongs in the Block B migration — not something to discover at H+13 with a timeout on the clock |

> **The lesson from errors 5–7 is worse than the lesson from 1–4, and the lesson
> from 11–12 is worse than both.** A correction log that *itself* contains
> un-caught errors teaches a reader to distrust the process rather than the
> number. Ten of the twelve were found by one rule — **the two invariants** — or
> by **executing the library instead of recalling it.** Two of the census errors
> were found *after* the first correction log was written.
>
> **The rule that follows, and it is the one that generalises to a decade of
> organizers running this platform: every census table is generated and prints
> its own row count; every framework-behaviour claim is a five-line script with
> its output pasted in.** `ENVIRONMENT.md` is where the second kind lives.
> We learned the first rule the second time we broke it, and the second rule
> because a *documented DRF default* turned out to be the wrong way round.

---

## Findings we contributed upstream

**Not our errors. These are things we found in the published material, reported
with the evidence attached, and either corrected or still open.** They are
recorded separately from the table above because mixing "we were wrong" with
"we found something" would be dishonest in both directions.

| # | Finding | Evidence sent | Outcome |
|---|---|---|---|
| **U-1** | **The published σ = 0.94 is not obtainable from `fixtures.json`** under any of four natural definitions of judge spread. Largest obtainable: **0.4323** (sd across the 30 judge means) | The four definitions with their measured values, and the arithmetic | ✅ **Confirmed as a bug in the website description, most likely a cosmetic landing line not present in `/spec`. Homepage corrected to σ = 0.42 — the stdev of per-judge means — and we were asked to build the proof against the actual fixture values.** Full treatment in `06` §4.4c |
| **U-2** | **The fixture contains no measurable judge-severity effect.** Between-judge variance **0.0217** against a sampling-noise floor of **0.0971**; permutation **p = 0.234**; detection floor **τ = 0.75** at n̄ = 4.2 | The variance decomposition, the permutation test, the power analysis | ⏳ **Open — asked as a question, not asserted.** `06` §4.1b |
| **U-3** | **The published normalized figure of 0.31 is reproducible by three global standardizations, none of which contains a per-judge term** (0.3174, 0.3240, 0.3301) — which is what you would expect if there is not much judge effect to remove | The sweep, framed as *"we think we can reproduce it, here's our definition"* | ⏳ **Open — asked in a mod DM, awaiting reply** |
| **U-4** | **Asked whether labelled synthetic data is permitted in the Normalization Proof artefact** | The construction: fixture's own judge–project edge list held fixed, only the values changed, snapped to the same 0.05 lattice, 200 panels, one judge forced constant | ✅ **"Yes, synthetic data is fine for validation as long as the proof also runs on the real fixtures. Showing it recovers a known effect is exactly the kind of rigour the bonus is looking for."** Condition already satisfied by construction — `06` §4.4a now states where each real-fixture result sits |
| **U-5** | **They told us the grading criterion in plain language, unprompted** | — | ✅ **"exactly the kind of rigour the bonus is looking for"** — see below |

> ### The most valuable sentence we have received
>
> **"Showing it recovers a known effect is exactly the kind of rigour the bonus
> is looking for."**
>
> That is a moderator describing the grading rubric for the Best Judging Engine
> prize, in ordinary language, without being asked to. **It de-risks the entire
> Normalization Proof plan** — the block we had protected six hours of the
> 69-hour clock for (`08` §9) — and it confirms the one thing we were betting on
> and could not verify: that a **parameter-recovery experiment** is the artefact
> they want, rather than a bigger σ reduction.
>
> **It also means the ordering in `06` §4.4a is not a stylistic preference any
> more.** Their condition was *"the proof also runs on the real fixtures"* —
> with "also" doing the work. So the real-fixture results are the proof and the
> synthetic panels are the supplement, which is exactly the order we already
> publish them in. **We were compliant before we knew the condition existed,
> which is the right way round.**

**Why this section exists at all.** The brief says *"Honest gap reporting is
rewarded"* — and this is the same discipline pointed outward rather than inward.
`U-1` is the proof that the method we built to check our own numbers works on
someone else's: we ran it on the spec, it produced a discrepancy we could not
explain away, we reported it with the evidence, and it was correct. **That is
worth more to a panel than a σ figure**, because it is the difference between a
claim and a method.

**And why `U-2` and `U-3` are asked rather than published as findings.** We do not
know the organizers' definitions, and we may have the wrong one. Reporting
"your normalization is doing nothing" as a *conclusion* would be showing off
with a number we cannot fully explain. **Asking is the honest version, and if
they tell us the definition, we either learn something or we are wrong — both
are better outcomes than a confident guess in a document.**

**Confirmed correct, no change needed:** 8 tracks / 30 judges / 40 teams /
41 projects / 126 scores; `submissions_close = 2026-03-01T18:00:00Z` in the
past; titles `[0:3] = Glass Signal, Small Meadow, Deep Compass`; 21 single-track
and 9 dual-track judges; team sizes 13/12/6/9; 51/126 empty comments; zero
duplicate `(judge, project)` pairs; zero off-track scores; no project with zero
reviews; no late submissions; all 30 judge emails and all 91 member emails
unique and disjoint, all `@example.org`; all three per-criterion value
histograms; `prj_07` + `prj_41` duplicate pair, 13h 28m apart; `jdg_07` constant
at 4/4/4 × 3 across `prj_09`, `prj_17`, `prj_19`; `jdg_01` and `jdg_23` at n=1;
`jdg_24` at n=11; panel mean 3.4937, median 3.5417, sd 0.4323; `jdg_01` is 39.8%
of the measured severity spread; **the judge–project bipartite graph is one
connected component of 71 nodes, and all eight per-track subgraphs are
connected.**

**Three new findings from the second pass, all of which strengthen the
deliverables:**

- **The fixture has no measurable judge-severity effect at all.** A one-way
  random-effects decomposition puts the between-judge variance at **0.0217**
  against a **sampling-noise floor of 0.0971** at n̄ = 4.2 reviews per judge;
  permutation **p = 0.234** for severity and **p = 0.186** for dispersion. At
  this panel size you could not have detected a severity spread smaller than
  **τ = 0.75**. And **P(the minimum of 30 noisy judge means lands at or below
  2.0 | no judge effect) = 0.0145** — so `jdg_01` at 2.0000 is a once-in-seventy
  event, not a discovery. Full analysis in `06` §4.1b.
- **The organizers' published σ = 0.94 was not reproducible from the fixture**
  under any of four natural definitions; the largest obtainable value is
  **0.4323**. We reported it with the evidence; they confirmed a website bug and
  **corrected the homepage to 0.42 — our number**. Recorded as a contribution
  (`README` § Findings we contributed upstream, U-1), not a caveat. *We would
  rather be checkable than competitive, and this is what that looks like when it
  works.* Full treatment in `06` §4.4c.
- **Normalizing the fixture measurably works, and we can prove it out of
  sample.** Leave-one-review-out, predicting a held-out review from the other
  reviews of the same project: **0.7952 uncorrected → 0.7099 with candidate C →
  0.6753 with the empirical-Bayes estimator**, paired-bootstrap CIs excluding
  zero. And **leave-one-*judge*-out is impossible** — the parameter is
  unidentified without that judge's own data — which is the kind of thing a
  statistician checks first and which we now say out loud.

**Standing rule adopted from this pass:** any census figure quoted in
`DATA-MODEL.md` or the normalization proof asserts both invariants — bucket
counts sum to the population, and `Σ(n × count)` equals the record total. The
seed step prints them on boot (`04` §6). The verification script itself is
written at H+0 as `tools/verify_census.py` and becomes the loader's test — it is
**not** written now, because "new code only, in the window" is a scored rule
and a planning document is not an exception to it.

---

## Standing decisions

These were decided before writing. Change them here, not in scattered files.

| Decision | Choice | One-line reason |
|---|---|---|
| **Stack** | Django 5 + DRF + SQLite-by-default, single container | Shortest path to a *correct* role model (40%), and one service means `docker compose up` genuinely works offline (20%). See `01` §6. |
| **Database** | SQLite (WAL) default; schema written Postgres-portable with a documented `DATABASE_URL` switch | No second service to pull or race. A database person still gets a defensible schema plus a migration path. |
| **Deployment shape** | One image, one service, gunicorn + whitenoise, seeds on `migrate` | "One command to running" is 20% of the score. Every additional service is a judge who gave up at minute three. |
| **Auth** | Django sessions, self-hosted, no external IdP | Auth-as-a-service is an explicit disqualifier. |
| **Role isolation** | DRF permission classes + **queryset-level scoping**, never view-level post-filtering | Must survive a `curl`. Structural, not incidental. Two layers only, and the reason is a failure-independence argument, not "defence in depth" (`07` §2b) |
| **Isolation error** | Literal `403`, never a `302` to a login page | `run.py` follows redirects. A redirect returns `200` and fails the check. This is the single highest-value line in the project. |
| **Isolation, made visible** | `for_actor()` returns a queryset carrying a human-readable `ScopeReason`; every list view renders it | A judge can verify isolation by *reading*, not by trusting our tests. One object, three consumers (`05` §6a) |
| **Seed** | Idempotent loader for `fixtures.json` + deterministic four test identities whose headers are printed on boot | The checker never logs in. We hand it headers. They must be printed or we have to hardcode them. |
| **CSV** | First line is a comma-containing header row | That is literally the assertion. |
| **Normalization** | Robust location/scale + shrinkage (`06` §4.3C) as the **legible default**, empirical-Bayes offsets (`06` §4.3D) as the **constant-free estimator whose numbers we report** | Legibility for the human-facing default, accuracy for the headline number, and we say which is which |
| **Normalization, before anything** | Detectability analysis first: is there an effect to remove? | A normalisation claim that does not test for the effect it removes is a subtraction, not a proof (`06` §4.1b) |
| **Assignment** | One flow over all tracks; min-max capacity by search; load-imbalance + seeded tiebreak only; min-cut certificate | Dual-track judges couple the tracks, so per-track flows are wrong. Two cost terms cut on measurement, one moved to eligibility (`06` §2) |
| **Audit** | Append-only **and hash-chained**, with `omitted_since_prev` inside the chain | Rate-limited sampling plus a chain is incoherent — a gap looks like an edit. The count goes in the chain (`06` §5.2) |
| **Signed records** | Ed25519 (RFC 8032) over an **in-toto Statement v1 inside a DSSE envelope**, keys on their own volume | DSSE signs bytes, so no third party has to agree with us about canonicalisation. Separate volume because our own checklist runs `down -v` (`05` §9) |
| **Signed records, and no Merkle log** | Publish one chain head; replicate it into every judge's record | CT's value is witnessing and we have no witness. A root we compute ourselves proves only what the chain already proves (`05` §9c) |
| **Voting** | Quadratic influence, with the claim stated as **cost amplification inside an identity budget, not Sybil resistance** | The mechanism-design literature is explicit that the second requires a cost we do not have and cannot have (`06` §6.1) |
| **Ballot order** | Seeded per-voter permutation, stable across requests. Claim: **zero-*mean*, not zero** | Randomisation cannot do better than zero-mean, and the paper says so (`06` §6.3) |
| **Escape hatch** | Seven CSVs for humans + one canonical JSON document for the property test + a signed archive | CSV is not a canonical form; asserting byte-identity on it is a trap (`05` §8b) |
| **Round trip** | Byte-identical **including `source_key`**; only surrogate PKs may differ | "Modulo generated IDs" is not a testable property — a dropped column passes (`05` §8a) |
| **Scope** | Full T4, flagship, nothing knowingly broken | Accepted risk, mitigated by hard demotion gates in `08`. |
| **Bonuses** | Normalization Proof first, Threat Model second, API First third; Pairwise as pure upside. Gate at hour 62 | The proof is the artefact that decides the $100 prize and it is the highest value per hour (`06` §8, `08` §13) |

---

## Non-negotiables

If any of these is untrue at freeze, we are not done. Each maps to a checker
assertion or an explicit rule.

1. `docker compose up` → portal on `localhost:8080`, seeded, **with the network off**.
2. Seeded with `fixtures.json`'s own `submissions_close` (a past date), not our own.
3. A peer-scores request from `judge_b` returns **403**, not 200, not 302.
4. The first page of the public gallery contains one of `Glass Signal`, `Small Meadow`, `Deep Compass`.
5. `run.py` is run against the running portal and its **actual output** is committed as `acceptance-report.txt`.
6. `.dogfood.toml` claims only what the report verifies.
7. OSI license. No assignment, no CLA, nothing to sign.
8. Nothing in the repo requires a cloud account, a hosted database, or an auth provider.

---

## The four sentences that decide the outcome

Everything else is negotiable. These are not.

> **"Hiding another judge's scores in your template is not refusing."** — the spec, on the check that costs the most points. Which is why our isolation is enforced in the data-access layer, refused with a literal 403, printed as a matrix by one command, and *explained to the user in the page itself*.

> **"A clean T2 beats a broken T4."** — stated three separate times in the brief by people who have run thirty-five events. We take the third one seriously and engineer around it: build T4, but make every tier independently verifiable, and demote honestly at the gates in `08` rather than ship a T4 that lies. The demotion is a *process* decision made with data, not a panic. That discipline is itself scored.

> **"We measured whether there was anything to fix, and we told you."** - ours, not theirs, and it is the sentence the second research pass made possible. The published fixture has no detectable judge-severity effect (p = 0.234), any per-judge centring reports a judge spread of *exactly zero* by arithmetic rather than by merit, and **we found a real error in the published spec, reported it with evidence, and it was corrected to our number** (0.94 to 0.42, where 0.4323 is what we measure). **Every one of those is a trap, and every one of them is an opportunity for whoever names it first.**

> **"Here is the curve, and here is what we would have gained by cheating."** — the sensitivity disclosure in `06` §4.4b. Our shipped `ε = 0.5` is *not* the held-out optimum; `ε = 2.0` scores better and we did not adopt it. A panel shown that paragraph reads every other number we publish as checkable. A panel not shown it reads them all as assertions.

We take the third one seriously and engineer around it: build T4, but make
every tier independently verifiable, and demote honestly at the gates in `08`
rather than ship a T4 that lies. The demotion is a *process* decision made with
data, not a panic. That discipline is itself scored — "Honest gap reporting is
rewarded, inflated claims are penalised."

---

## Reading order

- **Planning / before code:** `01`, `02`, `03`, `04`
- **Building the schema:** `05`, then `04` again
- **Building judging:** `06`, `07`
- **Shipping:** `08`

Ask in Discord when something is ambiguous. *"An ambiguity found on Wednesday
is a fixed spec. The same ambiguity found on Saturday is three teams building
three different things."* We are past Wednesday. Log every assumption in
`02` §5 as we find them, and resolve the high-severity ones out loud.
