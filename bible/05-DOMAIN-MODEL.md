# 05 · Domain Model

**Purpose:** the schema, its constraints, its indexes, the access-control
primitive built on top of it, and the escape hatch. Written to be lifted
directly into `DATA-MODEL.md` with light editing.

**Constraints this design obeys, from `README.md`:**
- Works on **SQLite** (the shipped default) and **Postgres** (documented
  switch). No Postgres-only features: no `jsonb` operators, no `ArrayField`, no
  `DISTINCT ON`, no `pg_trgm`, no CTEs in migrations.
- Uses Django 5 idioms end to end, because the schema is read as part of the
  code and consistency is worth more than cleverness.
- Every decision below states its reason and its cost. That is what "a schema a
  database person would defend" means in practice.

---

## 1. Shape at a glance

```
                        ┌──────────┐
                        │   User   │  identity, credentials
                        └────┬─────┘
                             │ 1
                             │
              ┌──────────────┼───────────────┐
              │ M            │ M             │ M
        ┌─────▼─────┐  ┌─────▼──────┐  ┌─────▼──────┐
        │ Membership│  │RoleBinding │  │  Session   │
        └─────┬─────┘  └─────┬──────┘  └────────────┘
              │ team          │ scoped to event (and track)
        ┌─────▼─────┐        │
        │   Team    │        │
        └─────┬─────┘        │
              │ 1            │
              │ M            │
        ┌─────▼─────┐   ┌────▼─────┐  ┌──────────┐
        │  Project  │   │ Rubric   │  │  Audit   │
        └─────┬─────┘   │ Criterion│  │  Entry   │
              │ M       └────┬─────┘  └──────────┘
        ┌─────▼─────┐        │ 1
        │ Assignment│◄───────┘ M
        └─────┬─────┘
              │ 1
              │ M
        ┌─────▼─────┐        ┌──────────┐
        │   Review  │        │   Vote   │
        └─────┬─────┘        └──────────┘
              │ M
        ┌─────▼─────┐
        │   Score   │
        └───────────┘
```

Nine aggregates. `Event` is the tenant boundary; every other table that matters
carries `event` directly or one hop away, because **every query must be
scopable to an event and a role** and that is only cheap if the index prefix is
right.

---

## 2. Event, track, prize

### `Event`

| Field | Type | Notes |
|---|---|---|
| `id` | `CharField(32)` PK | Fixture IDs preserved verbatim (`evt_01`). Makes `curl` transcripts in the docs checkable against the published dataset. |
| `slug` | `SlugField` unique | URL identity, human-facing. |
| `name` | `CharField(200)` | |
| `description` | `TextField` blank | |
| `starts_at`, `submissions_close`, `submissions_open` | `DateTimeField` | All UTC. `submissions_close` is **the deadline the guard reads**. |
| `judging_closes_at` | `DateTimeField` null | |
| `results_state` | `CharField` choices | `hidden` / `published`. See §3. |
| `voting_mode` | `CharField` choices | `closed` / `open_link` / `email_gated` / `authenticated` (REQ-T3-01) |
| `voting_opens_at`, `voting_closes_at` | `DateTimeField` null | |
| `reviews_per_project` | `PositiveIntegerField` default 3. **Default only** — the operative target is per-track; see below. |
| `rubric_weights_locked_at` | `DateTimeField` null | Weights cannot change once judging starts. |
| `created_at`, `updated_at` | `DateTimeField` auto | |

**`reviews_per_project` is a default, not a policy — and the fixture is why.**
Measured on `fixtures.json` (`06` §2.1a): `trk_01` and `trk_08` each have 6
projects and 3 judges, so a target of 3 reviews per project needs 18 assignments
from 3 judges — exactly the maximum possible, with **zero structural slack**.
One withdrawal makes it arithmetically impossible, and a single global integer
cannot express "3 everywhere except these two tracks, which cannot do 3 at all."

So the real target lives on `Track`:

```
Track.target_reviews_per_project   PositiveIntegerField null
                                  → falls back to Event.reviews_per_project
```

Null means "inherit," which keeps the common case of a uniform event to a single
field and makes the exception explicit rather than duplicative. The assignment
solver (§`06` §2) reads the effective target per project, and the infeasibility
report is generated per track — because the binding constraint is
**judges-per-project in one track**, never the event-wide average. An organizer
who sets 3 and gets a warning about `trk_01` needs to be able to fix it for
`trk_01`, and that is only possible if the target is settable there.

**Cost of this decision, stated because a reviewer will ask:** one nullable
integer, one fallback in the resolver, and a per-track rather than per-event
progress denominator. In exchange the product can actually represent the
situation it exists to solve, and the organizer UI can offer "reduce the target
for `trk_01` to 2, or invite a fourth judge" as concrete remedies instead of a
generic apology.

**Why three separate timestamps rather than a status enum:** the spec's
acceptance check depends on `submissions_close` being a *date the code reads*,
not a state we set. Keeping a real timestamp means the deadline is enforced by
comparison, which is the only enforcement that cannot be bypassed by forgetting
to flip a flag.

**`rubric_weights_locked_at` is a judgement call worth defending.** Allowing an
organizer to change weights mid-judging silently changes everyone's meaning.
Locking after first review submission is the honest behaviour, and it is a
schema-level statement of that policy rather than a UI convention.

### `Track`

`(event, name, slug, description, target_reviews_per_project)`, unique on
`(event, name)`.

`target_reviews_per_project` is nullable and inherits from the event when null —
see the `Event` table above for why it exists and what the fixture proves about
it. Everything else about a track is presentation; this one field is policy, and
it is the only per-track setting the assignment solver reads.

**A project belongs to exactly one track** — `CheckConstraint` on the project
(see §4). The fixture agrees: every project has exactly one track, and the
assignment model is track-scoped. An event with no tracks is allowed and is
simply un-tracked; we do not invent an "other" row, because a synthetic track
pollutes the gallery filters.

### `Prize`

`(event, name, amount_cents, currency, rank, category, track)`.

Amount in minor units as an integer. Never a float. Rank nullable for category
prizes. Currency defaults to `USD` but is stored, because the product is
international and the panel is in five countries.

