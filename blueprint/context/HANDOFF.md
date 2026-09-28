# Handoff — a self-contained prompt for a fresh session

> **This file is a prompt, not a document about the prompt.** Paste everything
> below the rule into a new session.
>
> **Why it exists, and why it is not a copy of the other context files.** The
> project already has `project-overview.md` (17,577 bytes, loaded every session)
> and a six-file read-in order. Duplicating them here would create a fourth copy
> of the same facts, and a fourth copy is a fourth thing to drift — which is the
> failure this project has committed six times (`bible/04` §2.1 had it right
> because a script wrote it; `project-overview.md` had `5@5` because I typed it).
>
> So this contains **only what is not on disk**: the order to read in, the state
> of the last thing built, the traps that have already cost real time, and the
> acceptance line for the next thing. Everything else stays single-sourced.
>
> If you find a fact in here that contradicts a file it points at, **the file
> wins** and this one is a bug worth reporting.

---

## The prompt

---

You are continuing a solo, time-boxed build. Read this fully before touching
anything. Do not ask me to re-explain the project — it is all on disk.

## The project

Judge Judy: a self-hostable hackathon submission AND judging platform, built as
a submission for DOGFOOD 2026. Django 5 + DRF + SQLite (WAL) in one container.
Offline, one command, no cloud account, no hosted DB, no external API, no API
key. 69-hour window, one person, solo.

Working directory: `C:\Users\Aalok\Desktop\Judge Judy`
Repository: `https://github.com/aalok101singh/judgejudy` (branch `main`, pushed,
clean tree at `0cad51d`)

## Read in this order, then stop and work

1. `AGENTS.md` — the rules, the traps, and the gate. **Start here.** It is
   short and it is the contract.
2. `blueprint/context/project-overview.md` — the whole project, ~17KB. The
   decisions D-01…D-15 that cannot be re-litigated are in §4.
3. `blueprint/context/current-feature.md` — the ONE in-flight scope, and its
   acceptance line.
4. `blueprint/context/findings.md` — what is known broken and what was chosen
   not to fix. Check anything touching the files you are about to touch.
5. `blueprint/history/features/02-schema-and-isolation.md` — the most recent
   archive. What was actually built, what it cost, and the eight things the next
   session would otherwise re-derive.
6. `blueprint/build-plan.md` — the acceptance line for the current feature.

DO NOT read the `bible/` folder. It is 330KB of research. The overview names the
section for every kind of question; open that one section. You will want
`bible/03` (the acceptance contract and the seven traps) and `bible/04` (the
fixture census and the eight edge cases) for FEAT-03.

## Where the build is

FEAT-01 (skeleton + container) and FEAT-02 (schema + isolation primitive) are
**done, verified, committed and pushed**. `4d28ce0` is the FEAT-02 commit.

**In flight: FEAT-03 — Loader, identities, gallery, deadline guard (5h).**
The scope and acceptance line are in `blueprint/context/current-feature.md`. It
is the feature that makes `isolation_proof` print a real matrix instead of
wiring checks, and the feature after which `just check` is *expected to go red*
on one check (see the traps below).

Do not start FEAT-04 (rubric, assignment, judge console). The judge surface
needs routes that do not exist yet.

## FEAT-03 reconnaissance — already done, do not redo it

These were re-derived from `fixtures.json` directly. **Re-derive anything you
are about to build on, but start from these rather than from nothing.**

| | | |
|---|---|---|
| top-level keys | `event`, `tracks`, `judges`, `teams`, `projects`, `scores` | |
| tracks | 8 — keys `id`, `name` | no descriptions |
| judges | 30 — keys `id`, `name`, `email`, `tracks` | **21 single-track, 9 dual** → 39 judge `RoleBinding` rows |
| teams | 40 — keys `id`, `name`, `members` | `members` are **emails** |
| projects | 41 — `id`, `team`, `track`, `title`, `summary`, `repo_url`, `submitted_at` | **no `description`, no tags, no images** |
| scores | 126 — `judge`, `project`, `criteria`, `comment` | `criteria` keys are always `functionality, quality, innovation` (that **order**) |
| **people** | **121** = 30 judges + 91 team members | **zero overlap** — no judge is a team member, and every member is in exactly one team |
| event | `id`, `name`, `submissions_close` only | **no `starts_at`, no `submissions_open`** — see below |

**Three consequences that are not obvious and cost time to find:**

1. **The census is exactly 121 people, so the demo identities must be drawn from
   those 121** rather than invented. Six synthetic accounts would make
   `verify_census` report 126 and quietly change a number the panel can check.
   Promote five of the 121 instead.
