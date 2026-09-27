# 04 · Fixtures Dataset Bible

**Purpose:** a measured census of `fixtures.json` — the data every team seeds —
and an account of the eight deliberate edge cases it contains, what each one
punishes, and the behaviour it forces on our loader and our schema.

Every number below was computed from the file, not read off the website. The
website says "roughly 40 projects, 30 judges, 8 tracks"; the file says 41, 30,
8, and 40 teams and 126 scores. The site also says the file contains "a judge
who gave every single project the same score, two review batches that were never
finished, and a duplicate submission." All three are present, identified below
by ID.

---

## 1. Top-level shape

Six keys, in this order:

| Key | Type | Count | Notes |
|---|---|---|---|
| `event` | object | 3 fields | The only event. |
| `tracks` | array | **8** | `trk_01`–`trk_08` |
| `judges` | array | **30** | `jdg_01`–`jdg_30` |
| `teams` | array | **40** | `tm_01`–`tm_40` |
| `projects` | array | **41** | `prj_01`–`prj_41` — one more than teams, on purpose |
| `scores` | array | **126** | ~3.07 per project |

### The event

```json
{ "id": "evt_01", "name": "Sample Hack 2026",
  "submissions_close": "2026-03-01T18:00:00Z" }
```

Three fields only. No start date, no end date, no prizes, no custom questions,
no rubric. Those are all things the *product* must support and the fixture does
not supply — so we seed them ourselves with defensible defaults, and we do so
without touching `submissions_close`. See §5.1.

**`submissions_close` is in the past** (2026-03-01, event window late Sept
2026). This is load-bearing: the spec says *"The fixture event's
`submissions_close` is a date in the past, so if you seeded honestly your
portal is already closed and this post has to be refused."* Seeding honestly
means the seeded event is born closed. Do not "fix" this by moving the date —
that is the single easiest way to fail T1-3.

### Track names

| ID | Name | Projects | Judges assigned |
|---|---|---|---|
| `trk_01` | Developer tools | 6 | 3 |
| `trk_02` | Data and analytics | 6 | 4 |
| `trk_03` | Accessibility | 6 | 6 |
| `trk_04` | Security | 5 | 8 |
| `trk_05` | Climate | 3 | 5 |
| `trk_06` | Health | 3 | 4 |
| `trk_07` | Education | 6 | 6 |
| `trk_08` | Open hardware | 6 | 3 |

Track sizes are **unbalanced (3–6 projects) and judge coverage is unbalanced
(3–8 judges)**. `trk_01` and `trk_08` have six projects and only three judges
each — precisely where an unweighted assignment produces an unfair workload.
This is not incidental; it is the assignment problem in miniature. See §4.6.

### Judges

30 records: `{id, name, email, tracks[]}`. 21 judges cover one track, 9 cover
two. All emails are `@example.org`, all unique, all synthetic.

`jdg_08` — three reviews — is our `peer_scores` target in `.dogfood.toml`,
chosen because they have actual reviews to protect. `jdg_07` — the constant
scorer — is three reviews, also useful for a demo of normalization.

### Teams

40 records: `{id, name, members[]}`. Membership size varies: 13 teams of 1,
12 of 2, 6 of 3, 9 of 4. All member emails are unique across the whole file —
no email appears on two teams. First member of `tm_01` is `priya1@example.org`,
a deliberate echo of Priya from the spec's story. Team names are single-word
synthetic names.

**Model implication:** membership is many-to-many in principle, and a person
may legitimately belong to exactly one team per event in this data. The schema
must not assume one-team-per-user as a hard rule; it must be a
per-event constraint, or the bulk import path breaks on real data.

### Projects

41 records: `{id, team, track, title, summary, repo_url, submitted_at}`.

- `submitted_at` ranges from `2026-02-26T23:30:00Z` to `2026-03-01T17:57:00Z`.
- **No project is late.** The latest, `prj_41`, is 3 minutes inside the
  deadline. So the fixture contains no *invalid* submission, only a **duplicate
  one** — the deadline check cannot be satisfied by rejecting data, and cannot
  be dodged by filtering.