---

## 3. Identity and roles

### `User`

Django's `AbstractBaseUser` + `PermissionsMixin`? **No** — a plain
`AbstractBaseUser` with a custom manager, and **no** `PermissionsMixin`.

Reason worth stating: Django's permission framework is global, not per-event.
A judge on `trk_03` and a judge on `trk_07` are the same Django user in the
default model, which is exactly the modelling mistake that produces the
cross-track leak FIG. 02 forbids. **Our authorization lives in `RoleBinding`,
not in Django permissions.** Keeping `PermissionsMixin` would invite the mistake
and buy nothing.

Fields: `email` (unique, the login identity — the fixture uses emails
throughout and hackathons are email-first), `display_name`, `password`,
`is_active`, `is_staff` (Django admin only, deliberately separate from product
roles), `created_at`.

### `RoleBinding` — the important table

| Field | Notes |
|---|---|
| `event` | FK |
| `user` | FK |
| `role` | `visitor` is *not stored* (it is the absence of a binding); `participant` / `judge` / `organizer` / `admin` |
| `track` | FK **nullable** |

Unique together on `(event, user, role, track)`.

**`track` nullable is the whole design.** A judge binding carries the track;
an organizer or admin binding carries `track = NULL` and is event-wide. A judge
with two tracks has two binding rows — which is exactly the fixture's shape for
its 9 dual-track judges, so the seed is a direct expression of the model rather
than a special case.

The `visitor` role is deliberately absent as a stored value: a visitor is
someone with no binding, and making it a row would mean every anonymous request
creates a user. The role model still *has* five roles, as the tier requires —
`visitor` is the implicit default, and the code that resolves an actor's roles
returns it explicitly.

### `Session`

Django's built-in `django.contrib.sessions` with the **database backend**.
Explicitly not signed cookies, and no external auth service.

- Database sessions mean a session is a row we can revoke, which matters for
  "kick a judge who finished", and it means the seeded session values in
  `.dogfood.toml` are real server-side state.
- They also mean our isolation reasoning has a single place to look: every
  authenticated request resolves to exactly one `User`, and every authorization
  decision is a `RoleBinding` lookup plus a queryset scope.

---

## 4. Teams, projects, submissions

### `Team`

`(event, name, slug, invite_code)`, unique on `(event, name)` and unique
`invite_code`.

### `TeamMembership`

`(team, user, role_in_team, joined_at)`, unique on `(team, user)`.
`role_in_team` ∈ `owner` / `member`. An `owner` can redeem an invite and
manage the team; a `member` can submit on its behalf.

**No uniqueness constraint on "a user in one team per event."** The fixture
happens to satisfy it, but real events have people who float between teams, and
a bulk import that trips a database constraint on real data is a bad import
path. Enforced in the UI as a warning; not enforced in the schema. This is a
deliberate, stated trade: data integrity at the database versus a loader that
never fails on real input.

### `TeamInvite`

`(team, code, created_by, expires_at, max_uses, uses, created_at)`.
Redeeming is idempotent on `(team, user)`.

### `Project` — with the deliberate choices called out

| Field | Notes |
|---|---|
| `id` | `CharField(32)` PK, fixture ID preserved (`prj_07`) |
| `team` | FK. **One-to-many.** `tm_07` has two. |
| `track` | FK, **non-null** |
| `title` | **No uniqueness constraint.** See below. |
| `summary` | Non-blank, required. Fixture value is uniform; the constraint is on non-emptiness, not content. |
| `description` | `TextField` blank — the long description, part of the stable field set |
| `thumbnail_url`, `video_url`, `live_url`, `repo_url` | Blank URLs, never fetched. |
| `tags` | `JSONField` list of strings. Portable across both engines. |
| `custom_answers` | `JSONField` object, keyed by custom-question ID |
| `images` | `JSONField` list of `{url, caption, order}` |
| `status` | `draft` / `submitted` / `withdrawn` |
| `supersedes` | FK self, nullable → `prj_41 → prj_07` |
| `submitted_at` | Nullable. **Null on a draft.** |
| `created_at`, `updated_at` | |

**No uniqueness on `title`.** Two fixture projects share the title `Dry Harbour`.
More importantly, titles collide in real events constantly, and a unique index on
a user-supplied string is a support incident waiting to happen. Uniqueness, where
it is wanted, lives on `slug` per team.

**`supersedes` rather than deletion.** This is the `prj_07` / `prj_41` decision
from `04` §3.3, expressed in the schema:

- Both rows persist. Nothing is destroyed on supersede.
- The superseded row's reviews persist with it, for the audit trail.
- Results aggregate by team, latest-wins.
- Export writes both, with the relation, so a round-trip is lossless.

The alternative — deduplicating on load — was rejected because it makes the
loader lossy, and a lossy import path quietly loses an organizer's data. That is
precisely the "platform you cannot leave" trap in reverse: a platform you
cannot trust to take your data in.

**Drafts are invisible to the gallery.** Enforced in the gallery queryset, not
in the template. `status = submitted` and a non-null `submitted_at` is the only
public state.

### The deadline guard

One service function, called by every write path — API, admin, bulk import:

```python
def assert_open_for_submission(event, *, now=None):
    now = now or timezone.now()
    if event.submissions_open and now < event.submissions_open:
        raise SubmissionClosed("Submissions have not opened yet.")
    if now >= event.submissions_close:
        raise SubmissionClosed("Submissions closed at ...")
```

Why a service function rather than a model `save()` override or a view
decorator:

- A `save()` override is bypassed by `bulk_create`, `update`, and queryset
  updates — exactly the paths bulk import uses.
- A view decorator is bypassed by the admin, the API, and the import command.
- A service function called by each caller is one `if`-equivalent that the
  checker exercises for real, and our own tests exercise for both the open and
  closed case.

`SubmissionClosed` maps to **HTTP 403**, never a redirect, per `03` §4.1.

---

## 5. Judging

### `Rubric` and `Criterion`

```
Rubric     (event, name, scale_min, scale_max, version, created_at)   unique (event, name, version)
Criterion  (rubric, key, label, description, weight, position, required)
```