2. **`Event.starts_at` is required by our schema and the fixture does not
   supply it.** Derive it — `min(project.submitted_at)` is defensible and is
   computed rather than typed. Leave `submissions_open = NULL`, which the deadline
   guard already treats as "no opening gate". Do **not** move
   `submissions_close`; the portal is born closed and that is the T1-3 check.
3. **The demo `participant` must hold ONLY the participant role.** `.dogfood.toml`
   sends the participant header to the judge-scores route and expects a refusal —
   so if the participant is also the organizer or a judge, the check fails for a
   reason that is not the isolation model.

**`.dogfood.toml` `[auth]` is four empty strings and that is deliberate.** The
checker never logs in; the brief says to hand over "whatever header proves you
are this role — a cookie, a bearer token, a basic auth string". The seed must
print real values and they get pasted in verbatim. **Nothing is invented to make
a check pass.** The organizers' own example uses a guessable fixed session
value, so a deterministic demo credential is the spec's design, not a shortcut.

Recommended mechanism, and the reason: **an HMAC'd bearer token derived from
`SECRET_KEY` and the identity's email, carrying the identity in the token
prefix.** No schema change, nothing stored, rotatable by rotating the key, and
printable on boot. The alternative — a `Session` row with a fixed key — also
works and is closer to the organizers' example, but it means the token is a row
in a table that `down -v` wipes, so `.dogfood.toml` would need repasting after
every reset. **Whichever you pick, document the trade — a predictable demo
credential is a real property of a self-hosted portal whose only data is the
fixture set, and the README has to say so.**

**The single most important thing FEAT-03 must get right, and it is a false pass
waiting to happen:** `run.py` accepts **any 4xx** for "closed event refuses
submissions". So if your `POST /projects/new` is refused by CSRF, or by "you are
not logged in", the check reports **PASS while the deadline guard is never
called**. That is F-40 again, in a place where the fixture's past close date
makes it look like it is working. The request must arrive as an authenticated
participant and be refused **by the guard**. Assert it in a test that names the
guard, and say so in the archive.

## The gate

    just check            # THE GATE. Clean volume, build, up, checker, proofs, tests.

Also run these, which are NOT inside `just check`:

    just doctor           # which interpreter, which docker, which tools
    just prove-offline    # boots under --network none and probes it
    just mutation-test    # 15 deliberate corruptions; all must be caught
    just lint             # ruff check + ruff format --check + JJ01
    just lint-migrations  # makemigrations --check: the schema and the migration agree
    python tools/verify_spec.py    # 67 spec checks, stdlib-only, exits non-zero

A feature is done when its acceptance line in `build-plan.md` passes on a clean
database AND `just check` is green AND `just lint` is green. Not when the code
exists.

## Verified state at `0cad51d`

| | |
|---|---|
| `just check` | **GATE GREEN** — 2 of 7 acceptance checks pass, 5 fail as expected |
| `just prove-offline` | **PROVED** — 5.4 s, 4 content-asserting probes |
| `just mutation-test` | **15/15** |
| `tools/verify_spec.py` | **67/67** |
| `just lint` | clean in 86 files; JJ01 finds no unscoped `Review` read |
| Suite | **160 passed** |
| Schema | 24 models / 12 apps, 12 initial migrations, `makemigrations --check` clean |
| `claimed` | `[]` — and that is accurate. No tier is complete. |

## What is already wired for you

**The entrypoint already calls `load_fixtures`.** `docker/entrypoint.sh` does
`migrate → collectstatic → load_fixtures → THEN gunicorn binds`, and it checks
`manage.py help | grep load_fixtures` first, so today it logs "no load_fixtures
command yet (FEAT-03); starting with an empty database" instead of crashing. The
moment the command exists it runs automatically, with **no compose change**.

**`tools/run_in_container.py` already knows the two commands** you are about to
write — `load_fixtures` and `verify_census` are in its `OWNERS` table, so step 5
of `just check` stops printing `SKIP` for them and starts **failing** on them if
they are broken. That is the check you want.

**Seeding is outside the checker's 10-second window.** gunicorn does not bind
until the seed finishes, so the ~2 s of real password hashing (5 identities,
F-12) is spent before the port exists rather than inside `run.py`'s
`TIMEOUT = 10`. Do not "optimise" this by hashing fewer.

**Routes `.dogfood.toml` already names:** `gallery = "/"` and
`submit = "/projects/new"`. `/` currently serves a placeholder page; the gallery
takes it over. The judge and export routes resolve in FEAT-05.

