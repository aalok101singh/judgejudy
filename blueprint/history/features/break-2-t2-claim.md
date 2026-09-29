---
title: BREAK-2 — the T2 claim, decided against what was green
date: 2026-09-29
---

# BREAK-2 — the T2 claim

**The claim is T2, and it is EARNED, not granted by the fact that two hours
remained.** Four checks pass, and — the part that decides it — they pass *for the
right reason*, each with a precondition that a wrong-reason refusal cannot
satisfy (F-40, and the FEAT-05 layer written for it).

## The seven-step block, run

| # | Step | Result |
|---|---|---|
| 1 | clean `down -v`, `up` network off | volume removed and recreated, **healthy** |
| 2 | `run.py` against `.dogfood.toml` | **7 of 7 PASS**, `claimed T1, verified T1 T2` |
| 3 | `isolation_proof` | **exit 0** |
| 4 | full extended suite | **479 pass** |
| 5 | slippage ledger (`bible/08` §1c) | D, E, F filled in, with the estimate quality stated |
| 6 | **decide the claim** | **T2** — this file |
| 7 | tag | `v-t2-verified` |

`run.py` **exits 0 unconditionally** (F-32), so none of the above is read off an
exit code. The acceptance result is parsed out of the report **body**.

## What the claim rests on, precisely

T2 is four checks: a judge sees their own scores, a judge **cannot** see a peer's,
a participant is blocked, and the CSV export works. All four pass.

The second is the one that carries the weight, and it is the one the whole
isolation design exists for. A denial is a **literal 403 with an empty body**,
never a 302 — because `run.py` follows redirects, so a redirect returns 200 and
fails the check while looking *correct in a browser*. That is a single function,
`reviewer/isolation/refusal.py`, shared by the console and the API, so it cannot
drift per surface (D-02). A judge sees **5 of 126** rows; an organizer sees 126.

The matrix, from the proof on a clean volume at this break:

| | draft | submitted | locked | leaderboard | export | audit |
|---|---|---|---|---|---|---|
| visitor | 0/126 | 0/126 | 0/126 | refused | refused | refused |
| participant | 0/126 | 0/126 | 0/126 | refused | refused | refused |
| **judge** | **5/126** | 0/126 | 0/126 | refused | refused | refused |
| organizer | 126/126 | 126/126 | 126/126 | 41/126 | 126/126 | 3 entries |
| admin | 126/126 | 126/126 | 126/126 | 41/126 | 126/126 | 3 entries |

## The gap, in plain words

**`verified` will read `T1 T2` on a flawless build, and that is arithmetic rather
than a shortfall.** `verified` is prefix-locked over `["T1","T2","T3","T4"]` and
breaks at the first tier with no passing check. **The organizers' program contains
no T3 or T4 checks at all** — seven checks, three in T1 and four in T2. So the
ceiling is reached the moment all seven pass, and the honest report ships printing
`verified T1 T2`. The README explains this in full; `acceptance-report.txt` is
generated and is **not** edited to say something more flattering.

**What is genuinely not built**, and is the real distance from T3:

- **Randomised ballot order as a product surface.** The function exists and the
  harness attacks it — `presentation_order` — so the claim and the implementation
  are deliberately the same code. The *surface that calls it* does not exist yet.
- **Voting**, with amplification inside an identity budget, and mandatory
  attributable abstention.
- **Comments** on gallery projects (the model and its constraints ship; the
  surface does not).
- **Public** result hiding. The **API** refusal is built and tested; the public
  pages are not.

So: **REQ-T3-01, 02, 03 and 04 are not all built, and T3 therefore is not
claimed.** T3 has **no machine checks whatsoever**, so a T3 claim is a human
judgement against a rubric, and an inflated one costs the credibility of
everything else in this document. The brief says that three times. This is the
rule working rather than aspirational — the same rule that left T2 unclaimed
while it sat earned and green, for five features.

## The claim is the human's

`.dogfood.toml` says `claimed = ["T1"]`. That is **correct today** and was not
edited on initiative. The exact diff for the human to apply is held in
`blueprint/context/current-feature.md`; once applied, `just report` and diff, and
the report header must read `claimed: T1 T2` with the summary line
`claimed T1 T2, verified T1 T2`.
