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

- [ ] **FEAT-02 Schema and the isolation primitive** — 5h
  - 20 models, 12 apps; SQLite WAL; **Postgres-portable** — no SQLite-only types
  - Indexes for the three hot paths: judge-on-track, judge-on-project, event gallery
  - `Review.objects.for_actor(actor)` → scoped queryset **+ scope receipt**
  - `isolation_proof` management command skeleton, exiting 0 on pass
  - The lint rule forbidding the unscoped `Review.objects.all()` form
  - **Verify:** `manage.py isolation_proof` exits 0 on the empty DB; the lint rule
    fires on a deliberately unscoped view and passes when scoped
  - **Depends on:** F-22 (Hypothesis model strategies need pytest-django, so the
    four invariants land in FEAT-03, not here)

## Phase C — Import, gallery, seed (FEAT-03, 5h)

- [ ] **FEAT-03 Loader, identities, gallery, deadline guard** — 5h
  - Idempotent loader from `fixtures.json` — run twice, same database
  - **5 test identities get real password hashes; ~116 get
    `UNUSABLE_PASSWORD`.** Hashing all 121 costs ~48 s against a 10 s timeout (F-12)
  - Gallery, first page in fixture order, ≥24 per page — `run.py` greps
    `projects[0:3]`
  - Deadline guard: `submissions_close` is **past**, so every mutating view is
    closed. Do not move the date.
  - The four isolation invariants as Hypothesis tests
  - `verify_census` — both `fixtures.json` invariants, and every generated table
    prints its own row count
  - **Verify:** fresh `up` → gallery shows the three greppable projects; deadline
    guard is visibly closed; `verify_census` clean; four invariants green

> ### ☕ BREAK-1 — H+14 — **☕ T1**
> Clean `down -v` → `up` network off · `run.py` · `isolation_proof` exits 0 ·
> full suite · **update the slippage ledger** · decide the T1 claim in writing ·
> tag `v-t1-verified`.
> **T1 is a hard gate: clear it or not be judged.**

## Phase D — Assignment and judging (FEAT-04, 7h)

- [ ] **FEAT-04 Rubric, assignment, judge console, reviews** — 7h
  - Weighted rubric, `functionality` heaviest. `ε = 0.5` as the legible default
  - Assignment: one flow over all tracks, min-max capacity by search, load
    imbalance + seeded tiebreak, min-cut certificate
  - **Infeasibility diagnosed, never asserted** — the min-cut names the
    deficient projects, the bottleneck judges, the deficit, and three remedies
  - Judge console: assignments, read rubric, submit review, save draft
  - **Verify:** a feasible instance assigns; the capacity-5 instance reports
    infeasible with a named min-cut; the seeded tiebreak reproduces byte-for-byte

## Phase E — Isolation enforced (FEAT-05, 8h)

- [ ] **FEAT-05 Isolation enforcement, dashboard, exports, event editor** — 8h
  - Every T2 access path through the accessor. Denials are 403, empty body, no
    `Location`
  - Judge dashboard, organizer dashboard, admin event editor
  - CSV export with the criteria **key order** preserved — the header is
    `functionality, quality, innovation` (F-04)
  - **Verify:** `run.py` passes T2-4 and T2-5; the T1/T2 `verified` ceiling is
    expected and explained in the README

> ### ☕ BREAK-2 — H+30 — **☕ T2**
> Same protocol. **Tag `v-t2-verified` — this is our fallback state, and the tag
> is the most important thing we produce all day.** T2 green is a genuinely
> defensible submission.

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
| **Completed** | 0 of 10 features |
| **Hours planned** | 69 (68 build + 1 held) |
| **Slippage to date** | see `bible/08` §1c — first entry at BREAK-1 |
| **Next** | **FEAT-01** — unblocked, environment verified |
