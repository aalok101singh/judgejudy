# Build Plan

> **The order of the work, with the gate at the end of each step.** This is the
> file a build session works from. Check items as they are genuinely done — not
> when the code exists, but when the acceptance line below it passes.
>
> Current in-flight scope: `context/current-feature.md`.
> Ledger: `context/findings.md`. Hour map and slippage: `bible/08`.

---

## Rules for this plan

- **A feature is done when its verification line passes**, not when the last
  line of code is written.
- **The gate is the claim.** Each break decides which tier we have actually
  earned, in plain words, with any gap named.
- **Slippage is recorded at the break, not during.** Mid-feature time tracking
  costs attention we do not have; the ledger is a break artefact (`bible/08` §1c).
- **Protected blocks are not displaced.** FEAT-08 and FEAT-10 are protected
  because they carry the bonuses and the honesty of the submission. If T4 slips,
  they slip first.
- **Cutting is a decision, not a drift.** Anything cut mid-build is written in
  the cut ledger the same day, with the reason and the regret.

---

## Phase A — Skeleton (FEAT-01, 4h)

- [x] **FEAT-01 Skeleton and container** — 4h
  - Dockerfile `python:3.13-slim`, non-root, `gunicorn` + `whitenoise`, no dev deps
  - `compose.yaml` with the instance volume, a healthcheck, and a network-off
    `up` that works
  - `run.py` runs the identical program the panel will run
  - `LICENSE` (MIT) and the README skeleton
  - **Verify:** `docker compose down -v && up`, wait for health, confirm a serving
    page in under 60 s with no network
  - **Unblocked:** F-13 closed — Docker 29.6.2/WSL2 verified, `just` 1.58.0 installed,
    `python:3.13-slim` pre-pulled. Open a new terminal so the PATH change is live

## Phase B — Schema and isolation primitive (FEAT-02, 5h)

- [x] **FEAT-02 Schema and the isolation primitive** — 5h
  - 26 models, 12 apps; SQLite WAL; **Postgres-portable** — no SQLite-only types
  - Indexes for the three hot paths: judge-on-track, judge-on-project, event gallery
  - `Review.objects.for_actor(actor)` → scoped queryset **+ scope receipt**
  - `isolation_proof` management command skeleton, exiting 0 on pass
  - The lint rule forbidding the unscoped `Review.objects.all()` form
  - **Verify:** `manage.py isolation_proof` exits 0 on the empty DB; the lint rule
    fires on a deliberately unscoped view and passes when scoped
  - **Depends on:** F-22 (Hypothesis model strategies need pytest-django, so the
    four invariants land in FEAT-03, not here)
  - **Note (F-44):** the model count was 20 here and 8 in `DATA-MODEL.md`, while
    `bible/05` names 24. All 24 ship; `tests/test_schema_contract.py` now reads
    this line and compares it to the app registry, so the number cannot be
    retyped.

## Phase C — Import, gallery, seed (FEAT-03, 5h)

- [x] **FEAT-03 Loader, identities, gallery, deadline guard** — 5h
  - [x] Idempotent loader from `fixtures.json` — run twice, same database
        (**measured: 979 created / 0 updated on the second run, 0 re-hashes**)
  - [x] **5 test identities get real password hashes; ~116 get
        `UNUSABLE_PASSWORD`.** Hashing all 121 costs ~48 s against a 10 s timeout (F-12)
        (**measured: 5 hashes, 1.90 s inside the seed**)
  - [x] Gallery, first page in fixture order, ≥24 per page — `run.py` greps
        `projects[0:3]` **positionally** (**24 per page, 41 projects, 2 pages**)
  - [x] Deadline guard: `assert_open_for_submission(event)` — a **service
        function**, not a `save()` override and not a view decorator
  - [x] The four isolation invariants as Hypothesis tests (P1–P4, `bible/05` §6b.2)
  - [x] `verify_census` — both `fixtures.json` invariants, and every generated table
        prints its own row count
  - **Verify:** fresh `up` → gallery shows the three greppable projects; deadline
    guard is visibly closed; `verify_census` clean; four invariants green
  - **Done 2026-09-28.** All three T1 checks PASS and `verified T1`; 291 tests;
    18/18 mutations; cold start 11.6 s. See
    `history/features/03-loader-gallery-deadline-guard.md`.
  - **Note (F-50):** `UNIQUE (event, name)` on `Team` was **dropped** — the
    organizers' fixture has 40 teams and 36 distinct names. Migration
    `teams/0002_remove_team_...`, and `(event, slug)` is kept.
  - **Note (F-55):** the demo credential is an HMAC'd bearer token
    `JJ1.<hmac>.<email>` signed with a **published** key, so `.dogfood.toml` keeps
    working across `down -v`. The trade is stated in the README and in the
    module's own docstring.

