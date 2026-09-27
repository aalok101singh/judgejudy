# DISCORD-QUESTIONS.md

**Purpose:** get the organizers' attention once, not nine times — and **without
handing the channel a map of our method.**

> ## ✅ CLOSED — 0 open questions. We are not sending the DM.
>
> **Asked:** is labelled synthetic data allowed in the Normalization Proof
> artefact?
>
> **Answered:** *"Yes, synthetic data is fine for validation as long as the proof
> also runs on the real fixtures. Showing it recovers a known effect is exactly
> the kind of rigour the bonus is looking for."*
>
> **The DM is not being sent.** The 0.31 question is dropped. It was a
> nice-to-have, we got a "yes" to the only question that mattered, and asking
> again is worth less than not bothering a moderator twice. **The 0.31 reading
> stays a private observation in `JUDGING.md`, offered as a possibility and not
> as a claim** — which is how it should have been written anyway, since we never
> knew their definition.
>
> **What that does and does not change:**
>
> - **The condition is already met.** Three of the proof's four components are
>   computed on the published 126 reviews with nothing simulated; the recovery
>   experiment validates the method rather than making a claim about the data.
>   `06` §4.4a maps a data source to every component, and
>   `docs/REAL-FIXTURE-RESULTS.md` exists so the real-fixture half can be read
>   with no synthetic content in it at all.
> - **They also told us the grading criterion, unprompted.** *"Exactly the kind
>   of rigour the bonus is looking for"* is a moderator describing the rubric in
>   plain language. **A parameter-recovery experiment is the artefact they
>   want, not a bigger σ reduction** — which de-risks the six protected hours in
>   `08` §9. Recorded as `README` U-4 and U-5.

**History:**

| | |
|---|---|
| **Asked, answered** | 2 — the σ question (contribution `README` U-1) and synthetic data (U-4) |
| **Asked, open** | **none.** Fourteen candidates → one survived the filter → asked → answered |
| **Dropped by decision** | 1 — the 0.31 DM, not sent |
| **Self-answered by reasoning** | 13 |
| **Moot** | 1 — webhook delivery, cut at H+0 |

> ## ⚠ STANDING RULE — read before posting anything
>
> **The first draft of the public post was wrong.** It carried the permutation
> test, the noise-floor ratio, the `k`-shrinkage dial, the σ curve and the 0.31
> reproduction — the substance of our Normalization Proof — sitting in a channel
> with thirty other teams in it.
>
> 1. **The public channel carries clarifications only.** Questions and decisions.
>    No numbers, no methods, no findings.
> 2. **A question must pass two filters before it is sent:** is the answer already
>    in the published material, and would we build differently? **If either
>    answer is no, drop it.** That filter took fourteen candidates down to one.
> 3. **The test for every line: would this help a competitor, or only help the
>    organizer?** If both, cut it.
> 4. **Do not send a second message to a moderator for a nice-to-have.** We got
>    a "yes" to the only question that mattered. That is the end of it.
| **Moot** | 1 — webhook delivery, cut at H+0 |

---

# 🟢 PUBLIC POST — paste this, in the public channel

**One question. That is deliberate — see "Why only one" below. Silence is a
valid answer, and the post is written so nobody feels obliged to reply to more
than the one question.**

**— — — — — — — — PASTE EVERYTHING BETWEEN THESE LINES — — — — — — — —**

> Thanks for the σ clarification — 0.42 lining up with what we measure was a
> useful confirmation.
>
> One question, then. Rather than a list: we did the work, we hit one wall we
> can't resolve from the spec, and it's a yes/no.
>
> **Is labelled synthetic data allowed in the Normalization Proof artefact?**
>
> We're planning to validate our estimator on simulated panels generated from
> the fixture's own structure, with known ground truth, so the artefact shows
> the method recovers a known effect rather than just that it didn't make
> anything worse. Every other part of the proof is analysis on the published
> fixture and needs none of it.
>
> If simulation isn't fine we'll drop it — the proof still stands on the
> fixture alone, just with a weaker claim.
>
> Happy to explain the construction if that would change the answer.

**— — — — — — — — END PASTE — — — — — — — —**

*108 words. Everything that was carrying method, results, or derivation is
gone.*

## Why only one

