# FEAT-06 increment 7 - the public results page (REQ-T3-03)

**Date:** 2026-09-29 - **Phase F** - **Gate:** none

**The last named T3 gap.** `results.results_visible_to` and `results.leaderboard`
both existed and were both tested -- for `/api/v1/results`. A reviewer opening a
browser never asks for JSON, so for nine hours the brief's most carefully worded
capability was enforced only on a surface nobody would have visited.

**17 tests, 3 new mutations.** One finding, and it is the ninth appearance of the
same class.

---

## One predicate, one aggregate, two renderings

The page calls the **same two functions** the API does, and the test that matters
is `TestThePageAndTheApiAgree`: same actor, same event, and the HTML page and the
JSON endpoint must produce **the same rows in the same order with the same means**.

Two renderings of one ranking is a liability. It is also the thing that caused
F-84's second-order bug, where `voters` meant one thing in the tally and another
in the influence report — and the reason it happened is that **nobody compared the
two.** This is that comparison, written before it was needed.

---

## F-89 [P2] - a published event served the public an empty board

`leaderboard` computed every row from `Review.objects.for_actor(actor)`, and for
a **participant or a visitor** that is empty — they hold no reviews. So once
results were published the page returned **200 with a board of nothing**:
structurally valid, renders, passes every status-code assertion, ranks **zero**
projects. **F-80's shape, on the capability the brief is most careful about.**

The FEAT-05 decision was deliberate and is **kept**: *"publishing the results
opens the endpoint, it does not widen the scope."* What that sentence did not
consider is that scoping is **protective rather than decorative** — it exists so
a judge cannot infer what other judges scored, and a visitor has nothing of their
own to protect, so narrowing is vacuous for them.

> **Narrow the board only when narrowing protects somebody.**

| actor | board | why |
|---|---|---|
| organizer / admin | whole event | they staffed the panel |
| **judge** | **their own reviews** | their five reviews would otherwise carry the standing |
| participant / visitor | whole event | nothing of theirs to hide, and a whole-event board leaks nothing they did not already know from the gallery |

The branch is `elif _has_any_review(actor)` — an ``EXISTS`` against the accessor,
**not** `actor.is_judge`, because a judge with no assigned reviews is in the same
position as a visitor, and the real question is *"is there anything of this actor's
own that narrowing would hide"*.

**It is still a scoped query.** The wider board is reached by building a real
``Actor`` and passing it to ``for_actor`` — not by adding an unscoped read, which
would be exactly what D-01 and the JJ01 lint rule exist to forbid, and `just lint`
is part of the gate, so this is enforced rather than asserted.

### Proved negative, and the detector is the point

Removing the narrowing is caught by
`test_a_judge_published_still_sees_a_ranking_over_a_scoped_set` — **a test that
predates this feature by two increments.** The security-relevant half of F-89 was
already pinned at FEAT-05, and the sabotage found it immediately instead of
needing a new assertion. That is what a pre-existing, well-targeted test is for.

---

## The refusal is asserted four ways, because four things could be wrong

A 403 whose body names the projects, or a page that says "results are not
available yet", is a **different answer** from a refusal — the second is a page a
reader can screenshot and describe. So the refusal is asserted on:

1. the **status** (403);
2. an **empty body** (D-02);
3. the **absence of a `Location` header** (never a redirect);
4. the **absence of any project title in the bytes** — the one a shape check
   cannot make. A page rendering a board of zeros satisfies "the page has a
   table" and fails "the reader learned nothing".

---

## Two things the page always says

- **`unnormalized-raw-weighted-mean`, on every 200.** A published ranking that
  does not say whether it is corrected is a ranking a reader has to guess about.
  There is a mutation that flips the label to `"corrected"`, because that is the
  exact assumption the whole detectability analysis exists to prevent — printed
  by the one surface a human reads.
- **Whether the board is scoped.** A published *judge* is told, in words, that
  they are seeing **their own reviews only** and that "a published ranking over
  your own scores is not a result." Without that, a judge reads four projects'
  worth of mean scores and calls it the results — the exact misreading this
  capability invites.

---

## What it cost

| | |
|---|---|
| Tests | 555 -> **572** (17 in `tests/test_results_page.py`) |
| Mutations | 82 -> **85** (3 new) |
| Findings | **F-89 [P2]** |
| Spec | the F-82 route check caught `/results/` as undocumented on its first run — the mechanism working |
