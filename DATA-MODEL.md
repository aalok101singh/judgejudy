# Data Model

> **Status: as built in FEAT-02, corrected by FEAT-03.** The migrations that
> implement this document are `src/reviewer/*/migrations/0001_initial_schema.py`
> — 13 apps, 26 models, twelve initial migrations — plus **one correction**,
> `teams/0002_remove_team_teams_team_event_name_uniq`. Each migration has a
> docstring naming the requirement or decision it serves. The model and app
> counts below are **checked against the Django app registry** by
> `tests/test_schema_contract.py`, which reads the number out of
> `blueprint/build-plan.md` and compares. They are not typed here and
> transcribed: the plan is the claim, the registry is the check, and F-44 records
> the two stale counts this document used to carry.
>
> **What FEAT-03 changed in the schema, and it is a measurement.** `Team` lost
> its `UNIQUE (event, name)` constraint because **`fixtures.json` violates it**:
> 40 teams, **36 distinct names**, `StillTrail` three times, `OpenSignal` twice,
> `AmberSwitch` twice — and two teams sharing a name own different projects. The
> constraint was not a design anyone argued for; it was inherited from
> "uniqueness is good" and the first code that ran against the real data killed
> it. `(event, slug)` is kept, because a slug is derived and therefore has to be
> unambiguous for a URL to mean one team. F-50.
>
> The plan for the depth behind each decision: `bible/05` (domain model, full
> depth) · `blueprint/build-plan.md` Phase B (FEAT-02, 5h) ·
> `blueprint/history/features/02-schema-and-isolation.md` (what was actually
> built, and what was left out) ·
> `blueprint/history/features/03-loader-gallery-deadline-guard.md` (what the
> real data changed).

---

## 1. What the fixtures actually contain

Every number here is re-derived by `python tools/verify_spec.py` from
`fixtures.json`, which is pinned by SHA-256. **Do not transcribe a number from
this table into code, a test, or a commit message — run the gate.**

`fixtures.json` · SHA-256 `252896BC…181121` · 46,687 bytes

| | |
|---|---|
| Events | 1 — `evt_01`, `submissions_close = 2026-03-01T18:00:00Z` |
| Tracks | 8 |
| Judges | 30 (21 single-track, 9 dual-track) |
| Teams | 40 |
| Projects | **41** |
| Reviews | **126** |
| Criteria | always `{functionality, innovation, quality}`, values 2–5 |
| **Key order** | **`functionality, quality, innovation`** |

### Four things in the data that are deliberate

The spec says the awkward cases are there on purpose. They are:

1. **`submissions_close` is in the past.** The portal is born closed. Every
   mutating view must refuse. **Never move this date** — the organizers' T1
   check POSTs a submission and requires a 4xx precisely because the honest
   seeded state is closed.
2. **`jdg_07` gave 4/4/4 on three projects, one of which (`prj_19`) has only
   two reviews.** A constant judge is half of that project's entire score. This
   is why normalization exists and why a *median/MAD* estimator must treat a
   structurally-zero MAD differently from an evidentiary one.
3. **`prj_07` and `prj_41` are the same team, track, title and repo**, 13h28m
   apart, with 5 and 4 reviews. Model as `supersedes`, keep **both** rows, and
   aggregate **by team, latest-wins**. The export carries a `counted` flag so
   the decision is auditable and reversible.
4. **`jdg_01` and `jdg_23` have exactly one review each.** Any per-judge
   estimate has to survive n=1 without pretending to a confidence it lacks.

### The number that is most quoted and most often wrong

Reviews per project: **8@2, 26@3, 3@4, 4@5** (mass: 8×2 + 26×3 + 3×4 + 4×5 =
126).

The mode — 26 of 41 projects at exactly 3 reviews — is the evidence for a
review target of 3. Not the total, which would be circular.

> This table was once wrong in this project: `5@5` instead of `4@5`, which
> gives a mass of 131. It was caught by the two invariants in `bible/04` §2.1 —
> bucket counts sum to the population, and `Σ n × count` equals the record
> count — and the correction is finding F-28. **Six of our first twelve
> findings were hand-typed census errors, two of them found after we had
> already published a correction log about the first four.** Hence the gate.

---

## 2. Shape of the schema

Implemented in FEAT-02, as `src/reviewer/`. Decided in `bible/05`.

```
Event ──┬── Track ──── Prize
        ├── Team ──── Membership ──── User ──── RoleBinding
        ├── Project ── (the supersedes chain; BOTH rows kept)
        │       ├── Assignment ──── Review ──── Score
        │       └── Rubric ──── Criterion        (rubric_version on every Review)
        ├── Ballot ──── Vote
        ├── Comment
        ├── AuditEntry   (hash-chained) ──── ResultPublication
        ├── JudgeCredential ──── SignedRecord
        ├── WebhookEndpoint ──── WebhookDelivery   (models only; D-14)
        └── RunSnapshot   (export/import manifest)

reviewer/isolation/     the primitive: Actor, Scope, ScopeReason, ScopedQuerySet
reviewer/normalization/ the estimator. No model. FEAT-08.
```

**26 tables across 13 apps.** Apps are named for the domain (`reviewer.reviews`),
not for the layer, and none holds more than three models — both asserted by
`tests/test_schema_contract.py`.

