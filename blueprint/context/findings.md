# Findings Ledger

**The durable record of everything we got wrong, everything we chose not to fix,
and everything still open.** Plain markdown, no script, no dependency.

**Why this file exists.** Six of our first twelve findings were census errors in
our own planning documents — and two of those were found *after* we had already
published a correction log about the first four. A finding that lives only in a
chat transcript is gone the moment the context clears: no ID to reference, no
status to update, nothing that notices a serious finding was reported and never
fixed. This is that record.

**Conforms to** `ai-blueprint.dev/docs/findings-ledger/`. IDs are sequential and
**never reused or renumbered.** Resolved entries archive under a work-item prefix
at completion (`05-block-c/F-13`), so a re-build of feature 5 uses
`05-build-2/F-13` and the two records stay distinct.

---

## Statuses

| Status | Meaning | Blocks completion |
|---|---|---|
| `unverified` | suspected, no confirming evidence yet | no |
| `open` | confirmed, not yet repaired | **yes, P0/P1** |
| `fixed` | repaired, not yet re-reviewed | **yes, P0/P1** |
| `closed` | repaired **and** re-reviewed against the new work | no |
| `accepted` | not fixing, by explicit decision, with a reason | no |
| `invalid` | re-examination proved it wrong, evidence recorded | no |

**`fixed` blocking is deliberate.** A repair is not done when the code changes;
it is done when a review has looked at the result. A fix can introduce a worse
defect than the one it removed.

---

## Open — blocking

**None.** The only blocking finding, **F-13 (Docker)**, was closed on
2026-09-27 after the real cause turned out to be a PATH problem rather than a
missing install — see the *Resolved — environment verification* section
below. **No P0 or P1 is open, so nothing currently blocks a feature from being
marked done.** One P2 (F-38, the ambient `python` is 3.14.6) still needs
settling before the build relies on a bare `python`.

## Open — non-blocking

### F-42 [P2] open - `run_acceptance.py` had a wrong default that produced the right answer

**File:** `tools/run_acceptance.py`
**Found:** 2026-09-28, by `tools/mutation_test.py`
**Why it matters:** The false-pass detector looked a route up as
`route_status.get("submit_route_exists", 0)` against a dict keyed `submit`. The
key did not exist, so the lookup returned its **default of 0** — and because 0
was in the "route is missing" set, the gate still reported a false pass. The
*verdict* was right and the *explanation* was wrong: it said `submit_route_exists
returned no response` when the route was answering **HTTP 404**.

This is the most expensive shape of bug there is. A wrong default that happens
to produce the right answer **survives a green test run** and lies in the one
message a human reads to decide what to fix. A reader debugging "no HTTP
response" would look at the network, not at the typo in a dict key.

**Suggested fix:** Map every precondition key to a route explicitly
(`PRECONDITION_ROUTES`), and **fail loudly** on an unmapped key rather than
defaulting. A precondition naming a route that does not exist is a broken
precondition, and defaulting blames the portal for a typo in our own file.
**Resolution:** Fixed. `PRECONDITION_ROUTES` added, unmapped keys are appended
to `problems`, and `test_every_precondition_names_a_real_route` plus
`test_probed_routes_are_the_ones_the_checker_uses` guard both directions. The
second test exists because the original defect was a *name* mismatch, so
asserting the name is what actually catches it.

### F-41 [P2] closed - Two tests could not fail: they asserted on substrings that a different bug also produced

**File:** `tests/test_gates.py`, `tools/mutation_test.py`
**Found:** 2026-09-28, by `tools/mutation_test.py`
**Why it matters:** Four tests asserted `assert "REGRESSION" in result.stdout`.
The synthetic report they used regresses **two** checks, so a second REGRESSION
line always appeared and satisfied the substring — and the tests passed with
the regression branch replaced by a string literal that could never fire.

The same class of failure appeared twice more in the same session:

- `assert "os.execv" not in source` failed because the file's **docstring**
  explains the bug and necessarily names it. Narrowing to `"os.execv("` failed
  again, because the docstring's worked example *is* a call. Fixed by parsing
  with `ast` and inspecting call nodes, so prose is excluded by construction.
- `assert "import django" not in source` failed on a **comment** that discusses
  Django. Fixed by matching `^\s*import django` with `re.MULTILINE`.

**Why it matters more than a normal weak test:** a test that cannot fail is
worse than no test, because it occupies the slot where a real check should be
and reports coverage. All three were found by mutation testing, none by reading
the code.
**Resolution:** **Closed.** Assertions are now on the *specific finding*
(`"'gallery is public' is expected to pass"`) rather than on a marker word, and
the `os.execv` check uses `ast`. Recorded in the test docstrings so the next
person does not "simplify" them back to a substring.

### F-40 [P1] closed - Two of the organizers' seven checks passed for the wrong reason, and the gate counted them as evidence

