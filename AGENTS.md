# AGENTS.md

**Judge Judy — DOGFOOD 2026.** A self-hostable hackathon submission and judging
platform. 69 hours, one person, solo. Freeze H+69.

**You are picking up a project mid-flight.** Read this file, then follow it in
order. It is short on purpose.

---

## Read in this order

| # | File | Bytes | When |
|---|---|---|---|
| 1 | **`blueprint/context/project-overview.md`** | **under 20,000 bytes** | **Always. This is the whole project in one load.** |
| 2 | `blueprint/context/current-feature.md` | — | Find the in-flight scope. Exactly one. |
| 3 | `blueprint/context/findings.md` | — | What is known broken, and what was chosen not to fix. Check anything touching the files you are about to touch. |
| 4 | `blueprint/context/ai-interaction.md` | — | How to work here. Read once per session. |
| 5 | `blueprint/build-plan.md` | — | The acceptance line for the current feature. Not a summary — the line. |
| 6 | `blueprint/history/features/` | — | The most recent archive. What was actually built, and what it cost. |

**Then stop and work.** You have enough. Everything else is opt-in.

---

## The depth trap

`bible/` is **330KB of research.** It is excellent and it will fill your context
and cost you the thread. Do not read the folder.

The overview names the section for every kind of question. Open that section:

| You need | Read |
|---|---|
| Why we win or lose, T4 risk, the scoring function | `bible/01` |
| A requirement ID, or the assumptions log | `bible/02` |
| `run.py` behaviour, the seven traps, the checklist | `bible/03` |
| Fixture facts, the invariants, the eight edge cases | `bible/04` |
| **Schema, indexes, the isolation primitive, the escape hatch** | `bible/05` |
| **Assignment, normalization, the proof, pairwise decisions** | `bible/06` |
| **Threat model, including what we did not stop** | `bible/07` |
| Hour map, break protocol, slippage ledger, cut ledger | `bible/08` |
| Installed versions, verified claims, the Docker blocker | `bible/ENVIRONMENT.md` |
| Organizer questions and answers | `bible/DISCORD-QUESTIONS.md` |

**`bible/06` and `bible/05` are the two you will need most.** Plan around them.

---

## The six things that are true and cost us if forgotten

1. **Isolation is a 403 with an empty body. Never a 302.** `run.py` follows
   redirects, so a redirect returns 200 and fails the check while looking
   correct in a browser. This is the highest-value line in the project.
2. **`run.py` reads only `projects[:3]`** — `Glass Signal`, `Small Meadow`,
   `Deep Compass` — and passes if **any one** of them appears in the gallery body.
   The slice is positional, so the first gallery page must be in fixture order.
   There are exactly **7 checks** (3 T1, 4 T2) and **no T3/T4 checks**, so
   `verified` can only ever read `T1 T2`. The acceptance timeout is **10
   seconds**, and only 5 identities get real password hashes; the other ~116 get
   `UNUSABLE_PASSWORD`. `run.py` **always exits 0** — parse its body, never gate
   on its exit code.
3. **Every number in a shipped document is generated, not transcribed.** Ninety-six
   findings, twenty-two of them fixed in this session alone, and two were found
   *after* we had already published a correction log about the first four. A
   correction log containing un-caught errors teaches the reader to distrust the
   writer. **I have now typed a count from arithmetic four times** - 91 mutations
   when the run printed 90, 760 created rows when the manifest said 979 - and both
   times the *tool that could have told me the number was sitting right there*.
4. **Every claim about library behaviour is executed, not recalled.** One of our
   documented DRF defaults was backwards, and it would have made the deadline
   check pass without ever testing the deadline.
5. **The claim is decided at a break, not at kickoff.** We build to T4; each
   break decides what is actually green. A T4 claim with half-working endpoints
   scores worse than an honest T3, and the brief says so three times.
6. **Docker is verified working, but `docker` was on no PATH.** It is installed
   per-user at `C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin`,
   now appended to the User PATH. **A stale shell will not see it** — the justfile
   also resolves it by absolute path. If `docker` reports NOT FOUND, that is a
   PATH problem, not a missing install; do not reinstall (F-34).