We started this list with fourteen items. It is now one, and the reasoning is
worth keeping because it is the filter for anything new that comes up:

> **A question earns its place only if the answer is not already in the
> published material, AND we would build differently depending on it. Both must
> be true.**

| Candidate | In the spec already? | Would we build differently? | Verdict |
|---|---|---|---|
| Is the `run.py` T1/T2 ceiling final? | **Yes** — `run.py` is published; if more checks were coming they'd publish them. And `spec.md` line 303 says the checker is a floor, not a ceiling; the spec's own example report shows `claimed T1 T2, verified T1 T2` | **No** — we build T4, claim T4, explain the prefix-lock either way | **Dropped** |
| Does the bonus want a visible σ drop or demonstrated correctness? | n/a | **No** — we ship both; the curve gives one and the held-out test gives the other | **Dropped** |
| Is 0.31 a target or illustrative? | n/a | **No** — we report our own numbers with definitions regardless | **Dropped** |
| Is the review target per-track or event-level? | n/a | **No** — a nullable per-track value that inherits is a strict superset of a single event integer, so "no" costs a sentence in `DATA-MODEL.md`, not a migration | **Dropped** |
| Must bulk import round-trip with export? | n/a | Marginally — "no" saves ~1.5h of 69 | **Dropped** |
| Per project, team or submission in the results? | **Yes** — the fixture's duplicate submission makes any other reading wrong | No | **Dropped** |
| Self-certifying records vs a key directory? | n/a | No — ~1h, and self-certifying is standard | **Dropped** |
| Draft behaviour after the deadline? | n/a | No — savable-never-submittable is standard product behaviour | **Dropped** |
| Judge who is also a team member? | n/a | No — COI is a hard block everywhere | **Dropped** |
| Bonuses independent or portfolio? | n/a | **No** — would not change a line of code | **Dropped** |
| **Is labelled synthetic data allowed in the proof?** | **No** — `spec.md` says the fixture is "input, not your data model" and the pairwise bonus implies synthetic comparisons are fine, but the Normalization Proof is scored separately and nothing settles it | **Yes** — the recovery experiment is the part that proves *correctness* rather than absence of harm, and it ships or it doesn't | **KEPT** |

**The dropped checker-ceiling question is worth recording anyway**, because the
thing it was *about* is still true and still has to be handled — we just handle
it in the README instead of by asking.

`run.py`'s `verified` list is prefix-locked and only T1/T2 have checks, so a
flawless build still prints `verified T1 T2` plus
`note: claimed but not verified: T3 T4`. **This is the spec's own example
output**, and the spec says the checker does not look at HTML, framework,
database, layout or history — it verifies 6 of 60 demands (`02` §11) and is a
gate, not a score. `README.md` states all of it in one plain paragraph, the
real `acceptance-report.txt` is committed unedited, and our **own extended
suite is committed separately and clearly labelled** as the evidence for the
T3/T4 demands the checker does not cover (`03` §5, `08` §6). No question
needed.

**The version of this question we would have sent, and why not:**

*"Is the T1/T2 ceiling on `run.py` final? We're building to T4 and plan to claim
T1–T4. As written, `verified` is prefix-locked and only T1 and T2 have checks, so
a flawless build still prints `verified T1 T2` plus the `note:` line. We plan to
explain exactly that in the README. Fine as-is, or is a fuller checker coming?"*

**Three reasons it fails the filter:**

1. **The answer is already available.** `run.py` is published. If more checks
   were coming, publishing them is the entire point of a shared acceptance
   suite. Asking a moderator to speculate about their own release schedule is
   not an ambiguity question.
2. **Nothing branches on the answer.** We build T4, claim T4, and explain the
   prefix-lock in the README in every branch. There is no line of code and no
   hour of the plan that changes.
3. **It reads as reassurance-seeking**, and the first thing a mod thinks is
   *"have you read line 303?"* Opening a first DM to a moderator with that is a
   bad first impression to spend on something that is already answered.

**One thing still visible and worth accepting:** the seven decisions themselves.
Some of our design choices are observable, and asking about them is the price of
getting them confirmed. If you want to go further, the least costly one to drop
from the list is the review-target line — it is the only one where our
justification is doing more work than the question. **The rest are table
stakes** that a competitor would arrive at anyway, and being visibly organised
in public is worth something on its own.

