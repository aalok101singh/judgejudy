# FEAT-02 — Schema and the isolation primitive

**Completed:** 2026-09-28 · **Planned:** 5h · **Actual:** ~5h · **Gate:** none
(first gate is BREAK-1 at H+14)

## What was built

- **12 apps, 24 models, 12 initial migrations** under `src/reviewer/`, each with
  a docstring naming the requirement or decision it serves. SQLite WAL,
  Postgres-portable, every table explicitly `db_table`'d.
- **`source_key` on all 24 tables** (D-11) — nullable and unique, in the initial
  migration because it is free now and 3 hours per table retrofitted.
- **`AuditEntry` chain columns** — `seq`, `prev_hash`, `entry_hash`,
  `omitted_since_prev` (D-08) — plus an `AuditQuerySet` whose `update()` and
  `delete()` **raise**, so append-only is a `TypeError` at the call site rather
  than a comment.
- **`Review.objects.for_actor(actor)`** with the **scope receipt**: the queryset
  carries a `Scope`, and `scope_receipt()` turns it into a `ScopeReason` with the
  rule, the constraints, the bindings and **visible-of-total** counts (D-01,
  `bible/05` §6a).
- **`reviewer/isolation/`** — `Actor` (frozen, resolved once per request),
  `Scope` / `ScopeReason`, `ScopedQuerySetMixin`. Three files, no model
  imports, so a reviewer can read the security model in one folder.
- **`manage.py isolation_proof`** — two modes, and it says which one it ran.
- **`tools/check_isolation.py`** — JJ01, the syntactic rule. Its own tests.
- **110 new tests** (49 → 160), plus `tests/factories.py` and
  `tests/ground_truth.py`.
- **`just prove-offline` and `just mutation-test` recipes** — which had been
  named in four documents and did not exist (F-47).
- **`DATA-MODEL.md`** rewritten from decisions to as-built, with the per-app table
  and the reasons two models are *not* in a place the reader would look for them.

## How it was verified

| | |
|---|---|
| Acceptance line (`build-plan.md`) | **pass** — `isolation_proof` exits 0 on the empty DB; JJ01 fires on a deliberately unscoped view and passes on the scoped one |
| Requirement IDs covered | none of the tier demands. `bible/05` §2–§9 in full; D-01, D-08, D-11 structural |
| Findings opened | F-43, F-44, F-45, F-46, F-47 |
| `just check` | **green** — 67/67 spec · clean build · container healthy · 2 of 7 as expected with the false pass reported · proof exits 0 · 160 tests |
| `just prove-offline` | **pass** — 5.8 s, 4 content-asserting probes, under `--network none` |
| `just mutation-test` | **15/15** |
| Lint | clean — `ruff check`, `ruff format --check`, JJ01 |
| Migrations | `makemigrations --check` clean |
| Container proof | exits 0 with 12 wiring checks, in the image, on a clean volume |

## The decisions, and the ones that changed

**The build order came from `bible/08`: write the migration while nothing depends
on it.** That is the whole argument for FEAT-02 preceding the features that leak.
`source_key` in particular is a schema decision that is free at H+4 and expensive
at H+50, and the reverse is also true of a *missing* `for_actor`: the primitive
is only cheap to build before there is a feature to leak through it.

**The decision that changed while building: the plan's model count was wrong, and
the fix was to make it un-typable rather than to correct it once.** `build-plan.md`
said 20, `DATA-MODEL.md` said 20 across 8 apps, `coding-standards.md` said "twenty
across eight", and `bible/05` names **24**. No gate covered any of them.
`tests/test_schema_contract.py` now **reads the number out of `build-plan.md` and
compares it to the Django app registry**, and separately out of `DATA-MODEL.md`.
It failed on the first run, which is the evidence that it is real (F-44).

**The second decision: `User` has no `PermissionsMixin`, and the cost is stated
rather than hidden.** Django's permission framework is global and cannot express
"a judge on `trk_03` and a judge on `trk_07` are the same person with different
authority" — which is precisely the cross-track leak the spec forbids. Ours lives
in `RoleBinding`. The consequence is that `has_perm` returns `False` and
`/admin/` shows an empty app list. That is the correct behaviour for this design —
the admin is not our security surface and must not be mistaken for one — and
Django's own `check_user_model` was **executed**, not recalled, before relying on
it.

**The third decision, and the one the reviewer will actually read: the scope
receipt's denominator is computed from the event, not from the queryset.** A
receipt saying "3 of 126" is only evidence if 126 was defined independently of
the filter that produced 3. `scope_total_count()` reads the event id out of the
`Scope` and re-queries, and `tests/ground_truth.py` is the one test module allowed
to hold an unscoped handle — so there is exactly one place the independent number
can come from.

**The fourth decision: the lint rule is a separate program, not a ruff plugin.**
Ruff's plugin API is Rust. `banned-api` in `pyproject.toml` would have to ban an
exact dotted path, which means it can ban `Review.objects.all` and silently allow
`Review.objects.filter` — the same leak by another name. JJ01 walks the AST and
holds the model name and the method name together.