**File:** `tools/expected_checks.json`, `tools/run_acceptance.py`
**Found:** 2026-09-28, while building the acceptance gate
**Why it matters:** `run.py` accepts **any 4xx** for "closed event refuses
submissions", and a **404 is a 4xx**. At this milestone `/projects/new` does not
exist, so:

| Check | Reported | Because |
|---|---|---|
| closed event refuses submissions | **PASS** | the route 404s; the deadline guard is never tested |
| judge cannot see peer scores | would PASS | a 404 satisfies the expected 401/403 |
| participant blocked | would PASS | likewise |

**This is F-11 turned on ourselves.** F-11 was a documented DRF default,
recalled rather than executed, that would have made the deadline check pass
without ever testing the deadline. Here the mechanism is different and the
outcome is the same: a check reporting PASS without exercising the behaviour it
names.

It matters more than an ordinary unbuilt feature because **a false pass is
believed**. A red check is obviously red; a green one is taken as evidence and
stops being looked at. The one check in this project whose entire value is
"the backend refuses this" was green for the reason that there was nothing to
refuse.
**Suggested fix:** A precondition table. The gate probes the portal and reports
a **FALSE PASS** — with the route and the status that answered — and fails on
it.
**Resolution:** **Closed 2026-09-28 by FEAT-01**, on the grounds that the
*defect* was the gate reporting a false pass as evidence, and that is repaired:
`tools/expected_checks.json` carries a `preconditions` table, `run_acceptance.py`
probes the routes and names the one that answered, and the gate exits non-zero.
The gate's own test asserts the current false pass is *detected*.

The false pass itself disappears in FEAT-03, when the route exists and the
deadline guard refuses it for the right reason. **At that moment the gate will
go red** — the expectation is stale, and a stale expectation is a finding. That
red is the design working, and it is the first thing to expect at FEAT-03.

`--allow-false-passes` exists so `just check` stays usable before then. It is
asserted **not** to rescue a regression or an overclaim — it downgrades exactly
one finding, and `test_allow_false_passes_downgrades_only_that_finding` fails if
that ever changes.

### F-39 [P2] closed - `os.execv` does not quote arguments containing spaces on Windows

**File:** `tools/docker.py`
**Found:** 2026-09-28, by running it rather than by reasoning about it
**Why it matters:** The first version of the Docker resolver used `os.execv`,
on the reasonable-sounding grounds that replacing the process is the cleanest
possible argument pass-through: the parent disappears, so the exit code, the
terminal and the signal handling cannot be lost.

**On Windows it does not quote.** An argument containing a space arrives at the
far end as two arguments:

```
os.execv(docker, [docker, "run", "--rm", img, "sh", "-c", "echo A; echo B"])
  -> the container runs `sh -c echo` with A; echo B as positional parameters
  -> prints nothing, and exits 0
```

`sh -c "..."` is exactly what the justfile's `sh` recipe does, so this broke a
real recipe while **exiting 0** — a silently wrong result, the same shape as
F-32. The repository directory is `Judge Judy`, so the path itself contains a
space and *every* invocation was affected.
**Suggested fix:** `subprocess.run` with a list. On Windows it quotes correctly
via `list2cmdline`; on POSIX it passes the vector straight through.
**Resolution:** **Closed.** Verified in both directions: `sh -c "echo A; echo B"`
prints both lines, and a failing command still propagates its exit code.
`tests/test_gates.py::TestDockerResolver` asserts this by **running** a
command that fails (`docker run --rm alpine:3 false`) rather than by reading
the source, because the first version of that test asserted only that the word
`returncode` appeared, and `tools/mutation_test.py` then swallowed the exit
code with the test still green. **The lesson is F-11's: a documented stdlib
function recalled rather than executed is a library claim recalled rather than
executed.**

### F-38 [P2] closed - The ambient `python` is 3.14.6, not the venv's 3.13.13, and Django is not installed on it

**File:** `AGENTS.md` §Verify, `blueprint/config.json` (app gate), the justfile
**Found:** 2026-09-27, while verifying the container against the venv
**Why it matters:** There are **three** Python versions in play, and two of them
are not the one the plan means:

| | Python | Django installed? |
|---|---|---|
| `python` on PATH (`…\WindowsApps\python.exe`) | **3.14.6** | **no** — `import django` fails |
| `.venv\Scripts\python.exe` | 3.13.13 | yes — Django 5.2.17, DRF 3.18.1 |
| container `python:3.13-slim` | 3.13.15 | installed by the Dockerfile at build time |

