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

## Resolved — found in FEAT-06, 2026-09-29 (in progress)

*Ten findings. **Four were found by re-running Phase 0 on a tree nobody had
touched** (F-72…F-75), **two by the influence report's own mutation harness and by
running the report in the real container** (F-76, F-77), and **three by the
bias-attack harness refusing to separate its own arms** (F-78…F-80) — not one by
reading the code. **Seven of the ten are about a number or a test that could not
be trusted**, and three are about a *fixture* or a *model* that could not
discriminate, which is the F-41 defect reached from the other direction. F-71,
from the previous increment, is the tenth. The remaining FEAT-06 work — voting,
ballot order and comments — is not started.*

### F-78 [P2] fixed - `bible/06` §6.3's power table does not reproduce from the formula it names, and the honest threshold is NARROWER than the published claim

**File:** `src/reviewer/ballots/bias_attack.py` (`POWER_TABLE`,
`comparisons_required`), `tests/test_bias_attack.py`
**Found:** 2026-09-29, at FEAT-06, by generating the table and comparing it with
the one §6.3 quotes
**Why it matters:** §6.3 publishes the sample a real event would need to detect
residual position bias: **28,573 / 4,556 / 1,125 / 490** comparisons for side
preferences of 0.52 / 0.55 / 0.60 / 0.65, and the sentence *"a real event has on
the order of 100–1,000 votes, we therefore cannot measure residual position bias."*

Fleiss' one-sample proportion formula, which is the formula §6.3 says it is
using, gives **4,904 / 783 / 194 / 85**. The ratio is **5.83, 5.82, 5.80, 5.76** —
near-constant across four independent rows, which is the signature of **one wrong
convention rather than four slips**. Solving for the `(z_alpha, z_power)` pair the
quoted numbers imply gives `z_alpha = 4.098` (a two-sided alpha of 0.000083) and
`z_power = 2.665` (power 0.9962), which is not the stated pair (1.9600, 0.8416).
**There is no standard convention that produces the quoted table.**

**The error is in the conservative direction, and the correction NARROWS the
claim rather than reversing it.** This is the part worth being careful about,
because "the document overstated" and "the document understated" have opposite
consequences:

* §6.3 says 4,556 comparisons to detect a 5-point preference, which puts it far
  beyond any real panel and makes *"we cannot measure this"* safe.
* The generated figure is **783**, so a 5-point preference **is** resolvable at
  n = 1,000 — at the very top of the plausible range.
* A 2-point preference still needs **4,904**, and a 10-point one needs **194**.

So the published conclusion survives for every realistic panel size and **fails at
the upper edge of its own stated range**. The shipped output says what the
measurement supports: 2 and 3 points are out of reach everywhere, 5 points is out
of reach below ~800, and only a 10-point preference is comfortably measurable.

**Resolution:** **Fixed 2026-09-29.** The table is **generated** by
`comparisons_required` on every run, never transcribed, and
`test_the_power_table_is_generated_and_never_transcribed` recomputes all four
entries and fails if any differs. A second test asserts the **conclusion**, in
both directions, so a future edit that made small effects look unmeasurable would
fail rather than quietly strengthen the claim. The first version of that test got
it wrong in the other direction — it asserted `comparisons_required(0.55) > 1000`
and failed, which is how the narrowing above was found rather than assumed.

**This is F-67 with a table attached.** Six of twelve early findings were census
errors in our own documents, two of them *after* a correction log about the first
four had been published. A planning document's number is no more trustworthy than
a test's number until something derives it.

### F-79 [P1] closed - The first bias-attack harness measured RANK TRANSFER, not position bias, and would have "confirmed" D-12 with a number that was never about randomisation

**File:** `src/reviewer/ballots/bias_attack.py` (`cast_ballots`)
**Found:** 2026-09-29, at FEAT-06, by prototyping the harness and reading the
numbers before writing any shipped code
**Why it matters:** The first model of a position-biased voter was "promote
whatever is in slot 1, regardless of quality". Measured, it reported a drift of
**−48 for the best project and +47 for the worst** under a *randomised* order.

**That is not a position effect.** The model transfers points from good projects
to bad ones, so it is a statement about rank transfer, and a harness using it
would have shown a large number for randomised order and thereby "confirmed" that
randomisation works — **for the wrong reason, with a number that was never about
the order.** The claim under test is about the order, with the bias held fixed, so
a model that changes the *bias* cannot test it at all.

The shipped model is the **serial-position effect**: a position-biased voter
**resolves its own top two by which is displayed first**. That is also the
defensible reading — serial position is an effect on choices *between presented
alternatives*, so a voter who never shortlists a project cannot be moved by where
it is displayed. The two models are pinned by
`TestPositionBiasIsModelledAsPrimacyNotAsAPromotion`, including the assertion that
a voter never promotes a project outside its own top two.

**This is F-76 one level up.** The `lift` metric was structurally *constant*; this
model was structurally *wrong*. Both read as detectors. **The generalisable check
is the same one: point the instrument at a case it should report and a case it
should not, and if it fires equally on both, it is measuring something you did not
name.** Found by prototyping before writing the module, which is the cheapest
place to find this class and the only place the first version of the harness still
existed.

### F-80 [P2] closed - The quality ladder made the harness a ONE-PROJECT instrument, and every "is the attack detected" test still passed

**File:** `src/reviewer/ballots/bias_attack.py` (`_quality_ladder`,
`QUALITY_SPREAD`)
**Found:** 2026-09-29, at FEAT-06, by the mutation harness reporting its own
mutation **NOT DETECTED**
**Why it matters:** The population's true qualities were laid out on a ladder from
1.0 to 0.12. Measured at 200 voters: project 0 was in *some* voter's top two
**100%** of the time, project 2 **13%**, and projects 5 and 7 **never**.

**The primacy model can only move a project a voter has shortlisted**, so pinning
the bottom of the ladder produced a drift of **−0.317 against a spread of 4.69** —
a **structurally constant row sitting in a table of measurements**. That is F-61's
seventh appearance and F-76's shape at the level of the *fixture*: the harness was
measuring exactly one project and reporting it as a study of position bias.

