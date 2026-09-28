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
below. F-38 (the ambient `python` is 3.14.6) was closed at FEAT-01.

**FEAT-03 opened three P1s and closed all three in the same feature**: F-49 (123
blank-password accounts), F-50 (`UNIQUE (event, name)` violated by the fixture)
and F-55 (a credential format that could never verify). **No P0 or P1 is open,
so nothing currently blocks a feature from being marked done.** The rate is
worth noticing rather than explaining away: this was the first feature that ran
our code against the organizers' *data* instead of data we built, and the
findings are almost all values that agreed with what we expected.

## Resolved — found in FEAT-03, 2026-09-28

*Eight findings from building the loader, the gallery and the deadline guard.
**Six of the eight are P1 or P2 and every one of them changed a shipped
artefact**, which is a higher rate than any previous feature and is worth a
sentence about why: this was the first feature that ran our own code against
the organizers' *data* rather than against data we built. Four of the eight are
values that agreed with what we expected and disagreed with what the file said.

F-48 is `closed` and was re-verified at BREAK-1: `just accept` prints the report
and `just coldstart` measures to a serving page. It stays in the *Open* section
below only as a historical placement, corrected as **F-57**.

### F-49 [P1] closed - 123 accounts with an empty password, and an empty password authenticates

**File:** `src/reviewer/importer/loader.py`
**Found:** 2026-09-28, at FEAT-03, by the seed's own census
**Why it matters:** The loader's first version guarded its password writes with
Django's own predicate:

```python
if not user.has_usable_password():
    user.set_unusable_password()
```

which looks exactly right and is **false for a row that has just been created**:

```
is_password_usable("")   ->  True
has_usable_password()    ->  True   (password == "")
check_password("", "")   ->  True
```

So on a first run every one of the 121 fixture people was *skipped*, and the
database was left with 121 rows whose credential was the empty string — plus the
two portal-created organizers, **123 accounts that authenticate with a blank
password.** The five demo identities were skipped too, so `passwords_hashed`
printed **0** and the seed's own self-test (which had not been written yet) had
nothing to catch it.

**The census caught it, and only because the census row exists.** `verify_census`
prints `accounts.User with a real hash` against a derived expectation of five,
and 0 ≠ 5. A row-count census would have said "123 users, looks fine".

**The fix is a prefix comparison against `UNUSABLE_PASSWORD_PREFIX`, in one named
function** (`_lacks_credential`) used in both directions, because the predicate
has to be right twice: write an unusable marker when there is no real hash, and
write a real hash when there is only a marker. A separate test
(`TestPasswords::test_a_fixture_person_cannot_log_in_with_an_empty_password`)
asserts `check_password("") is False` on a fixture person, which is the claim
that was false.

**The generalisable lesson, and it is F-11 in a new medium:** a library
predicate recalled rather than executed. `has_usable_password()` reads like
"does this account have a working password" and answers a different question —
"is the stored value something other than the unusable marker" — and for the
empty string those two questions have opposite answers. The production hasher is
still pbkdf2; only the suite swaps in MD5, and a test asserts the settings
module does not mention `PASSWORD_HASHERS` at all, so the fast suite cannot
become a fast portal.

### F-50 [P1] closed - `UNIQUE (event, name)` on `Team` is violated by the organizers' own fixture

**File:** `src/reviewer/teams/models.py`, migration `0002_remove_team_...`
**Found:** 2026-09-28, at FEAT-03, by the loader raising `IntegrityError`
**Why it matters:** The schema FEAT-02 shipped declared
`UniqueConstraint(fields=["event", "name"])` on `Team`, and the loader died on
the published fixture:

```
IntegrityError: UNIQUE constraint failed: teams_team.event_id, teams_team.name
```

**40 teams carry 36 distinct names.** `StillTrail` appears three times
(`tm_03`, `tm_30`, `tm_40`), `OpenSignal` twice, `AmberSwitch` twice — and two
of the colliding teams own different projects, so it is a property of the data
and not a fixture typo.

This is the same class as F-49 and it is the same lesson from the other side: a
constraint we designed, that no test could catch because the test data was ours,
and that the *real* input violates. Two teams named "Team Rocket" at one
hackathon is a Tuesday.

**Resolution:** The `(event, name)` constraint is **dropped**, by a named
migration rather than by an edit to `0001`, so the history records a constraint
that was tried against real data and corrected. `(event, slug)` is kept — a slug
is derived, so it is the column that has to be unambiguous for a URL to mean one
team — and the module docstring states the trade in the same terms
`teams/models.py` already used for the absent "one team per user per event"
constraint.

### F-54 [P2] closed - `slugify` collapses three fixture team names onto one slug

**File:** `src/reviewer/importer/loader.py`, `src/reviewer/importer/census.py`
**Found:** 2026-09-28, at FEAT-03, one error after F-50
**Why it matters:** With the name constraint gone, the *slug* constraint failed
instead. `slugify` is lossy — it drops case and punctuation — and three team
names collapse: `amberswitch` ← `tm_05`, `tm_34`; `opensignal` ← `tm_11`,
`tm_16`; `stilltrail` ← `tm_03`, `tm_30`, `tm_40`. Both `Track` and `Team` are
`UNIQUE (event, slug)`, so a loader deriving the slug from the name alone raises
`IntegrityError` part-way through, with a message that reads like a schema bug.