> ### ☕ BREAK-1 — H+14 — **☕ T1**
> Clean `down -v` → `up` network off · `run.py` · `isolation_proof` exits 0 ·
> full suite · **update the slippage ledger** · decide the T1 claim in writing ·
> tag `v-t1-verified`.
> **T1 is a hard gate: clear it or not be judged.**
> **DONE 2026-09-28.** All three T1 checks PASS, `just check` GATE GREEN on a
> clean volume, offline 8.0 s, 18/18 mutations, 291 tests, 67/67 spec. The claim
> was decided here and written to `.dogfood.toml` as `claimed = ["T1"]` with the
> reason beside it. **`v-t1-verified` tagged.** T2 deliberately unclaimed: all
> four T2 checks fail with real URLs. See `context/current-feature.md`.

## Phase D — Assignment and judging (FEAT-04, 7h)

- [x] **FEAT-04 Rubric, assignment, judge console, reviews** — 7h
  - Weighted rubric, `functionality` heaviest. `ε = 0.5` as the legible default
  - Assignment: one flow over all tracks, min-max capacity by search, load
    imbalance + seeded tiebreak, min-cut certificate
  - **Infeasibility diagnosed, never asserted** — the min-cut names the
    deficient projects, the bottleneck judges, the deficit, and three remedies
  - Judge console: assignments, read rubric, submit review, save draft
  - **Verify:** a feasible instance assigns; the capacity-5 instance reports
    infeasible with a named min-cut; the seeded tiebreak reproduces byte-for-byte
  - **Done 2026-09-29.** All three clauses pass on a clean volume; 340 tests;
    18/18 mutations plus 16 on the new modules; 68/68 spec. See
    `history/features/04-assignment-and-judge-console.md`.
  - **Note (F-60):** the textbook SSP solver returned feasible but **non-minimal**
    flows because it updated Johnson potentials incrementally. Potentials are now
    recomputed from Bellman-Ford every augmentation; 1,500/1,500 random instances
    agree with an independently written oracle.
  - **Note (F-61/F-62):** `bible/06` §2.3's "sink side of the cut" names **no
    judges** on this network; the bottleneck judges are the eligible judges **whose
    capacity is exhausted**. And §2.2's "77 edges" is **199** over 81 nodes.

## Phase E — Isolation enforced (FEAT-05, 8h)

- [x] **FEAT-05 Isolation enforcement, the T2 surface, the CSV export** — 8h
  - Every T2 access path through the accessor. Denials are 403, empty body, no
    `Location`
  - `GET /api/v1/judge/scores` — scoped scores, a scope receipt, and a peer
    parameter that is **refused rather than filtered**
  - `GET /api/v1/export.csv` — CSV export with the criteria **key order**
    preserved (F-04), read through `for_actor(actor)`
  - **Verify:** `run.py` passes T2-4 and T2-5; the T1/T2 `verified` ceiling is
    expected and explained in the README
  - **Done 2026-09-29.** **7 of 7 checks PASS**, `claimed T1, verified T1 T2`,
    which is the ceiling `run.py` can print. 374 tests, 44/44 mutations, 68/68
    spec, lint clean. See `history/features/05-t2-surface-and-export.md`.
  - **Note:** the two routes are **plain Django, not DRF**, and that is
    load-bearing. DRF populates `request.user` from its own authentication
    classes and would ignore the one our credential middleware assigns, so every
    header-only request would arrive anonymous and be refused — turning three
    checks that want a 403 green for the wrong reason.
  - **Note (F-51):** the judge-organizer overlap resolves to the **organizer**.
    The strict reading was the incoherent one, because the export already granted
    the same authority.
  - **Note (F-69):** `Review.source_key` is inherited from D-11 and never written
    by the loader, so the export's first column was 126 empty cells until a test
    that checks every *cell* caught it. The natural-key fallback is a workaround;
    populating the column belongs to FEAT-07.

