# Project Overview — Judge Judy

> **Loadable context for any agent session. Keep under 20,000 bytes.**
> Regenerate by editing `blueprint/project-plan.md` and `blueprint/build-plan.md`,
> never by patching this file by hand.
> Depth lives in `bible/` (330KB) — read the named section, never the folder.

**What this is:** a self-hostable hackathon submission and judging platform for
DOGFOOD 2026, built to be forked and run for a decade. Not a demo.
**Window:** 69 hours, one person, solo. Freeze H+69.
**Status:** FEAT-01, FEAT-02 and FEAT-03 built and verified. 24 models across 12
apps; the isolation primitive, the loader, the public gallery and the deadline
guard are in place. **`run.py` prints `claimed T1, verified T1`, and
`v-t1-verified` is tagged.** Next: **FEAT-04** — rubric, assignment + min-cut,
judge console.

---

## 1. The hard constraints — never re-litigate

1. **69 hours, solo.** This binds everything. Reject any idea over ~6 hours, and
   say so out loud.
2. **New code only, in the window.** The `bible/` and `blueprint/` layers are
   planning documents, not application code. Dependencies and environment setup
   are explicitly permitted by the spec.
3. **Offline, one command, laptop, network off.** No cloud account, no hosted
   database, no auth provider, no external API, no API keys. A binary
   disqualification if broken.
4. **Django 5 + DRF + SQLite (WAL), Postgres-portable schema, one container,
   gunicorn + whitenoise.** Do not propose a stack change unless it is worth
   more than ~4 hours of build time.
5. **Every idea must survive a `curl` from a judge with no documentation and no
   patience.**

## 2. The scoring function — optimise against this, not against feature count

| Criterion | Weight | What earns a 5 |
|---|---|---|
| Tier Completion & Correctness | **40%** | T4 verified, nothing broken. **T1 is a hard gate — clear T1 or not judged.** Correctness beats breadth |
| Judging Integrity | **25%** | Backend-enforced role isolation, documented + defensible normalization, readable audit trail, abuse thought about up front |
| Adoptability & Operability | **20%** | One command, seeded, documented, migration path in and out, clean licence |
| Code Quality & Innovation | **15%** | Idiomatic, defensible schema, "the decision that made a judge stop" |

**The structural fact that drives everything:** `run.py` machine-verifies **7
checks — 3 in T1 and 4 in T2, and nothing else.** It is a disqualification gate
and a credibility signal, not a score. ~90% of the 40%, and effectively all of
the 25/20/15%, is read by a human with a rubric. **Build for the reader, not the
checker.**

There are **no T3 or T4 checks at all**, and `verified` is prefix-locked over
`["T1","T2","T3","T4"]`, breaking at the first tier that has no passing check.
So a flawless build still prints `verified T1 T2`. That is arithmetic, not a
bug — see `bible/03` §2 and F-34.

Panel: 36 senior engineers, 3 reviews per project, σ = 0.94 on their own scale.
Marginal improvements do not separate us from the field. Be **decisively** better
on at least one axis.

## 3. Stack — installed and verified, not recalled

| | Version | Note |
|---|---|---|
| Python | **3.13.13** | venv. Container `python:3.13-slim` is 3.13.15 — same line, so local == container. **A bare `python` is 3.14.6 with no Django (F-38)** |
| Django | 5.2.17 | **LTS, not 6.1** — the organizers fork this for a decade |
| djangorestframework | 3.18.1 | |
| drf-spectacular | 0.30.0 | API First bonus |
| whitenoise · gunicorn · cryptography | 6.12.0 · 26.2.0 · 50.0.1 | gunicorn marked `sys_platform != "win32"` |
| pytest · pytest-django · hypothesis · ruff | 9.1.1 · 4.14.0 · 6.168.2 · 0.16.9 | dev only, not in the image |