`weight` is a `Decimal` (not a float — rubric weights are money-adjacent
arithmetic and binary floats make "weights sum to 1.0" fail for no good reason).
`CheckConstraint` that weights are positive. Weights are normalised at read
time rather than stored pre-summed, so an organizer editing weights from 40/35/25
to 4/3.5/2.5 does not have to think about scale.

`scale_min` / `scale_max` default to 1 and 5. The fixture only ever uses 2–5, but
the product's rubric is configurable and the spec's stable field set implies
organizer-defined criteria.

**Versioned rubrics.** A judge who scored against version 1 and a judge who
scored against version 2 are not comparable. Versioning the rubric and stamping
every `Review` with the version it was scored under is what makes normalization
defensible rather than hand-wavy. Most teams will not think of this. It costs one
FK.

### `Review` — the load-bearing table

| Field | Notes |
|---|---|
| `assignment` | FK, unique together with `judge` — one review per judge per project |
| `judge` | FK `User`. Denormalised from `assignment` on purpose. See below. |
| `project` | FK. Denormalised from `assignment`. |
| `rubric_version` | FK `Rubric`. The version this review was scored under. |
| `status` | `assigned` / `in_progress` / `submitted` / `declined` |
| `overall_comment` | Nullable. 51 of 126 fixture comments are empty. |
| `submitted_at` | Nullable |
| `duration_seconds` | Nullable. Feeds the "judge rushing" signal in `07`. |
| `is_conflicted` | Boolean. Organizer-declared conflict of interest. |

**Why `judge` and `project` are denormalised onto `Review` when `Assignment`
already has them.** This is the one place in the schema where redundancy is
correct, and the reason is authorization:

- The isolation query is *"every review by judge J"*, and *"every review on a
  project in track T"*. Both are single-table filtered reads. With the
  denormalised columns and a composite index, they are index scans.
- Without them, every isolation check is a join across `Assignment`, and the
  filter that must never be forgotten lives one hop further from the row it
  constrains.
- A `Review` row is a fact about a review. It should be self-describing. A
  reviewer reading the table should not have to traverse to `Assignment` to
  learn who reviewed what.

Constraint: `unique(assignment)`, plus `unique(judge, project)`.

`status = declined` is what makes conflicts real: a judge declares a conflict,
the project is reassigned, and the decline is visible to the organizer rather
than silently disappearing.

### `Score`

| Field | Notes |
|---|---|
| `review` | FK |
| `criterion` | FK |
| `value` | `SmallIntegerField`, `CheckConstraint` within the rubric's scale |
| `weight_applied` | `Decimal`, **snapshotted at submission time** |

**`weight_applied` is snapshotted, not joined.** If an organizer edits weights
mid-judging, existing reviews must not silently change meaning. The
`rubric_weights_locked_at` lock prevents it in the normal path; the snapshot
makes it impossible even in the abnormal path. Defence in depth on the one
number the whole result depends on.

Unique on `(review, criterion)`. Nullable value, because an in-progress review
has criteria filled in one at a time.

### `Assignment`

`(event, judge, project, batch, assigned_at, assigned_by, method)`.
`method` ∈ `manual` / `batch` / `algorithmic` — the spec says "by batch or
algorithmically," and both must be visible to an organizer.

Unique on `(judge, project)`. Indexed on `(event, judge, status)`.

**The scores in the fixture are evidence of assignment.** `04` §5: we
synthesise `Assignment` rows from the 126 score rows so the progress dashboard
and the isolation model run on real structure. The synthesis is deterministic
and idempotent.

---

## 6. The isolation primitive

**This is the architectural centrepiece, and the most likely "steal it"
decision.**

The requirement is that a judge can never read a peer's scores, another track's
reviews, or the aggregate. The naive implementation is a check in each view.
That is exactly what the spec calls "decorative."

Instead: **every read of `Review` goes through a manager that takes an actor and
returns an already-scoped queryset.** There is no code path from a view to an
unscoped `Review` queryset.

```python
class ReviewQuerySet(models.QuerySet):
    def for_actor(self, actor) -> "ReviewQuerySet":
        """The only sanctioned way to read reviews.

        Scoping is applied here, not in the view, so a view cannot leak a
        peer's review by forgetting a filter.
        """
        if actor.is_admin or actor.is_organizer_for(self.event):
            return self
        if actor.is_judge_for(self.event):
            return self.filter(judge=actor.user)      # own scores only
        return self.none()                            # everyone else: nothing
```

And the peer-scoped probe the checker uses is a **separate, explicitly
peer-blind** accessor:

```python
    def for_actor_and_subject(self, actor, subject) -> "ReviewQuerySet":
        # A judge asking about another judge is refused, not filtered.
        if actor.is_judge_for(self.event) and subject != actor.user:
            return self.none()
        return self.for_actor(actor)
```

Four properties, each worth points:

1. **Impossible to forget.** A new view that writes `Review.objects.all()` is a
   lint error, not a security bug. We ship that lint rule.
2. **Refusal, not filtering.** An empty `200` is a FAIL against the acceptance
   check. Scoping must produce a `403`, which means the *permission* layer
   raises and the *queryset* layer never runs. Two layers, both correct:
   permission decides, queryset constrains.
3. **Aggregate isolation falls out of the same place.** Leaderboards are
   computed from `Score` joined to a scoped `Review` set, so a judge asking for
   a ranking is asking over their own reviews only, and an organizer asking over
   all of them. One mechanism, two scopes.
4. **It is auditable.** `07` §5 logs every scope decision at the boundary, so
   the audit trail records not just who did what but what each actor was able to
   see.

### 6a The scope receipt — isolation you can read, not just isolation you have

**The third "steal it" candidate, and the cheapest item in this document.**
`for_actor()` returns a queryset that **also carries a human-readable reason for
the scope it applied**, and every list view renders it in a collapsed
`<details>`:

> **Why you are seeing 3 of 126 reviews**
> You are a judge on `trk_04` (Security). Isolation shows you your own reviews
> only — 3 of the 126 in this event. Peers, other tracks, and aggregates are
> refused at the API with `403`, not hidden on this page.

