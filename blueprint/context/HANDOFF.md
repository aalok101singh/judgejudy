# Handoff — a self-contained prompt for a fresh session

> **This file is a prompt, not a document about the prompt.** Paste everything
> below the rule into a new session.
>
> **Why it exists, and why it is not a copy of the other context files.** The
> project already has `project-overview.md` (loaded every session) and a
> six-file read-in order. Duplicating them here would create a fourth copy of
> the same facts, and a fourth copy is a fourth thing to drift — which is the
> failure this project has committed repeatedly (`bible/04` §2.1 had it right
> because a script wrote it; `project-overview.md` had `5@5` because I typed it).
>
> So this contains **only what is not on disk**: the order to read in, what to
> verify before you build, the traps that have already cost real time, and the
> acceptance line for the next thing. Everything else stays single-sourced.
>
> **It carries no numbers on purpose.** The census, the test count, the timing
> and the mutation count are all on disk in three places, and two of those are
> generated. Quoting them here would be the fourth copy. **Your first job is to
> regenerate them and say whether they were true.**
>
> If you find a fact in here that contradicts a file it points at, **the file
> wins** and this one is a bug worth reporting.

---

## The prompt

---

You are continuing a solo, time-boxed build. Read this fully before touching
anything. Do not ask me to re-explain the project — it is all on disk.

**You have no context from any previous session. Assume nothing. In particular,
assume every number and every status claim in this repository is a claim, not a
fact, until you have re-run the gate that produces it.** That is not caution,
it is the project's own working rule, and the previous session ended by
regenerating every figure in it.

## The project

Judge Judy: a self-hostable hackathon submission AND judging platform, built as
a submission for DOGFOOD 2026. Django 5 + DRF + SQLite (WAL) in one container.
Offline, one command, no cloud account, no hosted DB, no external API, no API
key. 69-hour window, one person, solo.

Working directory: `C:\Users\Aalok\Desktop\Judge Judy`
Repository: `https://github.com/aalok101singh/judgejudy`, branch `main`.

**Start by establishing where you actually are**, rather than believing a
document:

    git log --oneline -5
    git status --porcelain

A dirty tree is the first finding, not an inconvenience — say what changed and
whether it is intended before you touch it.

## Read in this order, then stop and work

1. `AGENTS.md` — the rules, the traps, and the gate. **Start here.** It is
   short and it is the contract.
2. `blueprint/context/project-overview.md` — the whole project, ~18KB. The
   decisions D-01…D-15 that cannot be re-litigated are in §4.
3. `blueprint/context/current-feature.md` — the ONE in-flight scope, and its
   acceptance line. **This names your next task. Trust it over anything here.**
4. `blueprint/context/findings.md` — what is known broken and what was chosen
   not to fix. Check anything touching the files you are about to touch. Note
   the statuses: `fixed` blocks completion **on purpose**, and a repair is not
   done until a review has looked at the result.
5. `blueprint/history/features/04-assignment-and-judge-console.md` — the most
   recent archive. What was actually built, what it cost, and the two P1s that
   were in our own reasoning rather than in the data.
6. `blueprint/build-plan.md` — the acceptance line for the current feature.

DO NOT read the `bible/` folder. It is 330KB of research. The overview names the
section for every kind of question; open that one section. For the next feature
(FEAT-05, the T2 surface) you will want `bible/07` (the threat model, including
what we did not stop) and `bible/05` §9 (the API surface). `bible/06` is still
worth its §2 if you touch the assignment engine again.

## PHASE 0 — verify the build before you extend it

**Do this first, in this order, and report what you measured.** The previous
session's numbers are in `AGENTS.md` §Current state, in `README.md` and in the
FEAT-04 archive. Regenerate them. Where a document disagrees with a run, **the
run wins and the document is a finding** — write it into `findings.md`.

    just doctor            # which interpreter, which docker, which tools
    just check             # THE GATE. Clean volume, build, up, checker, proofs, suite
    just prove-offline     # boots under --network none and probes it
    just mutation-test     # every deliberate corruption must be caught
    just lint              # ruff check + ruff format --check + the isolation rule
    just lint-migrations   # makemigrations --check: models and migrations agree
    python tools/verify_spec.py     # spec checks; stdlib-only; EXITS NON-ZERO
    just coldstart         # cold start against the 60 s budget