- **First three titles — the only ones T1-2 looks for:** `Glass Signal`,
  `Small Meadow`, `Deep Compass`.
- `summary` is the literal string `"One line of what it does."` on every
  record. Useless as content; fine as a required non-null field.
- `repo_url` is `https://example.org/repo/NN` — a placeholder host, not a real
  repository. Do not attempt to fetch it (rule 05, and it would break the
  offline requirement).

### Scores

126 records: `{judge, project, criteria{...}, comment}`.

- **Criteria are always exactly the same three keys** — `functionality`,
  `innovation`, `quality` — in all 126 records. No missing keys, no extra keys,
  no nulls. One set, 126 times, so the seed never has to handle a ragged rubric.
- **The key *order* in the file is `functionality, quality, innovation`** — all
  126 records, without exception. Note this is *not* the order the criteria are
  listed in `spec.md`'s sample, nor the order we seed the rubric in
  (functionality 40 / innovation 35 / quality 25, per `06` §3.1). The set is
  stable; the order is the fixture's business, not ours.
  **Engineering consequence, and it is a real one: never derive column or
  field order from the fixture.** A CSV writer or a form builder that takes
  `list(record["criteria"].keys())` off the first row it sees will emit
  `functionality, quality, innovation`, which will not match the rubric's own
  ordering and will silently transpose two columns in every export. **Rubric
  and `Criterion.position` own the ordering; the fixture is a bag of values
  keyed by name.** This is also why `05` §5 makes `Criterion.key` the join
  rather than a positional index.
- Value range is **2–5 for all three criteria**. Never 1, never 0, never 6+.

| criterion | 2 | 3 | 4 | 5 |
|---|---|---|---|---|
| functionality | 25 | 37 | 31 | 33 |
| innovation | 29 | 30 | 36 | 31 |
| quality | 29 | 32 | 28 | 37 |

- **51 of 126 comments are empty strings** (40%). A comment is optional. The
  fixture says so.
- **Zero duplicate `(judge, project)` pairs.** So a unique constraint on that
  pair is safe *for this fixture* and still correct in general.
- **Zero off-track scores.** Every score has the judge covering the project's
  track. So the fixture will not embarrass us with a data-integrity error; we
  must enforce that rule ourselves because the data does not demonstrate it.

---

## 2. Review distribution

> **Correction log.** An earlier revision of this section carried two wrong
> histograms: projects at 3/4/5 reviews as `22 / 9 / 2`, and judges at 2/3
> reviews as `7 / 5`. Both were caught by the invariant check in §2.1 on
> re-measurement against the file, and both are now correct. The lesson is
> recorded in §2.1 because our own seed step has to make the same class of
> mistake impossible, and because a `DATA-MODEL.md` that quotes a
> distribution which does not reconcile loses the reader's trust in every other
> number in it.

| Reviews per project | 2 | 3 | 4 | 5 |
|---|---|---|---|---|
| Projects | **8** | **26** | **3** | **4** |
| Project IDs | `prj_10` `15` `18` `19` `24` `29` `39` `40` | *(26 projects)* | `prj_11` `prj_37` `prj_41` | `prj_07` `prj_08` `prj_14` `prj_35` |

**No project has zero reviews.** The distribution is sharply peaked: **26 of 41
projects have exactly 3 reviews**, which is the `reviews_per_project` target,
so the median project is fully covered and the mean is 3.07. **8 projects are
below target at 2 reviews** — those are the ones a naive average leaves at the
mercy of whichever two judges happened to reach them.

| Reviews per judge | 1 | 2 | 3 | 4 | 5 | 6 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|
| Judges | 2 | 6 | 7 | 4 | 3 | 5 | 1 | 1 | 1 |