`AGENTS.md` tells a session to run `python run.py .dogfood.toml`. In a fresh
terminal that resolves to **3.14.6 with no dependencies**, and fails on the first
import. Worse, **Django 5.2.17's own metadata cannot prevent this** —
`Requires-Python: >=3.10` has no upper bound, so the pin looks satisfied on
3.14.6. This is the one open item from the Docker verification that will still
bite at hour 40, and it is the same shape of error as everything else in this
ledger: **an assumption that was never verified.**
**Suggested fix:** Invoke the venv interpreter explicitly everywhere, *and
assert the version* rather than assuming it.
**Resolution:** **Closed 2026-09-28 by FEAT-01.** The suggested fix was done
in full, and the second half is the part that matters: `tools/guard_interpreter.py`
*verifies* the interpreter rather than trusting the path, and every justfile
recipe names `.venv\Scripts\python.exe` explicitly. `just doctor` reports the
resolved interpreter and fails loudly on the wrong line. The venv has no `pip`
module, which is harmless — the image installs from `requirements.txt` and the
host runs pre-resolved packages — and is noted so the next session does not
spend an hour on it.

### F-14 [P2] closed - No git repository; no history for the Write Up Quest or the spec layer

**File:** repository root
**Found:** 2026-09-27 during environment setup
**Why it matters:** `bible/08` §14 builds the Write Up Quest submission on
"the numbers we got wrong" and "the design you abandoned." Twelve findings and a
twelve-row correction log are that material, and none of it is under version
control. It also means the spec layer has no diff story, and `fixtures.json`'s
SHA-256 (`252896BC…`) is not pinned anywhere it can be checked against.
**Suggested fix:** `git init`, then commit in this order: `bible/`,
`blueprint/`, `requirements*.txt`, `.venv` ignored. Pin `fixtures.json` by hash
in `blueprint/context/project-overview.md` so a re-download is detectable.
**Resolution:** **Closed 2026-09-28 by FEAT-01.** Repository initialised and
wired to `https://github.com/aalok101singh/judgejudy` (empty at the time; no
second history created locally). `.venv` is ignored. The fixtures pin is now
**asserted by a test** — `TestFixturesPin::test_fixtures_hash_matches_the_pinned_value`
— rather than only being a comment, so a re-downloaded fixture fails the suite
instead of silently invalidating every derived number.

---

## Resolved — environment verification, 2026-09-27

*Four findings, one root cause. **F-13 is the headline: Docker was running the
whole time and nothing could find it.** `docker --version` returning NOT FOUND
is what we took as “not installed” — and that conclusion was wrong, which is
why F-34 exists and why the F-13 entry above is closed rather than deleted.*

### F-34 [P2] closed - Docker Desktop was installed per-user, so `docker` was on no PATH and nothing could find it

**File:** environment (user PATH)
**Found:** 2026-09-27 during Docker verification — this is the real F-13
**Why it matters:** Docker Desktop was **running the whole time**, with its
daemon up. The blocker was never "Docker is not installed"; it was that the
binary lives in `C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin`,
which is **not** a standard location and was in neither the in-session PATH, the
User PATH, nor the Machine PATH. `docker --version` returned NOT FOUND, and the
honest conclusion from that alone would have been the wrong one. At hour 40 this
costs real time: a session would conclude the blocker was unfixed and start
reinstalling a working tool.
**Suggested fix:** Append the bin directory to the **User** PATH.
**Resolution:** **Closed 2026-09-27.** Appended to the persisted User PATH;
`docker --version` → 29.6.2 and `docker compose version` → v5.3.1 with no full
path. **A new terminal is required for the change to reach new shells** — an
in-flight shell keeps its old PATH, which is why the justfile should also
resolve `docker` by absolute path as a fallback. The per-user install path is now
in `bible/ENVIRONMENT.md` and asserted by `verify_spec.py --env`.

### F-35 [P2] closed - `just` was not installed, though `just check` was named the gate command in three files

**File:** `AGENTS.md`, `blueprint/build-plan.md`, `blueprint/config.json`
**Found:** 2026-09-27 while verifying the environment
**Why it matters:** The plan's single most-repeated command is `just check`, and
nothing in the plan ever listed `just` as a prerequisite. No justfile exists yet
— FEAT-01 creates it — but the **binary** was absent, so the gate command was
fiction in all three files that name it. The same class of error as F-11 and
F-28: **an assumption that was never verified.** It is also the cheapest finding
in the ledger to have caught and the most expensive to discover at a break.
**Suggested fix:** Install `just`, and add the tool to the plan's prerequisites
rather than assuming it.
**Resolution:** **Closed 2026-09-27.** `just 1.58.0` installed via
`winget install --id Casey.Just` (the official package). `just --version` → `just
1.58.0`. Now recorded in `bible/ENVIRONMENT.md` as a prerequisite, and asserted
by `verify_spec.py --env` so it cannot silently vanish.

### F-36 [P2] closed - `python:3.13-slim` was not pulled, so Block A would have waited on a network at H+0

**File:** environment (local image cache)
**Found:** 2026-09-27 during Docker verification
**Why it matters:** The plan says pull it *before* kickoff precisely so the
Block A build is not waiting on a network at H+0, on a laptop, offline. A cold
`docker compose build` with an absent base image either stalls on the network or
fails outright, and the spec requires the whole thing to work with the network
off.
**Suggested fix:** `docker pull python:3.13-slim` before kickoff.
**Resolution:** **Closed 2026-09-27.** Pulled, digest `sha256:7c61056e61ac89e8
…`, 178 MB. The container reports **Python 3.13.15**, which is the 3.13 line and
matches the venv's 3.13.13 to within a patch — so the "local == container" claim
holds, and F-38's ambient-3.14.6 path does not.

