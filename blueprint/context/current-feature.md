# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-02 — Schema and the isolation primitive

**Planned:** 5 hours · **Phase B** · **No gate of its own** (first gate is
BREAK-1)

### Scope

- [ ] 20 models, 12 apps; SQLite WAL; **Postgres-portable** — no SQLite-only types
- [ ] `source_key` on every importable table (D-11) — free now, 3 h if retrofitted
- [ ] `AuditEntry` chain columns: `seq` / `prev_hash` / `entry_hash` /
      `omitted_since_prev` (D-08)
- [ ] Indexes for the three hot paths: judge-on-track, judge-on-project, event gallery
- [ ] `Review.objects.for_actor(actor)` → scoped queryset **+ scope receipt** (D-01)
- [ ] `isolation_proof` management command skeleton, exiting 0 on pass
- [ ] The lint rule forbidding the unscoped `Review.objects.all()` form

### Acceptance

`manage.py isolation_proof` exits 0 on the empty DB; the lint rule fires on a
deliberately unscoped view and passes when scoped.

### Depends on

- **F-22** — the Hypothesis model strategies need `pytest-django` with a
  configured `DJANGO_SETTINGS_MODULE`. They now *can* run, because FEAT-01
  created the Django project — but the four invariants still need routes, so
  they land in FEAT-03, not here. The ordering in `bible/08` is unchanged.
- **F-40** (new, found at FEAT-01) — the `submit` route does not exist, so
  `run.py`'s "closed event refuses submissions" passes on a 404. Flip
  `tools/expected_checks.json` when the route lands, and the gate goes green on
  that check for the right reason. Do not treat the current PASS as evidence.

### Environment

Working and verified. `just doctor` is the one command that checks it.

| | |
|---|---|
| Interpreter | `.venv\Scripts\python.exe` → **3.13.13**. **Never a bare `python`** — the ambient one is 3.14.6 with no Django (F-38) |
| Docker | 29.6.2 / Compose v5.3.1, reachable by bare name *and* by absolute path |
| Container | `python:3.13-slim` pinned by digest; Python 3.13.15 |
| `just` | 1.58.0 |

### Not in this feature

The loader, the gallery, the deadline guard and the four Hypothesis invariants —
those are FEAT-03. Do not start them here; the primitive is only cheap to build
before any feature exists to leak.

### State

| | |
|---|---|
| **Status** | **ready** — FEAT-01 verified green |
| **Started** | — |
| **Elapsed** | 0h of 5h |
| **Last touched** | FEAT-01 verified; `just check` green end to end (`../history/features/01-skeleton-and-container.md`) |
| **Next action** | write the initial migration, all of it, while nothing depends on it |

---

## Next up

- **FEAT-03** Loader, identities, gallery, deadline guard, 4 Hypothesis
  invariants — 5h
- **BREAK-1** at H+14 — **☕ T1.** Hard gate. `just check` plus
  `just prove-offline` plus `just mutation-test`, against a clean volume.