```python
class ScopedQuerySet(models.QuerySet):
    def for_actor(self, actor) -> "ScopedQuerySet":
        qs = ...                       # the filtering, as above
        qs.scope_reason = ScopeReason(
            actor=actor,
            rule="judge: own reviews only, track-scoped",
            visible=<int>, total=<int>,           # 3 of 126
            bindings=[("judge", "trk_04")],
        )
        return qs
```

**Why this is the strongest one-hour item in the project.** Our existing
decision — *refusal, not filter* — makes the **denial** correct. This makes the
**scope** self-explaining, which means **a judge can verify isolation without
reading our code and without trusting our test suite**: the page states the rule
that fired and how many rows it let through. It generalises the same instinct
behind the refusal-not-filter distinction (two situations, two code paths) into
a property: **every access decision explains itself.**

And it is the same object feeding three consumers, which is what makes it an
architecture rather than a UI feature:

| consumer | what it renders |
|---|---|
| the judge's list view | the `<details>` block above |
| the audit entry | the scope string, alongside the actor and the action |
| `manage.py isolation_proof` | the "3 of 126" column, per actor |

**Cost: ~1 hour.** One attribute on the queryset, one template partial, one call
site. Fifteen seconds of demo video, and it is the only candidate that makes a
*mechanism* visible rather than a *result*.

### 6b Proving the matrix, rather than testing 25 cells

`05` §6 above is the design. Two things make it a *provable* property rather
than a tested one, and both are cheap.

#### 6b.1 `manage.py isolation_proof` — a table that matches a published figure

One command, exits nonzero on any mismatch. A test suite's output is a list of
test names; **this is the published matrix, reproduced with live data**, and a
judge comparing it to FIG. 02 sees the figure they were given.

```
$ python manage.py isolation_proof
DOGFOOD isolation proof -- evt_01 -- 2026-09-27T14:22:01Z

  actor        own  peer  cross-track  aggregate  export  audit   audit-json
  visitor       403   403      403         403      403     403       403
  participant  403   403      403         403      403     403       403
  judge         200   403      403         403      403     403       403
  organizer    200   200      200         200      200     200       403
  admin        200   200      200         200      200     200       200

  20 of 20 cells match FIG. 02.
  Every denial: status 403, empty body, no Location header.   (verified, not assumed)
  Peer probe: GET /api/judge/scores?judge=jdg_08 as jdg_07 -> 403
  Rows visible to jdg_08: 3 of 126.  Reason: judge on trk_04, own reviews only.
$ echo $?
0
```

**What it must print, specifically:** the **status code per cell** (not ✓/✗ —
the number is the evidence); for every denial, **403 + empty body + no
`Location` header**, asserted three ways (that is `03` §4.1 as an executable
invariant, and it is the check the brief names as the one that costs the most
points); **visible-of-total row counts** per actor (that is the difference
between "we hid it" and "we scoped it"); and the **raw `curl` equivalent** of
the peer probe, so this output and the acceptance transcript cannot disagree.
Nonzero exit on any mismatch, so it gates CI and the H+48 checkpoint.

**~1.5 hours.** It is a loop over the matrix calling the existing DRF test
client; the only real work is the `Location`-header and row-count assertions.

#### 6b.2 Property-based testing with Hypothesis — invariants, not cells

**Hypothesis** (`hypothesis.extra.django.TestCase`, which runs **one
transaction per example** rather than per test — exactly what a `@given` test
needs, since the test function is invoked many times).

**Four properties. Note that none of them is "cell X returns 403" — that is
enumeration, and enumeration is what we already have.**

```python
P1  MONOTONICITY.  If actor A may see row r, and A's RoleBinding set is a
                   subset of B's (same event), then B may see r.
                   Authority is monotone under role inclusion.

P2  NO CROSS-EVASION.  For every pair of distinct judges j1 != j2, every route,
                   and every generated query-parameter combination q naming j2,
                   scoped(j1, route, q) contains no row with judge = j2.
                   Generate the parameters; do not enumerate them.

P3  DECLINE-NOT-FILTER.  A forbidden request returns 403 with an empty body and
                   no Location header. A permitted request returns 2xx. There is
                   no third outcome -- in particular 200-with-empty-body is a
                   FAILURE, not a pass.  (run.py's trap, encoded as an invariant.)

P4  SCOPE IS TOTAL.  |scoped(actor)| + |excluded(actor)| == Review.objects.count()
                   for every actor, and the excluded set is exactly the
                   complement -- no row is dropped by a filter that is not a scope.
```

**P1 and P2 are the ones that generalise.** P2 in particular covers the untested
cross-track cell and the aggregate cell for free, over the generated space
rather than 25 cells. P4 is the one that catches a subtle bug class: a filter
that accidentally drops rows for a reason unrelated to authorization.

**Cost and honesty: ~2 hours, and it is the most persuasive thing we can put
behind the 25%.** "We tested 25 cells" is an assertion; "we proved the matrix
over the generated space and here is the falsifying-example search that found
nothing in 50 examples" is a *method*.

**Three implementation notes that will save us an hour each if we know them now:**

- **`hypothesis.extra.django.TestCase`, never `TransactionTestCase`.** The
  Hypothesis docs explicitly warn that `TransactionTestCase` is "significantly"
  slower in a loop. Keep this suite out of the hour-60 run.
- **Build small worlds with `st.just()` and `st.builds`, not `from_model()` on
  the big tables.** `from_model` cannot infer a strategy for an `AutoField`, a
  nullable field, or an FK, and generating 126-row fixtures is slow for no
  benefit — we want Hypothesis exploring *actor and query* combinations, not
  data volume.
- `@settings(max_examples=50, deadline=None)`. Bound it, and put it in the
  verification suite rather than the critical path.

**One thing we are deliberately not doing: a third enforcement layer.** See
`07` §2b.

**The permission layer, in the same spirit:**