### F-37 [P3] accepted - Docker Desktop is allocated 3.71 GiB, which is tight for the cold-start budget

**File:** environment (Docker Desktop settings)
**Found:** 2026-09-27 during Docker verification
**Why it matters:** `MemTotal` is 3,982,098,432 bytes (3.71 GiB). FEAT-01's
acceptance is a **serving page in under 60 seconds from a clean volume**, and the
seed has a **10-second** window against a 5-identity hash budget. One small
Django + gunicorn + SQLite container fits comfortably, but the margin is thinner
than the usual 8 GB allocation, and the 10 s window is the constraint that will
actually be felt.
**Suggested fix:** None now. Raise the allocation to 6 GB in Docker Desktop
settings only if the FEAT-01 60-second measurement or a `run.py` seed misses.
**Resolution:** **Accepted 2026-09-27.** Recorded as a measurement to watch at
FEAT-01 acceptance, not a defect. `run.py`'s seed is already insulated by
F-12 (5 real hashes, 116 `UNUSABLE_PASSWORD`).

### F-13 [P1] closed — Docker: not missing, just unfindable

**Found:** 2026-09-27 during environment setup, as “Docker is not installed”.
**Resolution:** **Closed 2026-09-27.** Docker was installed and running the whole
time; the real defect was F-34. Verified working, and the base image pre-pulled:

| | Verified |
|---|---|
| Docker | **29.6.2**, build `dfc4efb` |
| Compose | **v5.3.1** |
| Server | 29.6.2 · `linux/x86_64` · 8 cores · driver `overlayfs` |
| Backend | **WSL2 confirmed** — `docker-desktop` on WSL 2.7.11.0, kernel 6.18.33.2-2 |
| Daemon | up — `\\.\pipe\docker_engine`, `dockerDesktopLinuxEngine` present |
| Install path | `C:\Users\Aalok\AppData\Local\Programs\DockerDesktop` (per-user) |
| Disk | 114 GB free |
| Image | `python:3.13-slim` pulled, `sha256:7c61056e…`, 178 MB, container = **Python 3.13.15** |

**Why it mattered anyway:** `docker compose up` with the network off is
requirement 1 of 5 in `spec.md` and the first numbered disqualification. Three
of the five required deliverables could not have been produced without it. The
finding was real; the diagnosis was wrong.

**FEAT-01 is unblocked.**

## Accepted — deliberate, with the reason recorded

*These are the cut ledger in reviewable form. "Accepted" is not "forgotten"; the
reason travels into the archive at completion and into `README.md`.*

### F-15 [P3] accepted - gunicorn is absent on the local Windows venv

**File:** requirements.txt
**Found:** 2026-09-27 during environment setup
**Why it matters:** Looks like a broken dependency at first glance.
**Suggested fix:** None. `gunicorn==26.2.0 ; sys_platform != "win32"` installs in
the Linux image and is skipped locally, which is correct. **Do not "fix" this by
removing the marker** — that breaks the container.
**Resolution:** Accepted 2026-09-27. Environment marker is intentional.

### F-16 [P3] accepted - No Merkle transparency log (CT / RFC 6962 / Sigsum)

**File:** bible/05 §9c
**Found:** 2026-09-27 during research
**Why it matters:** A hash-chained audit log invites the question of whether it
should be a transparency log.
**Suggested fix:** None taken. CT's value is **witnessing** — an independent party
holding a copy to detect equivocation — and we have no witness. A Merkle root we
compute ourselves proves only internal consistency, which the 30-line hash chain
already proves, for three times the code. We take the strictly stronger 80%
instead: publish one chain head at results publication and replicate it into
every judge's signed participation record, so N parties outside the trust
boundary hold a copy.
**Resolution:** Accepted 2026-09-27. `bible/05` §9c records the reasoning.

### F-17 [P2] accepted - IRT / MFRM / joint project-difficulty model not built

**File:** bible/06 §4.3e
**Found:** 2026-09-27 during research
**Why it matters:** It is the textbook instrument for rater severity and its name
buys credibility with a panel.
**Suggested fix:** None. **Measured to lose.** Held-out RMSE 0.9097 against 0.6753
for the shipped estimator — *worse than predicting the panel mean* — and parameter
recovery RMSE 0.5414 against 0.2717. Estimating a free difficulty for each of 41
projects from ~3 reviews each costs more variance than the de-confounding gains.
**Resolution:** Accepted 2026-09-27. We borrow the vocabulary (severity is a
*facet*) and the standardised infit/outfit statistic for the `n = 1` case, and
`bible/06` §4.3e explains the rejection with numbers.