| App | Tables | |
|---|---|---|
| `accounts` | User, RoleBinding | authority lives here, not in Django permissions |
| `events` | Event, Track, Prize | the tenant boundary |
| `teams` | Team, TeamMembership, TeamInvite | |
| `projects` | Project | the `prj_07` / `prj_41` chain |
| `rubrics` | Rubric, Criterion | versioned |
| `reviews` | Assignment, Review, Score | the isolation surface |
| `ballots` | Ballot, Vote | randomised order, hashed identifiers |
| `comments` | Comment | |
| `audit` | AuditEntry, ResultPublication | hash chain + content hash |
| `credentials` | JudgeCredential, SignedRecord | Ed25519 / DSSE / in-toto |
| `webhooks` | WebhookEndpoint, WebhookDelivery | schema only, D-14 |
| `io` | RunSnapshot | the escape hatch manifest |

`reviewer/isolation/`, `reviewer/normalization/` and `reviewer/widget/` are
**packages, not apps**. They define no model, and listing an app with no models
would add a `models` module that does not exist and a migration that creates
nothing.

`reviewer/widget/` joined them in FEAT-07 and **the rule was applied rather than
amended.** It serves two routes (`/widget/results/`, `/widget/results.json`) and
builds one self-contained document, none of which needs a table — so making it an
app purely so Django would discover
`manage.py verify_widget_offline` would have bought a fourteenth app and two
useless files to keep a number in this document at thirteen. The command lives in
`reviewer.audit` instead, which owns the `ResultPublication` gate the widget
obeys. The alternative — registering the app and rewriting the paragraph above to
excuse it — was rejected as goalpost-moving for a feature that did not need it.

### Four rules that apply to every table

1. **`source_key` on every importable table.** The bulk round-trip must be
   **byte-identical including natural keys**. "Modulo generated IDs" is not a
   testable property — a dropped column passes it. One nullable column, free in
   the initial migration, three hours if retrofitted.
2. **Postgres-portable or not at all.** No SQLite-only types, no
   `JSONField`-index assumptions. We develop on SQLite because the brief
   requires it; the schema has to survive a port.
3. **`CheckConstraint`s over application validation** for anything a row could
   violate — a range or a length that must never exist, even transiently.
4. **Explicit `UniqueConstraint`s**, including composite ones.

**No migration without a stated purpose.** Each one's docstring says which
requirement or finding it serves. An unexplained migration is a finding waiting
to happen.

---

## 3. Two tables that are not ordinary

### `AuditEntry` — the hash chain

Append-only, hash-chained, with `seq`, `prev_hash`, `entry_hash` and
`omitted_since_prev`.

That last column is the design. Rate-limited audit sampling plus a hash chain
is **incoherent** — a gap in the sequence is indistinguishable from a deleted
entry. So the gap is inside the chain: the chain records what it did not
record.

Four columns are the difference between "append-only, we promise" and
"append-only, go and check."

**No Merkle transparency log.** A root we compute ourselves proves internal
consistency, which the chain already proves, for three times the code.
Certificate transparency's value is *witnessing* — an independent party holding
a copy to detect equivocation — and this project has no witness. Instead: one
chain head published at results publication, replicated into **every** signed
judge record, so N parties outside the trust boundary each hold a copy. For a
third of the code, that is strictly stronger.

### `SignedRecord` — the portable record

An **Ed25519** signature over an **in-toto Statement v1**, wrapped in a **DSSE**
envelope. Keys on their own volume, never in the database volume — a
`down -v` during testing must not invalidate every record in the README.

DSSE because it signs *bytes*. A hand-rolled canonicalisation format means
every third party who wants to verify a record has to reimplement our
serialisation, and gets it subtly wrong.

---

## 4. Constraints the data forces

These are not preferences. Each is a place where the naive schema is wrong.

| Constraint | Why |
|---|---|
| A project belongs to a team, not to a submitter | `prj_07`/`prj_41` are the same team twice. Per-submission attribution is what the fixture is testing. |
| `supersedes` is a self-reference, both rows kept | "Latest wins" computed at read time is a bug waiting for a second read path |
| `counted` is stored, not derived | The aggregation decision has to be auditable in the export, not recomputed differently by each consumer |
| A judge's eligibility is per track, not global | 9 of 30 are dual-track; a global flag cannot express "judges trk_04" |
| Track review target is **nullable, inheriting from the event** | Two tracks are provably infeasible at 3. A single event-level integer cannot express that |
| Conflict of interest is a **hard block** | A judge who is a team member is blocked at assignment and re-checked at submission |
| Drafts are savable after the deadline; submission is not | A platform that freezes every write fails an organizer fixing a typo |

---

## 5. The bulk round-trip

`export run` → `import run` must be **byte-identical, including natural keys.**

That is a testable property only because every importable table carries
`source_key`. Without it, "byte-identical modulo generated IDs" lets a dropped
column pass, and the round-trip test is decoration.

The load path is **idempotent** — run it twice, get the same database. A loader
that only works once makes `docker compose up` non-reproducible, and
reproducibility is 20% of the score under Adoptability.

Every census table **prints its own row count on boot**, and a count that does
not match its stated population is a boot failure. Six of our first twelve
findings were census errors in our own documents; this is the mechanism that
stops the next one.