| Actor | `view_review` | `change_review` | `view_results` | `export` | `admin` |
|---|---|---|---|---|---|
| visitor | ✗ | ✗ | published only | ✗ | ✗ |
| participant | ✗ | ✗ | published only | ✗ | ✗ |
| judge | own only | own only | **✗ until published** | ✗ | ✗ |
| organizer | all in event | ✗ | ✓ | ✓ | ✗ |
| admin | all | ✓ | ✓ | ✓ | ✓ |

The **judge/aggregate ✗** cell is the one nobody tests and everybody forgets.
`spec.md` and the site's FIG. 02 both mark it ✗. Judges do not see the
leaderboard while judging is open, because if they did, peer scores would be one
inference away.

---

## 7. Public layer

### `Vote`

`(event, project, voter_key, weight, created_at, ip_hash, user_agent_hash)`.
Unique on `(event, project, voter_key)`.

`voter_key` is the deduplication identity, resolved differently per voting mode:

| Mode | `voter_key` |
|---|---|
| `open_link` | hash of IP + UA + a signed cookie |
| `email_gated` | normalised email, after verification |
| `authenticated` | user id |

**Hashed identifiers, stored, never the raw IP.** We need to detect duplicate
voting without becoming a database of everyone's address. `ip_hash` is salted
per event so it is not reversible across events, and the salt is rotatable —
which is the whole reason the raw value is not kept.

`weight` defaults to 1 and supports quadratic voting (§`06` §6.1). Storing
`weight` rather than counting rows is what makes quadratic possible without a
schema change later.

### `Comment`

`(event, project, author, body, status, parent, created_at, moderated_by)`.
`status` ∈ `visible` / `pending` / `hidden`. `parent` for threading, nullable.

Bodies are rendered escaped, always, with no raw HTML. See `07` §4.

### `Ballot`

`(event, voter_key, seed, order, cast_at)`. `order` is the randomised
per-voter permutation of project IDs.

**Stable per voter, random across voters.** That is the entire point: it kills
position bias within a ballot while preventing a determined voter from
re-rolling the order by refreshing. The seed is stored so the same ballot can be
reconstructed for the audit trail.

---

## 8. Import and export — the escape hatch

> *"A migration path in and out, because a platform you cannot leave is a trap."*

This is filed under T4 but it is the sentence that gives it weight, and it is
the cheapest goodwill in the project.

**Export.** Seven named exports, satisfying "CSV export at every stage" and
giving an organizer everything they need to leave:

| Export | Contents |
|---|---|
| `registrations` | users, roles, memberships |
| `teams` | teams, members, invites |
| `submissions` | projects, custom answers, tags, submission timestamps |
| `assignments` | judge → project, method, batch |
| `scores_raw` | every score, un-normalized, with rubric version |
| `results_normalized` | raw, normalized, per-judge z, shrinkage factor, rank delta |
| `votes` | ballots and vote weights, `voter_key` only |

Every export starts with a comma-bearing header row — this is the T2-7
assertion, and it is a product convention rather than a checker
accommodation. All streamed.

**Import.** The same shapes, plus a documented JSON form of the full event
graph, and an importer for the published `fixtures.json` shape. The importer
validates and reports before committing: counts in, counts out, orphan
references, duplicates detected, near-duplicate submissions flagged. **A dry-run
mode that reports without writing** is the feature an organizer actually wants,
and it is thirty minutes.

#### 8a `source_key` — the rule that makes the round-trip property testable at all

> **Correction, and it is the difference between a test and a non-test.** An
> earlier draft stated the round-trip property as *"export → import → export is
> byte-identical **modulo generated IDs**."* **"Modulo generated IDs" is an
> escape hatch that quietly removes the property.** If IDs may differ, the
> assertion degrades to "the data is vaguely the same," and **it will pass while
> a column is silently dropped** — because a dropped column just makes the
> second export shorter, and nothing asserts the length.

**The fix is already in the schema and we had not drawn the consequence.** §2
gives `Event.id`, `Project.id` and friends as `CharField(32)` preserving fixture
IDs verbatim (`prj_07` stays `prj_07`), and `04` §6 requirement 5 makes that
explicit. So make it a **rule**:

> Every importable table carries **`source_key`** — the external natural key.
> The round-trip property is: *export → import → export is byte-identical
> **including every `source_key`**, with only surrogate integer primary keys
> permitted to differ, and the test asserts the exact set of differing primary
> keys against an allowlist.*

**Why this is worth 30 minutes and not 3 hours.** Retrofitting a column to nine
tables after the importer exists is expensive; adding it to the initial
migration is free. And with it, the property test actually catches the four
things that break real migrations: **dropped columns, reordered columns, coerced
dates, and normalised identifiers.**

#### 8b Three formats, three audiences, and the property test that proves it

| Format | For | Cost |
|---|---|---|
| **7 CSVs, header row first, streamed** | **The organizer in Excel.** Non-negotiable — it is what the brief asks for and what they will actually open. | already planned |
| **One canonical JSON document** (`export/event.json`, JCS-canonical, `schema_version` in the manifest) | **The round-trip property test.** JSON is a canonical form; **CSV is not** — quoting, line endings, BOM and trailing newline all vary. Asserting byte-identity on CSV is a trap. | 1h |
| **A signed archive** (`tar` of the above + `manifest.json` with per-file SHA-256 and an Ed25519 signature) | **Trust.** Turns "here is your data" into "here is your data, and here is proof nobody touched it." | 45 min |

**Not JSONL.** It is a fine interchange format but it has no place in a document
a human opens, and it is no more canonical than a JSON document. Its one real
advantage — streamability at enormous scale — is worthless at 41 projects.
**Not Parquet or Arrow:** columnar formats are for data that does not fit in
memory, and Parquet is not openable in Excel, which defeats the point.

**The property test that actually proves it, and it is Hypothesis again:**

```python
@given(world())
def test_round_trip_is_byte_identical(w):
    load(w); first = canonical_export()      # JCS bytes, source_keys included
    wipe(); import_from(first); second = canonical_export()
    assert second == first
    assert {r.pk for r in second} == ALLOWED_TO_DIFFER     # surrogate PKs only
```

