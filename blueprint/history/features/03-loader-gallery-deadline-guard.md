# FEAT-03 — Loader, identities, gallery, deadline guard

**Completed:** 2026-09-28 · **Planned:** 5h · **Actual:** ~6h · **Gate:** none
(first gate is BREAK-1 at H+14)

## What was built

- **`reviewer/importer/`** — a package, not an app, for the same reason
  `reviewer/isolation` is one: it defines no model, so `INSTALLED_APPS` would add
  a `models` module that does not exist and a migration that creates nothing.
  Three modules: `census.py` (re-derives the fixture and checks it),
  `demo.py` (the five identities the checker authenticates as, **derived**),
  `loader.py` (the importer).
- **`manage.py load_fixtures`** — idempotent, one transaction, and it prints the
  census, the two invariants, six named anomalies and the **paste-ready
  `[auth]` block last**. `docker/entrypoint.sh` already called it conditionally
  and now just runs it.
- **`manage.py verify_census`** — 14 tables, each with a derived expectation,
  plus the two invariants recomputed from `GROUP BY` over the *stored* tables,
  plus three orphan checks. Exits non-zero on a disagreement.
- **`reviewer/events/deadlines.py`** — `assert_open_for_submission(event)`, the
  service function every write path calls, and `SubmissionClosed` whose body
  **names the guard**.
- **`reviewer/projects/views.py`** — the gallery at `/` and the submit route at
  `/projects/new`, with a **conditional** CSRF exemption.
- **`reviewer/accounts/demo_tokens.py` + `authentication.py`** — the role-proving
  bearer token, one pure module and one Django auth backend behind a middleware.
- **Four new test modules** — `test_loader.py` (49), `test_denial_contract.py`
  (27), `test_gallery.py` (22), `test_isolation_invariants.py` (9, the Hypothesis
  invariants P1–P4), `test_demo_credentials.py` (23), `tests/fake_http.py`.
- **A new kind of precondition in the acceptance gate** — see below, which is the
  part of this feature I would argue is worth the most.

## How it was verified

| | |
|---|---|
| Acceptance line (`build-plan.md`) | **pass** — all three T1 checks PASS, loader idempotent, four invariants green, `verify_census` clean |
| Requirement IDs covered | **T1-1, T1-2, T1-3** — the first tier demands to have any green behind them |
| Findings opened | F-48, F-49, F-50, F-51, F-52, F-53, F-54, F-55 (three P1) |
| `just check` | **green** — `GATE OK: no regressions, no stale expectations, no false passes` |
| `just prove-offline` | **pass** — healthy at 8.0 s under `--network none` |
| `just mutation-test` | **18/18** (15 → 18; three new mutations, all on the deadline guard) |
| `tools/verify_spec.py` | **67/67** — and it caught two stale numbers in our own documents on the way |
| Lint | clean — `ruff check`, `ruff format --check`, JJ01 in 105 files |
| Migrations | `makemigrations --check` clean; one new migration (`teams/0002`) |
| Suite | **291** (160 → 291) |
| Cold start | **11.6 s** to a serving page, budget 60 s (was 6.2 s; the seed costs 1.9 s of it) |

## The decision that mattered most: the gate can now tell a refusal from a refusal

`run.py` accepts **any 4xx** for "closed event refuses submissions". So before
this feature, a 404, a 405, a CSRF rejection and a 401 for an unrecognised
credential all reported **PASS** with the deadline never consulted. F-40 said
so; the precondition table made it visible; and FEAT-03 made it *unnecessary*.

**The gate now re-sends the checker's own request and asserts on the body.** The
precondition carries a `probe` — same method, same JSON, and **the same
`[auth]` value read out of the same `.dogfood.toml` the checker read** — and
requires `assert_open_for_submission` in the response. A CSRF rejection, a 404, a
401 and an emptied `[auth]` block all fail it now, and each of those four is a
test:

```
test_a_csrf_refusal_is_caught        test_a_404_is_caught
test_a_401_is_caught                 test_a_redirect_header_is_caught
test_an_emptied_auth_block_is_caught_before_a_request_is_sent
```