### F-18 [P3] accepted - TrueSkill not used

**File:** bible/06 §4.3f
**Found:** 2026-09-27 during research
**Why it matters:** It is a credible-sounding choice for "Bayesian normalization."
**Suggested fix:** None. TrueSkill is a win/loss online rating with a *dynamic*
skill parameter — order-of-arrival and skill drift. Our data is static ordinal
rubric scores with no sequence. Adopting it means abandoning the rubric, and the
weighted rubric is what T2 asks for.
**Resolution:** Accepted 2026-09-27.

### F-19 [P2] accepted - No Postgres RLS, Casbin or OPA in the authorization path

**File:** bible/07 §2c
**Found:** 2026-09-27 during research
**Why it matters:** All three are standard answers to "how do I prove isolation."
**Suggested fix:** None. RLS is Postgres-specific, needs `SET LOCAL` per
transaction with real pool-leakage hazards, and **views bypass it by default**.
Casbin/OPA would make the rules *non-portable* and create a second source of
truth — the exact opposite of our best architectural claim, which is "there is
exactly one place where the rules live." Our scoped-accessor layer is the
portable equivalent and expresses "judge on trk_04" as an index scan rather than
a correlated subquery per row.
**Resolution:** Accepted 2026-09-27. `bible/07` §2b carries the two-layer
justification and §2c the rejections, with citations.

### F-20 [P2] accepted - Webhook delivery not implemented

**File:** bible/05 §9, bible/07 §3.4
**Found:** 2026-09-27, decided at H+0
**Why it matters:** REQ-T4-01 names webhooks, and a stub could read as a gap.
**Suggested fix:** None. 2 hours, **zero points on all four criteria**, and P-8
(SSRF via webhook URL — scheme allowlist, DNS resolution against private ranges,
redirect limit) is a real bug class written from scratch under time pressure.
**Resolution:** Accepted 2026-09-27. **What ships:** both models, a view
returning **501**, and `export run` / `import run` audit entries, so the schema
exists for whoever extends it. `README.md` states in one sentence that delivery,
retries and HMAC verification are **not** implemented. `bible/07` P-7/P-8 read
*"N/A by omission — recorded as required future work"* rather than "Stopped."
**Regret:** Yes, slightly. It is the one cut a panel might notice. It is the only
row on the ledger that does.

### F-21 [P3] accepted - Ranked Borda ballot not built

**File:** bible/06 §6.2
**Found:** 2026-09-27, decided at H+0
**Why it matters:** The Schwartzian transform is the unique linear rank
aggregator satisfying the Condorcet criterion (Fishburn 1973) — a theorem, and a
good line in a write-up.
**Suggested fix:** None. It *changes* the outcome; the anti-abuse influence
report *explains* it. The brief asks for *"an answer to people trying to cheat
it"* and an answer is a report. Break 4 candidate if G finishes early.
**Resolution:** Accepted 2026-09-27. Influence report ships (`bible/08` §7).

### F-22 [P3] accepted - Hypothesis model strategies need pytest-django active

**File:** requirements-dev.txt
**Found:** 2026-09-27 during environment setup
**Why it matters:** `hypothesis.extra.django.models` raises
`ModuleNotFoundError` in a bare Python process, which looks like a broken install.
**Suggested fix:** None. It needs `pytest-django` running with a configured
`DJANGO_SETTINGS_MODULE`, so the strategies cannot be used before the Django
project exists. **This is why the four isolation invariants sit in Block C, not
Block B** — the ordering in `bible/08` is correct and now has a reason.
**Resolution:** Accepted 2026-09-27.

### F-23 [P3] accepted - Several dependency version pins were first written from memory

**File:** requirements.txt, requirements-dev.txt
**Found:** 2026-09-27 during environment setup
**Why it matters:** The first drafts pinned `djangorestframework==3.16.1`,
`drf-spectacular==0.28.0`, `pytest-django==5.3.0` and others that do not exist or
are stale. `pytest-django==5.3.0` made the install unresolvable.
**Suggested fix:** None needed — the resolver produced the real versions and
`requirements.txt` now carries them with a reason beside each. Recorded because
**it is F-11's lesson in miniature**: a version number recalled rather than
queried is a library claim recalled rather than executed.
**Resolution:** Accepted 2026-09-27. Pins are resolver output, not memory.

---

## Closed — found in the Blueprint spec layer, 2026-09-27

*Found by the first build-readiness audit: every claim in `blueprint/` and
`AGENTS.md` re-derived from the **given** inputs (`fixtures.json`, `run.py`,
`spec.md`) rather than read off the earlier bible. Five errors in a layer that
exists precisely to stop transcription. Closed in the same pass; the re-run of the
audit is the review that `closed` requires.*

### F-28 [P2] closed - The reviews-per-project histogram said 5@5; it is 4@5

