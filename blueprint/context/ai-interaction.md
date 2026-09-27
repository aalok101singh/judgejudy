# AI Interaction

> **How an agent works in this project.** One human, 69 hours, solo. The rules
> exist because a build this size fails on attention, not on code.

---

## 1. The default shape of work

1. **Load `context/project-overview.md` first.** It is under 20,000 bytes and it
   is written to be loaded on demand. Everything else is opt-in.
2. **Read `context/current-feature.md` to find the scope.** One feature, not
   ten. If the current-feature file is vague, that is the bug to fix before
   writing code.
3. **Check `context/findings.md` for anything touching the files you are about
   to touch.** `F-11` and `F-12` both landed in files that looked finished.
4. **Then build**, and update the findings ledger and current-feature file as
   part of finishing, not afterwards.
5. **Depth is opt-in.** Read the `bible/` section named in the overview. Never
   load the folder — it is 330KB and most of it is not about your task.

## 2. Do not re-litigate a decision

D-01…D-15 in the overview, and §8 of the project plan, are decided. If you
think one is wrong, say so **once, in one paragraph, with the specific
consequence** — and then follow it anyway unless the human says otherwise.

What is not acceptable:

- Re-proposing a cut feature "just in case" (webhooks, Borda, IRT, Merkle,
  Casbin/OPA, RLS, TrueSkill). Each has a recorded reason. See the cut ledger.
- Re-litigating the stack. C-3 bounds it, and a stack change has to be worth
  more than four hours of build time to even be discussed.
- Suggesting a "quick win" that is not in the build plan. Adding scope is
  subtracting from a fixed 69 hours.
- Treating a published target as an objective. `k = 0` scores better than the
  value we ship.

## 3. Ask, but ask well

**Ask when the decision is genuinely the human's:** changing a requirement,
cutting a feature, taking on a risk that could lose points, deviating from the
stack.

**Do not ask when the answer is already written down.** The bible is 330KB
precisely so these questions have answers. Read it first. Asking a question the
documents answer costs the human attention that the questions above are trying
to buy.

**When you do ask:** give the options, a recommendation, and the cost of each in
hours. A question with no recommendation is a way of transferring work back to
the busiest person in the project.

## 4. Report honestly, and cheaply

The brief rewards honest gap reporting and penalises inflation. `run.py` prints
`claimed` against `verified`, and the panel runs the identical program. There is
no version of this that benefits from an optimistic summary.

- **Never edit `acceptance-report.txt` by hand.** It is generated.
- **If something is half-built, say "half-built"**, and name the half.
- **If you fixed a finding, say what it was, not just that it is fixed.** The
  twelve corrections are the Write Up Quest material.
- **If you are unsure, say unsure.** "I think the min-cut is correct, unverified
  against a real infeasible instance" is useful. "The min-cut is correct" is a
  claim we then have to defend.
- **Report the number that is inconvenient.** Between-judge variance of 0.0217
  against a noise floor of 0.0971 is the most important sentence in the
  normalization section precisely because it is disappointing.

**Length:** short by default. The human is at hour 40 of 69. A four-paragraph
status report is a feature that does not get built. Lead with the decision or the
blocker, not with the process.

## 5. The verification discipline

- **Execute, do not recall.** Every claim about library behaviour is verified
  against the installed version. `F-11` was a documented DRF default that was
  backwards, and it would have made the deadline check pass without testing the
  deadline.
- **`just check` is the gate.** Not "the tests I was working on."
- **A repair is not done when the code changes.** It is done when a review has
  looked at the result. `fixed` blocks completion in the findings ledger on
  purpose — a fix can introduce a worse defect than the one it removed.
- **Report working from the open findings as a checklist.** Review the work
  fresh, then update the ledger with what the review found. Verifying only the
  known items is how a repair-introduced defect ships unnoticed.

## 6. Scope discipline

The build plan has 10 features in 69 hours. That is the whole budget, and it has
no slack beyond the ~1.5 hours × 4 breaks already accounted for.

- **Ship the gate, not the ambition.** A clean T3 with an honest gap is a strong
  submission. A T4 claim with half-working endpoints scores worse, and the brief
  says so three times.
- **Protected blocks are not displaced.** FEAT-08 (the proof) and FEAT-10 (docs,
  acceptance, commit) carry the bonuses and the honesty of the submission. If
  T4 slips, they slip first.
- **Anything cut mid-build goes in the cut ledger the same day**, with the reason
  and the regret. Two entries currently say "yes, slightly" in the regret
  column, because a ledger where everything says "no" teaches nothing.
- **Do not gold-plate a passing feature.** Note it and move on. There is a
  feature list for a reason.

## 7. Recovery

If you arrive mid-project with no context:

1. `context/project-overview.md` — the shape of everything.
2. `context/current-feature.md` — where the last session stopped.
3. `context/findings.md` — what is known broken, and what was chosen not to fix.
4. `history/features/` — the most recent archive, which says what was actually
   built and what it cost.
5. `git log` — once F-14 is resolved.

Then work the acceptance line in `build-plan.md` for the current feature. Not a
plan, not a summary of a plan: the acceptance line.