`world()` composes `st.builds` over teams, memberships, projects (including the
supersede chain), assignments, reviews with scores, votes, ballots and audit
entries — **no fixed event, no fixed tracks, arbitrary n**, and at least one of
every awkward case: an `n=1` judge, the constant judge, empty comments, the
duplicate submission, a dual-track judge, a zero-comment review. **Hypothesis will
find the case we did not think of, and that is the entire argument for using it
here.** ~1.5h, and it is the single best answer we have to *"a platform you
cannot leave is a trap"* — because it converts a claim into a command anyone can
run.

#### 8c Schema evolution: a manifest that refuses rather than guesses

```json
{ "schema_version": 3,
  "generated_at": "2026-09-27T14:22:01Z",
  "files": { "submissions.csv": {"sha256": "...", "rows": 41}, ... },
  "compatible_with": [1, 2, 3],
  "signature": { "algorithm": "Ed25519", "keyid": "evt_01:org", "sig": "..." } }
```

Four rules, each one line of code, each preventing a real migration failure:

- **Refuse an unknown `schema_version`. Do not guess.** A wrong guess silently
  drops data; a refusal costs an afternoon.
- `compatible_with` is an explicit list, so a v1 archive is importable by a v3
  portal **because the v3 importer says so**, not because someone hoped.
- **Unknown *columns* in an incoming file are preserved in a passthrough table**,
  not dropped and not rejected. *This is the single highest-value importer
  behaviour and almost nobody does it:* an organizer's custom field survives a
  round trip through a portal that has never heard of it. That is the difference
  between "you cannot leave" and "we do not lose your data."
- **Unknown *rows* are quarantined with a reason and reported**, never silently
  discarded. Pairs with the dry-run-before-commit policy.

---

## 9. Audit, credentials, and the API surface

### `AuditEntry`

`(event, actor, action, object_type, object_id, before, after, ip_hash,
created_at)`.

Plus three columns for the chain: **`seq`** (monotonic per event),
**`prev_hash`**, **`entry_hash`**.

`before`/`after` are `JSONField` diffs, populated only for changes that matter:
role binding, score edit, rubric weight change, results publication, export,
import, denial.

**The design goal, taken from the spec's words: an audit trail an organizer can
read without a database client.** That means: a filterable HTML view first, a
plain-text export second, and raw JSON never the only interface. Denials are
logged too — a run of refused peer-score requests is exactly the signal a
security-minded organizer wants, and it is free here.

Append-only. No update or delete paths, enforced by a manager that raises.
**And hash-chained**, per `06` §5.2, which makes "append-only" a *verifiable*
claim rather than a promise.

**Two schema details that are load-bearing and cheap:**

- **`omitted_since_prev: int`.** Rate-limited denial sampling plus a hash chain
  is incoherent — a gap is indistinguishable from an edit. Putting the dropped
  count *inside* the chained entry turns the gap into a **provable, disclosed**
  fact instead of a tamper signal. See `06` §5.2.
- **`scope_reason` is stored on the access-denied entry**, from `05` §6a, so the
  audit trail records not just *who did what* but *what each actor was able to
  see*.

### `ResultPublication` — the content hash

```
results_hash = SHA256( JCS({
    "event":            event_id,
    "published_at":     iso8601(published_at),
    "rubric_version":   v,
    "input_digest":     SHA256( JCS(all raw score rows, sorted) ),
    "ranking": [ {project_id, team_id, raw_mean, normalized_mean,
                  n_reviews, rank, rank_delta, flags}, ... ],   # sorted by rank
}) )
```

Stored on the publication row, rendered on the results page, printed in the
README, and embedded in every signed judge record (§9b).

**Why it survives an untrusted database, which is the only attack that matters
here.** The organizer's own database is the thing we do not trust. But
`input_digest` is re-derivable from the raw scores by anyone holding the export,
and the `ranking` block is re-computable by anyone running the published method.
**So the hash is a claim and the export is the evidence.** An organizer who
alters a result and leaves the hash alone has produced a mismatch any third
party can detect with no access to our database. That upgrades `07` §3.1 J-10
from "Detected" to "Detectable by a third party," which is the difference
between a claim and a control.

`manage.py verify_results <published_at>` recomputes the hash from the current
raw scores and compares. Twenty lines. It doubles as the strongest possible
statement about the escape hatch, because the same command works on a
re-imported archive.

### `JudgeCredential`

`(event, judge, public_key, issued_at, revoked_at, signature, record_hash)`.
One Ed25519 keypair per judge per event, generated at first boot.

**Keys live on their own named Docker volume, not the database volume.** This
is a 15-minute decision that prevents a self-inflicted wound at hour 66: our own
`03` §6 verification checklist runs `docker compose down -v && up` twice, and if
the keys are on the database volume that wipes every previously issued record —
including ones quoted in the README and the demo video. On boot, if the database
is empty but a published record references a key that is absent, **print a loud
warning.**

**Ed25519** is RFC 8032 §3.1 (Edwards-curve DSA over Curve25519) — deterministic,
64-byte signatures, 32-byte keys, no parameter selection, no nonce management.
Available via `cryptography.hazmat.primitives.asymmetric.ed25519`, which is a
near-universal transitive dependency and adds nothing to the image. **Not a
Merkle accumulator** (that is for compact set-membership proofs with many
independent witnesses; we have one record per judge) and **not a keyed BLAKE3**
(that authenticates a stream you did not sign, and gives no third-party
verifiable identity — which is the entire requirement).

### 9b The participation record conforms to a published format

> **Change of direction, and it is an improvement in both cost and correctness.**
> The earlier draft said "a signature over the canonical form," which means we
> must get JSON canonicalisation exactly right *and* a third party must
> reimplement it identically. We should not be inventing a format when one
> exists.

**We emit an in-toto Statement v1 (`https://in-toto.io/Statement/v1`) inside a
DSSE envelope** (Dead Simple Signing Envelope, `in-toto/attestation`).