**28 packages, 17 runtime. Deliberately absent, with reasons in
`requirements.txt`:** numpy, scipy, networkx (measured unnecessary — 126 rows, a
40-node graph), celery/redis (a second service is a disqualifier), argon2-cffi
(Django 5's default is correct for this posture), any cloud SDK.

Verified working: FTS5 gallery search, WAL, JSON1, `CheckConstraint` /
`JSONField` / composite `UniqueConstraint` portable across both engines, and
Ed25519 sign/verify **with tamper rejection**.

## 4. Decisions that cannot be re-litigated

| # | Decision | One-line reason |
|---|---|---|
| D-01 | **Isolation in the data-access layer.** `Review.objects.for_actor(actor)` returns an already-scoped queryset. No code path from a view to an unscoped `Review`. A lint rule forbids the unscoped form | The spec names this: *"hiding another judge's scores in your template is not refusing"* |
| D-02 | **Denial is a literal 403, never a 302.** Empty body, no `Location` header | `run.py` follows redirects; a redirect returns 200 and fails T2-5. **Highest-value line in the project** |
| D-03 | **Two enforcement layers, not three.** Permission *decides* and raises; the queryset *constrains* and cannot. They fail in opposite directions | A third layer is derived, therefore a second source of truth. The lint rule is the exception: it enforces a *syntactic* property, which is mechanically checkable (`bible/07` §2b) |
| D-04 | **Normalization: robust median/MAD + shrinkage `k=3`, `ε=0.5` as the legible default; empirical-Bayes (`τ²` by moments) as the constant-free estimator whose numbers we report** | EB measured 4.9% better held-out RMSE and has **no tunable constant at all**, which removes our largest exposure |
| D-05 | **Detectability analysis first.** Is there an effect to remove? | A normalization claim that doesn't test for the effect it removes is a subtraction, not a proof |
| D-06 | **Assignment: one flow over all tracks, min-max capacity by search, load-imbalance + seeded tiebreak only, min-cut certificate** | 9 of 30 judges are dual-track, so per-track flows are wrong. Two cost terms cut on measurement, one moved from cost to eligibility |
| D-07 | **Infeasibility is diagnosed, never asserted.** The min-cut names the deficient projects, the bottleneck judges, the deficit, and three remedies with arithmetic | "Feasible" and "provably impossible" are different answers and get different code paths |
| D-08 | **Audit is hash-chained**, with `omitted_since_prev` inside the chain | Rate-limited sampling plus a chain is incoherent — a gap is indistinguishable from an edit |
| D-09 | **No Merkle transparency log.** Publish one chain head; replicate it into every signed judge record | CT's value is *witnessing* and we have no witness. The chain head in N signed records is strictly stronger for a third of the code |
| D-10 | **Signed records: Ed25519 in an in-toto Statement v1 inside a DSSE envelope.** Keys on their own volume | DSSE signs bytes, so no third party reimplements our canonicalisation |
| D-11 | **`source_key` on every importable table.** Round-trip is byte-identical *including natural keys* | "Modulo generated IDs" is not a testable property — a dropped column passes |
| D-12 | **Voting claims cost amplification inside an identity budget, not Sybil resistance.** Randomized order makes bias zero-*mean*, not zero | The mechanism-design literature is explicit; claiming otherwise is falsifiable in one search |
| D-13 | **Anti-abuse = the published influence report**, not a fancier ballot | The brief asks for *"an answer to people trying to cheat it"* and an answer is a report |
| D-14 | **Webhooks cut.** Models + 501 stub + audit events ship | 2h, zero points on all four criteria, and SSRF is a real bug class under time pressure |
| D-15 | **No LLM scoring.** Measured and closed | Laya scores 0.35 vs a 0.318 random baseline; Jev needs a hosted API. Also: it deletes the thing 25% of the score is about |

## 5. Fixture facts that will bite — `fixtures.json`, re-derived

`fixtures.json` SHA-256 `252896BC45D49FCA69AD413BE40C6BFDE9D9B9F9DD8DB702B3FF74EAAA181121`,
46,687 bytes. **Re-derive, never trust a number quoted anywhere, including here.**

- 1 event `evt_01`, `submissions_close = 2026-03-01T18:00:00Z` — **a past date, so
  the portal is born closed. Never move it.**
- 8 tracks · 30 judges (21 single-track, 9 dual) · 40 teams · **41 projects** ·
  **126 reviews**. Criteria always `{functionality, innovation, quality}`, values
  2–5, key **order** is `functionality, quality, innovation`.
- Reviews per project **8@2, 26@3, 3@4, 4@5** (mass 126) → the mode, 26/41, is
  the evidence the target is 3.
- Reviews per judge 1–11. `jdg_07`: 3 reviews, 4/4/4 on `prj_09`, `prj_17`,
  **`prj_19`** — and `prj_19` is a **2-review project**, so a constant judge is
  half of its entire score. `jdg_01` and `jdg_23`: n=1.
- `trk_01` and `trk_08` are **zero-slack, not infeasible** — 18 needed, 18
  possible. **Provably impossible at per-judge capacity 5.** Three tracks missed
  the target, five over-covered, net +3 — a global bar hides three local failures.
- `prj_07` + `prj_41`: same team, track, title, `repo_url`, 13h28m apart, 5 vs 4
  reviews. Model as `supersedes`, keep both rows, aggregate by team latest-wins,
  carry a `counted` flag in the export.
- Graph is **one connected component, 71 nodes.** A joint IRT model is identified
  here (and still loses — F-17); the pairwise disconnected-graph caveat **cannot
  be demonstrated on this fixture.**
- **The panel has no detectable judge-severity effect:** between-judge variance
  0.0217 vs a noise floor of 0.0971, permutation **p = 0.234**, detection floor
  **τ ≈ 0.75**.

## 6. The four traps that cost the most points

1. **`run.py` reads `fixture_titles(fixture, n=3)`** → `projects[:3]`, and the
   check is `any(title in body for title in titles)`. So it needs **any one** of
   `Glass Signal`, `Small Meadow`, `Deep Compass` on the gallery route. Ship all
   three anyway — it is free — but the first gallery page **must be in fixture
   order**, because the slice is positional, not a search.
2. **Denial must be 403, not 302.** See D-02.
3. **`verified` is prefix-locked and only T1/T2 have checks.** A flawless build
   still prints `verified T1 T2`. Explain it in `README.md`; ship the unedited
   report; commit our own extended suite separately and clearly labelled.
4. **No seeded timing is tight.** Only the 5 test identities get real password
   hashes; the other ~116 get `UNUSABLE_PASSWORD`. Hashing all 121 costs ~48 s
   against a **10 s** timeout.

## 7. Build plan — 10 features, 69 hours

| ID | Hours | Feature | Gate |
|---|---|---|---|
| FEAT-01 | 4 | Skeleton, Docker, compose, healthcheck, `LICENSE`. `compose up` → serving page <60 s | — |
| FEAT-02 | 5 | Schema, isolation primitive, `isolation_proof` skeleton, scope receipt | — |
| FEAT-03 | 5 | Loader, seed identities, gallery, deadline guard, 4 Hypothesis invariants | — |
| **BREAK-1** | 1 | **☕ T1.** Full verify, slippage ledger, claim, tag `v-t1-verified` | **T1** |
| FEAT-04 | 7 | Rubric, assignment + min-cut, judge console, reviews | — |
| FEAT-05 | 8 | Isolation enforcement, dashboard, exports, event editor | — |
| **BREAK-2** | 1 | **☕ T2.** Tag `v-t2-verified` — the fallback state | **T2** |
| FEAT-06 | 9 | T3 public: voting, comments, results hiding, ballot order, **influence report** | — |
| **BREAK-3** | 1 | **☕ T3.** Claim, tag | **T3** |
| FEAT-07 | 13 | T4: bulk IO + round-trip test, signed records, `results_hash`, widget, OpenAPI | — |
| **BREAK-4** | 1 | **☕ T4.** How much of T4 is green? Claim. Tag | **T4** |
| FEAT-08 | 7 | Normalization engine + proof artefact. **Protected; do not displace** | — |
| FEAT-09 | 3 | Demo video | recorded |
| FEAT-10 | 4 | Docs, acceptance report, verification, commit. **Protected** | **FREEZE** |

**The claim is decided at a break, not at kickoff.** We build to T4; each break
decides what is actually green. If Break 4 arrives with two T4 items outstanding,
we claim T3 and name which two. A T4 claim with half-working endpoints scores
worse than an honest T3 — the brief says so three times.

**Break protocol (1 hour, fixed):** clean `down -v` → `up` network off ·
`run.py` · `isolation_proof` must exit 0 · full suite · **update the slippage
ledger** (`bible/08` §1c) · decide the claim and write it down · tag.

## 8. Verify — two gates, at different times

```bash
python tools/verify_spec.py   # the plan vs the organizers' files. 67 checks. Runs NOW.
just check                    # the application. Needs Docker. Runs at every break.
```

`verify_spec.py` is **stdlib-only** — no venv, no Docker, no network — so it
works before Phase A exists, and it **exits non-zero**, unlike `run.py`. It
re-derives every count in §5 from `fixtures.json` and every claim about `run.py`
from its source. **Run it after any edit to this plan, and before trusting any
number quoted anywhere.** It has already caught five wrong numbers that a
careful read missed — including `5@5` instead of `4@5` in this very file, and
"6 demands" where `run.py` runs 7 checks.

The build clock is checked too: 69h exactly, all four breaks on the cumulative
clock, freeze at H+65, and tier hours agreeing with the features.

The proof's published numbers are **asserted in CI** (held-out RMSE, recovery
RMSE, sensitivity curves), so a refactor that silently changes the method fails a
test instead of quietly weakening the document.

