# FEAT-13 — Organizer settings: the lifecycle, in a browser

**2026-10-01** · `src/reviewer/events/settings_view.py`,
`src/templates/organizer/settings.html`, `tests/test_organizer_settings.py`
**29 tests, 7 findings (3 P1, 4 P2), 0 open blocking.**

---

## Why this was the last gap

FEAT-11 made an empty database into a runnable event from a browser, and FEAT-12
made it importable. Both stopped one step short, and the step was the same one:

> An organizer finished `/setup/` in a browser and then had to drop to
> `docker compose exec` to open the submission window, open voting, or publish
> results — because `publish_results` is a management command and the deadlines
> have no editable surface at all.

**A tool whose lifecycle ends in a shell is a tool for the person who built it.**
That is the whole argument, and it is why this was built after the features that
made the shell unnecessary for *loading* data.

### What is editable, and why that list and not a bigger one

| Editable | Why it is on this page |
|---|---|
| The windows (start, submissions close, judging close) | The only thing gating submissions, so they have to be reachable |
| The voting mode and its window | Provisioning creates every event with `voting_mode="closed"` — the safe default, because a public vote nobody can deduplicate is the free-for-all REQ-T3-01 names. **Without this a fresh deployment can never take a public vote at all.** |
| Publishing results | Through `reviewer.audit.publication.publish`, never a field write |

The three voting modes are genuinely different products, which is why the mode is
a choice rather than a boolean: `open_link` needs no account, `email_gated` and
`authenticated` do.

### What is deliberately not editable here

- **The rubric's criteria and weights.** A judge who has already scored under one
  rubric must not see the board move underneath them; `rubric_weights_locked_at`
  exists for that, and unlocking it is a deliberate act rather than a field in a
  form.
- **Track membership of a project**, because it decides which judges can see it.
- **Anything about isolation.** No setting here can widen what an actor reads,
  and a settings page is exactly where somebody would try.

`TestNoSettingWidensAccess` asserts this **as an absence** — by regex over the
rendered inputs, against `results_state`, `reviews_per_project`,
`assignment_seed`, `judge_capacity`, `track`, `weight`, `criteria`. Asserting the
absence is the only way it stays true when somebody adds a convenient-looking
checkbox, and `results_state` is on the list precisely because it must go through
`publish()`.

---

## The findings: seven, and three were 500s only an organizer could reach

**None was found by reading the code.** They came from running the page's own test
file, and the distribution is the lesson.

| ID | P | One line |
|---|---|---|
| F-118 | P1 | A form omitting a date wrote `None` into a `NOT NULL` column — **and the Publish button was the trigger** |
| F-119 | P1 | The validation path raised `KeyError`, so the validation error could never render |
| F-120 | P2 | A partial POST skipped every ordering check |
| F-121 | P2 | A no-op save wrote audit entries, because a form cannot express sub-second precision |
| F-122 | P1 | Every save 500'd on the `Actor`/`User` confusion |
| F-123 | P1 | Publishing an event with no rubric was a 500, behind a button that offered it |
| F-124 | P2 | `errors.__all__` again — F-106's construct, in a new template, an hour later |

### The rule that came out of it

> **Two buttons on one save path means the weaker form's omissions are the
> stronger form's bugs.**

Publishing and saving shared one code path, and the publish form deliberately
carried only the fields a publication needs. So the *smaller* form's omissions
became the *stronger* form's `IntegrityError`. The repair is structural rather
than defensive: `action=publish` short-circuits **before any field is parsed**, and
the template's hidden inputs are gone — because a form that restates the settings
has to restate them correctly or it is a second, worse way to write them.

**Absent now means unchanged.** A field is written only when the request actually
carries it, which is what lets a partial POST be safe and a full form still clear
a window by submitting it empty.

### Three 500s, one guard

F-118, F-122 and F-123 were all crashes on `/organizer/settings/` — and **every
guard test passed throughout.** The guard is the *first* thing the view does, and
every one of these bugs was in what came after it. The tests that existed were the
ones that had been written to pass; the ones that failed were the ones asserting a
property nobody had thought to state. That is the same shape as FEAT-12, and it is
the reason this archive leads with the distribution rather than the fixes.

### A fixture that made three tests pass while testing nothing

The `world` fixture built no rubric, so `publication.publish` raised `ValueError`
on every publish test — and **all three were green as refusals.** The hash, the
input digest and the chain head were never executed at all. F-123 is recorded as a
crash, but its real content is the coverage hole underneath: `make_rubric` in the
fixture is what turned a passing test into a real one.