The same shape appears for projects: `prj_07` and `prj_41` are one team, one
title, and `(team, slug)` is unique.

**Resolution:** `_entity_slug(name, natural_id)` appends the fixture id, and
`_project_slug` appends the numeric suffix. **And the census now reports the
collisions on every boot** rather than leaving the loader to raise — a seed step
that prints its own anomaly report is doing the reader's verification work, and
"three names collapse onto one slug" is a sentence a reviewer can check.

### F-55 [P1] closed - the demo token's first layout could never verify, and failed silently

**File:** `src/reviewer/accounts/demo_tokens.py`
**Found:** 2026-09-28, at FEAT-03, when the participant header arrived anonymous
**Why it matters:** The role-proving token was laid out as
`JJ1.<email>.<signature>` and parsed with `token.split(".")` expecting three
parts. **An email address contains dots.** `priya1@example.org` is three
dot-separated fields, so every token in the fixture produced **four** parts, the
length check rejected all of them, and `email_from_token` returned `None`.

The failure mode is the expensive one: `email_from_token` returns `None` for
"malformed" and for "wrong signature" alike, so the symptom was a demo identity
that **simply never authenticated** — no exception, no log line, and every
acceptance check still passing on the resulting 401. It was found by reading a
401 that should not have been a 401, which is the only reason it was found at
all.

**Resolution:** The signature comes **first** — `JJ1.<hmac>.<email>` — and the
signature's fixed width is checked before it is compared, so the split is
unambiguous rather than lucky. The committed `.dogfood.toml` values were
regenerated and are asserted against the identities the seed promotes, by
`tests/test_demo_credentials.py`, so an emptied or hand-edited value fails the
suite rather than the acceptance report.

### F-51 [P2] fixed - `for_actor_and_subject`'s docstring described behaviour the code does not have

**File:** `src/reviewer/reviews/queryset.py`
**Found:** 2026-09-28, at FEAT-03, by a Hypothesis counter-example
**Why it matters:** The docstring said *"Organizers and admins legitimately ask
about any subject, so this falls through to `for_actor` for them."* The guard is
`actor.is_judge`, so a user holding **both** a judge binding and an organizer
binding is **refused** when they ask about a peer — even though `for_actor`
alone hands that same user the whole event. The two accessors disagree, and the
comment said they did not.

It surfaced because the first version of Hypothesis invariant P2 was stated
over *every* role set, and is false: with `roles = ['judge', 'organizer',
'participant']` the actor legitimately saw three other judges' reviews. The
falsifying example arrived in about two seconds.

**A judge who also organises is the ordinary case at a hackathon, not a
misconfiguration** — the same premise F-45 was found on — so this is a real
question, not a typo.

**Resolution, and the reasoning is the point:** the **code is kept** and the
**docstring corrected**, because the strict reading is the safe one and nothing
can reach that accessor until FEAT-05 builds the route that does. Widening an
access rule to match a sentence in a comment is the wrong repair at this hour;
recording the ambiguity for the feature that owns the judge console is the right
one. Both halves are now pinned by tests — the organizer-only fall-through and
the judge-organizer refusal — and P2 is restated over the roles it is actually
about, with the counter-example quoted in its docstring.

### F-52 [P3] closed - this ledger's own F-28 entry has the wrong mass arithmetic

**File:** `blueprint/context/findings.md`, the F-28 entry
**Found:** 2026-09-28, at FEAT-03, while writing the test that injects F-28
**Why it matters:** The entry says the mass invariant settles the histogram and
quotes the sum as `8x2 + 26x3 + 3x4 + 5x5 = 126`. That sum is **131**. The
buckets also total **42**, not 41, so **cardinality catches it too** — the entry
credits one invariant when the argument for having two is that both fire.

The correct histogram is `8@2, 26@3, 3@4, 4@5`: 8·2 + 26·3 + 3·4 + 4·5 = 126, and
8+26+3+4 = 41. `project-overview.md` §5 has it right; the ledger entry was the
transcription error.

**Finding a transcription error inside the entry about transcription errors is
not a surprise at this point, and it is not a reason to stop writing them down.**
**Resolution:** Corrected above and in place, and the test that injects F-28's
exact typo now asserts **both** invariants fire, with the arithmetic inline, so
the claim is checkable rather than remembered.

### F-53 [P3] closed — `bible/04` §5.2 names a track the fixture does not

**File:** `bible/04-FIXTURES-DATASET-BIBLE.md` §5.2
**Found:** 2026-09-28, at FEAT-03, while deriving the demo identities
**Why it matters:** The bible's table of the five seeded identities says
`judge_b` is `jdg_07` bound to **`trk_03`**. The fixture says `jdg_07` is bound
to **`trk_06`**. `jdg_08` is `trk_04`, not the `trk_04` the same row claims for
`judge_a` — that one is right.

