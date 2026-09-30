# FEAT-07 — Bulk IO: the escape hatch, and the round trip that proves it

**Date:** 2026-09-29 · **Phase G** · **Increment 1 of 5**

The round trip: **export → import → export is byte-identical, including every
`source_key`** (`bible/05` §8a). Delivered as `reviewer/io/bundle.py`,
`manage.py export_run`, `manage.py import_run`, and **31 tests**.

---

## The phrase is a correction, and it is the whole feature

The earlier draft said *"byte-identical modulo generated IDs"*. **"Modulo
generated IDs" quietly removes the property.** If ids may differ the assertion
degrades to "the data is vaguely the same", and **it passes while a column is
silently dropped**, because a dropped column just makes the second export shorter
and nothing asserts the length.

So primary keys travel too. That is stricter than "portable", and it is the right
trade for an archive whose entire value is that a reviewer can prove nothing was
lost. **And it turned out to be load-bearing:** see F-93, where five tables had no
natural key at all and the archive could not restore them.

---

## F-94 — the acceptance line passed with the importer writing nothing

The mutation harness's most valuable mutation was **"make `clear_all` clear
nothing"**, and it reported **NOT DETECTED**: the round trip exported, imported,
exported — and matched byte-for-byte, because the upsert rewrote identical values
onto rows that never left.

> **Byte-identical is necessary but not sufficient.** It cannot distinguish
> "restored correctly" from "never touched anything".

The repair is three assertions the byte comparison structurally cannot make: the
tables were **empty** beforehand, the import reported rows **created** rather than
updated, and the created count **matches the manifest** rather than a typed
literal. The first version hardcoded `760` from arithmetic; the manifest said
**979**. That is this project's fourth transcription mistake and the first one
inside the file whose subject is not trusting a number you did not compute.

---

## F-93 — five tables with no natural key, found in four disguises

`Review`, `Score`, `Assignment`, `RoleBinding`, `TeamMembership` all had
`source_key = NULL` for every loaded row. The `io` app shipped at FEAT-02 with
the column on every table and nobody had ever written one.

The symptom arrived four different ways, which is what made it expensive — and
each one read as somebody else's bug:

| symptom | how it looked |
|---|---|
| 126 reviews in the quarantine report | "the importer rejected the important table" |
| `NOT NULL failed: reviews_review.assignment_id` | "the fixture is malformed" |
| `NOT NULL failed: reviews_review.status` | "the archive lost a column" |
| census reading `123 fixture / 0 portal` | "the census is wrong" |

F-69 had closed the visible half at FEAT-05 with a **fallback at render time** and
deferred the cause to FEAT-07 by name. This is the cause.

**The repair is a test, not a patch.** Finding five tables by archaeology is
unacceptable when the property is one loop over `apps.get_models()`:
`TestEveryLoadedRowHasANaturalKey` asserts every exported table carries a key,
**with an exemption list asserted to be empty.** The demo users' exemption was
removed the moment the demo users got keys — see below.

**The sixth symptom was the one that mattered.** Two portal-created logins had
`NULL` keys, so a restore silently dropped them and **the demo stopped working on
the second boot**. `SourceKeyMixin`'s own `help_text` says *"Null for rows this
portal created"* — true of the **source system**, and impossible for a round trip,
because a NULL-keyed row has nothing to match on. Resolved in favour of the round
trip, with a generated `demo:`-prefixed key that can never collide with one an
organizer's system issued.

---

## F-95 — rule 1 refused nothing, because the archive certified itself

```python
# it checked the archive's own claim
if manifest["schema_version"] in manifest["compatible_with"]:
```

An archive declaring `schema_version = 99, compatible_with = [99]` sailed through
a v1 importer — precisely the silent data loss the rule exists to prevent.

> **A self-certifying archive is not a certificate.** The reader checks against
> *its own* capability: `SCHEMA_VERSION in manifest["compatible_with"]`.

The evidence it was real before it was fixed: a test asserting a refusal got a
successful import and said so.

---

## F-96 — catching a bad row aborted the restore it claimed to report on

A row missing a `NOT NULL` column raised out of the importer. The first repair
caught it and quarantined it — **and was worse than the crash**, because catching
an `IntegrityError` inside an atomic block leaves the transaction marked *needs
rollback*, so the next query died. One bad row in 10,000 meant: the report said
"1 quarantined", and **nothing else was restored.**

The fix is a **savepoint** — a nested `atomic()` per row. Rule 4 applied to a
malformed row rather than an unmatchable one: quarantine it, name the row, carry
on.

---

## Three mutations that were aimed at the wrong line

The file's own convention, now the third instance:

| mutation | why it was undetectable |
|---|---|
| `if model in exclude:` → `if False:` | **Backwards.** It made `clear_all` delete *more*, not less. Detected only by applying it by hand — the harness's report said "not detected" and I nearly believed the test was at fault rather than the mutation. |
| `scalars.pop("id", None)` → `pass` | Removing the pop writes the archived id back unchanged — which is **correct**. |
| …→ `scalars["id"] = obj.pk` | `obj.pk` *is* the id that was just written. **The replacement was semantically identical to the original**, twice over. Now `scalars["id"] = 1`. |

> **A mutation that cannot be detected is a mutation aimed at the wrong line** —
> and a replacement that is semantically identical to the original is worse,
> because it converts a missing test into a green tally that means nothing.

---

## Two sanctioned accessors, and one of them is the widest read in the codebase

JJ01 refused the exporter for `Review.objects.filter(...)`, and then refused the
tests for `Review.objects.count()` — **including a test written to check the
export.** Both got the same treatment as FEAT-08's: a **named accessor**, not an
allowlist entry.

- `Review.objects.for_cross_judge_analysis(event_id)` (FEAT-08)
- **`Review.objects.for_bulk_transfer()`** — unfiltered, no actor. The widest read
  in the codebase, so it gets its own test asserting **only `reviewer/io/bundle.py`
  may call it**, because the property that makes it safe is a *negative* and a
  negative cannot be reviewed by reading the call site.

And the exporter routes `Review` through that accessor **rather than through its
generic loop**, so the one dangerous read is greppable by name instead of hidden
inside `for model in ordered_models()`.

---

## What it cost

| | |
|---|---|
| Code | `io/bundle.py`, `io/models.py` + migration, `export_run`, `import_run`, `for_bulk_transfer`, and five natural keys in the loader |
| Tests | 607 → **636** (31 in `tests/test_bulk_round_trip.py`) |
| Mutations | 90 → **95** |
| Findings | **F-93…F-96**, all four about a test that could not be trusted |
| Tables | 24 → **26** |

## Not yet built in this feature

`results_hash` at publication replicated into the signed records (D-09), Ed25519
in-toto/DSSE with keys on their own volume, the embeddable offline widget, and
OpenAPI 3.1. **And note what BREAK-4 is now:** a T4 claim is *equally* impossible
to verify, because `run.py` has no T4 checks either — so this feature earns its
place as a brief deliverable, not as a claimable tier.