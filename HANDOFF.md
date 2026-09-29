# Handoff prompt — Judge Judy (DOGFOOD 2026)

**Copy everything below the horizontal rule into a new chat window. Nothing above it.**

---

You are continuing **Judge Judy**, a self-hostable hackathon submission and judging
platform for DOGFOOD 2026, being built solo inside a 69-hour window. You are
picking it up mid-flight with no memory of the previous session. **Do not ask me
to re-explain anything. Everything you need is in the repository, and the
repository is the source of truth — not this prompt, and not your recollection of
a pattern that merely looks similar.**

**WORKING DIRECTORY:** `C:\Users\Aalok\Desktop\Judge Judy`
**BRANCH:** `main`. **REMOTE:** `github.com/aalok101singh/judgejudy`. Commit as
`aalok101singh` only. No collaborators. No build files in the repository.

---

## STEP 0 — READ THESE, IN THIS ORDER, BEFORE YOU TOUCH ANYTHING

1. `AGENTS.md` — the rules, the six traps, the gate. **Short. Read it whole.**
2. `blueprint/context/project-overview.md` — the whole project, under 20,000 bytes.
   This is the single most useful file; it is written to be the entire load.
3. `blueprint/context/current-feature.md` — the ONE in-flight scope. Trust it.
4. `blueprint/context/findings.md` — **90 findings.** Note that a status of
   "fixed" **blocks** completion on purpose: a repair is not done until a review
   has looked at it. Read the entries for the files you are about to touch.
5. `blueprint/history/features/` — the most recent archive is
   `06-public-results-page.md`; the ones before it are voting, comments, the
   ballot order, and the bias-attack harness.

**DO NOT read the `bible/` folder. It is 330KB and it will eat your context.**
The overview names the section for every kind of question. Open only that one
section. For the next tier you want `bible/02` (the T4 requirements), `bible/08`
§1b (the break protocol), and `bible/08` §13 (the cut ledger).

---

## STEP 1 — VERIFY THE LAST BUILD BEFORE YOU BUILD ANYTHING NEW

**A green gate on top of an unverified gate is not a green gate.** Run all of
these and **report the numbers you measured**. Do not quote a number from any
document, including this one. If your run disagrees with a number written down,
**the run wins and the document is a finding** — write it down as one.

```
git log --oneline -3
git status --porcelain
just doctor
just check                    # THE GATE
just prove-offline
just mutation-test
just lint
.venv\Scripts\python.exe tools\verify_spec.py
just report                   # then: git diff acceptance-report.txt  -- must be EMPTY
```

**Expected, as of the last commit. Treat any disagreement as a finding, not a
surprise:**

| | |
|---|---|
| spec | **72/72** |
| acceptance | **7 of 7 PASS**, printing `claimed T1, verified T1 T2` |
| tests | **575** |
| mutations | **86/86** |
| findings | **90, 0 open blocking, 17 fixed (awaiting review)** |
| cold start | 11.8–20 s against a 60 s budget |
| container | Docker 29.6.2, `just` 1.58.0, `python:3.13-slim` |

**If a gate is RED, name it and fix that before anything else.** Do not start a
new feature on a red gate.

`just check` takes roughly 10–12 minutes and `just mutation-test` about 8. On
Windows, run them **detached** or they get killed mid-run — that has happened
more than once in this project and it is not a failure of the gate.

---

## STEP 2 — WHERE THE PROJECT ACTUALLY STANDS

**FEAT-01 to FEAT-06 are built, verified and green.** T1 and T2 are both earned.

- **T2 is earned and NOT yet claimed.** `.dogfood.toml` says `claimed = ["T1"]`,
  and that is **correct today**. BREAK-2 has been run; the exact diff is prepared
  and held in `blueprint/context/current-feature.md` under "THE DIFF FOR THE
  HUMAN TO APPLY". **Do not edit `.dogfood.toml` on your own initiative.** Show
  the diff to the human, let them apply it, then re-run `just report` and diff.
- **All five REQ-T3 requirements ship**, so the T3 claim is *available*. BREAK-3
  has **not** been run. That is the human's decision.
- **`verified` cannot exceed T2, ever, on a flawless build.** `run.py` is
  prefix-locked over `["T1","T2","T3","T4"]` and there are **no T3 or T4 checks in
  the organizers' program at all** — seven checks, three T1 and four T2. The
  report ships printing `verified T1 T2` and the README explains it. This is
  arithmetic, not a gap. **Do not "fix" it by editing the report.**

**What FEAT-06 shipped, across seven increments:** the three isolation-matrix
columns, the audit chain's missing writer, the influence report (D-13), the
bias-attack harness, the randomised ballot as a product surface, voting with an
identity budget and a Borda tally, moderated comments, and the public results
page.