**File:** `blueprint/context/project-overview.md:99`
**Found:** 2026-09-27 by re-deriving the histogram from `fixtures.json`
**Why it matters:** It is **F-01's exact failure mode, committed by the layer
written to forbid it.** The line said `8@2, 26@3, 3@4, 5@5`. Actual is
`8@2, 26@3, 3@4, 4@5`, and the mass invariant settles it: 8×2 + 26×3 + 3×4 +
**4**×5 = 126. Five at 5 would give 131.
**Suggested fix:** Generate the number. It is now `4@5` with the mass check
inline.
**Resolution:** **Closed 2026-09-27.** The instructive part: `bible/04` §2.1
always had this right because a script wrote it, and `project-overview.md` had it
wrong because I typed it. **The generated document was correct and the
hand-written summary was not** — which is the whole argument for the rule,
demonstrated against us.

### F-29 [P1] closed - "run.py machine-verifies 6 demands" — it runs 7 checks

**File:** `AGENTS.md`, `blueprint/context/project-overview.md` §2,
`blueprint/project-plan.md` C-5, `blueprint/config.json`
**Found:** 2026-09-27 by reading `build_checks` in `run.py`
**Why it matters:** It is the single most-repeated number in the plan, and it was
**wrong, and the real number is worse in a way that matters.** The truth is
**3 T1 + 4 T2 = 7 checks and no T3 or T4 checks whatsoever**:

| # | Tier | Check label |
|---|---|---|
| 1 | T1 | gallery is public |
| 2 | T1 | project from fixtures shown |
| 3 | T1 | closed event refuses submissions |
| 4 | T2 | judge sees own scores |
| 5 | T2 | judge cannot see peer scores |
| 6 | T2 | participant blocked |
| 7 | T2 | csv export works |

"Six of sixty" also implied there were **sixty machine-checked demands**. There
are not.
**Suggested fix:** State 7 checks, 3 T1 + 4 T2, and name them so a build session
can tick them off individually.
**Resolution:** **Closed 2026-09-27.** Corrected in all four files, with the seven
labels enumerated in `config.json`.

### F-30 [P2] closed - The tier hours in the project plan did not sum to the window

**File:** `blueprint/project-plan.md` §5
**Found:** 2026-09-27 by walking the cumulative clock
**Why it matters:** §5 claimed T1 = 9h and T2 = 13h. The build plan's features
give T1 = 4+5+5 = **14h** and T2 = 7+8 = **15h**, and its four rows totalled 44h
against a 69h window — silently omitting FEAT-08 (7h), FEAT-09/10 (7h) and the
four breaks (4h). A reader planning the build from §5 would have believed 25 hours
were unallocated.
**Suggested fix:** Derive the tier hours from the features, and show the
reconciliation.
**Resolution:** **Closed 2026-09-27.** §5 now reads 14/15/9/13 = 51h with the
remaining 18h itemised, and points at `build-plan.md` as the clock's source of
truth. **The build plan's own clock was checked and is correct**: cumulative
hours land exactly on all four declared break times (H+14, H+30, H+40, H+54),
total exactly 69h, and the freeze falls exactly at H+65 with 4h protected.

### F-31 [P2] closed - "60 demands in spec.md" — spec.md has no such numbering

**File:** `blueprint/project-plan.md` §5, `blueprint/context/project-overview.md` §11
**Found:** 2026-09-27 by reading `spec.md` directly
**Why it matters:** It implied the organizers published 60 numbered demands. The
brief is 14,861 bytes with **no demand IDs at all** — four tier lines, four file
descriptions and five required items. The 60 are `bible/02`'s own decomposition:

| Prefix | Count | Meaning |
|---|---|---|
| `REQ-T1` / `T2` / `T3` / `T4` | 7 / 6 / 5 / 5 = **23** | the actual tier demands |
| `REQ-RULE` | 9 | the binary rules |
| `REQ-DEL` | 11 | the eight deliverables + extras |
| `REQ-SCORE` | 4 | scoring criteria |
| `REQ-BONUS` | 4 | bonus challenges |
| `REQ-ZERO` | 9 | explicitly out of scope |

Attributing our own numbering to the brief overstates both the brief's precision
and our compliance surface.
**Suggested fix:** Say plainly that the IDs are ours.
**Resolution:** **Closed 2026-09-27.** §5 now shows the full breakdown and states
that the IDs are ours, not the organizers'. This is also the more useful claim —
an unverifiable traceability matrix is a liability in a write-up.

### F-32 [P2] closed - `run.py` always exits 0, so it cannot gate CI on its status

**File:** `run.py` (`return 0` at the end of `main`)
**Found:** 2026-09-27
**Why it matters:** Every check in it can FAIL and it still returns 0. A
`just check` that gates on the exit code would pass on a fully broken portal.
**Suggested fix:** Parse the report body, or wrap `run.py` in a checker that
counts `FAIL`.
**Resolution:** **Closed 2026-09-27 as a design constraint.** Recorded in
`config.json` (`"ALWAYS exits 0, so parse the body, never the exit code"`) and in
`AGENTS.md` §6. The wrapper is a FEAT-10 item; the `just check` recipe is in
`config.json` under `verify`.