Judge load runs from **1 to 11** — a 3.67× spread between the least and most
loaded judge. `jdg_01` and `jdg_23` have a single review each; `jdg_24` has
eleven. The spec calls these "two review batches that were never finished."
Both ends of the distribution are the *same* phenomenon: partial completion.

### 2.1 The invariant check — and why it is in this document

Any histogram over a fixed population has two invariants, and **both of the
corrected tables above violated one of them.** They are cheap to check and they
catch a whole class of careless transcription:

1. **Cardinality.** The bucket counts must sum to the population.
   `Σ(judge counts) = 30`. The old table summed to **29** — one judge had
   vanished, which is why the error was invisible on a casual read.
2. **Mass.** The bucket counts weighted by their bucket must sum to the total
   number of records. `Σ(n × judge count) = 126`. The old per-project table
   gave `8·2 + 22·3 + 9·4 + 2·5 = 128`, not 126 — **two more score rows than
   the file contains.** A distribution that describes 128 rows cannot be a
   distribution of 126 rows, whatever the bucket counts add up to.

Invariant 1 is the weaker check and it is the one that passes while the table
is still wrong. **Invariant 2 is the one that catches it.** So the rule for
this project: every census figure quoted in `DATA-MODEL.md` or the
normalization proof gets both invariants asserted, and the seed step in `04`
§6 prints them on boot. If the loader's own anomaly report cannot prove
`Σ(n × count) = len(scores)`, it is not finished.

**Why this is more than tidiness.** The scoring criteria are read by thirty-six
senior engineers, and `JUDGING.md` is the document they read most closely. A
normalization proof built on a distribution that does not reconcile with the
dataset is not a proof, and the first person to check it will not be a
sympathist. The proof is generated by code rather than typed, precisely so this
cannot happen there — but the *narrative* around it is typed, and the narrative
has to be right.

> **The invariant log caught six errors, not four.** Rows 5 and 6 below were
> found on a second pass *after* the correction log in `README.md` had already
> been written — a 26-row per-judge table over a 30-judge population, and a
> mis-ranked judge, both in `06` §4.1a, which is the table the entire
> normalization argument rests on. **The lesson is worse the second time:** a
> correction log that itself contains un-caught errors teaches a reader to
> distrust the process rather than the number. Every census table in this folder
> is now generated and prints its own row count.

**What this forces, concretely:**
- Aggregation must tolerate 1..N reviews per project without dividing by zero
  or crashing.
- Normalization must not treat a single-review judge as a reliable estimator of
  that judge's severity. Two judges with n=1 have no measurable variance — this
  is the central statistical problem in the file, and `06` §4 is devoted to it.
- The progress dashboard has something real to show: `jdg_24` complete,
  `jdg_01` and `jdg_23` at 3%.

---

## 3. The three named cases, identified

The spec names three. Here they are by ID.

### 3.1 The constant scorer — `jdg_07`

`jdg_07` reviewed 3 projects and gave **4/4/4 on every one**. Functionality 4,
innovation 4, quality 4, three times. The three projects are **`prj_09`,
`prj_17` and `prj_19`**.

This is the case the whole judging-integrity criterion is built around. The
brief's own words: *"Tell us what you did about the judge who marks everything
a 3."* Here it is a 4, which is worse, because 4 is plausible-looking and a
constant judge produces a perfectly respectable-looking mean that carries
**zero** discriminating information.

**And here is the sharpest version of the case, which the fixture hands us for
free and which is worth more than the abstract argument:**

> **`prj_19` is one of the eight projects sitting at 2 reviews out of a target
> of 3.** `jdg_07` is one of its two reviewers. **A judge who marks everything
> 4/4/4 therefore contributes half of `prj_19`'s entire score, and half of it is
> the number 4.0000 — the arithmetic mean of nothing.** A project at 2-of-3 is
> already the fixture's most fragile result, and the constant judge is sitting
> on one of them.