**Three controls are cut inside it, and disclosed three times** (cut ledger,
README, module docstring): comment rate limiting, ballot cookies/rate limiting,
and quadratic voting.

---

## STEP 3 — BUILD THE NEXT TIER

**`blueprint/build-plan.md` is the clock's source of truth.** Two candidates:

- **FEAT-07 (13h) — T4:** bulk IO with a **byte-identical round trip including
  natural keys** (D-11; `Review.source_key` is currently never written by the
  loader — a **known open gap belonging to this feature**, F-69); Ed25519 signed
  records in an in-toto Statement v1 inside a DSSE envelope; `results_hash`
  replicated into every signed judge record (D-09); an embeddable offline results
  widget; OpenAPI 3.1.
- **FEAT-08 (7h, PROTECTED) — the normalization proof.** The project's own
  analysis ranks this as the best value per hour: protected, near-zero risk, and
  the organizers named the criterion (*"Showing it recovers a known effect is
  exactly the kind of rigour the bonus is looking for"*). It is also what makes
  the currently-**unnormalized** published leaderboard honest, and that page says
  so on every render.

**FEAT-08 is the better hours-to-value trade and it is the protected one; FEAT-07
is the larger tier.** If you have ~7 hours, do FEAT-08 first — the leaderboard
currently ships an unnormalized mean, which is a visible honesty debt.

**Do NOT claim a tier yourself.** The claim is made at a break, by the human, in
writing. T3 has **no machine checks whatsoever**, so a T3 claim is a human
judgement against a rubric, and an inflated one costs the credibility of
everything else in the repository. The brief says that three times. **An honest T2
scores better than an inflated T3.**

---

## THE SIX TRAPS THAT HAVE COST THE MOST POINTS

1. **Isolation is a 403 with an EMPTY body. Never a 302.** `run.py` follows
   redirects, so a redirect returns 200 and fails a scored check while looking
   perfectly correct in a browser. Highest-value line in the project, and it is
   **one function** — `reviewer/isolation/refusal.py` — shared by every surface.
   Do not write a second one.
2. **`run.py` reads only `projects[:3]` and passes if ANY of them appears.** The
   slice is **positional**, so the first gallery page must be in fixture order.
   Exactly 7 checks, no T3/T4. **It ALWAYS exits 0** — parse its body, never gate
   on its exit code. The acceptance timeout is 10 s and only 5 identities get
   real password hashes.
3. **Every number in a shipped document is GENERATED, not transcribed.** Twelve
   early findings were hand-typed census errors, two found *after* a correction
   log was published. **If a number you write can rot, derive it or delete it.**
4. **Every claim about library behaviour is EXECUTED, not recalled.** Three times
   this project has been bitten by a *recalled* default: F-11 (a DRF default),
   F-79 (a model of position bias), and F-88 (Django's `{# #}` template comment
   is **single-line only**, so a wrapped one renders as literal page source — nine
   had shipped, two of them since FEAT-04).
5. **The claim is decided AT A BREAK, not at kickoff.**
6. **Docker is installed PER-USER and was on no PATH.** If `docker` says NOT
   FOUND that is a **stale PATH, not a missing install** — do not reinstall. The
   justfile resolves it by absolute path. Also **a bare `python` is 3.14.6 with
   no Django.** Always use `.venv\Scripts\python.exe` explicitly.

---

## FOUR TRAPS THIS PROJECT HAS EARNED. THESE ARE THE ONES THAT BITE.

**20. A metric you have not shown to DISCRIMINATE is a tunable constant with a
decimal point.** The "lift" detector read exactly 1.0 on the attack and was cut.
"Does it catch the attack?" is half the question. "Does it catch anything
**else**?" is the half people skip — a **constant** seed makes a ballot perfectly
*stable*, so every anti-refresh test stays green while the ballot is not
randomised at all.

**21. A fixture or a path that cannot separate its subject from its control
produces green output that means nothing.** The influence report's "organic
control" was itself a brigade of nine and all 24 tests passed. The cheapest fix is
one assertion: **assert the case you expect NOT to fire does not fire.**
`just check` will NOT catch this class — everything it runs is correct.

**22. ESCAPING IS A PROPERTY OF EVERY RENDER PATH, NOT OF THE DATA.** The safe
filter on the **moderation queue** left all four of the public-thread's escaping
tests green, because they all read the page as a visitor (F-86). A test that
proves a payload is escaped on page A has proved nothing about page B. Count the
places user-controlled text reaches HTML, and enumerate the assertion over that
count.

**23. THE SUITE IS STRONG ON STATE AND WEAK ON SENTENCES.** Three findings
(F-85, F-88, F-90) were output that was **correct in the database and wrong on the
page** — a stale budget, template source printed to the user, a scope warning
contradicting the table beside it. **F-90 was a wrong *sentence* rather than a
wrong number, which is why no assertion could see it.** When you write a page,
read its actual HTTP response. Every time.

**Generally: ASSERT VALUES, NOT SHAPES, and PROVE A NEW TEST CAN FAIL** by breaking
the code on purpose and watching it go red. A check that has only ever passed is
not evidence. Run `just mutation-test` after any new logic.

---

## SECRETS — THERE IS NO CONTEXT LEAK, BUT BE CAREFUL ANYWAY

The credentials in `.dogfood.toml` are **HMAC tokens signed with a key published
in this repository on purpose** (`src/reviewer/accounts/demo_tokens.py`). They are
**demo credentials, not secrets**, and the README says so in plain words.

- **Never paste their VALUES into any document, commit message, test name, or
  report.** Read them from `.dogfood.toml` at runtime; never inline one.
- `settings.py` generates `SECRET_KEY` onto the instance volume; it is gitignored.
- **`acceptance-report.txt` is GENERATED. Never hand-edit it.** Run `just report`
  and diff. A hand-edited report is a lie.
- Before every commit, scan the staged diff for token shapes:
  `git diff --cached | Select-String -Pattern "eyJ[A-Za-z0-9_-]{10,}|BEGIN PRIVATE KEY|JJ1\.[0-9a-f]{8}|AKIA[0-9A-Z]{16}"`
- **Do not add a `Co-Authored-By:` trailer for an AI.** A previous session added
  five, they had to be stripped by a history rewrite, and the human asked for that
  removed. Commits are authored by `aalok101singh` only.

---

## KNOWN WRONG NUMBERS STILL IN THE TREE

**F-78:** `bible/06` §6.3's power table (28,573 / 4,556 / 1,125 / 490) **does not
reproduce** from the formula it names. The generated figures are
**4,904 / 783 / 194 / 85**. The error was conservative so the conclusion survives,
but the correction **narrows** it: a 5-point side preference needs 783 comparisons,
and that section's own "100 to 1,000 votes" range reaches 1,000. The stale numbers
are in **`bible/06` around lines 1477–1487 AND `bible/02` line 109**. **If you
touch either, fix both, and generate the table rather than retyping it.** The
generator is `src/reviewer/ballots/bias_attack.py`, and it is mutation-tested.

**F-69:** `Review.source_key` is inherited from D-11 and **never written by the
loader**, so the export's first column has been 126 empty cells; the export falls
back to the `(judge, project)` natural key. **Populating it belongs to FEAT-07.**

---

## WORKING RULES THAT ARE NOT NEGOTIABLE

- **Record every cut in `bible/08` §13 THE SAME DAY**, with reason and regret. A
  ledger where every row says "no" teaches nothing — two rows currently say
  **"Yes, slightly"** and more should.
- **A `verify_spec.py` check that has only ever passed is not evidence.** Prove
  each new one can fail.
- **Never retype a gate's own check count.** Three places did it and all three
  rotted (F-72). `verify_spec` now fails if you do.
- **Keep `project-overview.md` under 20,000 bytes** — the cap is asserted and the
  file is loaded at the start of every session. It is at **19,954 bytes**: about
  **46 bytes of headroom**, so **anything you add must displace something**.
  Expect exactly **one** `just spec-quiet` failure at the end of a session that
  edits it, because editing it changes its own size.
- **Re-run the verification BEFORE you commit, not after.**
- **When you finish a feature:** update `current-feature.md`, update `findings.md`,
  and write the archive in `blueprint/history/features/`. A repair is not done
  when the code changes; it is done when a review has looked at the result.
- **Push to `main` when something is verified.**

---

## THE FIRST THREE THINGS I WOULD DO

1. Run the Step 1 verification and **report the measured numbers**. If anything
   disagrees with the table above, stop and write it down as a finding.
2. Read `blueprint/history/features/06-public-results-page.md`, then
   `06-voting-and-identity-budget.md`. Between them they hold the findings most
   likely to be relevant to whatever you build: **F-89/F-90** (output correct in
   the database and wrong on the page) and **F-84** (a control that silently did
   the opposite of what its name says).
3. Take **FEAT-08** if you have ~7 hours, **FEAT-07** if you have more. Then
   **BREAK-3** if the human wants the T3 claim made, using the seven steps in
   `bible/08` §1b — and remember the claim itself is theirs to make.