So a planning document carried a transcribed track id for a person, which is
F-28's shape, and it survived the audit that produced F-28…F-32 because the
audit checked *histograms*, not per-person track bindings.

**Resolution:** The loader does not use the bible's ids at all. `importer.demo`
**derives** the demo identities from the fixture by a stated rule — the lowest-id
judge with at least two reviews on exactly one track, then the lowest-id judge on
a *different* track — so the choice is a pure function of the file and a
transcribed id cannot reach it. The bible's specific ids are left as they are
written: it is a research document, and the fix belongs in the code that was
wrong to depend on them.

**One entry below is `fixed` and deliberately not `closed`: F-51.** The code is
right for now and the docstring now matches it, but the underlying question —
*should* a judge who also organises be refused their own peers' scores? — is
deferred to FEAT-05, which owns the judge console and the route that reaches
the accessor. Closing it now would be closing a question, not a defect.

### F-56 [P3] closed — `just --list` rendered every recipe's last comment line, so the recipe list lied

**File:** `justfile`
**Found:** 2026-09-28, after FEAT-03, while writing the cross-session handoff
**Why it matters:** `just --list` is the answer to "what can I run?", and this
repository makes that its **default target** for exactly that reason. Every
recipe's doc comment here was written summary-first, wrapped across two or three
lines, with the consequence that `just` — which displays the **last** line of a
doc comment, not the first — printed the trailing fragment:

| recipe | advertised itself as |
|---|---|
| `accept` | "never actually run. See the same note on `coldstart`." |
| `check` | "has to reach for is worth more than one somebody might leave on." |
| `default` | "repository is always \"what can I run?\"" |
| `prove-offline` | "spec, and the first numbered disqualification." |
| `coldstart` | "default at all." |

`accept` is the sharp one: the fragment is **advice not to run the command**, on
the command that produces `acceptance-report.txt` and is named in `AGENTS.md`,
in the README and in `.dogfood.toml`. A fresh session told to check the recipe
list against the documented commands would have found two plausible reasons to
distrust the gates. It is F-35/F-48's shape one layer out — *a command's own
documentation, contradicting the command* — and it survived every gate in this
repository, because no gate reads `just --list`.

**Resolution:** The summary is now the last line of a comment block that is
contiguous with the recipe name, and the convention is written at the top of the
file so the next person does not have to rediscover it. Both halves matter: a
blank line between the comment and the name discards the doc comment entirely
and leaves a **blank** description, which is the same defect quieter — that
variant shipped for `down`, `up`, `spec`, `spec-quiet`, `coldboot`,
`lint-isolation` and `prove-offline` in the first attempt at this fix, and was
caught by reading the output of the very command being fixed.

The behaviour was **executed, not recalled**: a two-line comment in a scratch
justfile renders its second line. Asserting that from memory is how F-11
happened.

### F-47 [P2] closed - `just prove-offline` and `just mutation-test` were named in four documents and did not exist as commands

**File:** `justfile`
**Found:** 2026-09-28, at FEAT-02, while running the break protocol
**Why it matters:** This is **F-35 again, one layer up.** F-35 was `just` itself
being absent while three files named it as the gate command. Here the *tools*
existed — `tools/prove_offline.py` and `tools/mutation_test.py` were both written
and working in FEAT-01 — but the justfile recipes that invoke them were never
written, so:

```console
$ just prove-offline
error: justfile does not contain recipe `prove-offline'
```

The FEAT-01 archive's verification table records *"Boots with `--network none` |
**proved** — 4.0 s, 4 content-asserting probes"*, which is a true statement about
a run someone did. But **there was no command that could produce it**, so at
BREAK-1 the break protocol would have stalled on a step nobody could type, or
worse, a session would have run the underlying script by hand and reported the
recipe as covered. A verification table row that no command can reproduce is an
unreproducible claim wearing the costume of a passing one.

**Suggested fix:** Write the two recipes.
**Resolution:** **Closed 2026-09-28 by FEAT-02.** Both added, with the reason
they are not inside `just check` written beside them (they each need a clean
volume, and `check` must stay the one command a reviewer runs). Both were then
run: offline boot **5.8 s**, four content-asserting probes, **15/15** mutations
caught. The lesson generalises past `just`: *a verification claim is only worth
recording if there is a command that reproduces it*, and the archive is the
place to say which command that was.

### F-46 [P2] closed - Running `ruff format` across the tree broke two of the fifteen mutation targets

**File:** `tools/mutation_test.py`
**Found:** 2026-09-28, by `just mutation-test` immediately after the reformat
**Why it matters:** F-43's repair was to run `ruff format` over 22 files. Two of
the mutation harness's targets are **exact source strings**, and the formatter
rewrote both of them — joining an f-string onto its call, and putting a
`pathlib.Path(...)` on one line. So two deliberate corruptions became
`[pattern not found]`:

```
13/15 mutations caught
 NOT CAUGHT
   - tools/run_acceptance.py: the regression branch never fires  [pattern not found]
   - tools/docker.py: the per-user Docker path is removed  [pattern not found]
