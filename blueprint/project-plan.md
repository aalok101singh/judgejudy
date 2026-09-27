# Project Plan — Judge Judy

> **Durable product definition.** This is *what we are building* and *why the
> design is shaped this way*. It changes rarely. The *order* of the work lives in
> `build-plan.md`; the current scope lives in `context/current-feature.md`.
>
> New agent session: load `context/project-overview.md` first (under 20KB, on
> demand). Read this file when you need the requirement it is attached to.

---

## 1. Product definition

A self-hostable hackathon submission **and judging platform**. The submission
side is the product we are judged on; the judging side is what makes it credible.
Built to be forked by a real hackathon and run for a decade without the author.

**Judged on:** tier completion, judging integrity, adoptability, code quality.
Not on feature count, not on architecture novelty.

**Two products, one schema:**

| | |
|---|---|
| **The judging side** | Organizers create tracks, import submissions, assign judges, and watch a signed, hash-chained audit trail. The isolation and normalization arguments are the substance. |
| **The submission side** | Teams browse, submit, and track. Dashboard, public gallery, comments, voting, results. Offline, no accounts, no moderation. |

## 2. Constraints that bound every decision

| # | Constraint | Consequence |
|---|---|---|
| C-1 | 69 hours, solo, one person | Any idea over ~6 hours is rejected on sight, out loud |
| C-2 | One command, network off, laptop | No cloud account, hosted DB, auth provider, external API, or API key. Binary disqualification |
| C-3 | Django 5 + DRF + SQLite WAL, Postgres-portable schema, one container | 17 runtime packages, deliberately no numpy/scipy/networkx/celery/redis |
| C-4 | New code only, in the window | `bible/` and `blueprint/` are planning documents, not application code. Dependencies and environment setup are permitted by the spec |
| C-5 | `run.py` machine-verifies **7 checks — 3 T1, 4 T2, none in T3/T4** | It is a gate and a credibility signal, not a score. Clear T1 or not judged |
| C-6 | 3-day-window data model (`submissions_close`) | Portal is born closed. A live portal needs real continuous judging; a closed one with an editorial archive and a proven normalizer does not |
| C-7 | A panel with 36 seniors, 3 reviews each, σ = 0.94 | Marginal improvements do not separate us. Be decisively better on one axis |

## 3. Success criteria

Ordered by how much score they carry.

1. **T1 green, absolutely.** Hard gate. Correctness beats breadth at 40%.
2. **Isolation provable and documented.** 25% of the score is judging integrity,
   and the spec says in plain words that hiding scores in a template is not
   refusing. This is the highest-leverage *design* requirement we have.
3. **One command, seeded, documented, portable.** 20% of the score, and the
   cheapest 20% available.
4. **Normalization that survives contact with a critical reader.** 25% plus the
   $100 Normalization Proof bonus. The organizer confirmed what earns it.
5. **T4 green, honestly scoped.** The remaining slice of 40%.
6. **One decision a judge can point at.** 15%, and the cheapest 15%.

### Explicit anti-goals

- More features than T1 and T2 need.
- A cleverer normalization method than we can defend.
- A normalization that improves a published number. It would be overfitting and
  `bible/06` says so.
- Webhooks, Borda voting, IRT/MFRM, Merkle logs, Casbin/OPA, RLS, TrueSkill.
  All cut, all with reasons, all in the cut ledger.

## 4. Architecture in one page

```
run.py ──▶ single container: gunicorn + whitenoise + Django 5 + DRF
           │
           ├── /admin          Django admin, the judge console
           ├── /api/v1         DRF, drf-spectacular OpenAPI
           ├── /gallery        FTS5 search, public after deadline
           └── (static)        whitenoise, no CDN

data/
  ├── instance/db.sqlite3     WAL
  └── media/                  project media, local volume

reviewer/  (the 12-model base, 20 tables)
  accounts → events → tracks → projects → reviews → ballots → comments
  audit.AuditLog   hash-chained, signed publication points
  crypto.SignedRecord  Ed25519 in an in-trio Statement v1 in DSSE
  io.RunSnapshot   import/export, byte-identical round-trip
```

**The one architectural claim worth making:** a scoped-accessor layer means
there is exactly one place where the rules live. It is the portable equivalent
of Postgres RLS, it works on SQLite, and it is a hundred lines instead of a
migration and a pool-safety argument.

## 5. The requirements

`bible/02` decomposes the brief into **60 traceability IDs** across nine
categories. Only **23 are tier demands**; the rest are the 9 binary rules, 11
deliverables, 4 scoring criteria, 4 bonus challenges and 9 zero-scoring
out-of-scope items. The IDs are ours, not the organizers' — `spec.md` itself is
a short brief with no numbering.

| Tier | `REQ-` IDs | Hours | Contents |
|---|---|---|---|
| **T1 Skeleton** | 7 | 14 | Docker, health, one command, README, licence, models |
| **T2 Judging** | 6 | 15 | Assignment, isolation, judge console, review UI, census, slop |
| **T3 Public** | 5 | 9 | Gallery, results, voting, comments, dashboard, slop |
| **T4 Advanced** | 5 | 13 | Bulk IO, signed records, `results_hash`, widget, OpenAPI, **normalization proof** |

