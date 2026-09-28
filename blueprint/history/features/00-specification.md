# FEAT-00 — Specification and environment

**Completed:** 2026-09-27 · **Planned:** pre-window · **Actual:** pre-window
**Gate:** none — this is the phase before H+0

## What was built

- **A corrected research bible** — 9 documents in `bible/`: mission and win
  conditions, requirements traceability (60 IDs across 9 categories, 23 of them
  tier demands), the `run.py`
  acceptance contract, the fixture census, the domain model, the judging engine,
  the security and threat model, the delivery plan, and the environment record.
- **Twelve corrections to our own planning documents**, found by re-deriving from
  `fixtures.json` or by executing the installed stack, recorded as F-01…F-12.
- **A real Python environment** — `.venv` on Python 3.13.13, 17 runtime packages
  and 11 dev packages, all pins produced by the resolver rather than recalled.
- **Verified environment claims** — FTS5, WAL, JSON1, portable constraints,
  Ed25519 sign/verify with tamper rejection, and the DRF CSRF default.
- **The AI Blueprint specification layer** — `AGENTS.md` plus `blueprint/`, so a
  fresh coding session can start from a 16KB overview instead of 330KB of
  research.
- **`tools/verify_spec.py`** — 67 checks that re-derive every load-bearing number
  in the spec layer from the organizers' own files. Stdlib-only, exits non-zero,
  mutation-tested against nine deliberate corruptions.
- **A closed question tally** — `bible/DISCORD-QUESTIONS.md`: 2 answered, 13
  self-answered by reasoning, 1 dropped, 0 open.

## How it was built

**By re-deriving everything from the primary source.** Every number in the bible
was recomputed from `fixtures.json` rather than carried forward from a previous
document, and every claim about library behaviour was executed against the
installed version. That is what produced twelve findings, four of them P1.

**The decision that changed while building: the questions stopped.** Fourteen
question candidates were filtered down to one worth asking publicly, and the one
worth asking was about synthetic data in the proof artefact. The 0.31 DM was
prepared, then dropped — we got a "yes" to the only question that mattered, and
a second message to a moderator is worth less than not asking twice. The
reframing that made it droppable: the 0.31 reading is a *question*, not a
correction, because we do not know their definition and we may have the wrong
one. That phrasing was the right one whether or not we had asked.

**The second decision: the spec layer, not a bigger bible.** The bible is already
330KB and correct. Adding to it would have made it worse. The problem was not
missing knowledge, it was that no fresh session could load it. So the fix was a
loadable overview under a hard 20,000-byte cap that a new session reads first,
plus plans that change rarely and a findings ledger that changes often.

> The byte count is deliberately **not** quoted here, and neither is it quoted in
> `AGENTS.md` beyond what the gate itself reports. It was 17,086 bytes when this
> was written; every subsequent feature moved it, and `verify_spec.py` failed on
> each move until the number was dropped. **A quoted size drifts the moment the
> file is edited, so the honest fix is to drop the number** — which is what the
> gate's own failure message has always said.

**The third decision: audit the audit.** The spec layer was built, and then every
claim in it was re-derived from the **given** inputs rather than read off the
bible. That found **five errors in the layer written to prevent transcription**
(F-28…F-32) — including the histogram wrong in `project-overview.md` while
correct in the generated `bible/04`, and a headline "6 demands" where `run.py`
runs **7 checks** (3 T1 + 4 T2, none in T3/T4). It also found that the *tally in
`AGENTS.md`* was wrong: 16 accepted and 9 closed, against an actual 9 and 20.

**The fourth decision: make the rule executable.** Five findings from a
throwaway script is five findings that could recur, because nothing stopped the
next session retyping the same numbers. So the audit became
`tools/verify_spec.py` — stdlib-only so it runs before the venv and Docker
exist, non-zero exit so it is allowed to fail loudly, and **mutation-tested
against nine deliberate corruptions** because a checker that has only ever passed
is not evidence of anything. It had three bugs of its own on first run, all
false *failures*, all in the checker. That is the right direction for a broken
checker to break in.

## How it was verified

