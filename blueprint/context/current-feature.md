# Current Feature

> **Exactly one in-flight scope.** If this file is vague, the next session will
> guess. That is the bug.
>
> One feature at a time. Completed features move to `../history/features/`.

---

## In flight: FEAT-13 — Organizer settings (built; awaiting review)

**Phase G** · **Gate:** BREAK-4 ☕ (the T4 claim decision)

**The code is done and every gate is green. The feature is not marked done
because `fixed` is blocking by design** — a repair is done when a review has
looked at the result, and seven findings on one page is exactly the case where
that distinction earns something. Archive: `13-organizer-settings.md`.

### The one-line state

**FEAT-01…FEAT-08, FEAT-10, FEAT-11 and FEAT-12 all ship and verify.**
FEAT-13 closed the last product gap in the organizer's week: the lifecycle is now
reachable in a browser, and **nothing in the setup→run→publish path needs a
shell.**

| Feature | Archive |
|---|---|
| FEAT-06 | `history/features/06-public-results-page.md` (+ `-influence-report`, `-bias-attack-harness`) |
| FEAT-08 | `history/features/08-normalization-proof.md` |
| BREAK-3 | `history/features/break-3-t3-claim.md` |
| FEAT-10 | `history/features/10-signed-records-dsse.md`, `10-openapi-and-readme.md` |
| FEAT-11 | `history/features/11-provisioning-login-roster.md` |
| FEAT-12 | `history/features/12-comment-ratelimit-and-import.md` |
| FEAT-13 | `history/features/13-organizer-settings.md` |

### The claim has not moved, and the arithmetic is why

`.dogfood.toml` says `claimed = ["T1", "T2"]`. **T3 is fully built and
deliberately unclaimed** (F-91, accepted by decision), and the mechanism is
arithmetic rather than a gap: `run.py` contains **3 T1 and 4 T2 checks and no T3
or T4 checks at all**, so `verified` is prefix-locked to `T1 T2` and any claim
beyond T2 lands in the overclaim set. **The same holds for T4** — there is no T4
check to fail or pass, so a T4 claim cannot be partially verified. `v-t3-verified`
is therefore untagged, because tagging it while the gate prints OVERCLAIM would
assert the opposite of what the machine says.

### What FEAT-13 found, and the pattern it confirmed

Seven findings from one page. **Three were 500s reachable only by an organizer** —
invisible to the guard tests, because the guard is the first thing the view does
and every bug was in what came after it. One was a **fixture with no rubric**,
which made three publish tests pass while testing nothing. One was **introduced by
the fix for another** (F-119, made reachable by repairing F-118). And F-124 is
F-106's construct recurring in a template written an hour after F-106 was
recorded, because the lint rule fires per-template.

**The rule that came out of it, and it is the one to keep:** *two buttons on one
save path means the weaker form's omissions are the stronger form's bugs.* Absent
now means **unchanged**.

### Do not

- **Do not claim T3 or T4.** It turns the gate red. Proved twice; reverted twice.
- **Do not move `submissions_close`.** It is in the past because that is what makes
  the deadline check meaningful.
- **Do not edit `acceptance-report.txt` by hand.** It is generated.
- **Do not re-litigate D-01…D-15.**
- **Do not retype a gate's own check count.** `verify_spec` fails if you do (F-72).
- **Do not type a count from arithmetic.** Measure, then write — the spec gate
  caught three stale finding tallies within a minute of writing them.
- **Do not build for the video.** It is not the deliverable.

### State

| | |
|---|---|
| **Status** | **FEAT-13 built and green, awaiting review.** FEAT-01…FEAT-08 and FEAT-10…FEAT-12 shipped and verified. FEAT-09 is scripted and timed; recording it needs a human and a voice |
| **Started** | 2026-09-29 |
| **Last touched** | FEAT-13 `/organizer/settings/`: **906** tests passing (1 skipped), `114/114` mutations, spec `75/75`, lint clean over 196 files, `just check` **GREEN** at 7 of 7 with `claimed T1 T2, verified T1 T2`, `just prove-offline` **PROVED**, acceptance-report diff empty |
| **Claim** | `claimed = ["T1", "T2"]`. T3 built and **unclaimed** (F-91). `v-t3-verified` untagged, deliberately |
| **Next action** | **A review of FEAT-13**, since seven findings in one feature is the case the `fixed`-is-blocking rule exists for. After that: FEAT-09's recording (a human and a voice) and BREAK-4, which asks "how much of T4 is green?" — and the honest answer is *all of it or none of it*, because there is no T4 check |
| **Tag** | `v-t1-verified` (BREAK-1), `v-t2-verified` (BREAK-2), `v-submission` |