The emptied-credential case is the one I would point a panelist at, because it is
the failure that is invisible from inside the portal: someone tidies up
`.dogfood.toml`, the header goes with it, the request arrives anonymous, and
**every 4xx still counts**. The probe now reports that as a *false pass* with
the reason — "the probe cannot present the credential the checker used … none of
them is the deadline" — and fails.

**The cost, stated rather than hidden:** a probe is only as good as its marker,
and ours is the guard's own function name, which the view puts in `refused_by`. A
view that refused everything with that body would pass. That is why
`tests/test_denial_contract.py::test_the_same_form_post_is_refused_only_by_the_clock`
sends the **identical** form post with the window open (201, a project created)
and closed (403, naming the guard). The marker is only meaningful because
something else is possible.

**And the escape hatch is gone.** `just check` no longer passes
`--allow-false-passes`. The flag still exists and is still tested, because FEAT-05
brings back the same class of problem for the judge-scores routes — but a gate
that no longer needs a hatch is worth more than one that has learned not to open
it.

## The decisions that changed while building

**1. Five identities are *derived*, three of them promoted from the fixture's 121.**
The census is exactly 121 people, and the acceptance panel can check that against
`fixtures.json` without running anything — so six synthetic accounts would have
quietly changed a checkable number to 127. Three are promoted instead. The other
two are ours, because **nobody in `fixtures.json` is an organizer**, and
promoting a team member would make an organizer a competitor in the event they
administer. The census reports the two populations separately so they are never
added together.

**2. The organizer is not `is_staff`, and that is F-45's refusal arriving early.**
`bible/04` §5.2 suggests "organizer + admin" as one identity. `Actor.label`
returns the *strongest* role, and the isolation proof's organizer row refuses to
be populated by an actor whose strongest role is `admin` — so seeding them as one
user empties a row of the published matrix. The seed splits them, and a test
asserts the organizer is not staff.

**3. `Event.starts_at` is derived and `submissions_open` is left NULL.** The
schema requires a start and the fixture does not supply one, so it is
`min(project.submitted_at)` — computed, not typed. The opening gate stays `NULL`,
which the guard reads as "no opening gate": the operator configured a close, so
the window is open until it.

**4. The CSRF exemption is narrow, and it took three attempts to get right.** The
view is `@csrf_exempt` and re-enters Django's own `CsrfViewMiddleware` for
anything a cross-origin form could have sent. The first two versions were wrong
in ways that all failed *silently*:

| | what was wrong | why nothing caught it |
|---|---|---|
| v1 | wrapped the view in the middleware and returned its result | `MiddlewareMixin.__call__` only runs `process_request`/`process_response`; the check is in `process_view`, which the handler calls. **Nothing was checked.** |
| v2 | applied the wrapper to the exempt `new_project` instead of `_new_project` | the view called itself; every form post died with a `RecursionError` about 1000 frames deep |
| v3 | — | works |

and then a fourth thing, found by running it: **Django's test `Client` sets
`_dont_enforce_csrf_checks`**, and `process_view` honours it by accepting early —
so a test that does not pass `enforce_csrf_checks=True` observes *no CSRF
behaviour at all*, and a broken wrapper looks like a working one. Every client in
`test_denial_contract.py` passes the flag, and the module docstring says why
before the first test does.

The exemption is now asserted **from both directions**: a JSON POST reaches the
guard, and a form-encoded POST is refused by CSRF with Django's own failure text.

**5. The demo credential is signed with a *published* key, on purpose.** The
obvious choice is `SECRET_KEY`, and it is the wrong one: the key is generated per
instance volume, so `down -v` rotates it, the committed `.dogfood.toml` goes
stale, and the participant probe silently becomes an anonymous request. That is
F-40 arriving through a different door. So the key is a constant in the
repository, overridable with `DJUDGE_DEMO_TOKEN_KEY`, and the module docstring
leads with the consequence: **anyone holding this repository can mint a token for
any of the 121 fixture identities.** The organizers' own example uses a guessable
fixed session value, so this is the same posture applied to a single-tenant
portal whose entire dataset is a public fixture. The README says so in the same
words.