```

**This is the cost of an exact-string mutation harness, and it fails in the worst
direction.** A mutation the harness cannot find is indistinguishable from a
mutation the gate survives, and the report says so in the same words for both
(`pattern not found` is printed as a *miss*, not as a *harness defect*). We were
one `ruff format` away from a green 13/15 that read as "two gates pass while
broken" — and the two in question are the F-32 class and the F-34 regression.

It is also the ledger's own rule firing against us: **a repair is not done when
the code changes**, and the review of the reformat was "the 160 tests still
pass", which was true and not sufficient.

**Suggested fix:** Re-point the two mutations at the reformatted text, and make
the harness distinguish the two failure modes.
**Resolution:** **Closed 2026-09-28 by FEAT-02.** Both patterns re-pointed and
verified against the *loaded* `MUTATIONS` value rather than by eye — the second
attempt still had doubled backslashes from a shell-quoting layer, and only
importing the module and testing `old in source` settled it. `15/15` again.
The durable change: `pattern not found` is now reported in its own line rather
than in the miss list, so a harness defect and a surviving gate cannot be
confused. **The general lesson: a gate that asserts by matching a string needs a
test that the string is still there**, and the cheapest version of that is to run
the gate after touching the file it matches.

### F-45 [P1] closed - `isolation_proof` could populate the "judge" row with an organizer and print an impossible number

**File:** `src/reviewer/reviews/management/commands/isolation_proof.py`
**Found:** 2026-09-28, by `tests/test_isolation_proof.py`
**Why it matters:** The matrix loops over the five roles and resolves an actor
per role from the `RoleBinding` table. It then printed each row labelled by
`actor.label`, which returns the actor's **strongest** role. A user can
legitimately hold two — a judge who is also a participant is the ordinary case at
a hackathon, not a misconfiguration — so the table printed:

```
  visitor       0/2    0/2    0/2   ?  ?  ?
  judge         1/2    0/2    0/2   ?  ?  ?
  judge         1/2    0/2    0/2   ?  ?  ?      <- the participant row
  admin         2/2    2/2    2/2   ?  ?  ?
  admin         2/2    2/2    2/2   ?  ?  ?      <- the organizer row