**The revealing part is that all 48 tests passed.** Setting the spread back to
0.875 and re-running the whole suite left every "is the attack detected"
assertion green, because project 2 was still reachable enough to move. **A test
that checks the attack fires does not check the field is contested.**

It was found because the mutation harness reported a corruption as **not
detected** — which is the direction that matters, and which the pytest suite
cannot produce on its own.

**Resolution:** **Fixed 2026-09-29.** `QUALITY_SPREAD = 0.45`, so the top three
projects are reachable (94% / 63% / 25% at 120 voters) and pinning the third gives
a fixed-order drift of **+7.39 with a CI excluding zero** while randomised order
spans zero. **The harness now discriminates at two points on the quality ladder
rather than one.** The property is now asserted directly by
`test_the_ladder_leaves_a_contested_field_rather_than_one_winner` — at least three
projects above 1% reach, and the best below 100% — and reach is *measured* by a
helper rather than asserted from memory, because it is a property of the noise
model and a transcribed figure is exactly the habit F-72…F-75 exist to prevent.

### F-86 [P2] fixed - The MODERATION QUEUE rendered comment bodies unescaped, and every escaping test was green

**File:** `src/templates/comments/thread.html`, `tests/test_comments.py`
**Found:** 2026-09-29, at FEAT-06 increment 6, **by a sabotage the tests did not
catch** — which is the finding
**Why it matters:** the sabotage put the safe filter on the **moderation
queue's** copy of `comment.body`, not the public thread's, and **all four
rendering tests stayed green.** They were green because every one of them read
the page as a *visitor*, and the queue is rendered only for an organizer.

**The queue is the highest-privilege rendering of user-controlled text in the
whole feature.** It is what an organizer looks at, in their own authenticated
session, for every comment anyone has ever posted — and a hostile comment that is
*never approved* never reaches the public thread at all, so the public tests were
structurally incapable of catching it. Stored XSS against the person whose job
is to review the content, triggered by the content itself.

**This is the F-80 shape applied to a security property**: a render path that
exists, is reachable, renders user input, and had **no test at all**. The claim
"we escape comment bodies" was true of **one of two call sites**, and the second
was written in the same file, twenty lines below the first.

**The generalisable lesson, and it is the one worth keeping:** *escaping is a
property of every render path, not of the data.* A test that proves a payload is
escaped on page A has proved nothing about page B. **The number that matters is
the count of places user-controlled text reaches HTML, and the assertion has to be
enumerated over that count** — not written once and trusted.

**Fixed, and pinned by `test_the_moderation_queue_escapes_too`**, which reads the
page *as an organizer* and asserts the queue is present, non-empty, and escaped.
Its companion `test_both_render_paths_are_covered_by_this_file` exists so the
first cannot pass **vacuously** against an empty queue — a test that asserts on a
page section that is empty passes no matter what the escaping does.

### F-87 [P2] fixed - A comment escaped the moderation queue entirely: a pending comment was invisible to the moderator who has to approve it

**File:** `src/reviewer/comments/views.py`, `tests/test_comments.py`
**Found:** 2026-09-29, at FEAT-06 increment 6, on the first test run
**Why it matters:** `_moderate` rebuilt only the **queue** in the context after
acting, and re-rendered the **public thread** from a context built *before* the
write. So approving a comment updated the database and then re-rendered a page on
which the comment was still absent — **the organizer pressed "Approve", the row
went visible, and the page said it had not happened.** The same shape as F-85
one module over, and the second time this session that a right-in-the-database
write was paired with a wrong-on-the-page render.

**Found immediately, unlike F-85, because the moderation tests re-render the page
after acting** — which is the habit that caught it. That is the whole difference
between the two findings, and it is a habit worth naming: **a write test that
re-reads the page is a test about the product; one that asserts on the database
is a test about storage.**

### F-85 [P2] fixed - After casting a vote the page reported the PRE-cast budget and empty weight boxes

**File:** `src/reviewer/ballots/views.py`, `tests/test_voting.py`
**Found:** 2026-09-29, at FEAT-06 increment 5, **by casting a real vote against
the running container with `curl`-shaped requests** -- not by pytest
**Why it matters:** the view builds one `context` dict, renders it on GET, and
then **reused the same dict after writing**. So the page a voter lands on after
voting said **"0 of 41 weight spent"** and showed every weight box empty -- a
**stale value rendered as a current one**, and a lie about the voter's own action
on the single number the identity budget exists to make legible.

**The database was correct the whole time.** Every assertion in the suite that
looked at `Vote` rows, at `spent()`, or at `tally()` passed, because the defect
was entirely in what got rendered afterwards. **This is the seventh appearance
of the same defect class**: a feature returning structurally correct output whose
*values* are wrong. The two predecessors in this feature (F-83, F-84) were both
caught by tests; this one was caught by a human reading an HTTP response, which
is the honest measure of how much the automated half of this project's checking
is worth.

**The lesson is about where the tests were looking.** Every test asserted the
*effect* of the cast, and the effect was right. None asserted what the voter is
**shown** after casting -- because "the page looks right" felt like a template
concern. It is not: **the page is the product**, and a template that renders a
correct value computed before the write is a wrong page.

**Fixed** by `_recompute` refreshing `spent` and the per-project weights after the
cast, and pinned by two assertions **on the rendered bytes**
(`b"5 of 5 weight spent"`, `value="3"`) rather than on the database. The sabotage
was run: removing the recompute turns both red.

### F-84 [P1] fixed - An abstention silently became a VOTE for the randomised order

**File:** `src/reviewer/ballots/tally.py`, `tests/test_voting.py`
**Found:** 2026-09-29, at FEAT-06 increment 5, by a test that asserted a TIE
**Why it matters:** `tally` iterated every `Ballot` and ranked it. `ranking_of`
returned *the voter's votes, then every unvoted project in ballot order* -- so a
voter who had cast **nothing at all** came back with a full-length ranking equal
to their raw ballot order, and the aggregator scored them as though they had voted
for it. **An abstention was being counted as a vote, and the vote it was counted
as was "yes, in this exact random order."**