That is one row, one project, and one arithmetic operation, derived entirely
from the published dataset. It is the shot for the demo video.

Two judges with n=1 (`jdg_01`, `jdg_23`) are trivially constant and are *not*
the interesting case — a single observation carries no evidence of
inconsistency. A defensible method must distinguish "constant because
inconsistent" (n≥2, variance 0) from "constant because n=1" (unknown). `06` §4.2
specifies that distinction, it is the kind of detail a statistician on the panel
will notice immediately, and `06` §4.2a records a **correctness bug in the MAD
formula** that the distinction exposes: `median(|x − med|)` over a one-element
list is `0` for *structural* reasons, which is the same number `jdg_07` produces
for *evidential* ones. The two must not share a code path.

### 3.2 The unfinished batches

`jdg_01` (1 review) and `jdg_23` (1 review) versus `jdg_24` (11 reviews). Eight
projects with 2 reviews against neighbours with 5.

The failure this punishes is averaging naively: a project with 2 reviews is
dominated by whichever two judges happened to get to it, and if one of them is
`jdg_07` with the constant 4s, that project inherits a 4.0 that means nothing.
`06` §4's shrinkage estimator exists for exactly this case.

### 3.3 The duplicate submission

```json
{"id":"prj_07","team":"tm_07","track":"trk_03","title":"Dry Harbour",
 "summary":"One line of what it does.",
 "repo_url":"https://example.org/repo/07",
 "submitted_at":"2026-03-01T04:29:00Z"}
{"id":"prj_41","team":"tm_07","track":"trk_03","title":"Dry Harbour",
 "summary":"One line of what it does.",
 "repo_url":"https://example.org/repo/07",
 "submitted_at":"2026-03-01T17:57:00Z"}
```

Identical team, track, title, summary and `repo_url`. Different IDs. **13h 28m
apart**, the second three minutes before the deadline. `tm_07` is the only team
with two projects, and `prj_41` is the only project with no earlier sibling.

Three defensible readings, and we must pick one and defend it in `DATA-MODEL.md`:

1. **Two submissions of the same work** — a late re-upload, or a team that
   submitted twice. Then they should be deduplicated for results.
2. **Two genuinely different projects with a name collision** — possible, but
   the identical `repo_url` makes it very unlikely.
3. **Dirty data** — a fixture-generation artefact.

The spec's framing — *"a duplicate submission"* — points at (1) or (3). **We
choose: store both `Project` rows, link them with an explicit `supersedes`
relation, and aggregate by team in results.** Reasons:

- **Losslessness.** The loader is a fidelity boundary. If we silently drop
  `prj_07`, the import path stops being trustworthy and the export path stops
  round-tripping. An organizer who imports data with collisions must be able to
  get it back out unchanged.
- **It is the honest product behaviour.** Real events get double submissions.
  Modelling it explicitly is a feature, and it is a schema decision a database
  person would want to see defended.
- **It gives us a real thing to write about** in the Write Up Quest: the
  schema you would redo.

Consequence to be careful about: `prj_07` and `prj_41` have independent review
rows, so two projects in `trk_03` both carry scores. If we aggregate by team we
must decide how — maximum, mean, or latest. **Latest-wins is the rule**: the
superseding submission's reviews are the ones that count, and the superseded row
is retained with its reviews for the audit trail. Documented, deterministic, and
it matches the way a human organizer thinks about it. `06` §3 covers the
assignment implication (do not assign the same judge both siblings — it is a
wasted review and it correlates two errors).

**And here is the consequence that will be asked about, so measure it before
anyone raises it.** The two siblings are not reviewed to the same depth:

| | `prj_07` (superseded) | `prj_41` (superseding) |
|---|---|---|
| Reviews received | **5** | **4** |
| Status in the histogram | joint-highest in the event | mid-pack |

So **latest-wins discards five reviews and keeps four.** It is still the right
rule — the later submission is the one the team meant to be judged, and a
reviewer who saw the superseded draft was reviewing a different artefact — but
it is a rule that throws away more evidence than it keeps in this specific case,
and an organizer looking at the audit trail will notice.