**6. `public_review_counts` is sanctioned in the lint rule rather than allowlisted.**
The gallery needs per-project review counts, `Review.objects.filter(...)` in a
view is JJ01's forbidden form, and the honest options were "write a scoped
accessor" (there is no actor — this is a public page) or "allowlist the file"
(which exempts a whole file from the rule). The third is better: one **method** is
sanctioned in every file, so the rule keeps applying to the rest of the line. It
returns `{project_id: n}` and cannot return a row, and
`test_the_public_count_accessor_returns_no_rows` asserts its shape rather than
its name, because renaming it to something neutral is a security-relevant change
the rule would *not* notice.

**7. The allowlist cap moved from 5 to 6, and the reason is on the entry.**
`verify_census` needs to count the event; there is no actor, and a command that
asked "as whom?" could not check that the loader imported the right rows, which
is the one thing it exists to do. Scoping it would leave it verifying nothing —
F-40's shape inside our own gate.

## The eight findings, and what they have in common

All eight are in `context/findings.md` with the full narrative. Three were P1,
and the pattern is the part worth carrying forward:

> **This was the first feature to run our code against the organizers' _data_
> rather than data we built, and it opened three P1s.** Every one of them is a
> value that agreed with what we expected and disagreed with what the file said.

- **F-49 (P1)** — the loader's `has_usable_password()` guard. `is_password_usable("")`
  is `True`, so a brand-new row looks like it already has a credential, every one
  of the 121 people was skipped, and `check_password("", "")` is `True`.
  **123 accounts that authenticate with a blank password.** The census row
  `accounts.User with a real hash` is what caught it; a row-count census would
  have said 123 users, looks fine.
- **F-50 (P1)** — `UNIQUE (event, name)` on `Team` is **violated by the
  organizers' own fixture**: 40 teams, 36 distinct names, `StillTrail` three
  times. Dropped, by a named migration rather than an edit to `0001`.
- **F-55 (P1)** — the token's first layout was `JJ1.<email>.<sig>` split on `.`,
  and **an email contains dots**, so every credential produced four parts, the
  length check rejected all of them, and `email_from_token` returned `None` for
  "malformed" and "wrong signature" alike. Every demo identity was silently
  anonymous and every check still passed on the resulting 401.
- **F-54 (P2)** — `slugify` collapses three team names onto one slug, and
  `(event, slug)` is unique. The census now **reports** the collisions on boot
  rather than letting the loader raise.
- **F-51 (P2)** — `for_actor_and_subject`'s docstring said organizers fall
  through; the guard is `is_judge`, so a judge-organizer is refused. Found by a
  Hypothesis counter-example in about two seconds. **Code kept, docstring
  corrected**, because the strict reading is the safe one and nothing can reach
  that accessor until FEAT-05. Left as `fixed`, not `closed`, on purpose.
- **F-52 (P3)** — this ledger's own F-28 entry has the wrong mass arithmetic
  (`… + 5×5 = 126`; it is 131) and credits one invariant when both fire.
- **F-53 (P3)** — `bible/04` §5.2 says `jdg_07` is bound to `trk_03`; the
  fixture says `trk_06`. The loader derives the demo identities rather than
  reading the bible's ids, so a transcribed id cannot reach it.
- **F-48 (P2)** — `just accept` and `just coldstart` declared a variadic default
  of the literal string `{}`, so `just accept` — named in `AGENTS.md`, in
  `.dogfood.toml` and in the README — had **never once worked**.

## What was cut or deferred

Nothing was cut from the stated scope. Four things are *recorded as not done*,
and each is a decision:

1. **Prizes, custom questions, votes, comments and audit entries are not
   seeded.** `bible/04` §5 lists them as seeds and they are all real
   requirements at T1/T3. They are absent because nothing renders them yet and a
   seed nobody can see is not a seed. The `Prize` model shipped in FEAT-02 and
   stays empty; the census reports it as such rather than omitting it.
2. **`Event.description` and the track/team descriptions are empty.** The fixture
   supplies neither, and inventing prose a reviewer would read as data is the one
   thing the project has refused to do elsewhere.
3. **The `_next_suffix` slug disambiguator is a count, not a hash.** An
   auto-slug collision is resolved by appending the team's project count. It is
   deterministic and tested, and it is slightly worse than the derived-project-id
   form the loader uses for the fixture — a note for whoever reads it cold.
