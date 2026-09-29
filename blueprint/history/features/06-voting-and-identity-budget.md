# FEAT-06 increment 5 - voting, the identity budget, and the tally (REQ-T3-01)

**Date:** 2026-09-29 - **Phase F** - **Gate:** none

Closes the cut recorded at increment 4. `/vote/` renders the order *and* accepts
a ranking; the vote is written, the budget binds, the tally calls the estimator
the harness attacks.

---

## The budget is one sentence

> **Weight 1 on every project exactly exhausts it.**

D-12 says voting claims cost **amplification inside an identity budget, not Sybil
resistance** -- we are not trying to stop someone buying forty identities, we are
trying to stop one identity concentrating. So the cap is on total weight per
`voter_key`, and it equals the ballot size.

The consequence is the whole point: a voter who wants weight 3 on a favourite
must give another project up, or leave it unvoted (which ranks it last). That
makes the ballot **constant-sum**, and constant-sum is exactly what
`bias_attack.schwartzian` relies on when its docstring says drift is "a genuine
*redistribution*" with "no room for a uniform inflation to hide inside".

### A budget of `3 x n` was the first design, and it was decoration

It permits weight 3 on *every* project, so the cap never binds. **A budget that
cannot bind is not a budget** -- it is the F-76 class in a constraint: a tunable
constant wearing the costume of a rule. It is now the first mutation, and the
sabotage proved **five tests** turn it red.

---

## F-84 [P1] - an abstention silently became a VOTE

`tally` ranked every `Ballot`. `ranking_of` returned *the voter's votes, then
every unvoted project in ballot order* -- so a voter who had cast **nothing at
all** came back with a full-length ranking equal to their raw ballot order, and
the aggregator scored them as though they had voted for it.

**The surface had a button labelled "Abstain" that recorded the abstention in the
database and then voted the ballot anyway when tallying.**

This is P1 and not P2 for a reason the others are not: the defect does not corrupt
a number, it **inverts the meaning of a control the brief explicitly asks for**.
REQ-T3-01 requires mandatory attributable abstention. A reader auditing the code
would have found the correct abstention model *and* a tally that contradicted it,
in the same commit.

### How it was found: a test asserting a TIE

A test created a third ballot to break a tie between two others, and asserted the
two were equal. **They were not.** The instinct was "the tie test is wrong"; the
reality was that **the third ballot had moved the numbers** -- because the third
ballot had no votes and was being counted anyway.

**A test asserting a negative caught a positive-valued defect.** That is the F-21
lesson applied to a case nobody was looking for, and it is the cheapest possible
route to a P1: no new test, no new harness, one assertion that was already
written for a different reason.

Pinned by three tests: standings must be **byte-identical** before and after
adding an abstainer, and an abstainer must add zero to the `voters` count.

### A second-order bug in the same function

`voters` counted "ballots whose ranking mentions this project", so a project
ranked **last** by every voter reported **full support** -- contradicting the
influence report's distinct-identities count *on the same data*. **Two shipped
artefacts answering one question with different definitions is a worse defect than
either being wrong alone**, and a reader comparing the leaderboard to the
influence report would have found the disagreement. One definition now, read from
the `Vote` rows.

---

## A property worth saying out loud

**Two perfectly opposite ballots cancel exactly** -- 4+3 and 3+4 -- and a test now
pins it. That is the constant-sum property, and its consequence is real:

> **A perfectly symmetric brigade cancels. Brigading has to be *asymmetric* to
> move anything.**

The cancellation test alone would pass against a tally that always returns equal
points, so the **opposite** is asserted too: a third asymmetric voter must break
the tie. A control that only fires is not a control.

---

## The two things reused rather than rewritten

| | |
|---|---|
| `schwartzian` | the tally calls it, so the harness's drift measurement describes the function the product uses |
| `projects.views._csrf_enforced` | the POST goes through the *existing* CSRF wrapper -- a second copy would be a second thing to get wrong in the layer that lets somebody cast a vote as you |

And the form is a **form, not a free-text ranking**: the server reads the ranking
out of the ballot order it already fixed, so reordering the page cannot submit an
order the voter was never shown.

---

## What it cost

| | |
|---|---|
| Tests | 503 -> **526** (23 in `tests/test_voting.py`) |
| Mutations | 72 -> **76** (4 new, each naming its detecting test) |
| Suite | 526 pass - `just check` **GATE GREEN** at 7/7 - spec 72/72 - lint clean |
| Findings | **F-84 [P1]** |
| Cuts recorded | quadratic voting; rank-only results weighting; the increment-4 ballot cut marked superseded |
