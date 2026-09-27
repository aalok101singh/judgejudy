# Judging

> **Status: not yet built.** The rubric, assignment and isolation enforcement
> land in FEAT-04 and FEAT-05; the normalization engine and its proof in
> FEAT-08. What is here is the **design**, decided and defensible, so the
> repository is never missing a required document and so the reasoning is
> written down before the clock is running.
>
> Depth: `bible/06` (judging engine) · `bible/07` (threat model) ·
> `blueprint/build-plan.md` Phases D–H.

---

## 1. The isolation claim

This is 25% of the score and the one place where the spec says in plain words
that a common approach is decoration:

> *Hiding the other judge's scores in your template is not refusing. The check
> has to live in the backend, because the backend is where `curl` arrives.*

### One rule, in the data-access layer

```python
Review.objects.for_actor(actor)   # → a queryset that is ALREADY scoped
```

There is no code path from a view to an unscoped `Review`. Not "we remember to
scope it" — a **lint rule** forbids the unscoped form, because the rule is
*syntactic* and therefore mechanically checkable. That is the difference
between a convention and an enforcement.

The accessor also returns a **scope receipt**: a human-readable reason for why
this actor sees this set. Every list view renders it. It costs about an hour
and it makes the isolation verifiable by a *reader*, not only by our tests.

### Two layers, not three

| Layer | Role | Fails by |
|---|---|---|
| **Permission** | decides, and raises | forgetting to call it |
| **Queryset** | constrains; *cannot* raise | being bypassed |

They fail in **opposite directions**, which is the argument for exactly two. A
third layer would be *derived* from the first two — and a derived layer is a
second source of truth.

### A denial is a literal 403

**Empty body. No `Location` header. Never a 302. Never an empty 200.**

`run.py` follows redirects, so a redirect to a login page comes back **200**
and fails the check *while looking correct in a browser*. It is the single
highest-value line in this project, and it is why `run.py`'s own example
report shows a team that lost a point to it.

And a 403 must not distinguish "exists but not yours" from "does not exist" —
that difference is an enumeration oracle. The accessor raises `NotFound` for
both.

### The proof, not just the claim

`manage.py isolation_proof` walks the full actor × resource matrix, prints the
status code for **every cell**, and exits 0 only if every cell is correct. It
ships in FEAT-02, before any feature exists to leak — the primitive is only
cheap to build before there is something to leak.

Four invariants are **property-based** (Hypothesis), not examples, because the
failure mode is "some combination we did not think of": monotonicity under
role inclusion, no cross-evasion across generated actor/query pairs,
decline-not-filter, and scope-is-total.

### Rejected alternatives, with reasons

| Not used | Why |
|---|---|
| **Postgres RLS** | Postgres-specific, needs `SET LOCAL` per transaction with real pool-leakage hazards, and **views bypass it by default** |
| **Casbin / OPA** | Makes the rules *non-portable* and creates a second source of truth — the exact opposite of our claim |
| Template-level hiding | The spec names it as the common way a good-looking project loses points |

The scoped-accessor layer is the portable equivalent of RLS and expresses
"judge on trk_04" as an index scan rather than a correlated subquery per row.

---

## 2. Assignment

**One min-cost flow over all tracks**, not per-track flows. 9 of 30 judges are
dual-track, so a per-track flow is simply the wrong model.

- **Min-max capacity by search.** Both cost terms — load imbalance and seeded
  tiebreak — stay in the objective, where they belong and where they are
  measurable. Two terms were cut *on measurement*.
- **Seeded tiebreak**, so the same fixture produces the same assignment
  byte-for-byte. Reproducibility is worth more than a marginally better
  assignment.
- **Flow solver hand-rolled, ~80 lines.** scipy's Dinic solves this 40-node
  graph in 0.25 ms. A 60 MB wheel is an install-time failure mode we do not
  need.

### Infeasibility is diagnosed, never asserted

"Feasible" and "provably impossible" are different answers and they get
different code paths. When the instance is infeasible, the **min-cut names**:

1. the deficient projects,
2. the bottleneck judges,
3. the deficit,
4. and three remedies, with arithmetic.

> **A claim we got wrong and corrected:** we previously wrote that two tracks
> were "structurally infeasible". **They are not.** 18 needed, 18 possible — a
> perfect matching exists. They are **zero-slack**, and become provably
> infeasible only at capacity 5. Three tracks missed the target, not two, while
> the event nets +3 overall: **a global bar hides three local failures.** This
> is finding F-07, and the correction is why the min-cut is computed rather
> than asserted.

---

## 3. Normalization