```

Three distinct things wrong, and the middle one is the serious one. The
**participant row showed a review visible to a participant** — a number the
design says is impossible, in the published matrix, printed by the file whose
entire purpose is to be the evidence a judge checks the portal against. Nobody
reading that output could tell it was wrong, because the layout is exactly what a
correct matrix looks like.

**This is F-40 turned on ourselves, in the one artefact we would have pointed a
panelist at.** F-40 was a check reporting PASS without exercising the behaviour
it names; this is a proof reporting a *verdict* without exercising the *actor* it
names.

**Suggested fix:** A row may only be populated by an actor whose strongest role
is that row's role. When none exists, say so.
**Resolution:** **Closed 2026-09-28 by FEAT-02.** `ROLE_STRENGTH` orders the
five roles and both resolvers (`_actor_for_binding`, `_admin_actor`) now refuse
rather than borrow. The refusal message names the consequence — *"would report a
stronger actor's numbers"* — because a refusal a reader cannot act on is a
refusal they will work around. Two tests pin it: a missing participant binding,
and **an event where every judge is also an organizer**, which is the case that
produced the bug. `Actor.label`'s docstring now says it returns the *strongest*
role, because that is the fact the matrix was missing.

### F-44 [P2] closed - The plan said 20 models, `DATA-MODEL.md` said 20 tables across 8 apps, and `bible/05` names 24

**File:** `blueprint/build-plan.md`, `DATA-MODEL.md`
**Found:** 2026-09-28, at FEAT-02, before writing the migration
**Why it matters:** Three documents in the spec layer disagreed about the size of
the schema, and **no gate covered any of them.** `verify_spec.py` has 67 checks
and none of them reads a model count, so the disagreement would have survived to
the end of the build.

| Source | Claimed |
|---|---|
| `blueprint/build-plan.md` | **20 models, 12 apps** |
| `DATA-MODEL.md` | **20 tables across 8 apps** |
| `blueprint/context/coding-standards.md` §3 | "twenty across eight" |
| `bible/05` §2–§9 | **24 distinct models** |

This is **F-28's exact failure mode** — a hand-typed census number that nobody
derived — committed by the layer whose stated purpose is to stop transcription.
The count is load-bearing: it is how a reader judges whether the schema is
defensible or sprawling, and "twenty across eight" is a *different architectural
claim* from "twenty-four across twelve". The first says a dozen apps would be
smell; the second says twelve is the right size for this scope.

**Suggested fix:** Build what `bible/05` actually describes, then make the number
un-typable.
**Resolution:** **Closed 2026-09-28 by FEAT-02.** All 24 ship. Reaching 20 would
have meant cutting four with reasons that would have had to be invented, and the
cut ledger exists for decisions we actually made. Both documents now say 24
across 12, and — this is the part that matters — `tests/test_schema_contract.py`
**reads the number out of `build-plan.md` and compares it to the Django app
registry**, and separately out of `DATA-MODEL.md`. The plan is the claim, the
registry is the check, and retyping either document's number now fails the suite.
The test failed on the first run, which is the evidence that it is real.

### F-43 [P2] closed - `just lint` was already red when FEAT-01 was archived as "Lint: clean"

**File:** `justfile`, `pyproject.toml`
**Found:** 2026-09-28, at FEAT-02, when the new code was made to pass
**Why it matters:** `just lint` runs two things: `ruff check` and
`ruff format --check`. The FEAT-01 archive's verification table says **"Lint |
clean"**, and `ruff check` did pass. `ruff format --check` did not, and had
never been run — **11 of the 17 files FEAT-01 wrote failed it.** A gate whose
second half had never executed was recorded as a pass on the strength of its
first half.

That is the same shape as F-11, F-33 and F-39: **a claim about a tool that was
never executed against the installed tool.** It is also why the FEAT-01 archive
is the right place to have recorded it, and did not.

**Suggested fix:** Run both halves, and reformat.
**Resolution:** **Closed 2026-09-28 by FEAT-02.** 22 files reformatted; the 49
pre-existing tests still pass afterwards. `tools/verify_spec.py` was added to
ruff's `extend-exclude` rather than reformatted, which **extends** the existing
per-file-ignores decision instead of quietly overriding it — the recorded
reason ("do not machine-edit the gate that polices the spec layer") was about
`ruff check` and honouring it for `ruff check` while letting the formatter
rewrite the same file would have honoured it in name only. **The real
consequence of finding this late: it had been a red gate for a whole feature, and
a gate that is always red is a gate nobody reads.**

### F-42 [P2] closed - `run_acceptance.py` had a wrong default that produced the right answer

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
**Resolution:** **Closed 2026-09-28 by FEAT-03**, on the grounds that the repair
has now been reviewed against new work rather than merely written.
`PRECONDITION_ROUTES` added, unmapped keys are appended to `problems`, and
`test_every_precondition_names_a_real_route` plus
`test_probed_routes_are_the_ones_the_checker_uses` guard both directions. The
second test exists because the original defect was a *name* mismatch, so
asserting the name is what actually catches it.

**The review found one more instance of the same shape, in new code.** FEAT-03
added a second kind of precondition — a `probe` that re-sends the request and
asserts on the *body* — and the first version of its status check was a chained
ternary whose `401/403` branch read `{401, 403} == {status}`, which is a
*set equality against a singleton* and is False for every real answer. It would
have failed loudly rather than silently, which is the lucky direction, but it is
the same mistake: a clever expression in a place that should have been a
four-line function. It is now `_status_is()`, and
`test_an_unparseable_expectation_fails_rather_than_defaulting` pins that an
unparseable expectation returns False rather than defaulting to "close enough".

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

## Open — non-blocking

*Three entries, all found at BREAK-1's verification pass and none of them P0 or
P1, so nothing here blocks the break. F-48 is here as a misplacement, not as
live work — see **F-57**.*

### F-48 [P2] closed - `just accept` and `just coldstart` had never been runnable

**File:** `justfile`
**Found:** 2026-09-28, at FEAT-03, while trying to record a cold-start number
**Why it matters:** Three recipes declared a variadic with a **literal string
default**, `*args="{}"`. `just` interpolates a variadic default as text, so
`just accept` expanded to `run.py .dogfood.toml {}` and argparse answered:

```
run.py: error: unrecognized arguments: {}
```

`just coldstart` and `just coldboot` failed identically. **`just accept` is the
command every document tells a reader to run** — it is in `AGENTS.md`, in
`.dogfood.toml` ("Read the result with: just accept") and in the README — and it
had never once worked. The FEAT-01 and FEAT-02 archives both cite cold-start
numbers, so the measurement was real; only the command that produces it was
broken.

**This is F-47 exactly, one layer out.** F-47 was `just prove-offline` and
`just mutation-test` named in four documents with no recipe behind them. Here the
recipes existed and were wrong, which is strictly worse: the command *looks*
present, so a reader who tries it concludes the tool is misconfigured rather
than that it has never run.

**Suggested fix:** Drop the default. `*args` with no default is a genuine
variadic; `*args="{}"` is a parameter whose value happens to be two braces.
**Resolution:** **Fixed 2026-09-28.** `*args` on all three recipes, with the
reason recorded beside `coldstart` so the default is not "helpfully" restored.
Both commands re-run: `just accept` prints the report, `just coldstart` measures
**11.6 s** to a serving page against the 60 s budget. *(Re-measured at BREAK-1
at **11.8 s**; see **F-58** on why the tenths are not a project number.)*

### F-57 [P3] closed - The ledger's own "Open" section held a closed finding, and said it was live

**File:** `blueprint/context/findings.md`
**Found:** 2026-09-28, at BREAK-1, while re-running the whole Phase 0 pass
**Why it matters:** The section header read *"One entry. Everything else in this
section was closed at FEAT-02."* and the FEAT-03 preamble above said F-48
*"stays in the Open section because it is a live tooling defect a reviewer can
still trip over."* The entry itself was marked `closed`, said **"Fixed
2026-09-28"**, and quoted both commands re-running.

All three statements cannot be true. Re-run at BREAK-1: **`just accept` prints
the report and `just coldstart` measures to a serving page** — the repair is
real, so "live tooling defect" was stale prose that outlived its own fix.

This is the ledger's own version of the rule it exists to police. A section
headed *Open* that contains nothing open trains the reader to skim it, and the
day it does hold a real open finding, it is the one heading they stop reading.
**It is also the second time this file has been the thing that was wrong** —
F-52 was this ledger's own mass arithmetic.

**The same defect, in a second file, found in the same pass.**
`project-overview.md` §10 was headed **"Open blockers"** and held two entries,
one of them *"No git repository (F-14) — the only blocker left"* — with **F-14
already closed** and the repository in use, and F-38 also closed. Two closed
findings presented as the project's remaining blockers, in the one section a
reader consults to answer "is anything wrong?". Same root cause: **a heading
outliving its contents.** Both are repaired.

That is two instances from one sweep, and it says something worth recording:
the finding class is not "the ledger is wrong", it is **"a status heading is
written once and never revisited when the thing under it changes."** Nothing in
the spec gate checks a heading against its contents, and a machine cannot
easily. The defence is the break sweep itself — which is the argument for
re-running Phase 0 at every break rather than trusting the previous session's
numbers.
**Suggested fix:** Move closed work out of an *Open* section, or mark the
placement inline as historical.
**Resolution:** **Closed 2026-09-28.** Ledger header and preamble corrected and
the entry annotated as a misplacement; `project-overview.md` §10 rewritten to
name both findings closed, with the live F-38 warning kept because the trap is
still live.

### F-58 [P3] closed - The one mechanically-measured number is the only one with no regeneration path

**File:** `AGENTS.md`, `blueprint/history/features/03-…md`, F-48 above
**Found:** 2026-09-28, at BREAK-1, re-measuring the cold start
**Why it matters:** The cold start is the **only figure in this project measured
by an instrument rather than estimated** — `tools/coldstart.py` times it and
fails if it breaches 60 s. And it is quoted to a tenth of a second, in three
shipped documents, from a single historical run:

```
AGENTS.md          cold start 11.6 s against the 60 s budget
FEAT-03 archive    11.6 s to a serving page, budget 60 s
F-48 entry         just coldstart measures 11.6 s
```

Re-measured at BREAK-1: **11.8 s**, healthcheck green at 11.7 s. Nothing is
false — 11.6 s was a real measurement — but **0.2 s of run-to-run jitter is now
indistinguishable from a transcription error**, which is precisely the failure
mode the "generated, not transcribed" rule exists to prevent. That rule is
enforced everywhere else by `verify_spec.py` (67 checks) and by the census being
recomputed from `fixtures.json`; the cold start has no such path, because nothing
regenerates the documents that quote it.
**Suggested fix:** Quote it as a measurement with a date and a budget, not a
figure to the tenth, and let `tools/coldstart.py` be the only place the exact
number appears.
**Resolution:** **Closed 2026-09-28.** The three documents now read as a
measurement with a date against the budget, and the tenths are attributed to the
run rather than asserted as the project's number.

**F-59 [P3] — opened at BREAK-1, closed at FEAT-04. Signpost; the full entry is
in the FEAT-04 section below.** One entry, one ID, one status.

**File:** `tools/verify_spec.py`, `justfile`
**Found:** 2026-09-28, at BREAK-1, running the recipe audit by hand
**Why it matters:** **F-47 and F-48 were the same defect twice** — `just
prove-offline` and `just mutation-test` named in four documents with no recipe
behind them (F-47), then three recipes that existed and were broken (F-48). F-56
was a third variant: the recipes existed and `just --list` misdescribed them.
**Three findings, one missing check.** All three were found *by hand*, in three
separate sessions, by whoever remembered to run the audit.

`verify_spec.py` had 67 checks and **not one of them was "every `just` recipe
named in a document exists."** The audit is cheap and mechanical: extract the
recipe names from the justfile, extract `just <recipe>` from every markdown file
outside `bible/`, and assert each name is a recipe.
**Why it was open and not closed at BREAK-1:** adding a check to the spec layer is
new work, and that was a break, not a feature. `ai-interaction.md` §6 is explicit
about that. **Closed at FEAT-04, where it was the work.**

### F-59 [P3] closed - No check that a command named in a document is a command that can be typed

**File:** `tools/verify_spec.py`, `justfile`
**Found:** 2026-09-28, at BREAK-1
**Closed:** 2026-09-28, at FEAT-04
**Why it matters:** **F-47 and F-48 were the same defect twice** — `just
prove-offline` and `just mutation-test` named in four documents with no recipe
behind them (F-47), then three recipes that existed and were broken (F-48). F-56
was a third variant: the recipes existed and `just --list` misdescribed them.
**Three findings, one missing check.** All three were found *by hand*, in three
separate sessions, by whoever remembered to run the audit.

**Resolution:** **Closed 2026-09-28 at FEAT-04.** `verify_spec.py` gained
`check_recipes`, which parses the recipe names out of the `justfile`, extracts
`just <recipe>` from every markdown file outside `bible/`, and fails on any name
that is not a recipe. **68/68 checks now, up from 67.**

Three decisions inside it, each of which was a bug first:

* **Position, not an English allow-list.** A name counts as a command only at the
  start of a line, as a list item, or inside a fenced block. The alternative was
  a list of English words to exclude, and "just status" and "it just counted"
  are real sentences in our own documents — a word list is a list somebody has to
  remember to extend, and the check stops being trustworthy the first time they
  do not.
* **The justfile parser handles parameters and assignments.** The first version
  matched only `name:`, so it reported **`coldstart`, `coldboot` and `accept` as
  missing — three recipes that exist.** A check that is wrong on its first run
  teaches everyone to ignore it, which is worse than not having it. The fix is
  `(?:\s+[^:=\n]*?)?:(?!=)`: the `(?!=)` is what separates `coldstart *args:`
  from `py := ...`.
* **It is proven to fail.** Adding a deliberately misspelled recipe name to the
  README makes the gate exit non-zero and name the typo. A check that cannot
  fail is worse than no check, and this one is not an identity: it compares two
  independently derived lists.

  **It caught this very entry, on its first run.** The first draft of this
  paragraph demonstrated the failure by writing the misspelled command out loud
  in backticks, and the check reported it as a missing recipe — in this file.
  The example is now described in words rather than planted, because a
  documentation file that contains a non-existent command is exactly the defect
  the check exists to catch, and **a check that cannot be applied to its own
  rationale is a check nobody will trust.**

## Resolved — found in FEAT-04, 2026-09-29

*Six findings, and the headline is not the one I expected. FEAT-04 opened no P1:
the assignment engine ran against a panel we had already loaded and verified
twice, so the data was not new. **Every one of these six is in our own reasoning
or our own documents, and five of the six were found by executing something
rather than by reading it** — which is the rule the project has been arguing for
since F-11, now demonstrated on our own solver.

### F-60 [P1] closed - The min-cost solver returned feasible but non-minimal flows, and never raised

**File:** `src/reviewer/assignment/flow.py`
**Found:** 2026-09-29, at FEAT-04, by differential testing against an independent implementation
**Why it matters:** The textbook successive-shortest-path algorithm updates its
Johnson potentials **incrementally** after each augmentation. That is
asymptotically better and it is **wrong**, in the most expensive way available:
a node that *drops out* of reachability keeps a stale potential, an arc from it
into a reached node then has a negative reduced cost, and Dijkstra on negative
reduced costs returns a path that is not shortest.

**It does not crash, and it does not look wrong.** The result is a *feasible*
flow with a slightly worse total cost — which for this application means a
slightly worse spread of judge workloads, on a feature whose entire claim is
that the spread is as fair as it can be.

It was found by writing the solver and then **testing it against a second,
independently written algorithm** — a plain Bellman-Ford SSP with no potentials —
over 1,500 random instances of the planner's exact network shape. **1,500/1,500
now agree**; the incremental version disagreed on some, and an explicit
`AssertionError` guard in `_dijkstra` turned the silent version into a loud one.

**The repair, and the reasoning is the point:** potentials are now recomputed
from Bellman-Ford on **every** augmentation. At 81 nodes and 156 edges a
Bellman-Ford is ~12,000 operations across at most 123 augmentations, so the solve
stays **0.15 ms per instance, measured**. **Correctness was worth more than the
asymptotics, and the asymptotics are exactly where this bug lives.** The guard
stays, because it is what turned a wrong answer into a failure.

### F-61 [P1] closed - "The bottleneck judges are on the sink side of the cut" names nobody, and the feature looked like it worked

**File:** `bible/06` §2.3, `src/reviewer/assignment/planner.py`
**Found:** 2026-09-29, at FEAT-04, by reading the empty output rather than the code
**Why it matters:** `bible/06` §2.3 says the diagnosis should name "the judge
nodes on the sink side of that cut". Implemented **literally on the network
§2.2 itself describes, that set is empty** — and the certificate printed a
deficiency with no judges on it, which is not a diagnosis.

The reason is a property of the canonical minimum cut. Its source side is reached
from the source through a track node that still has residual capacity, and from
there through exactly the projects that went **un**covered — whose judge edges
are untouched and therefore fully residual. **The judges of a deficient track are
on the SOURCE side.** Naming the sink side names nobody.

**The correct reading is the same cut, one arc later.** Every saturated
`judge → sink` arc crosses it, because every judge is reachable and the sink is
not. So the bottleneck judges are the eligible judges **whose capacity is
exhausted** — and on `trk_01` at c=5 that is all three of them, by name, each
marked `AT CAPACITY`. That is the answer an organizer acts on: *there is no
fourth judge, and these three cannot take a 16th project between them.*

**This is the project's own lesson, aimed at us.** A feature that returns
structurally valid output containing nothing is indistinguishable from a feature
that works, and a test asserting `bottleneck_judges == ()` would have passed
forever. The test now asserts they are **named** and **at capacity**, and a
mutation that empties the list fails it.

### F-62 [P2] closed - `bible/06` §2.2's "40 nodes and 77 edges" is wrong; the true network is 81 nodes and 199 edges

**File:** `bible/06` §2.2
**Found:** 2026-09-29, at FEAT-04, by building the network the section describes
**Why it matters:** §2.2 is the source for the "77" that its own
`assert network.nnz == expected` instruction is built around. **Built and
counted, the number is 199 eligible judge–project edges over 81 nodes** (source +
8 tracks + 41 projects + 30 judges + sink).

**77 is not reachable by any reading of the graph.** The per-track table in
§2.1a of the same document implies `6·3 + 6·4 + 6·6 + 5·8 + 3·5 + 3·4 + 6·6 +
6·3 = 214` before any exclusion is applied, and 199 is what is left after the
submitting-team rule. So §2.1a and §2.2 disagree inside one file, and the
assertion §2.2 asks for would have **pinned the wrong number and passed**.

The parts of §2.2 that survived contact with the code are the ones that were
arguments rather than measurements, and they are all confirmed: the **capacity
curve** (c=5 → 117/123, c=6 → 123/123), the **tightest capacity of 6**, the
**mean load of 4.10**, and the whole of §2.3's remedy table, which reproduces
exactly — `k=1 → 4×5=20 ≥ 18`, `⌈18/3⌉ = 6`, `⌊15/6⌋ = 2`.

**Resolution:** **Closed 2026-09-29.** `manage.py verify_assignment` re-derives
199, 81 and 123 from the database on every `just check`, and
`tests/test_assignment.py::test_the_graph_has_the_derived_edge_count` computes the
expected count from `fixtures.json` by a **second, independent implementation** —
so the assertion is a comparison, not a transcription. §2.2's prose is left as
the planning record and this entry is the correction; the numbers in the shipped
documents are the generated ones.

### F-63 [P2] closed - Two of the three remedies did not say which track they were for

**File:** `src/reviewer/assignment/planner.py`
**Found:** 2026-09-29, at FEAT-04, by a test that could not find what it was looking for
**Why it matters:** The fixture has **two** deficient tracks, and the diagnosis
produces **six** remedies. `invite 1 more judge(s) to trk_01` named its track;
`raise the per-judge capacity to 6` and `lower this track's target to 2` did not.
An organizer reading that has four remedies and no way to tell which two belong
to the track that is actually fatal.