Two consequences we commit to handling rather than discovering:

1. **The dashboard shows both, and says which one counts.** The team view lists
   the supersede chain, the review count of each row, and a plain-language note
   that the superseded draft's reviews are excluded from the result. Nothing
   hidden.
2. **The results export carries both rows** with the `supersedes` link and a
   `counted` boolean, so the exclusion is auditable and reversible by an
   organizer who disagrees with the rule. `04` §6's lossless round-trip covers
   this, and it is the difference between "we made a judgement call" and "we
   lost your data."

Worth stating in `DATA-MODEL.md` for the same reason: this is the one place in
the schema where a defensible rule is visibly lossy, and volunteering that is
worth more than the rule is.

---

## 4. The eight edge cases, ranked by what they punish

The spec names three. Reading the data finds five more. Each is a trap, and each
traps a *different* lazy implementation. That is the design: they are there to
separate a portal that works on tidy input from one that works on real input.

| # | Case | Where | Punishes | Our required behaviour |
|---|---|---|---|---|
| 1 | Past `submissions_close` | `event` | Any attempt to fake liveness; a seeded-but-open event | Portal boots closed; the submit path returns 403; a *new* event can be opened by an organizer |
| 2 | Constant scorer `jdg_07` | 3 scores | Naive averaging; a normalizer with no robustness story | Inconsistency detection with a minimum-n rule; shrinkage toward the global mean; the judge is flagged in the audit view, not silently dropped |
| 3 | Incomplete batches | 2 judges at n=1; 8 projects at n=2 | `n=1` treated as a valid severity estimate; unweighted averaging across unequal review counts | Shrinkage by review count; explicit `n` everywhere; the dashboard shows partial completion |
| 4 | Duplicate submission | `prj_07` / `prj_41` | Deduplicating silently; keying projects by title; double-counting a team | Explicit `supersedes`, both rows retained, latest-wins aggregation, documented |
| 5 | 41 projects / 40 teams | global | Assuming one-project-per-team in the schema; title uniqueness | No title uniqueness; team-to-project is one-to-many; gallery and results aggregate by team |
| 6 | Load imbalance 1→11 | judges | An assignment algorithm that ignores load; a progress view with no notion of "behind" | Load-balanced assignment (§4.6); the dashboard ranks judges by completion |
| 7 | Uneven track sizes 3–6 projects, 3–8 judges | tracks | Global assignment; a per-track divide that assumes even sizes | Track-scoped assignment with a per-track load target; the unbalance is reported |
| 8 | 51/126 empty comments, uniform 1-word summaries | scores | `NOT NULL` on comment; content-based dedup; a gallery that renders a teaser | Comment nullable; summary is a required non-empty string; gallery shows track and tags, not the teaser |

**Case 8's summary deserves a note.** Every `summary` is the same 14-word
string. A gallery that renders summaries therefore looks identical on all 41
cards, which makes the gallery look broken in the demo video. **Build the card
around title, team, track, tech tags and review count** — not the summary — and
the seeded gallery looks like a real product even though the data is synthetic.
This is a small thing that costs ten minutes and shows up in the five minutes
everyone watches.

---

## 5. What the fixture does *not* give us, and what we seed

The fixture is input, not a data model — the spec says so twice. Everything
below is ours to invent, and every choice is a chance to be caught out by a
judge who knows the platform.