```json
{ "_type": "https://in-toto.io/Statement/v1",
  "subject": [ { "name": "evt_01/judge/jdg_08",
                 "digest": { "sha256": "<hash of the record body>" } } ],
  "predicateType": "https://dogfoodhack.com/attestation/judge-service/v1",
  "predicate": {
    "event": "evt_01", "judge": "jdg_08", "rubric_version": 1,
    "reviews_submitted": 3, "submission_digest": "sha256:...",
    "audit_seq_range": [301, 312],          ← §9c
    "audit_chain_head": "sha256:...",        ← §9c
    "results_hash": "sha256:..."             ← §9 above
} }
```

**Why DSSE and not "sign a canonical JSON blob":** the envelope spec is explicit
that an implementation **"SHOULD avoid depending on canonicalization for
security"** and **"SHOULD NOT require the verifier to parse the payload before
verifying."** The signature covers a **PAE (Pre-Authentication Encoding) of the
payload *bytes***, not a re-serialised object:

```
PAE = "DSSEv1 " + SP(len(payloadType)) + payloadType
    + SP(len(payload))     + payload
```

**In plain English: you sign bytes, so the verifier never has to agree with you
about key ordering, number formatting, or Unicode normalisation.** Switching to
DSSE eliminates an entire class of interoperability bug for about the same
amount of code, and it means anyone with `cosign` or an in-toto verifier can
check our records with tools that already exist.

**It exposes no scores**, and that is still the point: it lets a judge prove they
served and an organizer prove the panel was staffed, without publishing
anything confidential. Verification is a public endpoint plus a
`manage.py verify_record` subcommand that works **offline** against a downloaded
file — the Sigsum/Rekor tooling is unusable for us because it requires a network
and a witness quorum, both of which we are forbidden.

**Two implementation traps, both of which produce records that verify against
our own verifier and against nothing else:**

1. **`len()` in PAE is in BYTES, not characters.** Base64 output makes this safe
   for the payload, but the `payloadType` string is not base64.
2. **Test against one hardcoded vector from the spec.** One test, and it converts
   a silent interop failure into a red test.

### 9c The chain head goes into every signed record — and why, not a Merkle log

**The tempting thing to build, and why we do not build it.** A **Certificate
Transparency / Sigsum-style Merkle transparency log** looks exactly right here
and would be a mistake.

> **CT's value is *witnessing*.** A CT log exists so an independent party — a
> browser, a monitor, a witness — holds a copy and can detect *equivocation*,
> the log showing you two different trees. Sigsum's security model is a **quorum
> of witnesses** co-signing checkpoints; its documentation is explicit that your
> security "depended on two witnesses to verify that the log shows the same
> signed checksums to everyone."
>
> **We have no witness.** Our organizer runs the container. A Merkle root over
> our own log proves only *internal consistency* — which is precisely and only
> what the 30-line hash chain in `06` §5.2 already proves, for a third of the
> code. We would be implementing RFC 6962 to obtain a **strictly weaker**
> guarantee.

**What we do instead is strictly stronger, for one column:**

> **Publish the chain head once, at results publication, and replicate it into
> every judge's signed participation record.**

That converts *"the organizer's database says the log is intact"* into *"N
independently-signed documents, held by N people who are not the organizer, all
agree on a hash the log must produce."* To tamper, the organizer must either
forge Ed25519 signatures or produce two records that disagree — and any two
record holders can detect the latter with a five-line diff. **It survives the
database being untrusted, and it is cheaper and better than a Merkle tree.**

`audit_seq_range` is the field that makes the two T4 features reinforce each
other rather than sitting unrelated in a README: it says *your submissions are
audit entries 301–312 in a chain whose head at publication was X.*

**On deterministic key derivation** — deriving each keypair from a per-event
secret so a rebuild reproduces it — tempting, because it removes the `down -v`
problem. **Reject, and be honest about which guarantee we are buying:** a
deterministically derived key from a value stored in the same container is not
a secret, so it provides integrity against *accident* (a stray `rm`, a bad
volume) and **zero** integrity against *the host*. Worth having, if we say which
one we are getting. That sentence is worth more than the ten lines.

### API surface

Everything is a DRF viewset. **Design rule, and it is the whole of REQ-T4-01:
no UI action exists that is not also an API action.** No bespoke form-post
endpoints anywhere. If it mutates state it goes through a viewset, and the UI
calls the API.

That is why REQ-T4-01 is cheap on this stack and expensive elsewhere: it is an
architectural property rather than a second implementation. `drf-spectacular`
generates the OpenAPI document from the same source, so the published spec
cannot drift from the implementation.

### `WebhookEndpoint` and `WebhookDelivery`

**CUT at H+0 — the models ship, the delivery machinery does not.**

`(event, url, secret, events, active)` and `(endpoint, event_type, payload,
status, attempts, response_code, next_attempt_at)`.

**Why cut, stated in the threat model so nobody re-litigates it:** webhook
delivery is 2 hours, scores **zero points on all four criteria**, and the SSRF
mitigation (`07` §3.4 P-8 — scheme allowlist, DNS resolution checked against
private ranges before delivery, redirect limit) is a real bug class written from
scratch under time pressure. `01` §9 already filed it as "Nice."

**What ships:** both models, a stub view returning **501 Not Implemented**, and
`export run` / `import run` audit entries — so the schema is in the migrations
and whoever extends this has somewhere to put the code. **And `README.md` says
in one sentence that delivery, retries and HMAC signature verification are not
implemented.** The alternative — shipping a webhook endpoint that silently
fails to deliver — is the thing we are criticising everyone else for.

At-least-once with a visible log would have been the honest delivery semantic
anyway: we cannot guarantee delivery without infrastructure we are not allowed
to depend on, so we would have made the failure visible rather than pretending.
That reasoning survives the cut and belongs in the README.

---

## 10. Indexes