### F-33 [P2] closed - The rule "generated, not transcribed" was unenforceable; there was nothing to run it

**File:** `tools/verify_spec.py` (new, 67 checks)
**Found:** 2026-09-27, immediately after F-28
**Why it matters:** We had stated the rule in six files and enforced it in none.
The bible's numbers were generated, but every number in the spec layer was typed
by hand — and F-28 proved that the hand-typed ones drift. **A rule with no
executable check is a preference.** The audit that found F-28…F-32 was a
throwaway script; without a permanent one, the next session retypes the same
numbers and gets the same drift.
**Suggested fix:** A stdlib-only script that re-derives the load-bearing numbers
from the **given** inputs and fails on disagreement.
**Resolution:** **Closed 2026-09-27.** `tools/verify_spec.py`, 67 checks, no
third-party imports, no venv, no Docker, no network — it has to work before
Phase A exists. It covers five groups: given-input integrity (SHA-256 pin),
`run.py`'s real check surface, the fixture census, the build clock, and spec
integrity. **Exits non-zero**, unlike `run.py`.

**The tool had three bugs of its own, found and fixed on first run** — a
transposed histogram dictionary, a `max()` over the wrong row, and a regex that
broke on the embedded asterisks in FEAT-09's line. All three produced **false
failures**, not false passes, and all three were in the checker rather than the
documents. Worth recording because the failure direction is the right one: a
broken checker is noisy, and a checker that passes everything is dangerous.

**It was then verified by mutation testing, because a checker that has only ever
passed is not evidence of anything.** Nine deliberate corruptions, all caught:

| Mutation | Result |
|---|---|
| `4@5` → `5@5` in the histogram (F-28's exact error) | 1 failure |
| `9 dual` → `8 dual` judges | 1 failure |
| Change one feature's hours in the phase header only | 6 failures |
| Change FEAT-01's hours (breaks the window total) | 9 failures |
| Wrong T1 demand count in the project plan | 1 failure |
| Wrong T2 tier hours | 1 failure |
| Stale findings tally in `AGENTS.md` | 1 failure |
| Push the overview past 20,000 bytes | 1 failure |
| Change one byte of `fixtures.json` | 1 failure (SHA pin) |

**Also corrected while auditing** — the gallery trap was an OR, not an AND.
`run.py` calls `fixture_titles(fixture, n=3)` and tests
`any(title in body for title in titles)`, so **any one** of the first three
projects satisfies it, and `TIMEOUT = 10` is confirmed at `run.py:57`. The
previous wording ("greps only the first three projects") was ambiguous about
whether all three were required. Both `AGENTS.md` and the overview §6 now state
the `any()` explicitly.

---


*All found by re-deriving from `fixtures.json` or by executing the installed
stack. All verified fixed in the bible, then re-reviewed. Full narrative in
`bible/README.md` § Verification status and § Findings we contributed upstream.*

| ID | Sev | One-line | Closed by |
|---|---|---|---|
| F-01 | P2 | Projects-by-review histogram `8/22/9/2` implies 128 rows; the file has 126 | invariant 2, `bible/04` §2.1 |
| F-02 | P2 | Judges-by-review histogram summed to 29; there are 30 | invariant 1, `bible/04` §2.1 |
| F-03 | P2 | Three judges guessed severe; two are above the panel mean | recomputed, `bible/06` §4.1a |
| F-04 | P3 | Criteria key order is `functionality, quality, innovation` — a CSV writer deriving order from row 1 transposes two columns in every export | `bible/04` §1 |
| F-05 | P2 | `jdg_07` is the **4th** most generous judge of 30, not the 7th | sorted the means, `bible/06` §4.1a |
| F-06 | **P1** | The per-judge severity table listed **26 rows for a 30-judge population** — the table the whole normalization argument rests on | invariant 1, `bible/06` §4.1a |
| F-07 | **P1** | "Two tracks are structurally infeasible" is **false** — 18 needed, 18 possible, a perfect matching exists. They are **zero-slack**, and provably infeasible at capacity 5 | max-flow, `bible/06` §2.1a |
| F-08 | P2 | **Three** tracks missed the target, not two; the event nets +3, so a global bar hides three local failures | per-track counts, `bible/06` §2.1a |
| F-09 | P2 | "123 assignments vs 126 score rows confirms target 3" is not a valid inference; the real evidence is the mode, 26 of 41 at exactly 3 | `bible/06` §2.1 |
| F-10 | **P1** | `median(\|x − med\|)` over one element is 0 for a *structural* reason, identical to `jdg_07`'s evidentiary zero. Shipped answer was right by coincidence; the code contradicted the document | `bible/06` §4.2a |
| F-11 | **P1** | `bible/03` §3.2 claimed DRF's `SessionAuthentication` is CSRF-exempt **by default**. It is not — `enforce_csrf` is defined and called. **A CSRF 403 is a 4xx, so T1-3 would have passed without the deadline ever being tested** | executed the installed DRF, `bible/03` §3.2 |
| F-12 | **P1** | Seeding all 121 fixture people costs ~48 s at ~400 ms per `pbkdf2_sha256` hash — **4.8× `run.py`'s 10 s timeout**, inside the process gunicorn waits on. Only 5 identities should get real hashes; the other ~116 get `UNUSABLE_PASSWORD` | timed the hasher, `bible/04` §5.2, `bible/03` §4.7 |

**The pattern worth carrying forward.** F-01/02/06 were all the same rule: a
histogram must satisfy both *cardinality* (bucket counts sum to the population)
and *mass* (`Σ n × count` equals the record count). Two of the three were found
**after** we had already published a correction log about the first four — which
is worse than the original error, because a correction log containing un-caught
errors teaches the reader to distrust the process rather than the number.

F-11 and F-12 are the same lesson in a different medium: **a documented library
default, recalled rather than executed, was backwards.** Hence the standing rule
in `blueprint/config.json` — `verify_against_the_installation`.

---

## Upstream — findings we contributed to the organizers

*Not defects in our code. Tracked here because they change what we build, and
narrative in `bible/README.md` § Findings we contributed upstream.*

### F-24 [P2] closed - The published σ = 0.94 is not obtainable from fixtures.json

**File:** external (the brief)
**Found:** 2026-09-27 by re-derivation
**Why it matters:** Four natural definitions of judge spread; the largest is
0.4323. 0.94 is unreachable by any of them.
**Suggested fix:** None available to us. Report the measurement with its
definition.
**Resolution:** **Closed 2026-09-27 — organizers confirmed a bug in the website
description, likely a cosmetic landing line absent from `/spec`, and corrected
the homepage to σ = 0.42, which matches our 0.4323.** Their instruction: build
the proof against the actual fixture values. This became our highest-value
contribution and is `bible/README.md` U-1.

### F-25 [P2] closed - The fixture has no measurable judge-severity effect

**File:** bible/06 §4.1b
**Found:** 2026-09-27 by variance decomposition
**Why it matters:** Between-judge variance 0.0217 against a sampling-noise floor
of 0.0971 at n̄ = 4.2; permutation **p = 0.234**; detection floor **τ ≈ 0.75**.
**Suggested fix:** None. This is a property of the published data.
**Resolution:** **Closed as a published finding, not a question.** It anchors the
proof's ordering in `bible/06` §4.4a: the predictive result leads, the null
supports it, the recovery experiment validates it.

### F-26 [P2] closed - Synthetic data approved for the Normalization Proof

**File:** external (Discord)
**Found:** 2026-09-27
**Why it matters:** Determines whether the recovery experiment ships. It is the
part that proves *correctness* rather than absence of harm.
**Suggested fix:** None needed.
**Resolution:** **Closed 2026-09-27 — "Yes, synthetic data is fine for validation
as long as the proof also runs on the real fixtures. Showing it recovers a known
effect is exactly the kind of rigour the bonus is looking for."** Condition met by
construction: three of four proof components use the published 126 reviews with
nothing simulated, mapped in `bible/06` §4.4a, and
`docs/REAL-FIXTURE-RESULTS.md` isolates the real-fixture half.

### F-27 [P1] unverified - The published normalized figure of 0.31 is reproducible by a global standardization

**File:** external (the brief)
**Found:** 2026-09-27 by sweep
**Why it matters:** Three panel-level standardizations, none containing a
per-judge term, land at 0.3174 / 0.3240 / 0.3301 — all within 7% of 0.31. That is
consistent with F-25. **We do not know their definition, so this is
`unverified` and not `open`.**
**Suggested fix:** None. **The DM asking about it was dropped by decision** — we
got a yes to the one question that mattered and a second message to a moderator
is worth less than not asking twice.
**Resolution:** Stays a private observation in `bible/06` §4.4c, phrased as a
possibility with *"offered as a question rather than a correction, because we do
not know their definition and we may have the wrong one."* If a future session
finds a definition that matches, promote this to `open`.

---

## The rule that keeps this honest

**Run the spec gate before trusting any number in this project.**

```bash
python tools/verify_spec.py      # 67 checks, stdlib only, exits non-zero
python tools/verify_spec.py -q   # only failures
python tools/verify_spec.py --list
```

It re-derives the census in `project-overview.md` from `fixtures.json`, reads
`run.py`'s check surface from its source, walks the build clock, and checks that
every `bible/… §x.y` citation resolves. It has already caught five wrong numbers
that a careful read missed (F-28…F-32), and it was mutation-tested against nine
deliberate corruptions before being trusted (F-33).

This ledger reports status. **It never defines what a review looks at.** Every
pass reviews the work fresh and then updates this file with what it found.
Working from the open findings as a checklist and verifying only those is exactly
how a repair-introduced defect ships unnoticed.