| Missing | Why it matters | Our seed |
|---|---|---|
| Event start/end dates, description, banner | T1 requires configurable dates | A plausible window around `submissions_close`. **Never modify `submissions_close`** |
| Prizes | T1 requires configurable prizes | Four prizes matching the real structure: 1st 800, 2nd 500, 3rd 350, 4th 200, 5th 150, plus a category prize. Uses the actual amounts, which makes the demo legible to anyone who has read the site |
| Rubric and criteria | T2 requires a weighted rubric | Three criteria with **non-uniform weights**, to demonstrate the thing the market leader cannot do. Weights must be visibly unequal, e.g. functionality 40 / innovation 35 / quality 25 |
| Custom submission questions | "plus organizer-defined custom questions" in the stable field set | Two: "What did you build?" and "What would you do with a mentor's time?" — the second is a real hackathon question |
| Tech tags | In the stable field set | Derived deterministically per project from its ID, 3–5 tags, so filters have something to filter |
| Image gallery, demo video URL, live link | In the stable field set | Nullable, mostly empty. Empty is honest; a fake URL is not |
| Users, passwords, sessions | The checker attaches headers; it never logs in | Five deterministic identities (§5.2) |
| Assignments | The fixture has scores but no assignment records | **Synthesise assignments from the scores.** The score rows *are* evidence of assignment; reconstructing them means the progress dashboard and the isolation model operate on real structure rather than a stub |
| Votes, comments, audit entries | T3 | A modest seeded set so the public layer is not empty, and so the anti-abuse view has something to show |
| Pairwise comparisons | Pairwise bonus | Synthesise from the rubric scores as noisy preferences, clearly labelled as synthetic in `JUDGING.md` |

### 5.1 The date problem, stated once

The seeded event is **born closed**. Consequences we must design for, all of them
real:

- A judge opening the portal for the first time sees a closed event and cannot
  try submitting. The demo video therefore has to **create a second, open event**
  to show the submission lifecycle. This is a feature of the demo, not a
  workaround: *"create → submit → judge → publish"* is literally the required
  video structure, and the seeded fixture event is the *judging* fixture, not
  the *submission* fixture.
- T1-3 passes because the guard is real, exercised by our own tests against both
  a closed and an open event.
- The organizer UI must make "this event is closed" a first-class, visible state
  with the date and a way to reopen or clone it into a new event.

### 5.2 The five seeded identities

Required by the contract: an organizer, two distinct judges with reviews, and a
participant who is not a judge.

| Identity | Role | Bound to | Why this one |
|---|---|---|---|
| `organizer` | organizer + admin | `evt_01` | The CSV and aggregate checks |
| `judge_a` | judge | `evt_01`, `trk_04` (`jdg_08`, 3 reviews) | Real reviews, so the own-scores check returns data, not an empty list |
| `judge_b` | judge | `evt_01`, `trk_03` (`jdg_07`, 3 reviews) | **Different track from `judge_a`.** So the untested cross-track cell of the isolation matrix is also live in the demo |
| `participant` | participant | `evt_01`, member of `tm_01` | Not a judge, so T2-6 is a real refusal rather than a role mix-up |
| `admin` | admin | all events | For the admin surfaces |

`judge_a` and `judge_b` being on **different tracks** is a deliberate upgrade
over the spec's example. It means one live seed exercises peer isolation *and*
track isolation *and* aggregate isolation, so the demo video can show all three
refusals from real seeded state rather than from contrived setup. It costs
nothing and it is the kind of detail that reads as competence.

Each gets a stable, printable session value. Not secrets — this is a local demo
fixture — and the README says so plainly rather than implying they are
credentials worth protecting.

