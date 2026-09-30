# FEAT-07 increment 2 — `results_hash`, and the claim a stranger has to check

**Date:** 2026-09-29 · **Phase G · Increment 2**

`reviewer/audit/publication.py`, `manage.py publish_results`, **21 tests**.
`ResultPublication`'s columns shipped at FEAT-02 and **nothing ever wrote one** —
this is the code that does.

---

## The claim is not "we computed a hash"

It is **"anyone holding the export can recompute it."** The organizer's own
database is the thing we do not trust, so a hash nobody else can reproduce is a
fingerprint. A hash a stranger can recompute is evidence, and that is the
difference between the threat model's J-10 being *detected* and being *detectable
by a third party*.

**The centrepiece test is the two halves of this feature meeting.** It exports,
wipes, imports, recomputes the digest from the restored rows, and asserts it
matches:

> If you can take the data away and bring it back, the numbers still describe it.

An empty audit chain publishes an **empty** head rather than a placeholder — a
placeholder would look like a chain head to anyone comparing it, and would
mismatch the real chain's first entry forever after.

---

## F-97 [P1, OPEN] — the signed-records half of T4 has no data path

Grepping `src/` for `JudgeCredential.objects` returns **one hit: the model
definition.** After a full load: **zero** `JudgeCredential` rows, **zero**
`SignedRecord` rows.

**F-71 again, one app over.** `AuditEntry` shipped at FEAT-02 with a complete hash
chain and nothing wrote a row; FEAT-06 built the writer and found the chain empty.
`JudgeCredential` and `SignedRecord` ship with complete schemas — `public_key`,
`signature`, `record_hash`, the in-toto statement, the DSSE envelope — and no
writer. `RunSnapshot`'s own docstring names the shared cause: **a contract
invented at the same moment as the code it describes is a contract that fits
whatever the code happened to do.**

**Why it bites harder than F-71 did.** D-09 replicates the chain head into *every
signed judge record* so N judges who are not the organizer each hold a copy. With
no signed records there is **nothing to replicate into**, and the replication
logic is correct, tested, and running against nothing. F-61's shape at the scale
of a whole tier.

**So the honest sentence, until the signing increment lands:** *"D-09's
replication is implemented, and there is not yet anything to replicate to."*
**The spec layer now reports 1 open blocking finding, which correctly prevents
FEAT-07 being marked done.** That is the gate working, not the gate misfiring.

The test fixture builds a `JudgeCredential` **by hand and says why in its own
docstring** — it is the evidence, not a convenience.

---

## F-98 [P2] — the field list and the hash disagreed, and a constant counted as covered

**The mutation harness SKIPPED a mutation, and the skip was the finding.** The
replacement string no longer matched the source; underneath it, `_hashable` listed
its five fields by hand while `RANKING_FIELDS` named them separately, and the two
had drifted:

- it hashed a **`judges` key no row has** — a constant `None` in every hash;
- it had **stopped hashing `reviews_counted`**;
- its docstring said "exactly `RANKING_FIELDS`" and was **false**.

> **No test could have caught it.** A consistently-wrong hash is
> indistinguishable from a right one by any test that only checks that hashes
> *agree*. Structurally valid output containing nothing — F-61, one commit after
> F-93 closed the same shape in the same feature.

The repair is that `_hashable` now **derives from the tuple** — one source of
truth, the same "called, not reimplemented" rule the ballot surface follows with
`presentation_order`. Three tests assert the relationship directly, and **the
second one caught a second defect**: the tuple said `position` and
`results.leaderboard` sets `rank`.

**And then a test of mine was wrong**, in the same file, which is worth recording
because it is the third time this session. I asserted that no named field is
constant across rows; it flagged `normalization`, which is constant *on purpose*,
because "this whole ranking is unnormalized" **is the claim**. The assertion was
wrong about the field and the field was right. Perturbing each field is the
property that matters, and it passes for a constant field too.

**A stale mutation string is a stale code smell.** This one had been stale for
exactly as long as the bug it described — and once F-98's repair deleted its
target, it was stale permanently. Re-aimed at the tuple that replaced it.

---

## The replication, and the case it exists for

`results_hash` and `audit_chain_head` land **inside each record's `statement`** —
the signed payload — not in a column we own. **A column would be ours to rewrite,
and a rewritten column is invisible.** Putting them in the statement means editing
them afterwards invalidates that judge's own signature.

And a record that already carries a *different* hash is **left alone and
reported**, because overwriting it would destroy the only evidence that the
result changed after a judge signed. `replication_report` counts
agree/disagree/absent, and the command prints the disagreement as a warning:

```
signed records  28 agree, 1 disagree, 0 carry no hash
WARNING: 1 signed record(s) disagree with this publication.
         A judge signed, and the result changed afterwards.
```

That is the equivocation this replication exists to expose, and **it is the one
thing an organizer cannot see from inside their own database.**

---

## Why this is not a Merkle tree

The plan offered a Merkle transparency log. This project has **no independent
witness** and runs the container itself, so a Merkle root we compute proves
internal consistency — which the 30-line hash chain already proves, for three
times the code. What it would not do is let *anyone else* notice equivocation.
Putting the head in every signed record means **N judges who are not the organizer
each hold a copy**, and equivocation becomes a five-line diff between any two of
them. That is the value, and it is why this supplements a transparency log rather
than substituting for one.

---

## What it cost

| | |
|---|---|
| Code | `audit/publication.py`, `publish_results` |
| Tests | 636 → **659** (21 in `tests/test_publication.py`) |
| Mutations | 95 → **99** |
| Findings | **F-97 [P1, open]**, **F-98 [P2]** |

**F-97 is open and blocks the feature.** The Ed25519/DSSE increment is therefore
moved up from item 5 to item 3 — building the widget or the OpenAPI schema while
a P1 stands open would be the wrong order.
