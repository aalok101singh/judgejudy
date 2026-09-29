# BREAK-3 — the T3 claim, decided against what is green

**Date:** 2026-09-29. The same seven steps as `bible/08` §1b, run on a clean volume
with the network off.

---

## 1–4. What was verified, and how

| # | Step | Result |
|---|---|---|
| 1 | clean `down -v`, `up` **network off** | volume removed and recreated, **healthy** |
| 2 | `run.py` against `.dogfood.toml` | **7 of 7 PASS**, header `claimed: T1 T2`, summary **`claimed T1 T2, verified T1 T2`** |
| 3 | `isolation_proof` | **exit 0** |
| 4 | full extended suite | **green**, 575 tests |

`run.py` **exits 0 unconditionally** (F-32), so none of the above is read off an
exit code. The acceptance result is parsed out of the report **body**.

### The T2 claim was applied, and it is the one machine word in the file

`.dogfood.toml` said `claimed = ["T1"]` for five features after FEAT-05, and
**that was correct** — the claim is made at a break, by a human, in writing. The
diff was prepared and held rather than applied on initiative. One line changed;
the report was regenerated, never hand-edited.

### The isolation matrix, from the proof on a clean volume

| | draft | submitted | locked | leaderboard | export | audit |
|---|---|---|---|---|---|---|
| visitor | 0/126 | 0/126 | 0/126 | refused | refused | refused |
| participant | 0/126 | 0/126 | 0/126 | refused | refused | refused |
| **judge** | **5/126** | 0/126 | 0/126 | refused | refused | refused |
| organizer | 126/126 | 126/126 | 126/126 | 41/126 | 126/126 | 3 entries |
| admin | 126/126 | 126/126 | 126/126 | 41/126 | 126/126 | 3 entries |

A judge sees **5 of 126** rows. An organizer sees 126. Nobody but an organizer
gets a ranking while results are hidden, on **either** surface.

---

## THE SENTENCE IN THE REPORT THAT DID NOT CHANGE

```
claimed T1 T2, verified T1 T2
```

`verified` is the machine's word and it **could not have said T3**, because
`run.py` contains **no T3 checks at all** — seven checks, three T1 and four T2.
`verified` is prefix-locked over `["T1","T2","T3","T4"]` and breaks at the first
tier with no passing check, so **`verified T1 T2` is the ceiling a flawless build
can reach.**

A panelist reading that line should conclude: *they claimed T2, the machine
confirmed T2, and there is no machine check for T3.* That is the honest situation,
and it is the whole reason the claim in the next section is a **human judgement
against a rubric** and the one part of this break no command can verify.

---

## THE T3 CLAIM: what is genuinely built

All five REQ-T3 requirements ship, each with tests, and each traceable to a
module rather than to a paragraph:

---

## THE GAP, IN PLAIN WORDS

The claim is T3. These are the things a reviewer will find, and they should be
said by us first.

**1. Three controls are cut, and each is disclosed in three places** — the cut
ledger, the README, and the module docstring that would otherwise imply the
control is there.

- **Comment rate limiting.** `bible/07` V-8 names four controls for comment spam
  and XSS. **Three ship; this one does not**, and it is the only place this project
  has written a control down in its own threat model and then not shipped it. A
  reader of the threat model would reasonably expect all four.
- **Ballot cookies and rate limiting.** Open-link mode derives the identity from
  IP + user agent, hashed. A determined operator can mint ballots by changing
  networks. The identity is **weaker than it looks**, and the influence report is
  the mitigation we chose — which **explains** concentration rather than
  preventing it.
- **Quadratic voting.** Weight is capped at 3 inside the budget. Decided twice
  already: D-13 puts the anti-abuse answer in the published report rather than a
  fancier ballot, and a quadratic ballot would leave the harness measuring a
  function the product stopped using.

**2. The published leaderboard is an UNNORMALIZED raw weighted mean.** FEAT-08 is
not built. The page says so on **every** render, and there is a mutation that
flips the label to `"corrected"` so the sentence cannot be quietly upgraded. **The
inconvenient result that makes this defensible is published too:** the panel has
**no statistically detectable judge-severity effect** (permutation *p* = 0.234),
so this ranking is a fair reading of the data — but that is a measurement we
publish, not a property the code has.

**3. Randomisation makes position bias zero-MEAN, not zero.** The confidence
interval spans zero; the standard deviation does not. The ballot page says this
in the markup on every render, and a test fails if the word "eliminates" appears.

**4. Comment-based collusion is not prevented.** `bible/07` V-9 records this as
"Not prevented — moderation is human work", and nothing built here changes it.

**5. `verified` will read `T1 T2` even with this claim in the file.** Arithmetic,
not a shortfall. The report ships unedited and the README explains it in full.

---