## 9. The three steal-it candidates, ranked

1. **"We measured whether there was anything to fix, and we told you."** The
   detectability analysis plus parameter recovery. ~2.5 h, near-zero risk, lands
   on 25% + the Normalization Proof + the $100 prize. **The organizers confirmed
   this is what the bonus rewards**: *"Showing it recovers a known effect is
   exactly the kind of rigour the bonus is looking for."*
2. **"Feasible" and "provably impossible" are different answers, and we hand you
   the min-cut.** ~1.5 h, and it *removes* a risk — the old claim was false.
3. **The scope receipt.** `for_actor()` returns a queryset carrying a
   human-readable reason and every list view renders it. ~1 h. Makes isolation
   verifiable by a reader, not just by our tests.

## 10. Open blockers

**None.** The two entries that used to be here are both closed, and the section
kept its heading — see **F-57**, which is the same defect in a second file.

- ~~**No git repository (F-14, P2) — the only blocker left.**~~ **Closed.** The
  repository exists, on `main` at `github.com/aalok101singh/judgejudy`, with the
  findings ledger and the correction log versioned — which is the Write Up Quest
  material F-14 existed to protect.
- ~~**The ambient `python` is 3.14.6 with no Django (F-38, P2).**~~ **Closed at
  FEAT-01**, and still true, which is why it is kept as a live warning rather
  than dropped: the venv is 3.13.13, the container is 3.13.15, and a bare
  `python` is still 3.14.6 with no Django. Use `.venv\Scripts\python.exe`
  explicitly — Django 5.2.17's `Requires-Python: >=3.10` has no upper bound, so
  the pin will not save you. `just doctor` names the interpreter it resolved.