**The fifth, which was an accident worth having: the rule fired on our own
command on its first run.** `isolation_proof` reads every review, three times,
because its job is to publish a matrix. Rather than rewrite it to dodge the rule
— which is always the wrong repair — it went on the allowlist with a reason, next
to the accessor itself. The allowlist is five named entries, every one with a
sentence, capped at five, and a test fails if an entry loses its reason, grows,
or points at a file that no longer exists.

## The two bugs this feature found in itself

Both are in the findings ledger with the full narrative, and both are worth
remembering for a reason that is not "we made a mistake".

**F-45 (P1): the matrix could populate its "judge" row with an organizer.** A user
can hold two roles — a judge who is also a participant is ordinary, not a
misconfiguration — and the table labelled each row by the actor's *strongest*
role. So it printed a `participant` row **showing a review visible to a
participant**, in the published matrix, in the file whose whole job is to be the
evidence a judge checks the portal against. Nobody reading that table could tell
it was wrong, because the layout is exactly what a correct one looks like. This
is F-40 turned on ourselves: a check reporting a verdict without exercising the
thing it names.

**F-46 (P2): running `ruff format` across the tree broke two of the fifteen
mutation targets.** They are exact source strings, and the formatter rewrote both.
The harness reported them as `[pattern not found]` — in the same list, with the
same words, as "these gates pass while broken". A gate that cannot find its own
mutation and a gate that survives one are indistinguishable from the output, and
we were one command away from publishing a green 13/15.

## What was cut or deferred

Nothing was cut from the stated scope. Three things are *recorded as not done*,
and each is a decision rather than an omission:

1. **`Assignment` and `Score` are not in the lint rule's guarded set.** A
   `Score.objects.all()` in a view leaks every score in the event — the same
   failure one hop over. They are absent because **they have no scoped accessor
   yet**, and adding them to the rule first would ban every call with no
   alternative. The order is: write `for_actor` on both, then add them, in the
   same commit. That note is in `tools/check_isolation.py` beside
   `GUARDED_MODELS`.
2. **The `AuditEntry` chain writer and verifier.** The columns and the
   append-only manager ship; computing `prev_hash` / `entry_hash` is FEAT-05,
   because the sampling rate is part of the writer's design and guessing it now
   would produce a chain to rewrite.
3. **`ResultPublication.results_hash` is not computed.** The schema for it ships,
   including the rationale that the hash is a claim and the export is the
   evidence. The canonical document is FEAT-08's, which owns the ranking shape.

One thing was **added** and it should be flagged as possible overreach: the scope
receipt's `extras` mechanism, the `where_fields` tree walk, and the
role-strength rule in the proof. Together maybe forty minutes. The argument is
that each exists because a cheaper version produced a *number that looked right*
(F-45), which is the one outcome this project's evidence cannot afford. The
argument against is that FEAT-02 is not the milestone that scores. **Recorded so
the next session can disagree with it.**

## What the next session should know

1. **`for_actor` is a QUERYSET method on `Review` and the rule is syntactic.** If
   you need to scope something else, write the accessor **and** add the model to
   `GUARDED_MODELS` in the same commit. `just lint` runs the rule; `just
   lint-isolation` runs it alone, which is cheap enough to run on save.

2. **Two false passes are still expected, and one of them is the interesting
   one.** "closed event refuses submissions" still passes on a 404 (F-40), and
   `just check` passes it with `--allow-false-passes`. When FEAT-03 adds
   `/projects/new`, **the gate will go red** because the expectation is stale.
   That red is the design working. Flip the entry in
   `tools/expected_checks.json` with a reason that names the route.

3. **`isolation_proof` has two modes and only one of them is a matrix.** On the
   empty database it runs 12 wiring checks against in-memory actors — which is
   why it can prove the primitive before any feature exists to leak — and it
   prints `mode: WIRING ONLY` plus the list of what it has *not* proven. If you
   ever see it print a matrix on an empty database, that is a bug, and it is the
   F-40 shape. `--require-data` turns an empty database into a hard failure, and
   a verification break should use it.

4. **Every matrix cell is a count or a `?`.** Never a zero standing in for
   "unverified" — a zero reads as *verified, and the answer is none*. Three of
   the six columns are `?` until FEAT-04/FEAT-05, and the command prints the
   provenance of each one under the table.

5. **A role may not be borrowed for a weaker row.** `ROLE_STRENGTH` in the
   command exists because of F-45. If your fixture or seed gives every judge an
   organizer binding, the judge row will **refuse** rather than print an
   organizer's numbers — and that refusal is correct.

6. **`ruff format` can break `tools/mutation_test.py`.** Its targets are exact
   source strings. If you reformat anything, run `just mutation-test` afterwards
   and believe `[pattern not found]` as a **harness defect** (F-46), not as a
   surviving mutation.

7. **Swapping `AUTH_USER_MODEL` breaks a pre-existing local database** with
   `InconsistentMigrationHistory`. `just reset-local`. The container is
   unaffected.

8. **`tools/verify_spec.py` did not get the model-count check, deliberately.**
   It is stdlib-only and must run before the application exists, and the number it
   would need to compare against is only knowable from a live app registry — which
   is the `test` layer's job, not the spec gate's. Two gates for two different
   questions, and `verify_spec.py` stayed at **67 checks** rather than growing a
   check that would have been a regex over model files.