```bash
python tools/verify_spec.py
# 66/67 checks PASSED — the spec layer agrees with the given inputs

docker --version          # NOT FOUND  — F-13, blocking
docker compose version    # NOT FOUND
python -V                 # 3.13.13
```

> ### 📌 Later the same day — those two `NOT FOUND` lines were the wrong diagnosis
>
> **Docker was installed and running the entire time.** `docker --version`
> returned NOT FOUND because Docker Desktop is installed **per-user** at
> `C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\resources\bin`, which was
> in neither the in-session PATH, the User PATH, nor the Machine PATH. That is
> **F-34**, and it is now closed.
>
> Verified after the fix: **Docker 29.6.2** (`dfc4efb`), **Compose v5.3.1**,
> **WSL2** backend (`docker-desktop` on WSL 2.7.11.0, driver `overlayfs`), daemon
> up, `just` 1.58.0 installed, `python:3.13-slim` pulled (`sha256:7c61056e…`,
> container reports Python 3.13.15).
>
> **The lesson, recorded because it is the exact failure this ledger exists to
> catch:** a failing command is evidence that a command failed, not evidence about
> what caused it. "NOT FOUND" was treated as "not installed" for the whole of one
> phase, and the honest reading was wrong. **A diagnosis is a hypothesis until you
> test the alternatives** — the alternatives here were three (not installed /
> installed elsewhere / not running), and two of the three were live.
>
> `python -V → 3.13.13` above is the **venv**. A bare `python` on PATH is 3.14.6
> with no Django (**F-38**, still open).

| | |
|---|---|
| Acceptance | spec layer loadable and under the 20,000-byte cap *(exact size deliberately not quoted — see the note above)* |
| Requirement IDs covered | none — planning phase |
| Findings opened | F-01…F-33 |
| Findings closed | 21 |
| Environment | installed and verified; **Docker outstanding** *(resolved later the same day — see above)* |

## What was cut or deferred

| Item | Reason | Regret |
|---|---|---|
| The 0.31 mod DM | A "yes" to the one question that mattered. The reading is already in `06` §4.4c, phrased safely | none |
| 12 of 13 self-answered questions | Filter: is the answer already in the published material, and would we build differently? | none |
| A larger spec layer | The overview is 76% of budget with no padding. Depth stays in `bible/` and is read by section | none |
| `numpy`, `scipy`, `networkx` | 126 rows and a 40-node graph do not need them. Measured, not assumed | none |

## What the next session should know

1. **The biggest finding is not a number, it is a rule.** Six of twelve were
   hand-typed census errors, and two were found *after* we published a correction
   log about the first four. A correction log containing un-caught errors teaches
   the reader to distrust the writer. So: every shipped number is generated.

2. **Two of our published claims were false, and both were load-bearing.**
   "Two tracks are structurally infeasible" was wrong — they are zero-slack, and
   provably infeasible only at capacity 5. And the per-judge severity table had
   26 rows for a 30-judge population. Both were caught by the same two
   invariants, which are now the shape of every census check.

3. **Two library claims were backwards when recalled and right when executed.**
   DRF's `SessionAuthentication` is not CSRF-exempt by default, and seeding all
   121 fixture people costs ~48 s against a 10 s timeout. Both looked fine in a
   browser. Neither would have failed a test. Hence `verify_against_the_installation`.

4. **The organizing prize is not what we guessed.** They corrected the σ figure
   and confirmed that *"showing it recovers a known effect is exactly the kind of
   rigour the bonus is looking for."* The parameter-recovery experiment is the
   artefact. The six protected hours in FEAT-08 are now the best-expected-value
   hours in the project.

5. **Docker was never missing, and the ledger nearly said so for a whole phase.**
   `docker --version → NOT FOUND` got recorded as "Docker is not installed," and
   that was wrong: it was installed per-user and on no PATH (F-34, now closed
   with F-13). `NOT FOUND` is evidence that a command failed, not about why. **The
   other lesson from the same session:** the ambient `python` is 3.14.6 with no
   Django, so `python run.py` in a fresh terminal breaks while `.venv` works
   fine (F-38, still open). Three Pythons, two of them not the one we mean.