---

# 🟣 The DM — NOT SENT

**Dropped by decision, 2026-09-27.** It would have carried the recovery
experiment's full construction and the 0.31 finding. We got a "yes" to the only
question that mattered, and a second message to a moderator for a nice-to-have
is worth less than not asking twice.

**What we keep instead, and it is nearly all of it.** The construction is already
written down in `06` §4.4a item 3 in the proof itself, which is where a judge
reads it and where it belongs. The 0.31 reading is already in `06` §4.4c, phrased
as *"offered as a question rather than a correction, because we do not know their
definition and we may have the wrong one."* **That phrasing is what makes the
paragraph safe to publish**, and it would have been the right phrasing whether
or not we had asked.

---

# Self-answered, with the reasoning

**These are the ones we were going to ask and then worked out we don't need to.
Written down because "we checked and decided" is itself an answer worth having
in the repo — and because at hour 50 someone will want to re-open one of them.**

| # | The question | Our decision | Why it isn't a question |
|---|---|---|---|
| R-1 | Per **project**, **team** or **submission**? | **Team, latest-wins** on the `supersedes` chain | `fixtures.json` contains two identical submissions from `tm_07` under different IDs. Any reading that doesn't handle it is wrong. Both rows are retained and the export carries a `counted` flag, so it's auditable and reversible |
| R-2 | Event-level or **per-track** review target? | **Nullable per-track, inheriting from the event** | Two fixture tracks are provably infeasible at 3, which a single integer cannot express. The data makes the choice. (Stated publicly as a decision; the derivation goes in the DM) |
| R-3 | Proof: visible **effect** or demonstrated **correctness**? | **Both, in that order** | The curve gives 0.4323 → 0.2547; the held-out test gives 0.7952 → 0.6753 with a CI excluding zero. Whichever the bonus wants, we have it. Asking would be asking permission to do less |
| R-4 | Is 0.31 a **target** or illustrative? | Treat as **illustrative** | It changes nothing we publish. We report our own numbers with definitions and note the reproduction. The only way it changes the build is if we tuned to it, and we have decided not to (`06` §4.4b) |
| R-5 | **Round-trip** or one-way import? | **Round-trip**, with a property test | "A platform you cannot leave is a trap" reads as a requirement. The only cost of guessing wrong is ~1.5h of a 69h budget, and asking to save 1.5h is not a good use of their attention |
| R-6 | Published **key directory** or self-certifying? | **Self-certifying** + a published keyring | Standard, sufficient, verifiable offline. The alternative is ~1h for a discovery endpoint we don't need |
| R-7 | Records per **event** or portal lifetime? | **Per event** | Matches the schema, keeps revocation tractable, matches "judges served at this event" |
| R-8 | **Drafts** after the deadline? | Savable, never submittable | A platform that freezes every write fails an organizer fixing a typo |
| R-9 | Judge who is **also a team member**? | **Hard block**, at assignment and re-checked at submission | Conflict of interest is near-universally a hard block rather than an override |
| — | Normalization over judges or projects? | **Judges only** | Already decided and defended in `06` §4.5. Carried forward from the original ambiguity log |
| — | Bonuses independent or a portfolio? | Doesn't matter | It would not change a line of code |
| — | **Webhook** delivery semantics? | **Moot** | Cut at H+0: zero points on all four criteria, and the SSRF work is a real bug class under time pressure |
| — | Certificate format? | Ours | "Certificate and record generation"; we make it verifiable anyway at near-zero marginal cost |

---

## What we are NOT asking, and why

| Not asking | Why |
|---|---|
| Stack, framework, database | The spec is explicit that these are not graded and not checked. We picked what one person can build correctly in 69 hours |
| Whether to use an LLM to score | Settled locally with measurements. Not an open question |
| Whether `acceptance-report.txt` should be edited | Never. The brief says three times and the panel runs the same program |
| Anything derivable from `fixtures.json` | We re-derived it. Six errors in our own census came from *not* re-deriving. If it's in the file, it's our problem, not theirs |
| Our normalization method, constants, or results | **Competitively sensitive.** Goes in a DM to a mod, never in the channel |
| The rubric seed weights | Ours to choose, and unequal weights are the only way to demo the feature the market leader doesn't have |