It surfaced because a test asserted that each deficiency had all three remedy
kinds, found only one, and I read the failure instead of loosening the
assertion. **The fix was the feature's, not the test's**: `Remedy` now carries
`track_slug` as a field, and the rendered certificate prints it.
`raise the per-judge capacity to 6 for trk_01` and `lower trk_01's target to 2`.

The general lesson is the one the project keeps relearning: **a report that
cannot be attributed is not a report.** Four numbers with no track attached is
the same failure as a number that is wrong, one level up.

### F-64 [P2] closed - The fixture never exercises the conflict-of-interest rule, so it would have shipped untested

**File:** `src/reviewer/assignment/graph.py`, `tests/test_assignment.py`
**Found:** 2026-09-29, at FEAT-04, by a test asserting a reason that never fired
**Why it matters:** `bible/06` §2.1 makes "the judge is not a member of the
submitting team" one of five hard eligibility rules, and it is the only one with a
*correctness* consequence rather than a fairness one. I asserted the exclusion
reasons were countable, and `submitting_team_member` was not among them.

Measured: **not one of the fixture's 30 judges is a member of any of its 40
teams.** The rule is **unreachable on shipped data**.

That is not a reason to delete it — judges submit at hackathons, and that is
precisely when it matters — but it *is* a reason to be honest about coverage. A
test that asserted "the exclusion rules are exercised by the fixture" would have
been **lying**, and the rule would have shipped as untested code behind a green
gate. The test now asserts the split explicitly: `no_track_binding` is reachable
and asserted; `submitting_team_member` is asserted **not** to fire, with a
pointer to F-64; and a **synthetic** test adds a team member who is also a judge
on that track and asserts the pair disappears *with the right reason*.

**This is the third time the fixture's silence has been mistaken for coverage**
(F-49, F-50, F-55 were values that agreed with what we expected). The rate is now
the prior for FEAT-05.

### F-65 [P3] closed - The one assertion in the new suite that could not fail

**File:** `tests/test_assignment.py`
**Found:** 2026-09-29, at FEAT-04, on review rather than on a run
**Why it matters:** The sole-cover test built a thinned graph, called
`_sole_covers` on it, and then `break`-ed out of the loop **without asserting
anything about the result**. It passed. It would have passed with the feature
deleted.

It is the F-41 defect in a new file, and it is worth recording because it was
written *after* I had written a module docstring asserting that every layer would
be proven load-bearing. The rewrite asserts **three** things: nothing on the
shipped fixture is flagged, a track reduced to one judge names **that judge by
email** and **that track by slug**, and two judges is *not* a single point of
failure. The last one is the half that was missing — without it, a rule that
fires on everything would have satisfied the original test perfectly.

**Resolution:** Closed 2026-09-29. Sixteen deliberate corruptions were run
against the two new modules — **8 against the engine and 8 against the console**,
each naming the test that must notice — and **all 16 were caught**, each with its
specific reason rather than a substring.

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