## THE ACTUAL DECISION AT THIS BREAK, and it is not the one expected

**The T2 claim is applied. The T3 claim is prepared and NOT applied**, because
applying it turns this project's own gate red. That was not anticipated before
the diff was written, and it is the most interesting thing BREAK-3 produced.

### What the gate does

`tools/run_acceptance.py` enforces the organizers' own stated rule:

```python
overclaim = claimed_tiers - verified_tiers
if overclaim:
    problems.append("OVERCLAIM: .dogfood.toml claims ... but the report verified ...")
```

`verified` is `T1 T2`, because **there are no T3 checks in the organizers'
program**. So claiming T3 puts `{"T3"}` in the overclaim set.

### Proved by execution, not by reading the code

Claiming T3 and running the gate against it:

```
claimed: T1 T2 T3
T1  gallery is public ................. PASS
T2  csv export works .................. PASS
claimed T1 T2 T3, verified T1 T2
note: claimed but not verified: T3

 GATE FAILED:
   - OVERCLAIM: .dogfood.toml claims T3 but the report verified T1 T2.
     The organizers state that overclaiming is the one thing that actually costs points.
```

Then reverted, and the gate returns to `GATE OK`. The full T2 claim is in the
file and `acceptance-report.txt` is regenerated and committed.

### The collision, stated plainly

**All five REQ-T3 requirements ship.** And **the gate says claiming T3 is
overclaiming**, because the only way it can know what was built is by parsing
seven checks that stop at T2.

That is the honest collision at the centre of the whole brief. The brief says
overclaiming is the one thing that costs points. `verified T1 T2` is a **ceiling,
not a measurement of our work** — nothing in this repository can verify T3. The
gate is doing its job; the question is what the job is *for*, when the checker
cannot see the tier.

### Three options, and the choice is the human's

| | what it does | cost |
|---|---|---|
| **A. Claim T3** | `claimed = ["T1","T2","T3"]` | **the gate goes RED.** Ship red, or weaken a mutation-tested gate to go green |
| **B. Do not claim T3** — *recommended* | `claimed = ["T1","T2"]`; T3 shipped, tested and documented as built | the tier is **not entered in the organizers' scoring field** |
| **C. Add an accepted-overclaim flag** | a documented exception, like the deleted `--allow-false-passes` | **an escape hatch in the gate.** This project deleted one of those on principle and refuses to re-add |

**Why B is the recommendation.** The report is the organizers' artifact and it
ships **unedited**. If T3 is entered in the field their program parses, their
program will print a sentence containing the word **OVERCLAIM** about this
submission. That one word is worth more to a panel than the tier is, because it
is the single thing the brief singles out.

> **T3 being built, tested and documented is not the same claim as T3 being
> entered in the scoring field.** Only the first one is ours to make.

A gate that passes when broken is a lie (F-33) — but so is a gate switched off
because it is inconvenient. **Neither is on offer, and B is the branch where
neither has to be.** Recorded as **F-91 [P1], open on purpose**: a decision, not
a defect.

**Because the claim is not applied, `v-t3-verified` is not tagged.** Tagging it
while the gate prints OVERCLAIM about the same tree would assert the opposite of
what the machine says. `v-t2-verified` stands and is current.

---

## 7. THE T3 REQUIREMENTS, and what genuinely ships

| | requirement | what ships | tests |
|---|---|---|---|
| **01** | community voting, configurable access; amplification inside an identity budget | `/vote/`; weight 1 on every project **exactly exhausts** the budget, so favouring one project means giving another up; mandatory, attributable, **free** abstention; Borda via the `schwartzian` the harness attacks | `test_voting.py` |
| **02** | comments on gallery projects, with a moderation affordance | `/projects/<id>/comments/`; plain text, escaped at **both** render paths, `pending` by default, organizer queue, length cap | `test_comments.py` |
| **03** | results hidden from everyone but organizers during the window | `/results/` **and** `/api/v1/results`; same predicate, same aggregate, and a test asserts the two agree row for row | `test_results_page.py`, `test_results_and_audit.py` |
| **04** | randomised project ordering, stable across requests, zero-**mean** claim | `/vote/` calls `presentation_order` — **the same function the harness attacks**, so claim and code cannot drift | `test_ballot_order.py` |
| **05** | anti-abuse: duplicate detection, audit trail, published influence report | per-identity budget, hash-chained audit, and the report at `/api/v1/influence` with **no thresholds anywhere** | `test_influence.py`, `test_results_and_audit.py` |

Plus, from earlier increments in the same feature: the three isolation-matrix
columns and the audit chain's missing writer.

**This is a complete tier, not a partial one.** That has not been true before at
any break in this project, and it is why this break was a decision rather than a
formality — even though the decision turned out to be about the *claim* rather
than the *work*.