**The four Hypothesis invariants** (`bible/05` §6b.2) can finally run: F-22 is
accepted-and-resolved, FEAT-01 created the project, FEAT-02 created the models.
Use `hypothesis.extra.django.TestCase` (one transaction per example — what
`@given` needs), `@settings(max_examples=50, deadline=None)`, and
`st.just()` / `st.builds` over **small worlds**, never `from_model()` on the big
tables. The failure mode is "some combination we did not think of", not data
volume.

## The traps that have already cost real time

**1. `just check` WILL GO RED when you add `/projects/new`.** "closed event
refuses submissions" currently passes on a **404**, which is inside the checker's
4xx range — so the deadline guard is not being tested at all (F-40). The moment
that route exists, the check passes for the *right* reason and
`tools/expected_checks.json` is **stale**, which the gate treats as a finding.
Flip that entry with a reason naming the route. **That red is the design
working.** It is not a regression and not something to suppress.

**2. `run.py` is the organizers' file. It is UNMODIFIED and must stay so.** It
ALWAYS exits 0, even when every check prints FAIL. Never gate on its exit code;
`tools/run_acceptance.py` parses the report body instead.
`acceptance-report.txt` is generated and must never be hand-edited.

**3. Denial must be a literal 403 with an empty body and no `Location` header.
Never a 302.** `run.py` follows redirects, so a redirect returns 200 and fails
the check while looking correct in a browser. This is the single
highest-value line in the project.

**4. Three Pythons, two of them wrong.** `python` on PATH is **3.14.6 with no
Django**. The venv `.venv\Scripts\python.exe` is 3.13.13 and is correct. The
container is 3.13.15. Django 5.2 declares `Requires-Python: >=3.10` with no upper
bound, so the pin will NOT save you. **Never invoke a bare `python` for anything
that imports Django.** `just doctor` reports the resolved interpreter and fails
loudly on the wrong one.

**5. `docker` is installed per-user** at
`C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin\`, which was on
no PATH at all, and "not installed" was recorded as the diagnosis for an entire
phase — it was wrong (F-34). `tools/docker.py` resolves it by absolute path.
**Do not reinstall Docker.** A stale shell will not see the PATH change; open a
new terminal.

**6. A failing command is evidence that a command failed, not evidence about
why.** Test the alternatives before concluding anything. This has been true on
this project at least four times.

**7. Swapping `AUTH_USER_MODEL` breaks a pre-existing LOCAL database** with
`InconsistentMigrationHistory`, because `accounts.0001` is a dependency of
`admin.0001`. `just reset-local` fixes it. The container is unaffected because
`just check` starts from a clean volume.

**8. `ruff format` can break `tools/mutation_test.py`.** Its targets are exact
source strings. If you reformat anything, run `just mutation-test` afterwards
and believe `[pattern not found]` as a **harness defect**, not as a surviving
mutation (F-46). It now has its own section, but the habit is the fix.

## The rules, which are not negotiable

- **Every number in a shipped document is GENERATED, not transcribed.** Six of our
  first twelve findings were hand-typed census errors, two found *after* we had
  already published a correction log about the first four. A correction log
  containing un-caught errors teaches the reader to distrust the writer. Run the
  gate before trusting any number, including ones in these documents.
- **Every claim about library behaviour is EXECUTED, not recalled.** F-11 was a
  documented DRF default that was backwards, and it would have made the deadline
  check pass without ever testing the deadline.
- **Tests that assert on a substring are weak** — another bug can produce the
  same substring. Assert on the *specific finding*. Three of ours could not fail
  and were only found by mutation testing (F-41).
- **Do not re-litigate a decision.** D-01…D-15 in the overview are settled; the
  cut ledger in `bible/08` §13 records eleven rejected items with reasons. If
  you think one is wrong, say so **once, in a paragraph, with the consequence**,
  and then follow it.
- **Report honestly and cheaply.** Lead with the decision or the blocker. If
  something is half-built, say "half-built" and name the half. The brief rewards
  honest gap reporting and penalises inflation; `run.py` prints `claimed` against
  `verified` and the panel runs the identical program.
- **`.dogfood.toml` has `claimed = []`, which is accurate.** The tier claim is
  made at a scheduled break against what is actually green — not in advance, and
  not in a README.
- **Commit as yourself (`aalok101singh`) only.** No collaborators, no build
  files in the repository. Commit the file structure, source, tests and docs
  only. Push to `main` when a feature is verified.

## When you finish the feature

Update `current-feature.md`, update `findings.md`, write the archive in
`history/features/`, and commit. **A repair is not done when the code changes —
it is done when a review has looked at the result.** `fixed` blocks completion
in the findings ledger on purpose.

## Report back

Short. The human is on hour 4 of 69. Lead with the decision or the blocker. Name
the numbers you measured, not the ones you expect. If a gate is red, say which
and why in one line.

---