7. **The ambient `python` is 3.14.6 and has no Django.** Use
   `.venv\Scripts\python.exe` (3.13.13) explicitly, never a bare `python`. Django
   5.2.17's `Requires-Python: >=3.10` has no upper bound, so the pin will not
   save you (F-38).

Full reasoning: `blueprint/context/project-overview.md` §4 and §6.

---

## Rules

- **Do not re-litigate a decision.** D-01…D-15 are decided. If one is wrong, say
  so once, in a paragraph, with the consequence — then follow it.
- **Ask about requirements, cuts, risks and the stack. Nothing else.** If the
  answer is in `bible/`, read it rather than asking. The 330KB exists so these
  questions have answers.
- **Never hand-edit `acceptance-report.txt`.** It is generated, and the panel
  runs the identical program.
- **State the honest number.** The brief rewards honest gap reporting. The
  inconvenient result — the panel has no detectable judge-severity effect,
  permutation *p* = 0.234 — is the most important sentence in the normalization
  section precisely because it is disappointing.
- **Cutting is a decision, not a drift.** Anything cut goes in the cut ledger in
  `bible/08` §13 the same day, with the reason and the regret. Two entries
  currently say "yes, slightly", because a ledger where everything says "no"
  teaches nothing.
- **When you finish a feature:** update `current-feature.md`, update
  `findings.md`, and write the archive in `history/features/`. A repair is not
  done when the code changes; it is done when a review has looked at the result.

---

## Verify

```bash
python tools/verify_spec.py   # the spec layer vs the organizers' files — prints its own check count
just check                    # the application — clean down -v, up, run.py, proofs, pytest
```

**Two different gates, at different times.** `verify_spec.py` proves the *plan*
still matches `fixtures.json` and `run.py`, and it runs **now**, before any
application code exists. It is stdlib-only, needs no venv and no Docker, and it
exits non-zero on failure — unlike `run.py`, which always exits 0.

Run it after **any** edit to the plan, and before trusting a number quoted in a
document. The rule is generated-not-transcribed; this is what enforces it. It
has already caught five wrong numbers that a careful read missed, including
`5@5` instead of `4@5` in the overview and "6 demands" where `run.py` runs 7
checks.

```bash
just check
```

Clean `down -v` → `up` network off, then `run.py`, `isolation_proof`,
`verify_census`, `pytest`. One command proves a checkpoint. Not "the tests I was
working on."

The proof's published numbers are **asserted in CI** — held-out RMSE, recovery
RMSE, sensitivity curves — so a refactor that silently changes the method fails
a test instead of quietly weakening a document.

---

## Current state

FEAT-01 to FEAT-05 built and verified. 26 models across 13 apps; the isolation
primitive, the loader, the public gallery, the deadline guard, the assignment
engine with its min-cut certificate, the judge console, the scoped score
endpoint and the CSV export are in place, and **`run.py` prints
`claimed T1, verified T1 T2` with all 7 checks PASS.** T2 is **earned and not
yet claimed** — the claim is made at BREAK-2, by the human, in writing. Next:
**FEAT-06** — **COMPLETE. All five REQ-T3 requirements ship and are tested:**
community voting with an identity budget and a Borda tally (01), moderated
plain-text comments (02), results hidden on **both** the API and the public page
(03), randomised ballot order as a product surface (04), and the influence report
(05). **The T3 claim is now AVAILABLE and BREAK-3 has not been run** — the
decision, and the naming of the cut controls, is the human's.

| | |
|---|---|
| Findings | **126** - **0 open blocking**, 0 open, 45 fixed (awaiting review), 1 unverified (F-27), **11 accepted by decision (F-91)**, 69 closed |
| Acceptance | **T1 and T2 green** — **7 of 7 checks pass**, `claimed T1, verified T1 T2`. The `verified` ceiling is arithmetic in `run.py`, not a gap: there are no T3 or T4 checks at all |
| Suite | **910 tests** (1 skipped), **116/116** mutations, spec **75/75** |
| Container | cold start **11.8–20 s** observed 2026-09-29 against the 60 s budget (a range, not a value — F-68); `prove-offline` passes, and it now also renders the embeddable widget **inside** the `--network none` container |
| Environment | **fully verified** — Docker 29.6.2 (WSL2), `just` 1.58.0, `python:3.13-slim` pre-pulled |