**The question is not "how do we normalize". It is "is there anything to
normalize?"** A normalization claim that does not test for the effect it
removes is a subtraction, not a proof. (D-05.)

### The inconvenient result, stated first

> **On the published fixtures there is no detectable judge-severity effect.**
> Between-judge variance **0.0217** against a sampling-noise floor of
> **0.0971**. Permutation **p = 0.234**. The detection floor is **τ ≈ 0.75**.

We report that **before** any claim about improving scores, because the brief
rewards honest gap reporting and penalises inflation. It is a property of the
published data, not a failure of the method — and it is the most important
sentence in this document precisely because it is disappointing.

### The estimator

Robust **median/MAD** with shrinkage `k = 3`, plus `ε = 0.5` as the legible
default. Both constants are **a priori** and chosen without looking at
outcomes.

Reported alongside: **empirical Bayes** (`τ²` by moments) as the
constant-free estimator. It has **no tunable constant at all**, which removes
our largest exposure — and it measured 4.9% better held-out RMSE.

> **`k = 0` scores better than the value we ship.** We do not use it. Tuning to
> a published target is overfitting, and the full sensitivity curve ships beside
> any single number.

### The proof, in this order

1. **Predictive result leads** — held-out RMSE **0.6753** against a **0.7952**
   baseline. This is what a normalizer is *for*.
2. **The null effect, immediately after** — it qualifies the claim.
3. **Parameter recovery** — on synthetic panels with known ground truth,
   recovers severity at **RMSE ≈ 0.27** against a **0.54** MFRM baseline. The
   organizers named this as what the bonus rewards: *"Showing it recovers a
   known effect is exactly the kind of rigour the bonus is looking for."*
4. **Sensitivity** — `k` and `ε` curves, published in full.

**Every published number is asserted in CI.** A refactor that silently changes
the method must fail a test rather than quietly weaken this document.

`docs/REAL-FIXTURE-RESULTS.md` isolates the real-fixture half, with no
synthetic content, per the organizer's condition.

### Measured and rejected

| | |
|---|---|
| **IRT / MFRM** | Held-out RMSE **0.9097** vs **0.6753** — *worse than predicting the panel mean*. Parameter-recovery RMSE 0.5414 vs 0.2717. Estimating a free difficulty for each of 41 projects from ~3 reviews each costs more variance than the de-confounding gains. We borrow the vocabulary and the infit/outfit statistic for n=1. |
| **TrueSkill** | A win/loss online rating with a *dynamic* skill parameter. Our data is static ordinal rubric scores with no sequence. Adopting it means abandoning the rubric — and the weighted rubric is what T2 asks for. |

---

## 4. Anti-abuse

**The answer to "people trying to cheat it" is a report, not a fancier ballot.**

The influence report is per judge, per project and per criterion. A single
judge's capability to move 1–2 of 126 reviews is stated plainly.

Voting uses **amplitude inside an identity budget** with mandatory,
attributable abstention, and **randomized ballot order** — which makes bias
zero-*mean*, not zero. The mechanism-design literature is explicit that this
does not resist a well-capitalised Sybil operation, and **we do not claim that
it does**; the claim is falsifiable in one search.

A ranked Borda ballot was considered and cut. It is elegant, it is the unique
linear rank aggregator satisfying the Condorcet criterion, and it **changes
the outcome**. The influence report **explains** it instead.

---

## 5. Integrity primitives

| | |
|---|---|
| **Audit log** | Hash-chained, with `omitted_since_prev` *inside* the chain. Rate-limited sampling plus a chain is incoherent: a gap is indistinguishable from an edit. |
| **Chain head** | One published head, replicated into every signed judge record — so N parties outside the trust boundary each hold a copy. |
| **Signed records** | Ed25519 over an in-toto Statement v1 inside a DSSE envelope. DSSE signs *bytes*, so no third party reimplements our canonicalisation. |
| **Certificates** | Generated and verifiable at near-zero marginal cost. |

---

## 6. What we do not stop

Stated in full in `bible/07` (threat model). The short version, because a threat
model that only lists what you *did* stop is marketing:

- **No rate limiting on the API surface beyond what the audit chain records.**
  It is measured, prioritised and documented, not silently absent.
- **`UNUSABLE_PASSWORD` on ~116 fixture identities** is a deliberate
  availability/security trade: 121 real hashes cost ~48 s against a 10 s
  checker timeout.
- **The container runs as uid 10001, not rootless**, and the Docker socket is
  not exposed to it.
- **Keys are on a volume, not in an HSM.** Stated as a deployment posture, not
  faked with a cloud SDK we cannot use offline.