> ### ☕ BREAK-2 — H+30 — **☕ T2**
> Same protocol. **Tag `v-t2-verified` — this is our fallback state, and the tag
> is the most important thing we produce all day.** T2 green is a genuinely
> defensible submission.
> **T2 is EARNED and NOT YET CLAIMED.** All four T2 checks pass on a clean
> volume, so the claim is available; it is made here, in writing, against what is
> green, and not before. `.dogfood.toml` still reads `claimed = ["T1"]` until
> then, which is why the report says `claimed T1, verified T1 T2`.

## Phase F — Public surface (FEAT-06, 9h)

- [ ] **FEAT-06 Voting, comments, results hiding, ballot order, influence report** — 9h
  - Voting with amplitude inside an identity budget, mandatory attributable
    abstention
  - Randomized ballot order — makes bias zero-*mean*, not zero. Do not claim more
  - **The influence report** (D-13): per judge, project and criterion. *This is
    the anti-abuse answer.* Per-judge capability to read 1–2 of 126
  - Results hidden until the deadline; comments in
  - **Verify:** a bias-attack harness shows the estimator is zero-mean under
    position bias; the influence report renders for a synthetic attack

> ### Progress — FEAT-06 in progress; **BOTH acceptance clauses are built**
>
> - **DONE — the influence report.** `ballots/influence.py`, `manage.py
>   influence_report`, `GET /api/v1/influence`. Vote-mass Gini + identical-ballot
>   clusters, **no thresholds anywhere**, the caveat printed in the output, and
>   the empty case saying "NOT a finding" rather than printing zeroes. **Observed
>   in the container:** a 12-voter brigade ranks first with `clustered 12` and
>   every organic project reads `clustered 0`. See
>   `history/features/06-influence-report.md`.
> - **DONE — the bias-attack harness.** `ballots/bias_attack.py`, `manage.py
>   bias_attack`. **Observed in the container:** a fixed order pinning a project
>   to slot 1 gives **+27.64** with a CI **excluding** zero, the no-bias control
>   is **exactly 0**, and a per-voter seeded permutation gives **−0.53** with a CI
>   **spanning** zero and **sd 9.87** — **zero-MEAN, not zero**, which is the
>   claim D-12 makes and the one that must not be overstated. `479 tests`,
>   `68/68` mutations. See `history/features/06-bias-attack-harness.md`.
> - **DONE — the three `?` columns of the isolation matrix** (`aggregate`,
>   `export`, `audit`), and the audit chain has a writer that real traffic fills.
> - **NOT STARTED** — voting, comments, randomised ballot order as a product
>   surface, public result hiding. **The feature is not done.**
> - **A metric was cut rather than shipped (F-76).** The `lift` detector is
>   structurally constant, scored the synthetic attack at exactly 1.0, and is
>   pinned shut by a test. **Do not re-add it**; the arithmetic is in the module
>   docstring.
> - **Three claims were narrowed by measurement, not by argument.** `bible/06`
>   §6.3's power table does not reproduce (F-78) and is now generated; the
>   quality ladder that made the harness a one-project instrument is fixed
>   (F-80); and the first bias model measured rank transfer rather than position
>   (F-79). **All three were found by the harness failing to separate its own
>   arms, not by reading the code.**

> ### ☕ BREAK-3 — H+40 — **☕ T3**
> Same protocol. Claim, tag `v-t3-verified`.

## Phase G — T4 (FEAT-07, 13h)