This is the most serious of the findings in this increment and it is **P1 for a
reason the others are not**: the defect does not corrupt a number, it **inverts
the meaning of a control the brief explicitly asks for.** REQ-T3-01 requires
mandatory attributable abstention; the surface had a button labelled "Abstain"
that recorded an abstention in the database and then **voted the ballot anyway
when tallying.** A reader auditing the code would have found the correct
abstention model and a tally that contradicted it, both in the same commit.

**It was found by the cheapest possible assertion**, and the mechanism is worth
recording because it is not the one that was being looked for. A test created a
third ballot to break a tie between two others, asserted the two were equal --
and they were not. The instinct was "the tie test is wrong"; the reality was that
the third ballot had moved the numbers. **A test asserting a NEGATIVE caught a
positive-valued defect**, which is the F-21 lesson (`just check` will not catch
this class -- everything it runs is correct) applying to a case nobody had looked
for.

**Fixed** by `ranking_of` returning `[]` for a voter who cast nothing, and
`tally` skipping those ballots. Pinned by three tests: the standings must be
byte-identical before and after adding an abstainer, and an abstainer must add
zero to the `voters` count.

**And a second-order bug in the same function, found by the test that pinned the
first:** `voters` counted "ballots whose ranking mentions this project", so a
project ranked **last** by every voter reported **full support** -- contradicting
the influence report's distinct-identities count on the same data. **Two shipped
artefacts answering the same question with different definitions is a worse
defect than either being wrong alone**, and it is now one definition, read from
the `Vote` rows.

### F-83 [P2] fixed - The ballot permutation was keyed on a NULLABLE column, so a self-submitted project put a `None` in the order

**File:** `src/reviewer/ballots/order.py`, `tests/test_ballot_order.py`
**Found:** 2026-09-29, at FEAT-06 increment 4, by the tests on their first run
**Why it matters:** `ballot_order` originally keyed the permutation on
`Project.source_key`, which is the obvious choice -- it is D-11's portable
natural key and it is what the gallery and the export print. **`SourceKeyMixin`
says in its own docstring that it is "Null for rows this portal created".** So
every project submitted through `/projects/new` would have contributed a `None`
to the permutation, and a ballot of `None`s is **structurally valid and contains
nothing**: it stores, it renders, it satisfies every shape assertion, and it
ranks no project at all.

**This is F-80's shape one level down, and it is the sixth appearance of the
defect in five media.** The class is a feature returning output whose *values* are
empty while every *structural* property holds. A permutation needs a total order,
and a nullable column is not one.

**The tests caught it, not the gate, and not by reading the code** -- one of them
sorts the order, and `[None] < [None]` raises `TypeError`. That is luck, and the
honest version of the story is that the *shape* assertions would all have passed.
The test that now pins the class is
`test_a_self_submitted_project_with_no_source_key_still_appears`, which asserts
`None not in order` **and** that the self-submitted project is present -- because
a fix that dropped the project instead of re-keying it would satisfy the first
assertion and fail the second.

**Fixed by keying on `Project.id`**, the primary key, which is present for
fixture rows and portal-created rows alike.

**And the sabotage run earned its own finding.** Breaking the seed to a constant
was the mutation chosen to prove the suite was load-bearing, and the result is
the interesting part: **a constant order is perfectly stable per voter**, so all
four stability tests stayed green and only the three *discrimination* tests went
red. That is precisely the F-80 shape -- "does the guarantee hold" is half the
question -- and it is why `TestTheOrderActuallyVariesAcrossVoters` exists and why
it asserts *counts* rather than pairwise inequality. Both sabotages are now
mutations in `tools/mutation_test.py`, so a re-introduction of either is caught
by name.

### F-82 [P2] fixed - The README's route count was wrong twice, and the second "repair" invented a breakdown that did not sum over its own table

**File:** `README.md`, `tools/verify_spec.py`
**Found:** 2026-09-29, at BREAK-2, while reviewing the README repair that was
about to be committed
**Why it matters:** `README.md` said *"Four routes, and two of them are
features"* when `src/judge_judy/urls.py` held **thirteen** `path()` entries. The
repair retyped it as **"Eleven routes. Four are the public/organizer surface,
five are the API, and two are the judge console"** — and that is **also wrong,
twice over.** The table listed eleven rows but **omitted `/judge/review/<id>/`
entirely**, and the 4/5/2 apportionment does not sum over the table's own rows
(public 3, organizer 1, judge console 2, API 5, admin 1 = 12).

**This is F-67's class applied to a route count, and the interesting part is
that it survived one repair.** A retype fixes the sentence and leaves the
number just as un-derived as before; the second reader has no way to tell a
retyped number from a derived one, because they are byte-identical in the
document. The lesson generalises past the README: **a repair that replaces a
wrong number with a right number has not fixed anything a check could catch.**

**The fix is F-72's, not a retype: make the number un-typable.** A new
`verify_spec.py` check derives the routes from `urls.py` and asserts the README
names every one of them. It asserts a **property** — table and `urls.py` agree —
not agreement with a constant, so it cannot be satisfied by editing both sides the
same wrong way. The prose now says the count is derived rather than quoting it at
all, which is the same move the README already made to the spec-check and
mutation counts.

**Proved negative before it was trusted:** deleting the `/judge/review/<id>/` row
on purpose turns it red and names the exact route —
`expected 'all 13 routes', got ['judge/review/<int:assignment_id>/']`. A check
that has only ever passed is not evidence of anything (F-33), and this is the
fourth time that rule has had to be applied in two sessions.

**It was found by reading a diff, not by running a gate.** `just check` was
green throughout: the README is not application code, and every command in it
passes. The same class as F-67, where the rot was attached to a *command* rather
than a file.

### F-81 [P3] fixed - A mutation's description and detector were wired to each other's tuple, so the harness reported a false failure