| Table | Index | Serves |
|---|---|---|
| `Review` | `(judge, project)` unique | T2-4, isolation |
| `Review` | `(event, judge, status)` | judge console, progress dashboard |
| `Review` | `(project, status)` | project score rollup |
| `Review` | `(event, submitted_at)` | audit and export |
| `Score` | `(review, criterion)` unique | score reads |
| `Score` | `(criterion, value)` | normalization passes |
| `Assignment` | `(event, judge, status)` | progress dashboard |
| `Assignment` | `(event, project)` | project coverage |
| `Project` | `(event, track, status)` | gallery filter |
| `Project` | `(event, team)` | team view, supersede chain |
| `Vote` | `(event, project, voter_key)` unique | dedup, tally |
| `Vote` | `(event, voter_key)` | per-voter limits, quadratic tally |
| `RoleBinding` | `(event, user, role)` unique-ish | **every authorization decision** |
| `AuditEntry` | `(event, created_at)` | audit view |
| `AuditEntry` | `(event, actor, action)` | per-actor history |

**The two that matter most are the `RoleBinding` lookup and the `Review` composite
indexes**, because they are on the hot path of the two things the brief cares
most about: authorization, and isolation.

Full-text search on `Project` uses SQLite FTS5, maintained by a signal on save,
with a `icontains` fallback so the same code works on Postgres.

---

## 11. Decisions and their costs

Every one of these is a thing a reviewer will ask about. Having the answer ready
is what "defensible in writing" means.

| Decision | Why | What it costs |
|---|---|---|
| Roles per event, not global | Track-scoped judges are the requirement; global roles cannot express it | Every query carries an event scope |
| Denormalized `judge`/`project` on `Review` | Isolation reads become index scans; the row is self-describing | Two sources of truth, held by a constraint and a test |
| `weight_applied` snapshotted | Weights must not change meaning under a completed review | Redundant column, must be written correctly |
| Versioned rubric | Judges on different rubrics are not comparable | One extra FK and a version picker |
| `supersedes` rather than dedupe | Lossless import; the duplicate is a real-world case | Result aggregation needs an explicit rule |
| No title uniqueness | Titles collide; a unique index on user input is a support incident | Callers must scope slugs themselves |
| `visitor` is not a row | Otherwise every anonymous request creates a user | One special case in role resolution |
| Service function for the deadline | The only form that cannot be bypassed by `bulk_create` or the admin | Every write path must call it; lint rule enforces |
| Review target is per-track, nullable | The fixture has two tracks where a target of 3 is *zero-slack* and infeasible at capacity 5 (`06` §2.1a); a single event-wide integer cannot express that | One fallback in the resolver; per-track progress denominators |
| **Two enforcement layers, not three** (`07` §2b) | Permission *decides* and raises; the queryset *constrains* and cannot raise. They fail independently and in opposite directions. A third layer must be derived from one of the first two, or it is a second source of truth | Two things to keep consistent instead of one — and the lint rule makes that consistency *syntactic*, hence mechanically checkable |
| **Scope receipt on the queryset** (`05` §6a) | Makes the scope self-explaining, so isolation is verifiable by a reader rather than by a test suite. One object, three consumers | One attribute and one template partial; a `ScopedQuerySet` type that must not be confused with a plain `QuerySet` |
| **`source_key` on every importable table** (`05` §8a) | Without it, "byte-identical modulo generated IDs" is not a testable property, and a dropped column passes | One nullable column × nine tables, plus an allowlist in the round-trip test |
| **Hash chain on `AuditEntry`** (`06` §5.2) | Makes append-only verifiable. A chain gives the same internal-consistency guarantee as a Merkle tree for a third of the code | Three columns; a verifier; `omitted_since_prev` to keep rate-limited sampling coherent with the chain |
| **No Merkle transparency log** (`05` §9c) | CT's value is witnessing and we have no witness; a root we compute ourselves proves only what the chain already proves | We give up inclusion proofs — correctly, because nobody could check them |
| **DSSE + in-toto Statement, not a bespoke signed blob** (`05` §9b) | Signs bytes, so no canonicalisation agreement with third parties; verifiable with tooling that already exists | A base64 envelope and a `payloadType` string, and the byte-vs-character `len()` trap |
| **Key volume separate from the DB volume** (`05` §9) | `docker compose down -v` is in our own hour-66 checklist; keys there would invalidate every issued record, including ones in the README | A second named volume and a boot warning |
| **`ResultPublication.results_hash`** (`05` §9) | Upgrades J-10 from "detected" to "detectable by a third party with no access to our database" | One column and a 20-line verify command |
| SQLite default | One command, offline, no second service | No `jsonb` operators; documented Postgres path |
| **No Postgres RLS, no Casbin/OPA** (`07` §2c) | RLS is Postgres-specific, needs `SET LOCAL` per transaction with real pool-leakage hazards, and views bypass it by default; a policy engine would make the rules *non-portable* and create a second source of truth — the opposite of our best architectural claim | We rely on the scoped-accessor layer, which expresses "judge on trk_04" as an index scan rather than a correlated subquery per row |
| Append-only audit | An audit log that can be edited is not an audit log | No "delete old entries"; a documented retention job instead |
| Everything is a viewset | Makes REQ-T4-01 structural and OpenAPI automatic | Slightly more ceremony in the HTML layer |

---

## 12. What we would redo

Written now, while it is cheap, because the Write Up Quest asks precisely for
this and because knowing the weak joint early is a design skill.

1. **The `status` string columns.** `Review.status`, `Project.status`,
   `Comment.status`, `results_state` are all ad-hoc string choices. A proper
   state machine with legal transitions — enforced, not documented — would have
   caught the draft-leaking-into-the-gallery class of bug at the database level
   instead of in a queryset filter.
2. **Custom questions as `JSONField` rather than tables.** Organizer-defined
   questions are part of the stable submission field set, and they deserve
   `Question` / `Answer` tables with types, required flags, ordering, and
   per-question validation. JSON is faster to build and worse to operate, and an
   organizer defining their tenth question will want a dropdown, not a text box.
3. **No soft-delete or `withdrawn_at` distinct from `status`.** Withdrawn,
   disqualified, and deleted are three different things and they have different
   consequences for results and certificates. One status enum conflates them.
4. **Not modelling rubric weights as a first-class revision.** `rubric` is
   versioned, but the weights live on `Criterion` rows rather than on an
   immutable versioned set. A version whose weights were edited after the fact
   is a contradiction. An immutable `RubricVersion` aggregate with copied
   criteria would have been right.
