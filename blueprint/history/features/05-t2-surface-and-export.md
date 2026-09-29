# FEAT-05 — Isolation enforcement, the T2 surface, the CSV export

**Completed:** 2026-09-29 · **Planned:** 8h · **Gate:** none (next gate is
BREAK-2, tag `v-t2-verified`)

## The acceptance line, and whether it passed

`build-plan.md` Phase E, both clauses, on a clean database:

| Clause | Result |
|---|---|
| `run.py` passes T2-4 and T2-5 | **pass** — in fact **7 of 7 checks pass**, `claimed T1, verified T1 T2` |
| the T1/T2 `verified` ceiling is expected and explained in the README | **pass** — explained as arithmetic in their checker, with the claim still deliberately unclaimed |

**All four T2 checks have been failing with real URLs since the first commit.
They now pass**, and each one passes with a precondition that makes the pass mean
something — which is the part that took the time.

## What was built

- **`src/reviewer/reviews/api.py`** — `GET /api/v1/judge/scores` and
  `GET /api/v1/export.csv`. Plain Django views, and the reason why is the most
  important paragraph in the file.
- **`src/reviewer/isolation/refusal.py`** — the portal's **single** refusal
  primitive, promoted out of the console so the API and the console cannot drift
  on D-02. `console._deny` is now an alias, which is why two console mutations
  went `pattern not found` and were re-pointed rather than tolerated.
- **The scoped score endpoint**, with a scope receipt, four accepted spellings of
  the subject (`judge_a`, `jdg_01`, an email, a pk), and a 400 for a subject that
  does not exist rather than a silent fall-through.
- **The CSV export**, read through `for_actor(actor)`, refused to a judge with a
  403, header in the fixture's **key** order.
- **`header_must_contain` and `path_suffix`** in the acceptance gate's probe
  machinery, plus two new probes.
- **34 new tests** (340 → 374) in three modules.

## The finding you should read first: F-70, the one no gate could see

`just lint` went red on line lengths. The fix is `ruff format`, and **`ruff
format` with no path argument formats the whole repository** — including
**`run.py`, the acceptance program the panel runs.** It rewrote 54 lines of it,
plus `bible/03`, `bible/05` and `JUDGING.md` (ruff 0.16 formats Python fenced
blocks inside Markdown) and `docker/healthcheck.py`.

`run.py` is a **given input**. We ship the report it produced, and a submission
that machine-reformatted the organizers' checker is claiming to run something
identical while shipping something different. And the diff was whitespace-only,
so **nothing noticed**: `verify_spec.py` parses `run.py` for its check surface
and still passed 68/68, `just check` printed GATE GREEN, and the acceptance report
was byte-identical.

**That is the property that makes it the worst-shaped finding in the project:
every gate we have is a semantic check, and this change was semantically
identical.** Not found by a test, not found by a diff review, and not findable by
either — found by reading `git status` after the last gate run, when the tree was
*supposed* to be clean and wasn't.

Restored with `git checkout`, and `pyproject.toml` now excludes `run.py`, `bible`
and `*.md`, extending the decision already recorded against `tools/verify_spec.py`
(F-43) from *our* gate to *the file we do not own*. **Proven by re-running the
command that caused it:** `ruff format` with no path now leaves 91 files unchanged
and `git status` on those paths is empty.

**The rule: a gate can only catch a change it is looking for, so a class of change
with no gate needs an exclusion rather than a test.**

## The decision that mattered: plain Django, not DRF

DRF is installed and configured. Writing the two `/api/v1` routes as viewsets is
the obvious move and it would have been a bug **that the gate reported as green.**

`DemoCredentialMiddleware` resolves `Authorization: JJ1…` and assigns
`request.user` before the view runs. **DRF does not read that attribute** — it
builds its own `Request` and populates `request.user` from
`DEFAULT_AUTHENTICATION_CLASSES`, which is `SessionAuthentication` alone. A
header-only client has no session, so every request would have arrived
`AnonymousUser` and been refused — and **three of the four T2 checks want a 403.**

That is the expensive part. It is not a red check. The refusals would have been
*correct-looking*: participant refused, peer refused, empty body, no `Location`,
the whole D-02 contract satisfied by something that never read a score.
`judge cannot see peer scores` and `participant blocked` would have gone green
for a reason that has nothing to do with isolation. **F-40 exactly, and F-40 is
filed as the most expensive shape of bug there is: a false pass is believed.**

So the routes are plain Django views reading `request.user`, the same way the
judge console does. The OpenAPI document is a FEAT-07 item and will be a schema
*over* these views, not a replacement — the refusal contract is the part that
must not change.

## The other three that mattered

**F-69 (P1) — the export's first column was 126 empty cells.** `Review` inherits
`source_key` from D-11, and **the loader never writes it** — it keys a review on
`(judge, project)`. The export printed `review.source_key`, producing a
structurally perfect CSV in which one column contained nothing. No acceptance
check failed, the header was right, and `run.py` got a 200.

**It is F-61's shape for the third time**, in a different medium each time: a
min-cut certificate naming no judges, a leaderboard refused for the wrong reason,
and now a column of nothing. **The reason the header test could not find it is the
point: a test that asserts the header is testing the header.** The test that caught
it asserts every cell of every row against the database, keyed by criterion — which
is also the second half of F-04's assertion, since a correct header with
positionally paired values is the same defect with the evidence removed. Fixed by
a natural-key fallback, with a general "no column is empty throughout" test so the
next one is caught by shape rather than by name. **The underlying gap belongs to
FEAT-07**, which owns `source_key` and the round trip.