`just check` is the only command a reviewer needs. `prove-offline` and
`mutation-test` are deliberately **not** inside it — each needs a clean volume,
and `check` has to stay the one command.

Two things to check that a gate does **not** cover, and both have bitten:

- **A document that names a command has to be a command that can be typed.**
  Three recipes in this repository were once named in four documents and did not
  exist, and later three existed and were still broken. **This is now a
  mechanical check** — `verify_spec.py`'s `every 'just' recipe named in a
  document exists` covers it, so you no longer have to remember to run the audit
  (F-59). Run `just --list` against the recipes the documents name anyway, once,
  and do not re-derive it every session.
- **A committed `acceptance-report.txt` must be reproducible.** Run
  `just report` and diff it. It is generated and must never be hand-edited.

If something is red, **fix it before starting new work.** A green gate on top
of a known-red one is not a green gate.

## Where the build is

FEAT-01 (skeleton + container), FEAT-02 (schema + isolation primitive),
FEAT-03 (loader, gallery, deadline guard) and **FEAT-04 (assignment engine,
min-cut certificate, judge console)** are **done, verified and committed** at
`3e78d78`. **BREAK-1 is closed**: the T1 claim was decided in writing and
`v-t1-verified` is tagged. Read `blueprint/context/current-feature.md` for what
is in flight — it is the authority on this, not the paragraph below.

Three things about the state you should know before you plan.

**The next step is FEAT-05, the T2 surface**, and it is the tier that matters.
All four T2 checks have been failing with real URLs since the first commit, and
FEAT-05 is what makes them pass. The trap is live and unchanged: **denial must be
a literal 403 with an empty body, never a 302** — `run.py` follows redirects, so
a redirect returns 200 and fails a scored check while looking correct in a
browser. `tools/expected_checks.json` already carries a precondition for the
judge-scores route; **flipping an expectation to `pass` is only correct when the
feature that owns it is done and its acceptance line has passed.**

**One finding is deliberately left `fixed` rather than `closed`,** and `fixed`
blocks completion on purpose. `findings.md` says which and why. It is **F-51**:
should a judge who *also* organises be refused their own peers' scores? The
accessor refuses (the safe reading) and the docstring says so. **It is a product
decision, not a code decision** — say it once with the consequence, then follow
the human's answer. FEAT-05 builds the routes that reach it.

**The next session should expect no new P1 in the data, and should say so
out loud if it finds one.** FEAT-03 was the first feature to meet the organizers'
*data* and opened three P1s in one go. FEAT-04 opened **none**, because its data
was already loaded and verified twice. What FEAT-04 found instead were two P1s
in **our own reasoning** (F-60, F-61) — both found by *executing* something
rather than reading it. The rate tracks how much genuinely new input meets the
code, and FEAT-05 is mostly new code over old data. **Look for F-64's shape: a
rule the fixture cannot reach is a rule with no coverage, and the suite must say
so rather than let a green gate imply otherwise.**

## The gate

    just check            # THE GATE. Clean volume, build, up, checker, proofs, tests.

A feature is done when its acceptance line in `build-plan.md` passes on a clean
database AND `just check` is green AND `just lint` is green. Not when the code
exists.

## The traps that have already cost real time

These are all still live. Each one produced a wrong conclusion, not an error
message.

**1. `run.py` is the organizers' file. It is UNMODIFIED and must stay so.** It
**ALWAYS exits 0**, even when every check prints FAIL. Never gate on its exit
code; `tools/run_acceptance.py` parses the report body instead. Editing it would
invalidate every result in `acceptance-report.txt`.

**2. A green check is not evidence.** `run.py` accepts **any 4xx** for "closed
event refuses submissions", so a 404, a 405, a CSRF rejection and a 401 for an
unrecognised credential **all report PASS**. The portal now answers with a body
that names the guard, and the acceptance gate re-sends the checker's request and
requires that name back — so this class of false pass is now a failing test. When
you add a refusal, assert on the **mechanism** and not on the status code, and
keep the gate's probe honest: an emptied `.dogfood.toml` must be caught there.

**3. Denial must be a literal 403 with an empty body and no `Location` header.
Never a 302.** `run.py` follows redirects, so a redirect returns 200 and fails
the check while looking correct in a browser. This is the single highest-value
line in the project.

**4. `run.py` greps the gallery POSITIONALLY.** It reads `projects[:3]` and
tests `any(title in body)`. So the first gallery page must be in the fixture's
own order; sorting by title or track pushes all three greppable titles off page
one and fails a scored check for a reason that reads like a data problem. That
ordering lives in one named function, and it is load-bearing.

**5. Three Pythons, two of them wrong.** `python` on PATH is **3.14.6 with no
Django**. The venv `.venv\Scripts\python.exe` is 3.13.13 and is correct. The
container is 3.13.15. Django 5.2 declares `Requires-Python: >=3.10` with no upper
bound, so the pin will NOT save you. **Never invoke a bare `python` for anything
that imports Django.** `just doctor` reports the resolved interpreter and fails
loudly on the wrong one. (`tools/verify_spec.py` is the exception — it is
stdlib-only, and the `just spec` recipe deliberately uses the ambient one.)

**6. `docker` is installed per-user** at
`C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin\`, which was on
no PATH at all, and "not installed" was recorded as the diagnosis for an entire
phase — it was wrong (F-34). `tools/docker.py` resolves it by absolute path.
**Do not reinstall Docker.** A stale shell will not see the PATH change; open a
new terminal.

**7. A failing command is evidence that a command failed, not evidence about
why.** Test the alternatives before concluding anything. This has been true on
this project at least six times, and twice the confident conclusion was the
expensive one.

**8. `ruff format` can break `tools/mutation_test.py`.** Its targets are exact
source strings. If you reformat anything, run `just mutation-test` afterwards
and believe `[pattern not found]` as a **harness defect**, not as a surviving
mutation (F-46).

**9. Django's test `Client` does not enforce CSRF unless you ask.** Pass
`enforce_csrf_checks=True` or `process_view` accepts early and you are
observing **no CSRF behaviour at all** — which is indistinguishable from a
working exemption. This cost three versions of a wrapper.

**10. `has_usable_password()` is `True` for an EMPTY password**, and
`check_password("", "")` is `True` too. A guard written as "only set a password
if there isn't one" therefore skips every freshly created row. Compare against
`UNUSABLE_PASSWORD_PREFIX` instead. This shipped 123 blank-password accounts for
one run (F-49).

**11. Django's `MiddlewareMixin.__call__` never runs `process_view`.** Only
`process_request` and `process_response`. `CsrfViewMiddleware` does its check in
`process_view`, so wrapping a view in the middleware and returning its result
verifies **nothing**, silently.

**12. A CSRF rejection and a scope rejection are both 403, and a test that
passes `enforce_csrf_checks=True` without a token proves nothing.** CSRF fires
in middleware *before* the view runs, so a strict client with no token gets a 403
for the wrong reason and the isolation assertion passes without the scope ever
being consulted. The fix is a **same-client GET then POST** — a fresh client has
no CSRF *cookie* at all and is rejected before the token is even compared — and a
control test that pins down the two refusals are distinguishable. This is trap 9
again, one level in, and it is why
`tests/test_judge_console.py::test_a_strict_client_with_no_token_is_refused_by_csrf_not_by_scope`
exists next to the test it protects.

**13. A feature that returns structurally valid output containing nothing is
indistinguishable from a feature that works.** `bible/06` §2.3 says the min-cut
certificate should name "the judge nodes on the sink side of the cut". On the
network §2.2 itself describes, **that set is empty** — the canonical cut's source
side is reached through the projects that went *un*covered, whose judge edges are
untouched and therefore fully residual, so a deficient track's judges are on the
**source** side. The certificate printed a deficiency with nobody on it (F-61).
The right reading is the same cut one arc later: **the bottleneck judges are the
eligible judges whose capacity is exhausted.** The general trap: an empty
collection is a valid value, so a test asserting `== ()` passes forever. Assert
that something is **named**, and mutate the code to empty the collection and
watch the test fail.

**14. Textbooks are not evidence.** The min-cost flow in
`src/reviewer/assignment/flow.py` was written the standard way — successive
shortest paths with **incrementally updated** Johnson potentials — and it returns
**feasible but non-minimal** flows without ever raising, because a node that drops
out of reachability keeps a stale potential and Dijkstra then runs on a negative
reduced cost (F-60). It was caught by testing the solver against a **second,
independently written algorithm** over 1,500 random instances. That is the general
move: when you implement an algorithm, the cheapest proof is a differential test
against another implementation of the same specification. Recomputing potentials
from Bellman-Ford every augmentation costs 0.15 ms at this size and is correct.

## The rules, which are not negotiable

- **Every number in a shipped document is GENERATED, not transcribed.** Six of our
  first twelve findings were hand-typed census errors, two found *after* we had
  already published a correction log about the first four. A correction log
  containing un-caught errors teaches the reader to distrust the writer. Run the
  gate before trusting any number, including ones in these documents.
- **Every claim about library behaviour is EXECUTED, not recalled.** F-11 was a
  documented DRF default that was backwards, and it would have made the deadline
  check pass without ever testing the deadline. The empty-password trap above is
  the same lesson in a new medium.
- **Your first code that meets the organizers' DATA rather than data we built
  will find something we got wrong about it.** The previous session opened three
  P1s for exactly this reason. Treat the fixture as adversarial, not as input.
- **Tests that assert on a substring are weak** — another bug can produce the
  same substring. Assert on the *specific finding*. Three of ours could not fail
  and were only found by mutation testing (F-41).
- **A check that cannot fail is worse than no check.** If a census assertion is
  computed from the same list it just counted, it is an identity — say so rather
  than presenting it as verification. **An empty collection is a valid value**,
  so `assert found == []` passes forever and asserts nothing (F-61, F-65).
  **Prove a new test can fail: break the code on purpose and watch it go red.**
  FEAT-04 ran 16 deliberate corruptions across its two new modules, 8 against the
  engine and 8 against the console, each naming the test that must notice.
- **Do not re-litigate a decision.** D-01…D-15 in the overview are settled; the
  cut ledger in `bible/08` §13 records the rejected items with reasons. If you
  think one is wrong, say so **once, in a paragraph, with the consequence**, and
  then follow it.
- **Report honestly and cheaply.** Lead with the decision or the blocker. If
  something is half-built, say "half-built" and name the half. The brief rewards
  honest gap reporting and penalises inflation; `run.py` prints `claimed` against
  `verified` and the panel runs the identical program.
- **The tier claim is made at a scheduled break against what is actually green** —
  not in advance, and not in a README. It is **the human's decision**: do not
  write one into `.dogfood.toml` on your own initiative, and do not claim a tier
  whose checks are not green.
- **Commit as yourself (`aalok101singh`) only.** No collaborators, no build
  files in the repository. Commit the file structure, source, tests and docs
  only. Push to `main` when a feature is verified.

## When you finish the feature

Update `current-feature.md`, update `findings.md`, write the archive in
`history/features/`, and commit. **A repair is not done when the code changes —
it is done when a review has looked at the result.** `fixed` blocks completion in
the findings ledger on purpose.

**Re-run Phase 0 before you commit, not after.** Every number in the archive and
in the state files has to be the number you measured in *this* session — and
editing `project-overview.md` changes its own byte size, which is a spec-gate
check, so expect one `just spec-quiet` failure at the end and fix the quoted size
in `AGENTS.md`. Also keep the overview **under 20,000 bytes**: it is loaded at the
start of every session, and the gate fails if it goes over.

## Report back

Short. Lead with the decision or the blocker. **Name the numbers you measured,
not the ones you expect** — and in your first report, say whether the numbers
already written in this repository were true. If a gate is red, say which and
why in one line.

---