> ### ⚠ Only these five get password hashes. This is a measured constraint, not
> ### a preference, and it belongs in the Block B migration.
>
> The fixture contains **121 distinct people** — 30 judges + 91 unique member
> emails, all disjoint (`04` §1). On the installed stack, one
> `pbkdf2_sha256` hash at Django 5.2's default **1,000,000 iterations costs
> ~400 ms.**
>
> | | count | hashing cost |
> |---|---|---|
> | All fixture people given accounts | **121** | **~48 s** |
> | The five test identities only | **5** | **~2 s** |
>
> **48 s is 4.8× the 10-second timeout in `run.py`**, and the loader runs before
> the server binds, so every cold `compose up` pays it. Full analysis in
> `03` §4.7.
>
> **The rule, and it is a schema decision:**
> - The five seeded identities get real, hashed passwords.
> - **The other ~116 get `UNUSABLE_PASSWORD` and cannot log in.** They exist as
>   `TeamMembership` rows and as judges on `RoleBinding`. That is *correct*:
>   they are synthetic fixture people, and an account they cannot use is a
>   smaller liability than an account with a guessable password.
> - Cheapest variant: hash once at seed time and reuse the string, since these
>   are documented non-secret demo credentials.
>
> This also settles a question the fixture deliberately leaves open — **judges
> and team members are disjoint in this data, but a real event will not be.** A
> single `User` table keyed on email handles both, and this is why the five
> identities are `User` rows while the other 116 are membership records
> pointing at a `Person`-shaped row rather than being full accounts. See
> `05` §3.

---

## 6. Loader requirements

The loader is a first-class component, not a migration script.

1. **Idempotent.** `compose down -v && compose up` twice produces identical
   state. Natural keys — fixture IDs — are preserved as our IDs where possible,
   so a second load updates rather than duplicates.
2. **Lossless round-trip.** Export produces a file that re-imports to the same
   logical state. This is the escape hatch (REQ-T4-05) and it is what makes the
   duplicate case in §3.3 safe to keep.
3. **Never mutates the fixture's semantics.** `submissions_close` in, unchanged
   out. No date "fixing", no defaulting, no coercion that changes a value.
4. **Validates and reports.** Counts in, counts out, orphan references detected,
   duplicates flagged. Print a summary on boot: projects, reviews, judges,
   tracks, teams, and any anomalies found. **A seed step that prints its own
   anomaly report is doing the judge's verification work for them.**
   **The report must include the two invariants from §2.1** —
   `Σ(judge counts) = 30` and `Σ(n × judge count) = len(scores) = 126`, plus
   the same pair over projects (`41` and `126`). If either fails, the seed step
   prints a loud warning and the boot is treated as failed. This is cheap, it is
   the exact check that caught our own bad census, and a seeded portal that
   prints its own reconciliation is doing the verification we would otherwise
   have to do by hand.
5. **Preserves fixture IDs.** `prj_07` staying `prj_07` means a judge's `curl`
   in the demo video and our test fixtures refer to the same thing, and the
   isolation transcript is checkable against the published dataset.
6. **Tolerant of the ragged parts.** Missing comments, uneven review counts, the
   duplicate, the two-team-project case. It must not raise.

That last point is the one the spec is really testing: *"If your portal only
works on tidy input, you will find out on Friday rather than on Monday."*

---

## 7. The dashboard and the demo, driven by this data

Both should be visibly built on the fixture rather than generically nice:

- **Progress:** 30 judges, review counts 1–11, eight projects behind. Ranked,
  with the two `n=1` judges at the bottom and `jdg_07` flagged as low-variance.
- **Normalization panel:** raw σ vs normalized σ on the 41-project field, plus
  the ranking deltas. The site's own figure — σ 0.94 → 0.31 — is the
  comparison to beat or at least approach, and computing ours from this exact
  data is the proof.
- **Audit trail:** an organizer-readable list. Two judges at 3% completion, one
  flagged for low score variance, one project superseded, eight projects with
  fewer than the target number of reviews. All of it real, all of it derived.
- **Gallery:** 41 cards, 8 tracks, tag filters, search. First page must contain
  `Glass Signal` or `Small Meadow` or `Deep Compass` (T1-2).

---

## 8. Two structural facts about the graph that are not in any histogram

Both measured, both load-bearing, both found by asking a question the census did
not ask.

**1. The judge–project bipartite graph is fully connected.** Breadth-first from
any node reaches all 71 nodes (30 judges + 41 projects) in **one component**,
and all eight per-track subgraphs are individually connected as well.

