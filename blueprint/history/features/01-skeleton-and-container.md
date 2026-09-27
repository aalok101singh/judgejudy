# FEAT-01 — Skeleton and container

**Completed:** 2026-09-28 · **Planned:** 4h · **Actual:** ~4h · **Gate:** none
(first gate is BREAK-1 at H+14)

## What was built

- **`Dockerfile`** — `python:3.13-slim` pinned **by digest** (`sha256:7c61056e…`),
  non-root `uid 10001`, gunicorn 2×2, whitenoise, runtime deps only. No
  compiler, no dev dependencies, no keys.
- **`docker-compose.yml`** — one service, one named volume, one healthcheck,
  no required environment variables, works with the network off.
- **`docker/entrypoint.sh`** — `migrate → collectstatic → seed → THEN bind`.
  The ordering is the contract with the checker's 10-second timeout.
- **`docker/healthcheck.py`** — the single definition of "healthy", called by
  the Dockerfile `HEALTHCHECK`, the compose healthcheck, and the offline proof.
- **Django project** under `src/` — settings, urls, wsgi, `/`, `/healthz`,
  `/admin/`, one stylesheet, one template. No models, no schema.
- **The gate** — `justfile` (18 recipes), `tools/verify_spec.py` (67 checks,
  pre-existing), `tools/run_acceptance.py` (the ratchet),
  `tools/expected_checks.json`, `tools/coldstart.py`,
  `tools/prove_offline.py`, `tools/doctor.py`, `tools/docker.py`,
  `tools/guard_interpreter.py`, `tools/run_in_container.py`,
  `tools/mutation_test.py`.
- **49 tests** across `tests/`, including the gate's own tests.
- **Documents** — `README.md`, `ARCHITECTURE.md`, `DATA-MODEL.md`,
  `JUDGING.md`, `LICENSE`, `pyproject.toml`, `.gitignore`, `.dockerignore`,
  `.dogfood.toml`, generated `acceptance-report.txt`.

## How it was built

**The build order came from `bible/08` §2: start the image build first, and
write documents while it runs.** It was 90 seconds because the base image was
already pulled (F-36), which is exactly the hour it was pre-pulled to save.

**The decision that changed while building: the acceptance gate had to become a
ratchet, not a switch.** The plan said `just check` should be "wired up, even
though most steps no-op until later features". But `run.py`'s seven checks
include four that need a judge console and a CSV export, which do not exist
until FEAT-05. So "any FAIL is fatal" would be red from the first commit — and
**a gate that is always red is a gate nobody reads**, which is the same reason
a healthcheck that cries wolf is worse than no healthcheck.

`tools/expected_checks.json` records, per check, whether it is *expected* to
pass yet, with the reason and the feature that flips it. The gate then fails
in **both** directions: an expected-pass that fails is a regression, and an
expected-fail that passes means the expectations file is stale. The file only
moves from `fail` to `pass`, and only when the feature that owns the check is
done — which makes it a ratchet rather than a wish list.

**The second decision, and it is the more interesting one: two of the seven
checks pass for the wrong reason, and the gate now refuses to count them.**

`run.py` accepts any 4xx for "closed event refuses submissions", and a **404 is
a 4xx**. So with `/projects/new` absent, the check reports PASS while the
deadline guard is never tested. The same applies to the two isolation checks,
where a 404 satisfies the expected 401/403.

This is F-11 turned on ourselves: *a check reporting PASS without exercising
the behaviour it names is worse than one reporting FAIL, because it is
believed.* So the gate probes the portal and reports a **FALSE PASS** with the
route and the status code that answered:

```
submit (/projects/new) answered HTTP 404, so this PASS is not testing
the behaviour it names — A 404 is a 4xx, so this check passes while the
route is absent. The deadline guard is not being tested at all.
Isolation enforced by absence is not isolation.
```

`just check` passes `--allow-false-passes` so the gate stays usable before
FEAT-03, and that flag is asserted **not** to rescue a regression or an
overclaim — it downgrades exactly one finding.

**The third decision: a repository path with a space is a portability test
nobody schedules.** The directory is `Judge Judy`, and cmd.exe parses an
unquoted path as the command plus an argument. That cost three iterations of
real bugs before it was pushed into a script:

