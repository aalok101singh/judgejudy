# FEAT-07 increment 3 — Ed25519, in-toto v1, DSSE, and F-97 closed

**Date:** 2026-09-30 · **Phase G · Increment 3 — the one that closes a P1**

`credentials/keys.py`, `credentials/in_toto.py`, `credentials/signing.py`,
`manage.py sign_records`, a second named Docker volume, and **25 tests**.

---

## F-97 is closed, and it is closed with the finding still executable

Before: `grep JudgeCredential.objects src/` returned **one hit, the model
definition**. After a full load: **zero** credentials, **zero** signed records, and
no code that could make either.

`tests/test_signing.py` keeps a standing assertion of that:

```python
assert JudgeCredential.objects.count() == 0, "the loader creates no credentials"
records = signing.sign_all(loaded)
assert len(records) == distinct_judge_count
```

**A finding that lives only in prose rots.** This one is a test that fails if
somebody later wires credentials into the loader and the distinction is lost.

---

## Three places a plausible implementation is silently wrong

### The PAE is length-prefixed, and a wrong one still looks valid

DSSE signs `"DSSEv1" SP LEN(type) SP type SP LEN(payload) SP payload`. Two
properties of that make it uniquely dangerous:

- **A wrong PAE is still an ordinary string.** A verifier that reconstructs the
  PAE the same wrong way agrees perfectly. There is no failure until *someone
  else's* verifier disagrees.
- **Character-counting instead of byte-counting is correct for the type and wrong
  for the payload.** The type is ASCII, so it always works; the payload is UTF-8
  JSON, so it breaks the first time a judge's name has an accent in it.

So the test asserts **the specification's own worked example** — a byte string the
standard says is right — rather than this implementation's output:

```
DSSEv1 29 http://example.com/HelloWorld 17 {"hello":"world"}
```

A PAE built by the same code that verifies it agrees with itself forever. The
literal is the only thing that catches it, and there is **no independent witness**
in this project, which makes getting the bytes right the *only* defence.

### Verification never compares a stored hash to a stored hash

`verify_record` recomputes the PAE and asks whether the key signs *these bytes*.
The obvious cheaper design — hash the payload, compare to a stored digest — only
proves **two things the signer produced agree with each other**, which is not what
a signature is for. An organizer can rewrite a payload and update its digest; they
cannot produce a signature.

And a **PAE mutation is caught only by verification**, not by the PAE tests: the
encoder can be self-consistently wrong and the encoder tests still pass. That is
why the mutation's detector is `TestSignAndVerify`.

### The record commits to digests, never to scores

That restriction is **the mechanism, not a courtesy.** D-09 hands a copy of the
record to every judge so that an organizer equivocating becomes a five-line diff
between two of them. A record carrying scores would not be shareable with a judge
who was not the organizer — so it would replicate nothing, and the whole design
would be a signature nobody else can check.

---

## Keys on their own volume, and why that is load-bearing

`down -v` is how the break protocol resets the portal. **If the keys shared a
volume with the database, every reset would destroy every judge's signature —
taking the evidence with it.** Separate volumes mean a reset costs the *data* and
keeps the *evidence*, and a backup of `judgejudy-data` can be handed to somebody
because it contains no key material at all. That is a property you cannot retrofit
after the first backup you already gave away.

`keys.py` enforces it in three places, and the third is the one that matters:

> The path is **resolved** before the comparison, so a **symlink out of the key
> directory is refused too** — which is the only reason resolving is worth doing
> rather than comparing strings.

Raw 32-byte seeds, mode `0600`, directory `0700` — set explicitly, because a
umask of 022 would otherwise leave a private key world-readable inside an
otherwise single-tenant container.

---

## A test of mine caught the blast radius growing, and the fix was a narrower accessor

The test asserting that only `reviewer/io/bundle.py` may call
`for_bulk_transfer()` — **the widest read in the codebase** — failed, because the
signer was now calling it too.

The tempting fix is a second entry in the allowlist. **An allowlist that grows is
a rule that stops meaning anything**, so instead:

```python
def for_judge_signing(self, event_id, judge):
    """Every review ONE judge wrote in one event, for signing their own record."""
```

Signing needs *that judge's* work and nothing else, so the accessor is genuinely
narrower, fully determined by its arguments, and the test on
`for_bulk_transfer` goes back to asserting one caller. **The test did its job and
the code got more precise rather than more permissive.**

---

## And 39 judge bindings, 30 judges

`sign_all` iterated **role bindings**, and the fixture has **39 judge bindings
covering 30 judges** — one binding per track. Harmless for correctness (`sign` is
idempotent) and wrong for everything a human reads: the command would report "39
judges signed" over 30 signatures, and **the count is the only number the operator
gets.**

A test asserting `credentials == bindings` caught it. It now iterates distinct
users, and the expected count is derived rather than typed.

---

## What it cost

| | |
|---|---|
| Code | `keys.py`, `in_toto.py`, `signing.py`, `sign_records`, `for_judge_signing`, a second named volume |
| Tests | 659 → **684** (25 in `tests/test_signing.py`) |
| Mutations | 99 → **105** |
| Findings | **F-97 [P1] closed** · **0 open blocking** |

**The T4 data path is real for the first time.** Every table in the signed-records
half now has a writer, and D-09's replication has something to replicate into.
`run.py` still cannot verify any of it — a T4 claim remains impossible for exactly
the same reason a T3 claim does — but the capability is no longer a schema.
