# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-03 — Loader, identities, gallery, deadline guard

**Planned:** 5h · **Phase C** · **Gate:** BREAK-1 (H+14), the T1 claim

### Scope

- [ ] Idempotent loader from `fixtures.json` — **run it twice, get the same
      database.** `docker compose up` is run many times against one volume and
      a loader that only works once makes the portal non-reproducible
- [ ] **5 test identities get real password hashes; the other ~116 get
      `UNUSABLE_PASSWORD`.** Hashing all 121 costs ~48 s against `run.py`'s 10 s
      timeout (F-12)
- [ ] Gallery, **first page in fixture order**, ~24 per page. `run.py` reads
      `fixture_titles(fixture, n=3)` → `projects[:3]` **positionally**, so the
      slice is a page slice, not a search (overview §6 trap 1)
- [ ] Deadline guard `assert_open_for_submission(event)` — a **service
      function**, called by every write path, because a `save()` override is
      bypassed by `bulk_create` and a view decorator by the admin
- [ ] The four Hypothesis isolation invariants P1–P4 (`bible/05` §6b.2) — they
      finally can run: F-22 is resolved, FEAT-01 created the project, and
      FEAT-02 created the models
- [ ] `verify_census` command — every census table prints its own row count on
      boot, and a count that disagrees with its stated population is a boot
      failure. `tools/run_in_container.py` already has an entry for it

### Acceptance

Gallery serves the first three fixture projects in fixture order; the loader is
idempotent; the four invariants pass; `verify_census` exits 0.

### Depends on

- **F-40** — "closed event refuses submissions" currently passes on a **404**.
  When `/projects/new` starts existing it passes for the *right* reason and
  `tools/expected_checks.json` goes stale, so `just check` **goes red**. That red
  is the design working. Flip the entry with a reason naming the route.
- **F-44** — the model count is 24, not 20, and
  `tests/test_schema_contract.py` reads the number out of `build-plan.md`. If
  the loader needs a new table, add it to the plan first or that test fails.
- The isolation primitive is **done**, so the loader has something to seed
  `RoleBinding` rows *for*. The 9 dual-track judges are two binding rows each —
  the model is the fixture's shape, not a special case.

### Environment

Working and verified. `just doctor` is the one command that checks it.

| | |
|---|---|
| Interpreter | `.venv\Scripts\python.exe` → **3.13.13**. **Never a bare `python`** — the ambient one is 3.14.6 with no Django (F-38) |
| Docker | 29.6.2 / Compose v5.3.1, reachable by bare name *and* by absolute path |
| Container | `python:3.13-slim` pinned by digest; Python 3.13.15 |
| `just` | 1.58.0 |

**One new local trap:** swapping `AUTH_USER_MODEL` (done in FEAT-02) makes a
**pre-existing local database** fail with `InconsistentMigrationHistory`, because
`accounts.0001` is a dependency of `admin.0001` and the old database has
`admin.0001` applied without it. `just reset-local` fixes it. The container is
unaffected because `just check` starts from a clean volume.

### Not in this feature

The judge console, the CSV export, the audit view and the denial properties.
Those are FEAT-04/FEAT-05, and **`isolation_proof` cannot print the published
matrix without the loader** — which is why FEAT-03 is where that proof becomes
real.

### State

| | |
|---|---|
| **Status** | **ready** — FEAT-02 verified green |
| **Started** | — |
| **Elapsed** | 0h of 5h |
| **Fresh session?** | **Paste `HANDOFF.md`** — it is a self-contained prompt (read-in order, verified state, the eight traps) and is 9,710 bytes, so it loads whole. Anything in it that contradicts a file it points at is a bug in `HANDOFF.md` |
| **Last touched** | FEAT-02 verified and pushed; `just check` green end to end, `prove-offline` 5.4 s, `mutation-test` 15/15, spec 67/67, 160 tests (`../history/features/02-schema-and-isolation.md`) |
| **Next action** | write `load_fixtures`, run it twice, and prove the second run changed nothing |

---

## Next up

- **FEAT-04** Rubric, assignment + min-cut, judge console, reviews — 7h
- **BREAK-1** at H+14 — **☕ T1.** Hard gate. `just check` plus
  `just prove-offline` plus `just mutation-test`, against a clean volume.
