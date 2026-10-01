# Project Overview — Judge Judy

> **Loadable context for any agent session. Keep under 20,000 bytes — it is
> asserted by `verify_spec.py`, because the cap is the only thing keeping this
> file a *load* rather than a project.**
> Depth lives in `bible/` (330KB) — read the named section, never the folder.

**What this is:** a self-hostable hackathon submission and judging platform for
DOGFOOD 2026, built to be forked and run for a decade. Not a demo.
**Window:** 69 hours, one person, solo. Freeze H+69.
**Status:** FEAT-01 to FEAT-06 built and verified; **`run.py` prints
`claimed T1, verified T1 T2` with all 7 checks PASS.** T2 is **earned and not yet
claimed** — BREAK-2 is done and the exact `.dogfood.toml` diff is prepared, but
the claim is the human's to apply. **FEAT-06 is complete: all five REQ-T3
requirements ship**, so the T3 claim is *available* for BREAK-3, which has not
been run.

---

## 1. The hard constraints — never re-litigate

1. **69 hours, solo.** This binds everything. Reject any idea over ~6 hours, and
   say so out loud.
2. **New code only, in the window.** `bible/` and `blueprint/` are planning
   documents, not application code. Dependencies and environment setup are
   explicitly permitted.
3. **Offline, one command, laptop, network off.** No cloud account, no hosted
   database, no auth provider, no external API, no API keys. A binary
   disqualification if broken.
4. **Django 5 + SQLite (WAL), Postgres-portable schema, one container, gunicorn +
   whitenoise.** DRF is installed but the `/api/v1` routes are plain Django — §3.
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
`["T1","T2","T3","T4"]`, breaking at the first tier that has no passing check —
so a flawless build still prints `verified T1 T2`. **That is arithmetic, not a
bug, and FEAT-05 has now hit the ceiling with 7 of 7 passing** (`bible/03` §2,
F-34). `README.md` explains it in full; the report is shipped unedited.

Panel: 36 senior engineers, 3 reviews per project, σ = 0.94 on their own scale.
Marginal improvements do not separate us from the field. Be **decisively** better
on at least one axis.

## 3. Stack — installed and verified, not recalled

| | Version | Note |
|---|---|---|
| Python | **3.13.13** | venv. Container `python:3.13-slim` is 3.13.15 — same line, so local == container. **A bare `python` is 3.14.6 with no Django (F-38)** |
| Django | 5.2.17 | **LTS, not 6.1** — the organizers fork this for a decade |
| djangorestframework | 3.18.1 | **installed but NOT used for `/api/v1` — see the FEAT-05 archive.** DRF would ignore our credential middleware's `request.user` and turn three T2 checks green for the wrong reason |
| drf-spectacular | 0.30.0 | API First bonus, FEAT-07 |
| whitenoise · gunicorn · cryptography | 6.12.0 · 26.2.0 · 50.0.1 | gunicorn marked `sys_platform != "win32"` |
| pytest · pytest-django · hypothesis · ruff | 9.1.1 · 4.14.0 · 6.168.2 · 0.16.9 | dev only, not in the image |

**28 packages, 17 runtime. Deliberately absent, with reasons in
`requirements.txt`:** numpy, scipy, networkx (measured unnecessary — 126 rows, a
40-node graph), celery/redis (a second service is a disqualifier), argon2-cffi,
any cloud SDK.

Verified working: FTS5 gallery search, WAL, JSON1, `CheckConstraint` /
`JSONField` / composite `UniqueConstraint` portable across both engines, and
Ed25519 sign/verify **with tamper rejection**.

## 4. Decisions that cannot be re-litigated

