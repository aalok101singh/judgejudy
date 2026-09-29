# FEAT-06 increment 4 - the randomised ballot as a PRODUCT path (REQ-T3-04)

**Date:** 2026-09-29 - **Phase F** - **Gate:** none (BREAK-3 is next,
`v-t3-verified`)

The acceptance line's two clauses were already built. This increment is not a
clause: it is the **surface**, and it is the cheapest real T3 item because the
function the harness attacks already existed and the harness already attacked it.

---

## The one constraint that shaped the increment

**The surface must CALL `presentation_order`, not reimplement it.**

The claim and the implementation are the same code only as long as there is one
copy of the code. A second implementation of the seed formula would be invisible:
`manage.py bias_attack` would keep reporting zero-mean against a permutation the
product had stopped using, and every document would still be true.

So the module is a thin wrapper -- derive an identity, hand it to
`presentation_order`, persist the answer -- and the decision that was available
and refused is written down rather than assumed:

> **The order is stored, and it did not have to be.** `presentation_order` is a
> pure function of the identity, so a stateless implementation is possible and
> simpler: no row, no constraint, no migration. Rejected because the guarantee
> D-12 rests on is that a voter **cannot re-roll by refreshing**, and a pure
> function of a *cookie* is only stable while the cookie survives.
> `Ballot.UniqueConstraint(event, voter_key)` is the enforcement; the seed is
> stored beside the order so the order is **reproducible** rather than merely
> asserted to have existed.

`test_the_surface_calls_presentation_order` monkeypatches the symbol and asserts
it was called, so the constraint is enforced rather than trusted.

---

## F-83 - a permutation keyed on a NULLABLE column

The permutation was first keyed on `Project.source_key`. That is the obvious
choice -- D-11's portable natural key, what the gallery and the export print --
and **`SourceKeyMixin` says in its own docstring that it is "Null for rows this
portal created".**

So every project submitted through `/projects/new` would have contributed a
`None` to the order, and **a ballot of `None`s is structurally valid and
contains nothing**: it stores, it renders, it satisfies every shape assertion,
and it ranks no project at all.

**This is F-80's class for the sixth time, and the class has a name now: a
feature returning output whose values are empty while every structural property
holds.** A permutation needs a total order, and a nullable column is not one.

### How it was caught, honestly

By the tests on their **first run**, and **by luck**: one test sorts the order and
`[None] < [None]` raises `TypeError`. Every *shape* assertion would have passed.
The test that pins the class now asserts **both** halves:

```python
assert None not in order, "a NULL source_key leaked into the permutation"
assert "prj_late" in order
```

because a fix that **dropped** the self-submitted project instead of re-keying it
would satisfy the first assertion and fail the second.

**Fixed** by keying on `Project.id`, the primary key, which is present for
fixture rows and portal-created rows alike.

---

## The sabotage run, and the one result that matters

Two deliberate breakages before the increment was called done. Proving a test can
fail is the rule (F-33); *which* tests fail is the finding.

| Sabotage | Red |
|---|---|
| replace the permutation with the base order | **17 of 24** |
| **make the seed a constant** | **3 of 24** |

**The second is the interesting one, and it is F-80 again.** A constant order is
*perfectly stable per voter*: every "the same voter gets the same order twice"
test stays green, the second-request test stays green, the anti-refresh guarantee
is "verified" -- and the ballot is not randomised at all. Only the
**discrimination** tests went red.

That is the trap the project already wrote down, reproduced exactly:

> "does it catch the attack?" is half the question; "does it catch anything
> ELSE?" is the half people skip.

So the suite asserts **counts** rather than pairwise inequality
(`>= 4 distinct orders of 5 voters`, because a single collision in a permutation
is arithmetic and not a defect -- a pairwise-inequality test would be flaky and
therefore would not survive), and carries a **slot-1 control** asserting the
first project is not the same for every voter, because a "randomised" order that
always pins project #1 first is the harness's *attack* arm under another name.

Both sabotages are now mutations in `tools/mutation_test.py`, so a
re-introduction is caught **by name**.

---

## What ships, and what does not

| | |
|---|---|
| `/vote/` | Renders the order, the seed, and D-12's zero-**mean** caveat in the markup |
| `ballots/order.py` | Identity derivation per voting mode; the `presentation_order` call; persistence |
| Refusals | literal **403, empty body, no `Location`** via `isolation/refusal.py` (D-02) |
| **Not shipped** | **the ranking.** `/vote/` renders the order and does not accept a vote |

**Not shipping the ranking is a cut, and it is in the ledger** with two others
(stateless ballots, cookies/rate limiting), each with its reason and its regret.
Shipping the ranking would have meant shipping the aggregation, which is
REQ-T3-01 -- and the rule this project is built on is that a permutation nobody
can reproduce is a mechanism nobody can check.

**`voter_key` is hashed, per mode, from `SECRET_KEY`**, which the entrypoint
generates onto the instance volume and gitignores. A seed derived from a raw IP
would be brute-forceable over the IPv4 space in seconds, and the seed is *printed
on the page*. A test asserts the value is a 64-char digest and does not contain
the address.

---

## What it cost

| | |
|---|---|
| Tests | 479 -> **503** (24 in `tests/test_ballot_order.py`) |
| Mutations | 68 -> **72** (4 new, each naming its detecting test) |
| Suite | 503 pass - `just check` **GATE GREEN** at 7/7 - spec 72/72 - lint clean |
| Findings | **F-83** [P2] |