**Hours are the build plan's, not a restatement of the brief** — the brief
assigns no hours. T1–T4 is 51h; FEAT-08 (proof, 7h), FEAT-09/10 (ship, 7h) and
the four breaks (4h) bring the window to exactly 69h. The tier → feature mapping
is in `build-plan.md` §7, which is the source of truth for the clock.

T4's differentiators are the last two. T4 is the build target; the claim is
decided at Break 4 against what is actually green.

## 6. Design decisions

Full reasoning in the file named. Summarised in `context/project-overview.md` §4
as D-01…D-15. The five that shape the most code:

**D-01/D-02/D-03 — isolation is a language feature, and a refusal is a 403.**
`Review.objects.for_actor(actor)` returns a queryset already carrying its scope
*and* a human-readable reason string. A permission decides and raises; the
queryset constrains and cannot. The two fail in opposite directions. And denial
is a literal 403 with an empty body, never a 302, because `run.py` follows
redirects and a redirect returns 200. The scope receipt is the cheap part of
this: it makes the isolation visible to a reader instead of only to our tests.

**D-04/D-05 — normalization starts by asking whether there is anything to fix.**
Then a robust median/MAD plus shrinkage, with empirical Bayes as the
constant-free estimator whose numbers we report. `k = 3` and `ε = 0.5` are a
priori and legible, chosen without seeing outcomes; `k = 0` scores better and we
do not use it. The proof's ordering matters: the **predictive result leads**,
because that is what a normalizer is *for*; the null effect is reported
immediately after because it qualifies the claim; the recovery experiment
validates the estimator itself; the full sensitivity curves ship beside any
single number.

**D-06/D-07 — assignment is one flow over all tracks, and infeasibility is
diagnosed.** Nine of thirty judges are dual-track, so per-track flows are wrong.
A min-max capacity by search keeps the two cost terms in the objective, where
they belong and where they are measurable. Ties are broken by seeded shuffle so
results are reproducible. And if the instance is infeasible, the min-cut *names*
the deficient projects, the bottleneck judges, the deficit, and three remedies
with arithmetic — because "feasible" and "provably impossible" are different
answers that deserve different code paths. This also removed a false claim from
our own planning: `trk_01` and `trk_08` are **zero-slack, not infeasible**.

**D-08/D-09/D-10/D-11 — integrity primitives, each earning its place.** The
audit log is hash-chained with `omitted_since_prev` inside the chain, because
rate-limited sampling plus a chain is incoherent — a gap is indistinguishable
from an edit. No Merkle log: CT's value is *witnessing* and we have none, so we
publish one chain head and replicate it into every signed judge record, which is
strictly stronger for a third of the code. Signing uses Ed25519 in an in-toto
Statement v1 inside a DSSE envelope, so no third party reimplements our
canonicalisation. Every importable table carries `source_key`, because "modulo
generated IDs" is not a testable property — a dropped column passes it.

**D-12/D-13 — the abuse answer is a report, not a mechanism.** Vote weighting is
amplitude inside an identity budget with mandatory, attributable abstention. The
mechanism-design literature is explicit that this does not resist a
well-capitalized Sybil operation, and claiming otherwise is falsifiable in one
search. So we do not claim it. We ship an **influence report** — per judge, per
project, per criterion — that makes the exploit visible to whoever runs the
event. A Borda ballot is cut: it *changes* the outcome, while the report
*explains* it.

## 7. Risks and what we do about them

| Risk | Likelihood | Response |
|---|---|---|
| **`docker` unfindable in a fresh shell** | **live** | Installed per-user (F-34). User PATH is fixed and the justfile resolves it by absolute path. Never reinstall — it was never missing |
| T4 overrun | medium | 13 h of T4 across one feature; a clean T3 is a legitimate outcome and we name the gap |
| Isolation bug in one of ~20 access paths | medium | Layered by construction, a lint rule for the unscoped form, and `isolation_proof` as an exit-0 command |
| The normalization result is read as overfitting | medium | The null is reported first, the curves are published, constants are a priori, and `k = 0` is mentioned as the thing we declined |
| The 10 s seed timeout fails on a slow laptop | medium | 5 identities hashed, 116 `UNUSABLE_PASSWORD` (F-12) |
| Admin too large for one person to maintain | low | Tiers ordered so each is a shippable stopping point |
| A rebuilt `fixtures.json` is a different fixture | low | SHA-256 pinned in the overview; `verify_census` fails loudly on a mismatch |

## 8. Decisions taken before the window

Recorded here so a new session does not re-litigate them.

- Build to T4, claim against what is green at Break 4.
- Recover the largest fixed cost: ~1.5 h of block setup × 4 breaks. Every console
  jump is a recovery, so we stop at the four breaks and not at arbitrary points.
- The demo video is 3 minutes, showing a decision rather than a feature tour.
- No speculative abstraction. If a second implementation never arrives, the
  abstraction is a bug.
- Seed data is **deterministic** — fixed seed, stable ordering — so a judge
  rebuilding sees the same event. This matters for adoptability scoring.
- Do not tune to a published target. A calibration number is context, not an
  objective.
- Say the honest number. The brief rewards honest gap reporting; `run.py` prints
  `claimed` against `verified` and the panel runs the identical program.