### One defect introduced by repairing another

F-119 lived on the same line as F-118. The unparseable-date branch set
`errors[field]` and skipped assigning `after[field]`, and the ordering checks read
`after[...]` unconditionally — a `KeyError` instead of the intended 400. It was
**masked** until F-118 was fixed by restoring the previous value from the event,
which made it reachable. Repairing a defect in a validation path is exactly where
a second one hides.

### F-121, and why the audit trail now compares rendered values

`test_a_no_op_post_writes_nothing` failed with **two** entries where zero were
expected — and the view's logic was not at fault. `datetime-local` carries whole
minutes, a stored `starts_at` carries microseconds, and the two compare unequal.
**An organizer who opened the page and pressed Save having changed nothing logged
two changes to an append-only chain.** `_record` now compares the values *as the
form renders them*. The chain's job is to answer "when did judging close", and
"sub-second precision was dropped by a date picker" is not an answer to that.

### F-124, and a finding about the lint rule rather than the template

`{{ errors.__all__ }}` — the same illegal construct as **F-106** — in a new file,
in the same session that recorded F-106's repair. F-106's rule fires *per-template*,
so a template added after the rule was written is not covered until someone writes
it. Recorded separately rather than folded into F-106 because **the recurrence is
the finding**: a rule that catches the sixth instance but not the first of a new
file is a rule being applied by memory.

---

## What is asserted

29 tests, grouped by the property each one defends rather than by function:

- **`TestTheGuard`** — anonymous, judge, and participant each get the portal's own
  **bare 403 with an empty body** and the guard named; **a refused POST changes
  nothing** (a GET-only guard is not a guard); no event is a 403 rather than a 404,
  because a 404 is indistinguishable from a mistyped URL (F-40).
- **`TestNoSettingWidensAccess`** — the absence assertions above.
- **`TestTheWindows`** — save, and each of the four ordering rules refused **by
  name**; a refused POST leaves the event alone; a partial POST keeps `starts_at`
  (F-118); publishing depends on no settings field at all (F-118's structural fix).
- **`TestVoting`** — a fresh deployment can be moved to `open_link`; an unknown
  mode is refused rather than stored; and **every mode in the schema is
  selectable**, because the list imports the constants and a new mode that cannot
  be turned on would otherwise pass unnoticed.
- **`TestTheAuditTrail`** — a change records its old and new value; **a no-op post
  writes nothing** (F-121, the F-80 shape for a log).
- **`TestPublishing`** — a publication gets a hash; the call to
  `publication.publish` is **pinned by monkeypatch, so a settings page that
  published by other means would raise rather than quietly succeed** (F-92's shape
  in a new place); publishing twice **adds a row rather than editing**, because the
  history of publications *is* the tamper evidence.
- **`TestPublishingWithNothingToPublish`** — no rubric is refused **in words**,
  not a 500, and the button is hidden (F-123).

---

## The evidence chain

| Gate | Result |
|---|---|
| `pytest` | **906 passed**, 1 skipped (907 collected) |
| `just mutation-test` | **114/114** caught |
| `tools/verify_spec.py` | **75/75** |
| `just lint` | All checks passed, 167 files formatted, JJ01 clean over **196** files |
| `just check` | **GATE GREEN** — 7 of 7, `claimed T1 T2, verified T1 T2` |
| `just prove-offline` | **PROVED** — healthy after 8.2 s, widget renders with no network |
| `just report` | 7 of 7 PASS, **`git diff acceptance-report.txt` empty** |

The spec gate earned its place during this feature: **within a minute of adding
the seven findings it failed three checks**, because the tallies in `AGENTS.md`,
`project-overview.md` and `README.md` were still 117. They are now 124, and the
suite count was corrected from 877 to 906 in the same pass. **Generated, not
transcribed** — F-72.

---

## What this feature cost, honestly

- **The page was unreachable for most of its life.** Three of the seven findings
  are 500s on the organizer's only lifecycle surface, and the guard tests were
  green the whole time. The product was "finished" by its own test names.
- **Two findings were only findable by asking what a *form* can express**, not
  what the code computes (F-118, F-121). Neither would have been caught by a
  unit test of the view's logic; both came from the form and the storage disagreeing.
- **A test file's fixture is part of the product's test coverage**, and a fixture
  that omits a precondition converts a suite into a set of assertions about the
  refusal path (F-123).

The next honest step is not more features. It is that **every surface an
organizer touches is now reachable, and each of them was found to be broken in a
way its own tests could not see** — which is the argument for treating the
existing surfaces, rather than adding new ones, as the next place to look.
