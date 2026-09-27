# Coding Standards

> **Machine-enforceable first.** A rule that cannot be checked by a tool is a
> preference. A rule that can be checked belongs in `pyproject.toml` or the lint
> hook, and is marked ⚙ below.

---

## 1. The rules that exist to protect the score

These three are not style. Breaking any of them costs points, not elegance.

**1.1 — Isolation is non-negotiable.** ⚙

A view or serializer must never reach a queryset without an actor. The only
sanctioned forms are `Review.objects.for_actor(actor)` and the other accessors in
`reviewer/`. The unscoped form is a lint error, not a convention.

This is the one rule worth a lint hook, because it is *syntactic* — mechanically
checkable — and because the spec says hiding another judge's scores in a template
is not refusing. A reviewer should be able to see that the rule is enforced by
the build, not by our discipline.

**1.2 — A denial is a 403 with an empty body.** Never a 302, never a redirect to
a login page, never an empty 200. `run.py` follows redirects, so a redirect
returns 200 and fails T2-5 while looking correct in a browser.

**1.3 — No number is transcribed.** Every figure in a document, a comment, a
commit message or a test name is produced by code. Six of our first twelve
findings were hand-typed census errors, and two were found *after* we published
a correction log about the first four — which is worse, because it teaches the
reader to distrust the writer rather than the number.

⚙ **This one is enforced.** `python tools/verify_spec.py` re-derives every
load-bearing number in the spec layer from `fixtures.json` and `run.py`, and
exits non-zero on disagreement. It is stdlib-only and runs before the venv and
Docker exist. If you change a number in `project-overview.md`, `build-plan.md` or
`AGENTS.md`, run it before you believe the change.

## 2. Tooling

⚙ Everything in this section is enforced by `pyproject.toml`, the lint hook, or
`just`.

| Tool | Scope | Notes |
|---|---|---|
| **ruff** `0.16.9` | lint + format | Config lives in `pyproject.toml`, not a separate file |
| **pytest** `9.1.1` | tests | `pytest-django` supplies `db` and the model strategies |
| **hypothesis** `6.168.2` | the isolation invariants and the assignment proof | Strategy-based, not example-based, wherever the input space is small |
| **gunicorn** `26.2.0` | the container | Marked `sys_platform != "win32"` — do not "fix" that marker (F-15) |

**Default ruff ruleset:** `E`, `F`, `I`, `N`, `UP`, `B`, `C4`, `DJ`, `S`, `RUF`,
plus the project-specific isolation rule. `DJ` and `S` are the ones that earn
their place: `DJ` catches the model-argument mistakes Django 5 deprecated, and
`S` catches the hardcoded-secret and shell-injection classes that a security
reviewer will look for first.

**Line length 100.** Docstrings on every module, class and public function,
written for the next person who is also an AI assistant and has no context.

## 3. Layout

```
judge_judy/          settings, urls, wsgi
reviewer/            accounts, events, tracks, projects, reviews, ballots, comments
reviewer/isolation/  the accessors, the receipts, the lint rule
reviewer/audit/      hash chain, chain head, signing
reviewer/crypto/     Ed25519, in-toto Statement v1, DSSE
reviewer/normalization/  the estimator and the proof
reviewer/io/         export/import, source_key
manage.py            Django
run.py               the panel's program, unmodified
```

**Apps are named for the domain, not the layer.** `reviewer.reviews`, not
`reviewer.models`. Sixteen models in one app is a smell; we have twenty across
eight, which is the right size for this scope.

**`reviewer/isolation/` is the architectural centre.** It is the one claim we
make, so it gets its own module rather than being scattered through
`views.py`. A reviewer can read that one folder and understand the security
model.

## 4. Models

- **Postgres-portable or not at all.** No SQLite-only types, no
  `JSONField`-index assumptions, no `AUTOINCREMENT` games. We develop on SQLite
  because the brief requires it, and the schema has to survive a port.
  ⚙ `DJ` and the `migrations` check in `just`.
- **`CheckConstraint`s over application validation** for anything a row could
  violate — a length or a range that must never exist, even transiently.
- **`UniqueConstraint`s declared explicitly**, including composite ones, rather
  than relying on implicit single-column uniqueness.
- **`source_key` on every importable table.** Round-trip must be byte-identical
  *including natural keys*. `bible/05` §6.
- **No migration without a stated purpose.** If a migration exists, its docstring
  says which requirement or finding it serves. An unexplained migration is a
  finding waiting to happen.
- **Never edit an applied migration.** Add a new one.

## 5. Views and serializers

- **Views hold no data rules.** They resolve the actor, call an accessor, and
  serialize. Any `if` in a view about *what a user may see* belongs in the
  accessor or the permission.
- **A permission decides; a queryset constrains.** A permission raises. A
  queryset cannot. Do not put authorization logic in a queryset's `filter()` as
  the only gate — that is the layer that fails open.
- **Serializers are for the wire, not the database.** A serializer may be
  read-only, may nest one level, and may not reach for a related object that
  crosses a scope boundary. That would re-open 1.1 through the serializer layer.
- **Viewsets for collections, generics for the rest.** We have 12 models; a
  ViewSet that hides an action is a ViewSet we cannot reason about in a hurry.

## 6. Errors

| Case | Response |
|---|---|
| Unauthorized / forbidden | **403, empty body, no `Location`** |
| Not found, or scoped out | 404 — never 403, because a 403 confirms the object exists |
| Validation failure | 400 with a field-keyed body |
| Deadline passed | 409 with `submissions_close` in the body |

A 403 that distinguishes "exists but not yours" from "does not exist" is an
enumeration oracle. The accessor raises `NotFound` in both cases.

## 7. Testing

- **Test the requirement ID, not the function name.** `@pytest.mark.req("T2-4")`.
  A test that cannot be traced to a demand is either redundant or untraceable.
- **A fresh database per test.** No shared state, no ordering dependency, no
  `--reuse-db` in CI.
- **The four isolation invariants are property-based**, not examples, because
  the failure mode is "some combination we did not think of."
- **A denial test asserts all three properties**: the status, an empty body, and
  the absence of a `Location` header.
- **The proof's published numbers are asserted.** Held-out RMSE, recovery RMSE,
  the sensitivity curves. A refactor that silently changes the method must fail
  a test rather than quietly weaken a document.
- **A migration test runs the whole thing forward on a copy.** The adoption
  promise is worth a test.

## 8. Comments and commits

**Comments explain why, never what.** A comment restating the line below it is
noise. A comment explaining why an apparently silly line exists is the most
valuable thing in the file — that is where our findings belong, in the code, so
the next person cannot re-derive the mistake.

**Commit messages say what a reader needs to know, not what the diff says.** The
Write Up Quest is built on "the numbers we got wrong and the design you
abandoned", so the history has to carry that. Conventional Commits prefixes,
present tense, and the requirement or finding ID in the body when there is one.

**No comment written for a human reviewer of the panel.** There is one reviewer
per PR, and it is us at hour 60. Write for the judge.

## 9. What "done" means

A feature is done when:

1. Its verification line in `build-plan.md` passes on a **clean** database.
2. `just check` is green.
3. The lint and format checks pass. ⚙
4. The findings ledger is updated if anything surprising was found — **especially
   if it was found and not fixed.** An unrecorded fix is indistinguishable from
   a missing fix.
5. The current-feature file is updated so the next session starts in the right
   place.
