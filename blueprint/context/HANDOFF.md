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
clean tree at `4d28ce0`)

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

## Verified state at `4d28ce0`

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
