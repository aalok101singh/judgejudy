# FEAT-09 — the demo video: shape, and the material we actually have

**3h · ≤3 min · showing a *decision*, not a tour** (`blueprint/build-plan.md`
Phase I). This file exists so the recording session starts from a structure
rather than from a blank timeline.

**The shape is borrowed, and the source is named.** The structure below — full
frame for the argument, short inserts for the artefact, a dedicated
*what went wrong* section, and a close that says where the work is — is the shape
of `VIDEO_SCRIPT_STORY.md` from the Lamatic take-home, which is a working
example of the brief's own instruction. **The material is entirely ours**, and it
is much better than a tour would be.

---

## The rule the shape encodes

| section | job |
|---|---|
| the problem, in one sentence | the viewer has to know what was broken before the fix means anything |
| what it is | one paragraph, the mechanism, **not** the stack |
| **what went wrong** | **the memorable part, and the part most videos cut** |
| where I am | one sentence, no adjectives |

Two rules do the work:

- **A decision, not a tour.** Every claim has to be something we *chose* and can
  defend. "Here are six tables" is a tour. "A judge-organizer can read every
  score today, and I decided that was the right trade" is a decision.
- **The failure section is not an apology.** It is the evidence that the thing was
  actually built by someone who got it wrong first. A video with no failure in it
  reads as a screenshot with a voice.

---

## The material, in the order the shape wants it

### 0:00 — the problem, in one sentence

> A judging portal has to keep judges from seeing each other's scores, and it has
> to let a hackathon leave with its own data. Those two requirements pull in
> opposite directions, and the second one is the one everyone forgets.

### 0:20 — the decision that shaped the project

> **Isolation is a 403 with an empty body. Never a 302.**
> A redirect looks correct in a browser and returns 200 to the checker's script,
> so a portal that "protects" the scores by bouncing you to a login page passes
> every manual test and fails the one that matters.

### 0:45 — what it is

> A Django portal. A `for_actor(actor)` accessor is the *only* way to read
> reviews, and a lint rule fails the build if any other form appears — including
> in the tests. 126 reviews, 30 judges, 41 projects, from the organizers' own
> `fixtures.json`.

**Insert — the JJ01 rule failing on a file I wrote (3s).** This one is already on
record and it is the single best three seconds in the project.

### 1:10 — the finding, which is the strongest thing we have

> I built the normalization engine the brief asked for, and then measured whether
> it was needed. Between-judge variance is **0.0217**. The chance floor for
> thirty judges scoring four projects each is **0.0971**. So there is no severity
> effect — and the engine would move all 126 scores by half a rubric point for a
> null result.
>
> **So the leaderboard ships unnormalized, and the page says so on every render,
> with the measurement attached.**

That is a decision, it is counter-intuitive, and it is defensible because the
number is generated and asserted in CI.

### 1:50 — what went wrong, part one: the acceptance line that tested nothing

> The bulk escape hatch's acceptance criterion was "export, import, export is
> byte-identical." My mutation harness made the importer **delete nothing** — and
> the test stayed **green**, because re-importing rewrites the same values onto
> rows that never left.

**This is the best ten seconds in the video.** It is a real defect, found by
attacking my own test, and the lesson is one sentence: *byte-identical is
necessary but not sufficient — it cannot tell "restored correctly" from "never
touched anything."*

### 2:10 — what went wrong, part two: the escape hatch rejected the product

> Then the importer started quarantining all 126 reviews. Five tables had no
> natural key written by the loader, so there was nothing to match on. It
> surfaced as a NOT NULL violation, a census miscount, and a quarantine report —
> three unrelated symptoms, one cause.
>
> And two rows it did have keys for were the **demo logins**, so a restore
> silently deleted them and the demo stopped working on the second boot.

### 2:35 — the second thing worth saying out loud

> Claiming more than I could prove turned the acceptance gate **red**. I proved
> it, reverted it, and left the capability built and unclaimed — because the
> checkers' own program has no check for the tier I built, and the honest move
> was to say that rather than work around it.

### 2:50 — where I am

> Four tiers built, one proven and claimed, two built and honestly unclaimed.
> Ninety-seven findings, each one either fixed with a test or recorded with a
> reason. And a published leaderboard that tells you it is unnormalized, and
> why, and what it would cost to change.

---

## Recording notes

- **Full frame for every claim, inserts only for artefacts.** A B-roll bed under
  an argument is a signal that there is no argument.
- **The two failure sections are the ones to rehearse.** Everything else can be
  read off a slide.
- **The numbers on screen must match the repo.** 0.0217, 0.0971, 0.227, 126, 41,
  97. All generated; `tools/verify_spec.py` fails if a document quotes one
  wrongly, and the video is a document.
- **Do not claim T3 or T4 on camera.** State plainly that they are built and
  unclaimed, and why. That sentence is worth more than a tier that fails a check.