**Docker is no longer a blocker (F-13 closed).** 29.6.2 on WSL2, Compose v5.3.1,
`just` 1.58.0, `python:3.13-slim` pre-pulled — all re-verified at BREAK-1. One
trap remains: it is installed **per-user**, so `docker` was on no PATH at all
until F-34 was fixed. A stale shell still will not see it.

## 11. Where the depth lives

| Need | Read |
|---|---|
| Why we win or lose, scoring → tactics, T4 risk | `bible/01` |
| 60 traceability IDs (23 tier + rules/deliverables/scoring/bonus); assumptions log | `bible/02` |
| `run.py` reverse-engineered, 7 traps, checklist | `bible/03` |
| Fixture census, invariants, the 8 edge cases | `bible/04` |
| **Schema, indexes, isolation primitive, escape hatch** | `bible/05` |
| **Assignment, normalization, proof, pairwise** | `bible/06` |
| **Threat model, what we did not stop** | `bible/07` |
| Hour map, break protocol, slippage ledger, **cut ledger** | `bible/08` |
| Installed versions, verified claims, the per-user Docker path | `bible/ENVIRONMENT.md` |
| Discord questions — all closed | `bible/DISCORD-QUESTIONS.md` |

## 12. Working rules

- **Every number in a shipped document is generated, not transcribed.** Six of
  twelve findings were hand-typed census errors, two found *after* we published
  a correction log about the first four.