| # | Decision | One-line reason |
|---|---|---|
| D-01 | **Isolation in the data-access layer.** `Review.objects.for_actor(actor)` returns an already-scoped queryset. No code path from a view to an unscoped `Review`. A lint rule forbids the unscoped form | The spec names this: *"hiding another judge's scores in your template is not refusing"* |
| D-02 | **Denial is a literal 403, never a 302.** Empty body, no `Location` header. **One function** — `reviewer/isolation/refusal.py` — shared by the console and the API | `run.py` follows redirects; a redirect returns 200 and fails T2-5. **Highest-value line in the project** |
| D-03 | **Two enforcement layers, not three.** Permission *decides* and raises; the queryset *constrains* and cannot. They fail in opposite directions | A third layer is derived, therefore a second source of truth. The lint rule is the exception: it enforces a *syntactic* property, which is mechanically checkable (`bible/07` §2b) |
| D-04 | **Normalization: robust median/MAD + shrinkage `k=3`, `ε=0.5` as the legible default; empirical-Bayes (`τ²` by moments) as the constant-free estimator whose numbers we report** | EB measured 4.9% better held-out RMSE and has **no tunable constant at all**, which removes our largest exposure |
| D-05 | **Detectability analysis first.** Is there an effect to remove? | A normalization claim that doesn't test for the effect it removes is a subtraction, not a proof |
| D-06 | **Assignment: one flow over all tracks, min-max capacity by search, load-imbalance + seeded tiebreak only, min-cut certificate** | 9 of 30 judges are dual-track, so per-track flows are wrong. Two cost terms cut on measurement, one moved from cost to eligibility |
| D-07 | **Infeasibility is diagnosed, never asserted.** The min-cut names the deficient projects, the bottleneck judges, the deficit, and three remedies with arithmetic | "Feasible" and "provably impossible" are different answers and get different code paths |
| D-08 | **Audit is hash-chained**, with `omitted_since_prev` inside the chain | Rate-limited sampling plus a chain is incoherent — a gap is indistinguishable from an edit |
| D-09 | **No Merkle transparency log.** Publish one chain head; replicate it into every signed judge record | CT's value is *witnessing* and we have no witness. The chain head in N signed records is strictly stronger for a third of the code |
| D-10 | **Signed records: Ed25519 in an in-toto Statement v1 inside a DSSE envelope.** Keys on their own volume | DSSE signs bytes, so no third party reimplements our canonicalisation |
| D-11 | **`source_key` on every importable table.** Round-trip is byte-identical *including natural keys* | "Modulo generated IDs" is not a testable property — a dropped column passes |
| D-12 | **Voting claims cost amplification inside an identity budget, not Sybil resistance.** Randomized order makes bias zero-*mean*, not zero — **and the harness now measures the spread as well as the mean, because the spread is what makes the claim honest** | The mechanism-design literature is explicit; claiming otherwise is falsifiable in one search |
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
  2–5, key **order** is `functionality, quality, innovation` — the export header
  (F-04).
- Reviews per project **8@2, 26@3, 3@4, 4@5** (mass 126) → the mode, 26/41, is
  the evidence the target is 3. Reviews per judge 1–11. `jdg_07`: 3 reviews,
  4/4/4 on `prj_09`, `prj_17`, **`prj_19`** — and `prj_19` is a **2-review
  project**, so a constant judge is half of its entire score. `jdg_01` and
  `jdg_23`: n=1.
- `trk_01` and `trk_08` are **zero-slack, not infeasible** — 18 needed, 18
  possible, **provably impossible at per-judge capacity 5** (measured, named
  min-cut, at FEAT-04). Three tracks missed the target, five over-covered, net
  +3 — a global bar hides three local failures.
- `prj_07` + `prj_41`: same team, track, title, `repo_url`, 13h28m apart, 5 vs 4
  reviews. Model as `supersedes`, keep both rows, aggregate by team latest-wins,
  carry a `counted` flag in the export.
- Graph is **one connected component, 71 nodes**, so a joint IRT model is
  identified here (and still loses — F-17) and the pairwise disconnected-graph
  caveat **cannot be demonstrated here**.
- **The panel has no detectable judge-severity effect:** between-judge variance
  0.0217 vs a noise floor of 0.0971, permutation **p = 0.234**, detection floor
  **τ ≈ 0.75**. *The inconvenient result the normalization section leads with, and
  a finding rather than a failure.*

## 6. The four traps that cost the most points

1. **`run.py` reads `fixture_titles(fixture, n=3)`** → `projects[:3]`, and the
   check is `any(title in body for title in titles)`. So it needs **any one** of
   `Glass Signal`, `Small Meadow`, `Deep Compass` on the gallery route. Ship all
   three anyway — it is free — but the first gallery page **must be in fixture
   order**, because the slice is positional, not a search.
2. **Denial must be 403, not 302.** See D-02. **FEAT-05 made this a single
   function** (`reviewer/isolation/refusal.py`) shared by the console and the
   API, so it cannot drift per surface.
3. **`verified` is prefix-locked and only T1/T2 have checks.** A flawless build
   still prints `verified T1 T2` — see §2. **FEAT-05 hit that ceiling with 7 of 7
   passing.** `README.md` explains it; the report ships unedited.