*Why it matters.* Identifiability. A joint model that estimates both judge
severity and project difficulty (a two-facet Rasch model, or a Bradley-Terry
fit on the same graph) is **identified** on this data, so it will converge and
so the §7.3 disconnected-graph caveat in `06` will not fire. That cuts both
ways: it means the many-facet model is *worth testing* rather than immediately
rejected on identifiability grounds, and it means **we cannot demonstrate the
disconnected-graph handling on the published fixture at all.** Measured, the
many-facet model still loses on prediction (`06` §4.3e) — but the reason is
bias–variance at n=3 reviews per project, not non-convergence.

**2. `jdg_07`'s three projects are `prj_09`, `prj_17`, `prj_19`, and `prj_19` is
one of the eight projects at 2 reviews.** See §3.1. This is the sharpest
single-row argument in the dataset and it is entirely derived from the published
file.

---

## 9. Quick reference for implementation

```
event      evt_01  "Sample Hack 2026"  submissions_close 2026-03-01T18:00:00Z  (PAST → portal born closed)
tracks     8        trk_01..trk_08    3–6 projects each, 3–8 judges each
judges     30       jdg_01..jdg_30    21 single-track, 9 dual-track
teams      40       tm_01..tm_40      1–4 members, all emails unique
projects   41       prj_01..prj_41    one per team, except tm_07 which has two
scores     126      3 criteria {functionality, innovation, quality}, values 2–5
                      51/126 comments empty
                      0 duplicate (judge,project) pairs
                      0 off-track scores
reviews    per project 2..5   8@2, 26@3, 3@4, 4@5      → median 3, mean 3.073
             n=2: prj_10 15 18 19 24 29 39 40    n=4: prj_11 37 41
             n=5: prj_07 08 14 35                8 projects below the 3-review target
           per judge   1..11  2@1, 6@2, 7@3, 4@4, 3@5, 5@6, 1@9, 1@10, 1@11
             n=1: jdg_01, jdg_23                  max: jdg_24 = 11
INVARIANTS  Σ(judge counts)   = 30          (population)
            Σ(n × judge count) = 126 = len(scores)   (mass)   ← see §2.1
constant   jdg_07    3 reviews (prj_09, prj_17, prj_19), 4/4/4 every time
                         ^ prj_19 is a 2-review project -> jdg_07 is HALF its score
duplicate  prj_07 + prj_41   tm_07, trk_03, "Dry Harbour", same repo_url, 13h28m apart
titles[0:3]         "Glass Signal", "Small Meadow", "Deep Compass"   ← T1-2 greps these
                   (prj_01 trk_04, prj_02 trk_03, prj_03 trk_03 — keep all three on page one)
GRAPH     judge-project bipartite: 1 connected component, 71 nodes.
          All 8 per-track subgraphs connected.  => joint models are identified;
          the disconnected-graph caveat CANNOT be demonstrated on this fixture.
SCOPE     severity    0.94 not reproducible; max obtainable 0.4323 (sd of 30 judge means)
          effect      permutation p = 0.234; between-judge var 0.0217 < noise floor 0.0971
          n=1 judges  2 (jdg_01, jdg_23)   MAD returns 0 for structural reasons, not evidence
          n=3 judges  7                   jdg_07's MAD is genuinely 0 -> real inconsistency
TRACKS    trk_01, trk_08: 6 proj, 3 judges -> 18 needed, 18 possible. ZERO SLACK, not
          infeasible.  Feasible iff per-judge capacity >= 6; provably INFEASIBLE at cap 5.
          trk_06 also missed target (8 of 9).  3 tracks short, 5 over, net +3.
```

**What is NOT derivable from this file, and we publish that finding rather than
work around it:** the between-judge variance is **below the sampling-noise
floor**, so the published fixture contains no measurable severity effect, and
`σ = 0.94` cannot be reproduced under any of the four natural definitions of
judge spread. `06` §4.1b and §4.4c carry the full analysis. This is the single
most important thing in this folder and it is a null result.