**File:** `tools/mutation_test.py`
**Found:** 2026-09-29, at FEAT-06, by a mutation reporting NOT DETECTED that a
manual replication proved was caught
**Why it matters:** The primacy mutation (F-79's corruption) was reported
**MISSED** by the harness. The identical corruption, applied by hand to a sandbox
copy, **failed the tests as it should**. The cause: the description and the
detector command had ended up in each other's tuple, so the corruption was applied
and then checked with `TestTheControlCannotFire` — which correctly passed, because
the control genuinely is silent.

**A mutation whose detector is mis-wired is worse than no mutation**, because it
reports a confident false failure, and the response to a red mutation gate is
normally to go looking at the test rather than at the harness. The harness already
separates "pattern not found" from "not detected" (F-46), which is the same
instinct: a mutation that was never applied is a different defect from a gate that
survived one.

**Two of the three genuinely-undetectable mutations were also recorded rather than
deleted.** A hardcoded-`True` verdict is indistinguishable from a correct one, and
a mutation of the balanced order's *shuffle seed* is near-equivalent because
slot-1 balance still holds. Both now attack the **property** rather than the
arithmetic that computes it, and both record in their own description why the
first attempt could not work. **A mutation list where every entry is caught is
worth less than one that records the two that were not and why.**

### F-76 [P2] fixed - A metric I invented for the influence report was degenerate, and the synthetic attack scored it at exactly 1.0

**File:** `src/reviewer/ballots/influence.py`, `tests/test_influence.py`
**Found:** 2026-09-29, at FEAT-06, by running the report against a real brigade
**Why it matters:** I shipped the report with a fourth detector called **lift** —
first-preference share divided by voter share — on the reasoning that a project
over-represented against its own base is the shape of a bloc vote. The synthetic
attack scored it at **exactly 1.0**, and the reason is structural: **every voter
casts exactly one first preference**, so `first_share == voter_share` whenever a
project's backers are its first-preferencers, which is the overwhelmingly common
case. It can only depart from 1 when people first-preference a project they do
not back, which is not a brigade — it is a ballot display that disagrees with a
vote.

So it was a column that would have read as a real signal on **every row** of the
report while carrying no information, and **`bible/06` §6.2`'s worked example is
phrased in exactly those terms**, so a reader would have had no way to know.

**This is D-04's lesson applied to abuse rather than to normalization.** D-04
removed a tunable constant from the estimator because it was the largest exposure
we had. A metric that is structurally constant is the same exposure wearing a
decimal point, and it would have been the easiest thing in the report for a
reviewer to attack — and the attack would have been *correct*, which is worse.

**Resolution:** **Fixed 2026-09-29.** Cut. The report ships `bible/06` §6.2's
actual four fields — distinct identities, first-preference share, vote-mass Gini,
clustered identities — and the ranking is **clustered identities, then Gini, then
first-preference share**, the three numbers that are each either a structural fact
or a measurement. The docstring records *why* the cut happened and that the
metric was measured rather than assumed, because the next session's obvious move
is to add it back.

**And it is pinned by a test**, which is the part that matters:
`TestTheDegenerateMetricStaysCut` asserts no row carries a `lift` or
`voter_share` key and that the method string does not advertise it. **A cut
recorded only in a docstring is a cut that gets re-derived**, and the
reasoning here is short enough to look re-derivable.

**The generalisable lesson: a detector must be shown to *discriminate* before it
ships, and the cheapest way to show that is to point it at a case it should
report and one it should not.** The brigade was detected; the question I had not
asked was whether anything *else* was.

### F-77 [P2] fixed - The "organic control" in the influence tests was itself a brigade of nine, and a green suite did not notice

**File:** `tests/test_influence.py`
**Found:** 2026-09-29, at FEAT-06, by running `manage.py influence_report` in the container
**Why it matters:** Every "organic" voter in the fixture backed **exactly one
project at weight 1**. An identity is clustered by its *whole* vote vector, so
nine such voters have byte-identical vectors — **the control was a brigade.** The
report in the container duly printed `clustered 9` on every single row, which is
the visual signature of a fixture that cannot distinguish its subject from its
control.

**The test suite was green throughout, and that is the finding.** No assertion
ever said the organic rows *should not* be flagged, so nothing was checking the
only thing that made the control a control. Every test in the file passed while
the control was broken, including the acceptance clause itself. **Running the
command in the real container is what showed it** — pytest never would have, and
mutation testing never did either, because the code was correct and only the
*scenario* was degenerate.

**This is F-41 reached from the other direction.** F-41 is a test that cannot
fail. This is a **fixture that cannot separate the case under test from its
control** — the same defect wearing different clothes, and arguably worse,
because a test that cannot fail at least occupies a slot a reader might question,
while a fixture that cannot discriminate produces *green output that means
nothing*.

**Resolution:** **Fixed 2026-09-29.** `organic()` now gives each voter a distinct
weight and a distinct set of distractor projects, so their vectors genuinely
differ — which is also the realistic shape, since a real ballot ranks many
projects and the one-project-per-voter version was never plausible. Verified in
the container: the brigade reads `clustered 12` and every organic project reads
`clustered 0`.

**The missing assertion now exists and is the point of the class**:
`test_the_organic_voters_are_not_also_flagged_as_a_brigade` asserts
`clustered_identities == 0` on every control row, with a message that says the
control is broken rather than the detector. **A fixture needs the same
falsifiability discipline as the code it exercises**, and the cheapest check is
to assert on the case you expect *not* to fire.

### F-72 [P2] fixed - The banner of `just check` said the spec gate has 67 checks while the gate printed 68/68, and `AGENTS.md` contradicted itself about it

**File:** `justfile` (`check` and `spec-quiet`), `AGENTS.md`, `tools/verify_spec.py`
**Found:** 2026-09-29, at FEAT-06, by re-running Phase 0 on arrival
**Why it matters:** `AGENTS.md` §Verify said `verify_spec.py` has **67 checks**.
The `justfile`'s `check` recipe — the *banner* of the one command a reviewer
runs — printed `1/6  spec layer (67 checks, no Docker)`. The program printed
**68/68**. And `AGENTS.md` contradicted **itself**: line 113 said 67, line 157
said `68/68 spec checks`.

So the header of THE GATE misstated the gate's own size, on the same screen,
two lines above the truth. This is **F-67 verbatim, one layer out**: F-67 was a
number quoted about a command that no command could produce, and the fix then
built the mutation targets — but F-67's own lesson said explicitly that *"every
command named in a document exists"* is not *"every number quoted about a
command can be re-derived"*, and **that second check was never written.** The
count rotted the moment one check was added, which was F-59.

**Resolution:** **Fixed 2026-09-29; awaiting review.** The repair is
**subtraction, not correction** — retyping 67 as 68 would leave a hand-typed
count one edit from rotting again, which is the defect rather than the fix. The
number is now **un-typable** in all three live sites: the banner and the
`spec-quiet` comment no longer quote a count, and both documents say the
program prints its own tally.

**A new check asserts the absence rather than the agreement,** which is what
makes it immune to its own addition:

```
  no artefact quotes this gate's own check count                 PASS
```

`check_no_quoted_self_count` scans the justfile, `AGENTS.md` and the overview
for a count that names the spec layer, and fails if it finds one. **It cannot
be self-referential**: it asserts a number is *absent*, so adding the check
does not change the thing it is checking, and it needs no knowledge of the true
total. That is the general move for a self-describing gate.

**The first run failed, which is the evidence the check is real** (F-44's
repair is worth repeating verbatim: *"the test failed on the first run, which is
the evidence that it is real"*). It caught `AGENTS.md` and the overview both
still quoting the tally, **and two of its own false positives**, which is the
part worth recording:

* `1/6  spec layer` in the banner I had just rewritten — "1/6" is a **step
  counter**, not a count. A check tally is *N-of-M with M at or just above N*
  (68/68, 67/69); a step index never is, so `_is_tally` requires
  `M - N <= 2` and the banner is exempt on a *numeric* fact rather than a
  name in an allow-list.
* `7 checks` on five lines that are all **correct** — they are `run.py`'s 7
  acceptance checks, which we absolutely want to be able to say. The fix is a
  **two-part subject test**: a line is judged only if it names the spec layer
  *and* says "check". That is a fact about the line, the same discipline
  `check_recipes` uses for commands, and F-59's lesson about English
  allow-lists arriving one level down.

**The check's own blind spot is written into its docstring rather than left for
a reader to discover:** the subject test is per line, so a count split across a
line break ("verify_spec.py has 67" / "checks, no Docker") would escape it.
F-59's command check has the same per-line property and was accepted with it.
A paragraph-level test would be tighter and would start flagging prose that
mentions both checkers in one breath. **A check that reports its own blind spot
is worth more than one that silently has it.**

### F-73 [P2] fixed - The isolation proof's shipped footer pointed at `tests/test_results.py`, which does not exist

**File:** `src/reviewer/reviews/management/commands/isolation_proof.py`, `tests/test_isolation_proof.py`
**Found:** 2026-09-29, at FEAT-06, by reading the proof's output during Phase 0
**Why it matters:** The proof's `STILL NOT PROVEN` footer tells the reader that
the leaderboard predicate's own test lives in `tests/test_results.py`. **That
file does not exist.** The tests are in `tests/test_results_and_audit.py` —
the file the same feature created, and whose name the previous session evidently
had in hand when it wrote the line.

This matters more than a stale filename, because of *where* it is. The proof's
output is the artefact a panelist reads to decide whether the isolation claims
are real. A pointer to a file that is not there is worse than no pointer,
because the reader who follows it concludes **the test does not exist** rather
than **the name is stale** — and the honest answer, that a test does exist, is
the one the defect hides. It is F-59 one medium out: a document that names a
command has to be a command that can be typed, and this document is generated
Python rather than Markdown, so F-59's recipe scan never saw it.

**Resolution:** **Fixed 2026-09-29; awaiting review.** The footer names the real
file, and a new test walks **every** `tests/*.py` path the output names and
asserts it exists:

```python
    def test_every_test_file_it_names_actually_exists(self, seeded):
        named = set(re.findall(r"tests/[\w/]+\.py", output))
        assert named, "the proof named no test file, so this check proves nothing"
```

The check is general on purpose — the next renamed file is caught by shape, not
by someone remembering to fix a string — and the `assert named` is the F-61
guard: without it, a proof that named no file at all would pass vacuously,
which is the trap this project has now paid four times.

**The generalisable lesson: F-59 audits the Markdown and not the code, and
anything a command *prints* is a document.** The audit was extended to the
printed surface here, at the point of the one printed artefact that names a
source path.

### F-74 [P2] fixed - The findings tally's breakdown summed to 59 against its own stated total of 71, and no check added the parts up

**File:** `AGENTS.md`, `blueprint/context/project-overview.md`, `tools/verify_spec.py`
**Found:** 2026-09-29, at FEAT-06, by re-running Phase 0 and counting the ledger
**Why it matters:** Both files print:

```
| Findings | **71** — **0 open blocking**, 0 open, 1 unverified (F-27),
  10 accepted by decision, 48 closed |
```

and the parts sum to **59**, not 71. The true closed count is **60**: the
ledger's summary table holds twelve early findings (F-01…F-12) that
`verify_spec` folds into `closed`, and the printed "48" counts only the prose
entries. So the tally was **wrong by twelve, in the direction that makes the
ledger look worse than it is** — a P3-grade inaccuracy in the project's single
most-cited statistic.

**The check that should have caught it reached two numbers and stopped.**
`verify_spec` compared the claimed *total* against the ledger and the claimed
*open-blocking count* against the ledger, both correctly, and never summed the
breakdown. This is F-28's rule in its purest form: **a census number that
nobody derives from the census.** The total was derived; the breakdown beside it
was typed, and nothing in the project added them up.

**Resolution:** **Fixed 2026-09-29; awaiting review.** `48` → `60` in both
files, and a new check asserts the invariant rather than the value:

```
  AGENTS.md tally breakdown sums to its total                        PASS
  project-overview.md tally breakdown sums to its total             PASS
```

It extracts every `N <status>` bucket from the tally line and requires the sum
to equal the total, so the next finding that moves between buckets cannot
silently break the sum. **The lesson is the one F-58 already recorded and F-68
then had to re-learn:** a number with no derivation path must not be printed
next to a number that has one. The two sat three words apart and only one was
checked.

### F-75 [P3] fixed - The cold start was published as a 12–20 s range and measured 11.8 s, so the floor was wrong

**File:** `AGENTS.md`, `README.md`
**Found:** 2026-09-29, at FEAT-06, by `just coldstart` during Phase 0
**Why it matters:** F-68 closed by replacing a single value with **a range and a
budget** — *"a value is a claim a reader will check; a range is an admission."*
**This is that lesson arriving one session later, and it is a lesson about the
range itself: a range's endpoints are numbers too, and they were typed rather
than derived.** The published floor was 12 s; the measurement is 11.8 s.

The offset is 0.2 s and nothing is at risk — 11.8 s against a 60 s budget is a
factor of five. What is at risk is the *document*, because a reader who reruns
`just coldstart`, sees a figure outside the published interval, and concludes
**the tool is broken**. That is the exact failure mode F-68 was filed for, and
fixing the symptom while leaving the mechanism in place is what let it recur.

**Resolution:** **Fixed 2026-09-29; awaiting review.** The range is now
**11.8–20 s** in `AGENTS.md` and `README.md`, and the README names all three
observations (11.8 s, 12.1 s, 19.9 s) rather than a representative pair.
`tools/coldstart.py` remains the only place an exact figure appears, because it
is the only place one is reproducible — F-68's resolution, unchanged.

**There is no check here, and deliberately so.** A gate that re-measured the
cold start would need Docker, would double the length of the gate, and would
fail on machine noise rather than on a defect — a check that cries wolf is
worse than none. The standing rule is the one already written: **publish the
interval and the budget, and let the tool be the only source of a value.**

### F-71 [P1] closed - The audit chain was schema-only: `AuditEntry.objects.count() == 0` on a fully seeded event, and the proof verified it was append-only without ever checking it existed

**File:** `src/reviewer/audit/chain.py` (new), `src/reviewer/audit/models.py`,
`src/reviewer/reviews/management/commands/isolation_proof.py`
**Found:** 2026-09-29, at FEAT-06, by running the query instead of reading the model
**Why it matters:** `AuditEntry` shipped at FEAT-02 with `seq`, `prev_hash`,
`entry_hash` and `omitted_since_prev`, D-08 was decided at hour zero, and
`manage.py isolation_proof` could already assert that the trail is append-only —
`AuditQuerySet.update` and `.delete` both raise `TypeError`. **Nothing in the
repository ever wrote a row.** Measured on a fully seeded event:

```
results_state     = hidden
AuditEntry rows   = 0
```

So three separate things were true and none of them was visible:

* the audit trail, which the brief's *Judging Integrity* criterion asks for as a
  **"readable audit trail"**, contained nothing;
* `verify_chain` returned **no problems** — because "verifies" over an empty
  sequence is trivially true, and it is the most misleading PASS available;
* the isolation matrix's `audit` column had two possible answers and both were
  wrong. `0` reads as *"verified, and the answer is none"* — the exact option
  the `UNPROVEN` constant's own docstring says not to use. And `?` forever means
  the matrix never grows.

**This is F-61 for the fourth time, in four different media:** a min-cut
certificate naming no judges (F-61), a leaderboard that would have been refused
for the wrong reason, a CSV column of 126 empty cells (F-69), and now a
structurally perfect hash chain containing no links. The generalisation, and it
is what FEAT-06 should be read as: **a capability that is schema and a permission
is not a feature.** Every instance so far was a structure that could return the
right shape while containing nothing, and every one was found by a test that
asserted *content* rather than *shape*.

**The specific blind spot, and it is the interesting half:** the proof
**verified the trail's integrity without ever verifying its existence.** Those are
independent claims and the command only made the first. A check that re-walks a
chain is a check that a chain exists *and* is intact, and writing the first half
is what made the second half look covered.

**Resolution:** **Closed 2026-09-29.** `reviewer/audit/chain.py` is the writer and
the verifier: `append()` is the only supported way to create an entry, it takes a
row lock on the head so two concurrent appends cannot both claim a `seq`, and
`verify_chain()` recomputes each digest **from the row's own contents** rather
than re-reading the stored hash — so an in-place edit of `after` is caught, which
is the one tamper a signed list would miss and the reason the hash covers the
payload. `manage.py verify_audit` is the reviewer-facing command, and
`_still_not_proven` now says the matrix reports *how many* entries exist while
`verify_audit` re-walks the hashes.

**The chain is now populated by real traffic.** After a `just check` run:

```
  entries       7
  sequence      1..7
  chain head    ba2931abf07424d731fb22ad02dc7cb15127f41e707ce1a2d9f632f839b5edae
  CHAIN VERIFIED -- 7 entries re-walked, every entry hash recomputed.
```

Two of those seven are `denied` with **no actor**, and they are the gate's own
route-existence probes: `tools/run_acceptance.py` sends no credential on purpose,
because those preconditions ask "is this URL routed at all" and attaching a role
would make them answer a different question (F-42). The portal refused them and
logged it, which is the contract working. **It is recorded in `_log_denial`'s
docstring so the next reader does not file it as a defect** — and the alternative,
filtering our own probes out of the trail, would be a trail that hides who tried.

**Three corruption checks, and the first two runs found a gap in the tests.** The
sequence-gap check and the `prev_hash` link check could each be deleted with the
suite green, because the tamper test asserted
`any("is missing" in p or "prev_hash" in p ...)` — an `or` satisfied by whichever
check survived. That is **F-41's defect in a new file**: an assertion that cannot
distinguish the two defects it names, so it passes against half the implementation.
There are now three separate tamper tests, and the third is the case that matters
most: **a row inserted at the right `seq` renumbers nothing and leaves no gap, so
only the link check can see it.**

## Resolved — found in FEAT-05, 2026-09-29


*Five findings. **The one to read is F-70**, because it is the only one that was
*invisible to every gate in the project and would still have shipped.*

### F-70 [P1] closed - `ruff format` with no path argument reformatted `run.py` — the organizers' own acceptance program — and every gate stayed green

**File:** `pyproject.toml` (`extend-exclude`), and `run.py`, `bible/03`,
`bible/05`, `JUDGING.md`, `docker/healthcheck.py` as collateral
**Found:** 2026-09-29, at FEAT-05, by reading `git status` after the final gate
run
**Why it matters:** `just lint` was red on line lengths. The fix is
`ruff format`, and **`ruff format` with no path argument formats the whole
repository** — including `run.py`, which is the acceptance program **the panel
runs**. It rewrote 54 lines of it. It also rewrote `bible/03`,
`bible/05` and `JUDGING.md`, because **ruff 0.16 formats Python fenced code
blocks inside Markdown**, and `docker/healthcheck.py`.

**`run.py` is a GIVEN input.** AGENTS.md says the panel runs the identical
program; the submission ships the report that program produced. A submission
that reformatted the organizers' own checker, by machine, without noticing, is
claiming to run something identical while shipping something different — and the
diff is whitespace-only, so **no gate, no test and no reader of the report could
ever have told.**

That is the property that makes this the worst-shaped finding in the ledger:
**every existing check is a semantic check, and this change was semantically
identical.** `verify_spec.py` parses `run.py` for its check surface and still
passed 68/68. `just check` printed GATE GREEN. The acceptance report was
byte-identical. There is no gate in this project that can catch a
cosmetically-changed given file, and that is the finding — not the reformat.

**Resolution:** **Closed 2026-09-29.** All five files restored with
`git checkout`, and `pyproject.toml`'s `extend-exclude` now names `run.py`,
`bible` and `*.md` with the reason written beside them, extending the decision
already recorded against `tools/verify_spec.py` (F-43) from *our* gate to *the
organizers' file*. **Proven by re-running the exact command that caused it:**
`ruff format` with no path now reports 91 files unchanged and `git status` on
`run.py`, `docker/`, `JUDGING.md` and `bible/` is empty.

**The transferable rule, and it is the sharpest thing in this section: a gate can
only catch a change it is looking for, so a class of change with no gate needs an
exclusion rather than a test.** F-43 and F-46 were both about `verify_spec.py`;
this is the same lesson one layer out, and the layer is *the file we do not own*.
The reason it went unnoticed for a whole feature is also the general one: the
reformatting was invisible, so nothing prompted anyone to look.

### F-69 [P1] closed - The CSV export's first column was 126 empty cells, and the header test could not see it

**File:** `src/reviewer/reviews/api.py`, `tests/test_api.py`
**Found:** 2026-09-29, at FEAT-05, by the test that checks every exported value
against the database
**Why it matters:** D-11 puts ``source_key`` on every importable table so a
round trip is byte-identical *including natural keys*, and `Review` inherits the
column. **The loader never writes it** — it keys a review on `(judge, project)`
and leaves the field blank, so all 126 rows carry an empty string.

The export printed `review.source_key`. The result was a **structurally perfect
CSV of 126 rows whose first column contained nothing at all.** No acceptance
check failed. The header was right. `run.py` got a 200 and moved on.

**This is F-61's exact shape — structurally valid output containing nothing,
indistinguishable from output that works — and it is the third time this
project has paid it, in a different medium each time: a min-cut certificate that
named no judges, a leaderboard that would have been refused for the wrong reason,
and now a column of nothing.** The reason the header test could not find it is
the whole point: **a test that asserts the header is testing the header.** The
test that caught it asserts every cell of every row against the database, keyed
by criterion, and it is the second half of F-04's assertion — a correct header
with positionally paired values is the same defect with the evidence removed.

**Resolution:** **Closed 2026-09-29.** `_review_label()` falls back to the
`(judge, project)` natural key, which is what the loader actually keys on and
what a reader can check. `test_no_column_in_the_export_is_empty_throughout`
asserts the property generally rather than for this one column, so a future
empty column is caught by shape rather than by name. **The underlying gap —
populating `Review.source_key` — is NOT closed here** and belongs to FEAT-07,
which owns ``source_key`` and the byte-identical round trip. It is recorded in
`_review_label`'s docstring so the next person finds it where the workaround is.

### F-67 [P2] closed - "16/16 mutations on the new modules" was quoted in three documents and no command could produce it

**File:** `tools/mutation_test.py`, `AGENTS.md`, `blueprint/context/project-overview.md`
**Found:** 2026-09-29, at FEAT-05, by re-running the whole Phase 0 pass
**Why it matters:** FEAT-04 ran sixteen deliberate corruptions against the
assignment engine and the judge console, recorded the result in its archive, and
the number was copied into `AGENTS.md`, §13 of the overview and
`current-feature.md`. **`tools/mutation_test.py` had exactly one `MUTATIONS` list
of eighteen entries, and not one of them touched `reviewer/assignment/` or
`console.py`.** So the mutation harness could not produce the claim, could not
confirm it, and could not lose it.

This is **F-47 and F-48 verbatim**: a verification row that no command
reproduces is an unreproducible claim wearing the costume of a passing one. And
**F-59 could not catch it**, which is the more interesting half — `check_recipes`
asks whether a command named in a document *exists*, and this was a *number*
about a command, quoted correctly, attached to a command that exists. A check for
the existence of a tool cannot tell you the tool does the thing.

**Resolution:** **Closed 2026-09-29.** The sixteen were written into
`tools/mutation_test.py` with their detector test named, and **`just
mutation-test` now reports 44/44** — 18 original, 16 FEAT-04, 10 FEAT-05. The
harness caught **two of the new patterns as `pattern not found` on the first run**
(F-46's documented failure mode, from an indentation guess) and reported them as
a harness defect rather than as a pass, which is the behaviour F-46 was filed for.

**The generalisable lesson, and it is a gap in F-59:** *"every command named in a
document exists"* is not the same claim as *"every number quoted about a command
can be re-derived by running it."* Only the first is cheap to check. A number
attached to a command is exactly as load-bearing as one attached to a fixture,
and it drifts the same way.

### F-66 [P2] closed - `build-plan.md` said "3 of 10 features, next: FEAT-04" on a tree where FEAT-04 was committed and archived

**File:** `blueprint/build-plan.md`
**Found:** 2026-09-29, at FEAT-05, by re-running Phase 0
**Why it matters:** F-57 was found and fixed at BREAK-1: *"a status heading is
written once and never revisited when the thing under it changes."* It was
repaired in `findings.md` and in `project-overview.md` §10. **`build-plan.md` is
the third file carrying the same defect, and it is the file a build session works
from** — its Progress table read *"3 of 10 features — FEAT-01, FEAT-02,
FEAT-03"*, Phase D's checkbox was unticked, and **"Next: FEAT-04"** on a tree
where FEAT-04 had been committed six commits earlier with an archive and a green
acceptance line.

`verify_spec.py` passed 68/68 over it. **A machine cannot tell a stale feature
count from a fresh one** — the same limit F-57 already recorded, hit a third
time, and the reason this class keeps recurring is that the defence is the break
sweep rather than a check.

**Resolution:** **Closed 2026-09-29.** Corrected to 4 of 10, Phase D ticked with
its acceptance result and F-60/F-61/F-62's numbers, and the table now carries the
F-66 note inline **so the next reader sees the class rather than the fix.**

### F-68 [P3] closed - The cold start was documented as 12.0 s and measured 19.9 s

**File:** `AGENTS.md`, `blueprint/context/project-overview.md`
**Found:** 2026-09-29, at FEAT-05, by `just coldstart`
**Why it matters:** F-58 already closed the *class* — the cold start is the only
figure in the project measured by an instrument, it is quoted to a tenth of a
second in three shipped documents, and it has no regeneration path. It argued
from a **0.2 s** discrepancy that tenths are not a project number.

**0.2 s was the wrong estimate of the noise.** The measurement was **19.9 s**,
7.9 s — 66% — above the documented 12.0 s, on the same machine, on the same
budget. So the honest reading of F-58 is stronger than the one it closed with:
**not "the tenths jitter" but "the figure is dominated by machine state and has
never been reproducible."** Two runs in one session gave 9.1 s and 19.8 s for
the *same* offline boot path, which is a factor of two, not a rounding.

**Nothing is at risk: 19.9 s against a 60 s budget is a factor of three of
headroom.** What is at risk is a document that says 12.0 s when the tool says
19.9 s, because the number is quoted as *measured* and a reader who reruns it
concludes the tool is broken.

**And then the same session measured it again, 20 minutes later, at 12.1 s.**
Same machine, same command, same clean volume: **12.1 s and 19.9 s, a factor of
1.6.** The offline proof in the same session read 9.1 s and then 8.2 s. So the
figure is not merely jittery at the tenths — **it is dominated by machine state,
and the original 12.0 s was not a stale number but a lucky one.** Any single
value in any document was wrong roughly half the time.

**Resolution:** **Closed 2026-09-29.** Both documents now carry a **range and a
budget — 12–20 s observed, budget 60 s** — and `tools/coldstart.py` remains the
only place an exact figure appears, because it is the only place one is
reproducible. The lesson added to F-58 is the stronger one: **a number with no
regeneration path must be published as a range and a budget, never as a value.**
A value is a claim a reader will check; a range is an admission, and admitting one
is what keeps the rest of the document trustworthy.

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

### F-51 [P2] closed - `for_actor_and_subject`'s docstring described behaviour the code did not have, and a judge-organizer was refused a rule the export already defeated

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

**What happened next, and why it is the most valuable entry in this section.**
FEAT-03 did the right thing with an ambiguous security rule and almost the wrong
thing: it **kept the strict code and corrected the docstring**, on the grounds
that "the strict reading is the safe one and nothing can reach this accessor
until FEAT-05 builds the route that does." The finding was left **`fixed` rather
than `closed`**, and `fixed` blocks completion *on purpose* — a repair is not
done until a review has looked at it.

**The review looked, at FEAT-05, and it went the other way.** Presenting it as
a product question rather than a code question is what produced the answer,
because the strict reading turns out not to be the safe one — it is the
*incoherent* one:

* the refusal protected **nothing**. `/api/v1/export.csv` is organizer-scoped
  and contains every score in the event, so a judge-organizer read all 126 of
  them anyway, through a documented route, in the same feature;
* so the peer-blindness was real for a pure judge and **cosmetic for the one
  person it most plausibly matters about**;
* and **narrowing** — the only reading under which the refusal means anything —
  would have forced `can_read_all_reviews` to split into "may read all scores"
  against "may staff this event", *and* restricted the export, which is the very
  route T2-7 scores. A stricter rule that costs a scored feature is not obviously
  the safer rule.

**Decided by the human, in writing: the organizer wins.** The guard is now
`actor.is_judge and not actor.can_read_all_reviews`, so `for_actor` and
`for_actor_and_subject` agree for every actor, and the docstring is true.

**The consequence, stated rather than buried: a judge-organizer is not a
peer-blind actor, and this accessor is not what makes them one.** They are
refused the leaderboard *while judging is open* by a different rule (FEAT-06),
and until that rule exists they can read every score. That sentence is in the
docstring, because **closing F-51 quietly would close a question rather than
answer it** — which is the distinction `fixed`-blocks-completion exists to draw.

**Resolution:** **Closed 2026-09-29 at FEAT-05, by decision rather than by
patch.** Three deliberate corruptions were run against the new guard and all
three were caught by a test named for the rule: dropping the
`not can_read_all_reviews` clause (pure judges stop being refused), reverting to
the pre-F-51 strict reading, and removing the self-subject allowance. The
previous version's test would have passed against the first two, because it only
asserted that a judge-organizer was refused — so a rule that fired on *everyone*
satisfied it perfectly. The new test asserts **equivalence** between the peer
result, the self result and `for_actor`, and a separate one pins that a *pure*
judge is still refused, because a guard that grows a clause can grow it the wrong
way.

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

**F-51 is now `closed`, at FEAT-05, and it went the other way.** The paragraph
below is how the entry read when FEAT-03 wrote it, and it is left in place
because the reasoning it contains is the reasoning that made the decision
possible. The code was right *for now*, the docstring matched it, and the
underlying question — *should* a judge who also organises be refused their own
peers' scores? — was deferred to the feature that owns the route reaching the
accessor, on the principle that closing it then would be closing a question
rather than answering one. **FEAT-05 owned it, asked it as a product question,
and the answer went against the interim code** — because by then the CSV export
existed, and a rule the export already defeats is not a security control. See
**F-51 closed**, above.

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