4. **No seeded timing is tight.** Only the 5 test identities get real password
   hashes; the other ~116 get `UNUSABLE_PASSWORD`. Hashing all 121 costs ~48 s
   against a **10 s** timeout.

## 7. Build plan — 10 features, 69 hours

**`blueprint/build-plan.md` is the clock's source of truth and carries the
per-feature acceptance lines.** The hours below are the ones `verify_spec.py`
parses out of this table and cross-checks, which is why they are not prose.

| ID | h | Feature | Gate |
|---|---|---|---|
| FEAT-01 | 4 | Skeleton, Docker, compose, healthcheck | — |
| FEAT-02 | 5 | Schema, isolation primitive, `isolation_proof`, scope receipt | — |
| FEAT-03 | 5 | Loader, seed identities, gallery, deadline guard | — |
| **BREAK-1** | 1 | **☕ T1.** Full verify, claim, tag `v-t1-verified` | **T1** |
| FEAT-04 | 7 | Rubric, assignment + min-cut, judge console | — |
| FEAT-05 | 8 | Scoped scores, refusals, the CSV export — **done** | — |
| **BREAK-2** | 1 | **☕ T2.** Tag `v-t2-verified` — *the fallback state* | **T2** |
| FEAT-06 | 9 | Voting, comments, results hiding, ballot order, **influence report** | — |
| **BREAK-3** | 1 | **☕ T3.** Claim, tag | **T3** |
| FEAT-07 | 13 | T4: bulk IO + round trip, signed records, `results_hash`, widget, OpenAPI | — || **BREAK-4** | 1 | **☕ T4.** How much is green? Claim that. | **T4** |
| FEAT-08 | 7 | Normalization engine + proof. **Protected** | — |
| FEAT-09 | 3 | Demo video | recorded |
| FEAT-10 | 4 | Docs, acceptance report, commit. **Protected** | **FREEZE at H+65** |

**The claim is decided at a break, not at kickoff.** We build to T4; each break
decides what is actually green. If Break 4 arrives with two T4 items outstanding,
we claim T3 and name which two. A T4 claim with half-working endpoints scores
worse than an honest T3 — the brief says so three times. **T2 is earned as of
FEAT-05 and still unclaimed**, which is the rule working rather than aspirational.

**Break protocol (1 hour, fixed):** clean `down -v` → `up` network off ·
`run.py` · `isolation_proof` exits 0 · full suite · **update the slippage ledger**
(`bible/08` §1c) · decide the claim and write it down · tag.

## 8. Verify — two gates, at different times

```bash
python tools/verify_spec.py   # the plan vs the organizers' files. Prints its own count. Runs NOW.
just check                    # the application. Needs Docker. Runs at every break.
```

`verify_spec.py` is **stdlib-only** — no venv, no Docker, no network — so it
works before Phase A exists, and it **exits non-zero**, unlike `run.py`. It
re-derives every count in §5 from `fixtures.json` and every claim about `run.py`
from its source. **Run it after any edit to this plan, and before trusting any
number quoted anywhere.** It has caught more than a dozen wrong numbers that a
careful read missed, including `5@5` instead of `4@5` in this very file, "6
demands" where `run.py` runs 7 checks, and a stale feature count in
`build-plan.md` (F-66).

The proof's published numbers are **asserted in CI** (held-out RMSE, recovery
RMSE, sensitivity curves), so a refactor that silently changes the method fails a
test instead of quietly weakening the document.

## 9. The three steal-it candidates, ranked

1. **"We measured whether there was anything to fix, and we told you."** The
   detectability analysis plus parameter recovery — FEAT-08, protected, not
   displaced. ~2.5 h, near-zero risk, lands on 25% + the $100 prize. **The
   organizers confirmed this is what the bonus rewards**: *"Showing it recovers a
   known effect is exactly the kind of rigour the bonus is looking for."*
2. **"Feasible" and "provably impossible" are different answers, and we hand you
   the min-cut."** **Shipped at FEAT-04**, ~1.5 h, and it *removed* a risk — the
   old claim was false.
3. **The scope receipt.** `for_actor()` returns a queryset carrying a
   human-readable reason; every list view renders it and FEAT-05 exposed it over
   HTTP. **Shipped at FEAT-02.** Makes isolation verifiable by a reader.

## 10. Open blockers

**None.** The section kept its heading because **F-57** found the same
"empty section, delete the heading" defect in a second file and **F-66** in a
third.

- **No git repository (F-14)** — **closed.** The repository exists, on `main` at
  `github.com/aalok101singh/judgejudy`, with the findings ledger and the
  correction log versioned — the Write Up Quest material F-14 existed to protect.