4. **`Review.duration_seconds` is `NULL` for all 126 rows.** The fixture carries
   no timing, and the "judge rushing" signal needs real durations. Deriving them
   would be inventing the evidence that signal is about.

## The three that were not in the plan, and should have been

1. **The acceptance gate needed a second kind of precondition.** Route existence
   cannot distinguish two refusals, and the whole point of F-40 is that they
   look identical from outside. This is the highest-value hour of the feature
   and it is not on the plan.
2. **`tests/fake_http.py`.** The probe tests started as a real socket and were
   flaky at roughly one run in six on Windows (`WSAECONNABORTED`, 10053) — a
   failure belonging to `http.server`, not to the code. A stub that raises
   `HTTPError` for a 4xx exactly as `urlopen` does is faithful *and*
   deterministic. Two of the three tests that exercise the most important
   behaviour in the project are now hermetic as a result.
3. **The test suite's password hasher.** Five real hashes at 400 ms each, across
   the thirty-odd tests that need a loaded database, put the loader's module at
   **116 seconds**. Swapping in MD5 for the suite put it at 28 s, and a test
   asserts the *settings module* never mentions `PASSWORD_HASHERS`, so the fast
   suite cannot become a fast portal.

## What the next session should know

1. **The T1 claim is available and is not yet made.** `run.py` prints `claimed
   nothing, verified T1` with all three T1 checks PASS. `claimed` goes in
   `.dogfood.toml` at the break, with the gap named beside it.

2. **`load_fixtures` runs automatically.** `docker/entrypoint.sh` already
   guarded it on `manage.py help | grep load_fixtures`; the command exists, so
   it runs between `collectstatic` and gunicorn binding. **The seed finishes
   before the port opens** — 1.9 s of it is real password hashing — so none of it
   is inside `run.py`'s 10-second window. Do not "optimise" it by hashing fewer
   than five; `verify_census` asserts the number in both directions.

3. **The census is the thing to run when the loader changes.** It re-derives
   every number from `fixtures.json` at the moment of comparison, so it cannot
   drift the way a maintained table of expected counts does — and the `User with
   a real hash` row is what caught F-49.

4. **The submit route's refusal order is load-bearing: authenticate, then the
   GUARD, then the team check, then the write.** The guard is before the per-actor
   work on purpose, so no authorization bug can shadow it. Two tests pin the
   distinction (`401` vs the guard's `403` vs the team's `403`), and the gate's
   probe depends on the guard's name surviving to the body.

5. **Django's test `Client` does not enforce CSRF unless you ask.** Every CSRF
   test in `test_denial_contract.py` builds its client with
   `enforce_csrf_checks=True`. A test that forgets observes no CSRF behaviour at
   all, which is indistinguishable from a working exemption.

6. **The demo identities are derived, so do not hard-code them.** `judge_a` is
   `jdg_04` and `judge_b` is `jdg_05` **on this fixture**; the rule is "lowest-id
   judge with ≥2 reviews on exactly one track, then the lowest-id judge on a
   different one". A different fixture yields a different, still-defensible pair.
   `tests/test_demo_credentials.py` asserts the committed `.dogfood.toml` values
   against whatever the rule currently produces, so a mismatch fails the suite
   rather than the acceptance report.

7. **The isolation proof prints a real matrix now** — `visitor 0/126`,
   `participant 0/126`, `judge 5/126`, `organizer 126/126`, `admin 126/126` — and
   `just check` runs it with `--require-data`, so an unseeded container is a hard
   failure rather than a `WIRING ONLY` note. The judge row is a *representative*
   judge, not `judge_a`; that is correct for FIG. 02 and worth not "fixing".

8. **F-51 is still open by decision.** A judge who also organises is refused
   their own peers' scores. FEAT-04/05 own the console and the route, so they own
   the decision. It is `fixed`, not `closed`, and `fixed` blocks completion on
   purpose.

9. **`ruff format` can still break `tools/mutation_test.py`.** It has 18 exact
   source strings now, three of them added by this feature. After any reformat,
   `just mutation-test`, and believe `[pattern not found]` as a **harness
   defect** (F-46) rather than as a surviving mutation.