**F-67 (P2) — the "16/16 on the new modules" claim was reproducible by nothing.**
`tools/mutation_test.py` had one `MUTATIONS` list of 18, none touching
`reviewer/assignment/` or `console.py`, while three documents quoted the 16. The
sixteen were written into the harness; **`just mutation-test` now reports
44/44**. Two new patterns came back `pattern not found` on the first run and were
reported as a harness defect rather than a pass — F-46 working as filed.

**The interesting half is a gap in F-59:** *every command named in a document
exists* is not the same claim as *every number quoted about a command can be
re-derived by running it*. Only the first is cheap to check, and a number attached
to a command drifts exactly like one attached to a fixture.

**F-68 (P3) - the cold start, published as a range.** Documented 12.0 s; measured
19.9 s, then **12.1 s twenty minutes later on the same machine**. Two runs of the
same command on the same clean volume, a factor of 1.6 apart. So the original
12.0 s was not a stale number but a **lucky** one, and no single value in any
document was right more than about half the time. Both documents now carry
**12-20 s observed against a 60 s budget**, and `tools/coldstart.py` is the only
place an exact figure appears, because it is the only place one is reproducible.
**A number with no regeneration path must be published as a range and a budget,
never as a value.**

**F-51, decided — and it went against the interim code.** The guard is now
`actor.is_judge and not actor.can_read_all_reviews`, so the two accessors agree
for every actor. The reasoning is the interesting part: the strict reading was not
the safe one, it was the **incoherent** one, because the organizer-scoped
`/api/v1/export.csv` contains every score in the event and so the refusal
protected nothing. A judge-organizer is not a peer-blind actor, and **the accessor
is not what makes them one** — that rule is the leaderboard-while-judging-is-open
refusal, which is FEAT-06. The docstring says so, because closing F-51 quietly
would close a question rather than answer it.

## The trap the new gate machinery fell into, and how it was caught

FEAT-05 added `header_must_contain` and `path_suffix` to the probe machinery.
**Four deliberate corruptions of that machinery were run before any test
exercised it, and three produced no failure at all.** Removing the header check,
making it always match, and ignoring `path_suffix` all left the suite green.

The cause is structural and it is worth naming for the next feature: **the probes
only ever run against a live container inside `just check`, so adding a probe is
adding code whose tests do not exist yet.** A check that cannot fail is worse than
no check. `TestTheApiProbes` now drives `run_probe` and `judge_probe` against the
same faithful stubbed `urlopen` as `TestTheDeadlineProbe`, and all five
corruptions are caught, each naming the rule:

| Corruption | Caught by |
|---|---|
| `header_must_contain` check removed | `test_a_refusal_with_an_empty_body_and_no_reason_is_caught` and 3 more |
| `header_must_contain` always matches | 3 tests |
| `path_suffix` ignored | `test_the_peer_probe_visits_the_peer_url` |
| `must_not_have_header` removed | both probe classes |
| peer probe falls back to the role guard | 5 tests |

`path_suffix` is the sharp one. Without it the probe would GET the **bare** route
as judge_b and be refused by the *role* rule — a correct refusal of the wrong
check, leaving `for_actor_and_subject`'s peer-blindness unverified by the one gate
whose entire job is to verify it, while the gate stayed green.

## How it was verified

| | |
|---|---|
| Acceptance line | **both clauses pass** on a clean volume |
| `just check` | **GATE GREEN** — 7 passed, 0 failed, of 7 checks |
| Suite | **374** (340 → 374; 22 API + 10 gate + 2 restructured) |
| Mutations | **44/44** (18 → 44; 16 FEAT-04 + 10 FEAT-05), re-verified after `ruff format` (F-46) |
| `tools/verify_spec.py` | **68/68** — and it caught me twice: a stale quoted file size after I edited the overview, and the overview blowing its 20,000-byte cap (F-28's rule, enforced) |
| Lint | clean — and **JJ01 caught an unscoped `Review` read in a test I had just written**, which is D-01 working |
| Migrations | none needed; no schema change |
| Given files | **`run.py`, `bible/`, `JUDGING.md` verified byte-identical to `HEAD`** after F-70 — the organizers' program is untouched |

## What I would tell the next session

**The ratchet moves, and moving it breaks the gate's own tests — read the failures
before assuming the code is wrong.** Flipping four expectations from `fail` to
`pass` correctly turned every synthetic report with a T2 FAIL into a
**regression**, and four tests in `test_gates.py` went red for that reason. Two of
them were about the *milestone*, not the code, and one had become **unreachable
against the real file**: with all seven checks marked `pass`, there was no entry
left to make stale, so the stale-expectation branch now runs against a
**temporary expectations file** via the `--expectations` flag that already existed.
Deleting the test was the wrong repair; editing the real file to make it fire would
have been worse.

**`tools/mutation_test.py` is the first thing to re-run after any `ruff format`.**
It went `pattern not found` twice during this feature — once from my own
indentation guess, once because the `_deny` refactor moved the code the mutation
pointed at. Both were reported as harness defects, which is the behaviour F-46 was
filed for, and both were fixed by re-pointing rather than by loosening the report.

**`for_actor` and `for_actor_and_subject` now agree, and the test that pins it
asserts *equivalence*, not refusal.** The previous version asserted only that a
judge-organizer was refused, so a rule that fired on *everyone* would have
satisfied it perfectly. There is a separate test that a *pure* judge is still
refused, because a guard that grows a clause can grow it the wrong way.

**FEAT-06 inherits a named gap.** A judge-organizer currently reads every score
through the bare route and the export. The rule that should stop that — *the
leaderboard is refused while judging is open* — is the aggregate cell the
isolation proof prints as `?` and that its own "STILL NOT PROVEN" list already
names as "the aggregate cell nobody tests and everybody forgets."