- **Every claim about library behaviour is executed, not recalled.** F-11 was a
  documented DRF default that was backwards, and it would have made the deadline
  check pass without testing the deadline.
- **Never tune to a published target.** `k = 0` scores better than the value we
  ship. The whole curve is published beside the point.
- **A denied request is a refusal, not a filter.** Different code path, different
  status, and now a different explanation surfaced to the user.
- **State the honest number.** The brief rewards honest gap reporting and
  penalises inflation; `run.py` prints `claimed` against `verified` and the panel
  runs the identical program.
- **Refusal to cut is not a virtue.** The cut ledger in `bible/08` §13 is
  pre-populated with eleven rejected items, two of them with "yes, slightly" in
  the regret column, because a ledger where everything says "no" teaches nothing.

## 13. Current state

**FEAT-01, FEAT-02 and FEAT-03 are built, verified and committed.** 24 models
across 12 apps, one initial migration per app plus one correction,
`Review.objects.for_actor()` with its scope receipt, a hash-chained
`AuditEntry`, a lint rule that fails the build on an unscoped `Review` read, an
idempotent loader, the public gallery and the deadline guard. **BREAK-1 is
closed:** the T1 claim was decided in writing and `v-t1-verified` is tagged, with
the slippage ledger's first entry written. **Next action: FEAT-04** — rubric,
assignment + min-cut, judge console, reviews.

| | |
|---|---|
| Findings | **59** — **0 open blocking, 1 open** (F-59, P3), 1 fixed (F-51, a question deferred to FEAT-04/05), 1 unverified (F-27), 10 accepted by decision, 34 closed |
| Open questions | **0.** Two answered, thirteen self-answered, one DM dropped |
| Contributions upstream | 5 (`bible/README.md` U-1…U-5), incl. a corrected spec figure |
| Environment | **fully verified** — Docker 29.6.2 (WSL2), `just` 1.58.0, `python:3.13-slim` pre-pulled |
| Spec layer | audited against the given inputs 2026-09-27; five errors found and closed (F-28…F-32) |
| Gate at FEAT-03 | `just check` **green**, `verified T1` · `prove-offline` **8.0 s** · `mutation-test` **18/18** · spec 67/67 · **291 tests** · cold start **11.8 s** measured 2026-09-28 |

**The number that changed the shape of the project:** FEAT-03 was the first
feature to run our code against the organizers' *data* rather than data we
built, and it opened **three P1s in one feature** — 123 blank-password accounts
(F-49), a `UNIQUE` constraint their own fixture violates (F-50), and a
credential format that could never verify (F-55). All three are closed. The
rate is worth carrying into FEAT-04 as a prior: **anything that meets the
published data for the first time will find something we got wrong about it.**