- **The ambient `python` is 3.14.6 with no Django (F-38)** — **closed at FEAT-01**,
  and **still true**, so it stays a live warning: use `.venv\Scripts\python.exe`
  explicitly. Django 5.2.17's `Requires-Python: >=3.10` has no upper bound, so the
  pin will not save you. `just doctor` names the interpreter it resolved.

**Docker is no longer a blocker (F-13 closed).** 29.6.2 on WSL2, Compose v5.3.1,
`just` 1.58.0, `python:3.13-slim` pre-pulled. One trap remains: it is installed
**per-user**, so `docker` was on no PATH at all until F-34 was fixed, and a stale
shell still will not see it.

## 11. Where the depth lives

**Do not read `bible/` (330KB).** This file names the section for every kind of
question; open that one section.

| Need | Read |
|---|---|
| Scoring function, tactics, T4 risk | `bible/01` |
| 60 traceability IDs; assumptions log | `bible/02` |
| `run.py` reverse-engineered, 7 traps | `bible/03` |
| Fixture census, invariants, edge cases | `bible/04` |
| **Schema, indexes, the isolation primitive** | `bible/05` |
| **Assignment, normalization, pairwise, ballot** | `bible/06` |
| Threat model, what we did not stop | `bible/07` |
| Hour map, break protocol, cut ledger | `bible/08` |
| Installed versions, the per-user Docker path | `bible/ENVIRONMENT.md` |
| Organizer questions — all closed | `bible/DISCORD-QUESTIONS.md` |

## 12. Working rules

- **Every number in a shipped document is generated, not transcribed** — and now
  also **re-derivable by running the command that produced it**. Six of twelve
  early findings were hand-typed census errors, two found *after* a correction log
  was published; F-67 is the same class attached to a *command*, and F-78 is the
  same class attached to a *table*.
- **Every claim about library behaviour is executed, not recalled.** F-11 was a
  documented DRF default that was backwards, and FEAT-05's biggest near-miss was
  the same: a DRF viewset would have made **three T2 checks green for the wrong
  reason** rather than red.
- **Never tune to a published target.** `k = 0` scores better than the value we
  ship. The whole curve is published beside the point.
- **A denied request is a refusal, not a filter.** Different code path, different
  status, a different explanation surfaced to the user.
- **State the honest number.** The brief rewards honest gap reporting and
  penalises inflation; `run.py` prints `claimed` against `verified`.

## 13. Current state

**FEAT-01 to FEAT-06 built and verified; BREAK-2 is done, T2 is earned and
unclaimed pending the human's diff, and FEAT-06 is COMPLETE — all five REQ-T3
requirements ship.** The T3 claim is therefore *available* and BREAK-3 has not
been run. The narrative, the per-feature
verification and the counts live in `AGENTS.md` §Current state,
`context/current-feature.md` and `history/features/`.

| | |
|---|---|
| Findings | **117** - **0 open blocking**, 0 open, 43 fixed (awaiting review), 1 unverified (F-27), **11 accepted by decision (F-91)**, 62 closed |
| Environment | **fully verified** — Docker 29.6.2 (WSL2), `just` 1.58.0, `python:3.13-slim` pre-pulled |
| Gate (FEAT-06) | **green** — **7 of 7 checks PASS**, `claimed T1, verified T1 T2` · `mutation-test` **114/114** · spec layer green · **700 tests** · lint clean |
| Next | **BREAK-3.** All five REQ-T3 requirements ship, so the T3 claim is *available* for the first time. Per `bible/08` §1b the decision is the human's |

**Two things that changed the shape of the project.**

**FEAT-03 was the only feature that met genuinely new input** — the organizers'
data rather than ours — and it opened **three P1s at once** (F-49, F-50, F-55).
Every feature since has found its serious defect in *our own reasoning* or *our
own documents*. **The rate tracks how much new input meets the code**, so expect
fewer findings, not fewer bugs.

**And the same defect has now appeared FIVE times in five media: a feature
returning structurally valid output containing nothing** — a min-cut certificate
naming no judges (F-61), 126 empty export cells (F-69), an audit chain with
`count() == 0` (F-71), and at FEAT-06 a **structurally constant metric that read
as a detector** (F-76) and a **quality ladder that made a harness measure exactly
one project** (F-80). **The rule: assert values, not shapes — and assert that a
control does not fire.** A fixture that cannot separate its subject from its
control produces green output that means nothing.