- [ ] **FEAT-07 Bulk IO, signed records, `results_hash`, widget, OpenAPI** — 13h
  - `export run` / `import run`, **byte-identical round-trip including natural
    keys** (`source_key` on every importable table — D-11)
  - Ed25519 signed records in an in-toto Statement v1 inside DSSE; keys on their
    own volume
  - `results_hash` — the audit chain head at publication, **replicated into every
    signed judge record** (D-09)
  - Embeddable results widget, pure static HTML + JSON
  - OpenAPI 3.1 via drf-spectacular
  - **Verify:** the round-trip test passes byte-for-byte; signature and tamper
    rejection pass; the widget renders offline

> ### ☕ BREAK-4 — H+54 — **☕ T4**
> Same protocol. **How much of T4 is green?** Claim that, tag `v-t4-verified`.
> If two items are outstanding, claim T3 and name them. A T4 claim with
> half-working endpoints scores worse than an honest T3.

## Phase H — The proof (FEAT-08, 7h) — **PROTECTED**

- [ ] **FEAT-08 Normalization engine and the proof artefact** — 7h
  - The estimator: robust median/MAD + shrinkage `k = 3`; empirical Bayes as the
    constant-free reported estimator
  - **Component 1 — predictive.** Held-out RMSE 0.6753 against a 0.7952 baseline
  - **Component 2 — detectability.** Report the null immediately: between-judge
    0.0217 vs noise floor 0.0971, permutation **p = 0.234**, floor **τ ≈ 0.75**.
    *This is a finding, not a failure*
  - **Component 3 — parameter recovery.** Synthetic; **recovers severity
    RMSE 0.27 within ~11%** against a 0.54 MFRM baseline
  - **Component 4 — sensitivity.** `k` and `ε` curves, published in full
  - `docs/REAL-FIXTURE-RESULTS.md` — the real-fixture half, with no synthetic
    content, per the organizer's condition
  - **Verify:** CI asserts the published numbers, so a refactor that changes the
    method fails a test
  - **The organizer named the criterion:** *"Showing it recovers a known effect
    is exactly the kind of rigour the bonus is looking for."* Build the recovery
    experiment, not a bigger σ reduction

## Phase I — Ship (FEAT-09, 3h + FEAT-10, 4h) — **FEAT-10 PROTECTED**

- [ ] **FEAT-09 Demo video** — 3h · ≤3 min, showing a *decision*, not a tour
- [ ] **FEAT-10 Docs, acceptance report, verification, commit** — 4h
  - `acceptance-report.txt` — **generated, never hand-edited**
  - README: one command, the architecture, the 15 decisions, what we did not
    build and why, the honest `verified` ceiling
  - Final `down -v` → `up` → `run.py` from a clean clone
  - Commit. Tag the submission
- [ ] **FREEZE at H+65** — 4 protected hours for verification, acceptance report,
  video and commit. No features after this point.

---

## Progress

| | |
|---|---|
| **Completed** | **5 of 10 features** — FEAT-01 … FEAT-05 |
| **Hours planned** | 69 (68 build + 1 held) |
| **Slippage to date** | see `bible/08` §1c — first entry written at BREAK-1: A ≈4h, B ≈5h, C ~6h (**+1**) |
| **Acceptance now** | `run.py` prints **`claimed T1, verified T1 T2`**, with **all 7 checks PASS** |
| **Tag** | **`v-t1-verified`** (BREAK-1, 2026-09-28) |
| **Next** | **FEAT-06** voting, comments, ballot order, influence report (9h) |
| **Then** | BREAK-3 ☕ T3 — and BREAK-2 ☕ T2 first, which is now **earned and unclaimed** |

> **This table was stale until FEAT-05 opened (F-66).** It read *"3 of 10
> features"*, Phase D's checkbox was unticked, and **"Next: FEAT-04"** — on a tree
> where FEAT-04 had been committed and archived. This is **F-57's exact class**,
> which F-57 itself predicted: *"a status heading is written once and never
> revisited when the thing under it changes."* F-57 was found and fixed in
> `findings.md` and `project-overview.md`; the **third** file carrying the same
> defect was missed, and `verify_spec.py`'s 68 checks pass over it because a
> machine cannot tell a stale feature count from a fresh one.