- a `python -c "..."` inside `cmd /c`, which cmd's quote handling mangles
- a PowerShell `-f` format string fighting just's `{{` interpolation
- `cmd /c "…python.exe" … || echo fallback`, where the `||` mangles the quoted
  left-hand side

The fix was not more quoting. It was moving the logic into Python, which is
where the rest of this project's decisions already live. `tools/docker.py` and
`tools/run_in_container.py` exist partly because of that.

**The fourth decision: measure the number, do not type it.** The 60-second
acceptance criterion is a number that ends up in the README, so
`tools/coldstart.py` measures it and prints it in copy-pasteable form. The
Dockerfile's `HEALTHCHECK --start-period` was `10s` in the first draft — below
the real cold start, so the container would report itself unhealthy during
normal operation on a slow machine and healthy on a fast one. It is now `45s`,
matching compose, and both are asserted by a test.

## How it was verified

```bash
just check
```

| | |
|---|---|
| Acceptance line from `build-plan.md` | **pass** |
| Requirement IDs covered | none of the tier demands; required deliverables 1–5 partially |
| Findings opened | F-39, F-40, F-41, F-42 |
| Findings closed | F-14 (git repo), F-38 (interpreter pinned) |
| Cold start, clean volume | **6.2–6.7 s** against a 60 s budget |
| Boots with `--network none` | **proved** — 4.0 s, 4 content-asserting probes |
| Spec gate | **67/67** |
| Suite | **49 passed** |
| Lint | clean |
| Mutation test | **15/15 corruptions caught** |
| Acceptance report | 2 of 7 pass, 5 fail as expected; `claimed: nothing` |

The acceptance report is **generated** and committed with its failures:

```
T1  gallery is public ................. PASS
T1  project from fixtures shown ....... FAIL
T1  closed event refuses submissions .. PASS     <- false pass, see F-40
T2  judge sees own scores ............. FAIL
T2  judge cannot see peer scores ...... FAIL
T2  participant blocked ............... FAIL
T2  csv export works .................. FAIL

claimed nothing, verified nothing
```

`claimed = []` is the honest entry. The container, the healthcheck and the
offline guarantee are real; the gallery, the deadline guard and the judge
surface are not built, so **no tier is complete** and claiming T1 would mean
claiming a gallery that does not exist.

## What was cut or deferred

Nothing was cut. Nothing in FEAT-01's scope was skipped. Deferred to later
features, as planned: the loader and the gallery (FEAT-03), the isolation
primitive and the schema (FEAT-02), the docs that describe them.

One item was **added** rather than cut, and it is worth flagging as a possible
overreach: the false-pass mechanism and the mutation harness together are
roughly an hour of the four. The argument for them is that both would be
written anyway at BREAK-1 under time pressure, and that a gate nobody trusts
is a worse outcome than a smaller FEAT-01. The argument against is that
FEAT-01 is not the milestone that scores anything. **Recorded so the next
session can disagree with it.**

## What the next session should know

1. **`just check` is the gate and it is green. Run it before you believe
   anything.** Then `just prove-offline` and `just mutation-test` — the three
   together are the FEAT-01 proof, and the last two are not in `check` because
   they need a clean volume.

2. **The trap in this feature is a check that passes for the wrong reason.**
   `/projects/new` does not exist, so T1-3 passes on a 404. When FEAT-03 adds
   the route, flip `tools/expected_checks.json` for that check — the gate will
   go **red** when it starts passing for the right reason, because a stale
   expectation is a finding. That red is the design working.

3. **`run.py` is unmodified and must stay that way.** The panel runs the
   identical program. `tests/test_gates.py` asserts its `return 0` and its
   hashability; a byte change invalidates every line of
   `acceptance-report.txt`.

4. **Three Pythons and two `docker` binaries, all handled in code rather than
   in a README.** `tools/doctor.py` prints which of each it found and how.
   `just doctor` is the first thing to run when a gate fails for a reason that
   does not make sense — and *that* is the F-34 lesson: a failing command is
   evidence that a command failed, not evidence about why.

5. **`tools/expected_checks.json` is the thing most likely to be got wrong by
   someone in a hurry.** It is a claim about the build, and a wrong claim makes
   the gate lie. Every entry has a `reason` and a `flips_at`, and
   `TestExpectationsFile` asserts both are present — so the failure mode of
   "just flip it to green" is a failing test.
