# 01 · Mission and Win Conditions

**Purpose:** establish why we win or lose, convert the published scoring rubric
into concrete tactics, and define the gates that keep a T4 ambition from
producing the thing the brief explicitly says loses.

---

## 1. The actual objective function

The website publishes a rubric. Read literally it says: build tiers, be
correct, be defensible, be operable, be tasteful. That framing is a trap,
because it implies the four criteria are four independent sliders we can each
push a little. They are not. They are **one hard gate followed by a weighted sum
with a variance term.**

```
TOTAL = 0.40·TierCompletion
      + 0.25·JudgingIntegrity
      + 0.20·Adoptability
      + 0.15·CodeQuality        (each criterion scored 1–5)

TOTAL = 0  if T1 not cleared          ← the only true cliff
```

The panel is 36 seats, 3 reviews per project, evaluation window 29 Sep – 8 Oct.
The site publishes their own internal figure: **raw judge spread σ = 0.94**,
normalized σ = 0.31. That is a 3× compression. With σ = 0.94 across judges on
a 1–5 scale, the difference between a 4.0 and a 4.3 project is inside the
noise. **This is the single most important number on the page and almost nobody
will react to it.** It means:

- Chasing half a tier point is not a strategy.
- A *decisive* win (0.5+ on any criterion) is worth more than three mediocre
  ones. Breadth of features is nearly worthless; depth on the scored axis is
  everything.
- Consistency of signal matters more than volume of work. Three T4 features
  that half-work do not beat two T2 features that are flawless — stated
  explicitly, twice, by operators who have watched it happen.

> ### ✅ RESOLVED — and the finding is now a contribution, not a caveat
>
> We reported that the published σ = 0.94 was not obtainable from
> `fixtures.json` under any of four natural definitions of judge spread (largest
> obtainable: **0.4323**, the sd across the 30 judge means). The organizers
> confirmed it was a bug in the website description, most likely a cosmetic
> landing line not present in `/spec`, and **corrected the homepage to σ = 0.42** —
> the stdev of per-judge means, computed from `fixtures.json`. They asked us to
> build the normalization proof against the actual fixture values.
>
> **Two consequences, both good:**
>
> 1. **The comparison is now available and we are being invited into it.** Their
>    0.42 and our 0.4323 are the same number computed the same way. One flat
>    sentence in `JUDGING.md` — we found a discrepancy, reported it with the
>    evidence, it was corrected — and no more. **It is not a marketing point; it
>    is the method working on the one thing it was built to do.** Full treatment
>    in `06` §4.4c.
> 2. **The substantive finding is untouched and arguably now better supported.**
>    The organizers corrected the *number*. They did not address what the number
>    is a measurement *of*. A variance decomposition of the fixture puts the
>    between-judge variance at **0.0217 against a sampling-noise floor of
>    0.0971** — the panel has *no measurable severity effect* (permutation
>    p = 0.234), and at 4.2 reviews per judge you could not have detected one
>    smaller than **τ = 0.75**.
>    **And a second, independent signal points the same way:** the published
>    normalized figure of 0.31 is reproducible by three different *global*
>    standardizations, none of which contains a per-judge term (0.3174, 0.3240,
>    0.3301). **For a panel with no judge effect to correct, close-to-no
>    correction is close to the right answer.** We raise this as a question, not
>    a criticism — we do not know their definition and we may have the wrong one.
>    Still the single most valuable thing in the project: `06` §4.1b.

**Therefore our strategy is not "build everything." It is: clear the gate,
then go deeper than anyone on two axes the panel explicitly named, then be
immaculate on the one axis a stranger measures in sixty seconds.**

---

## 2. The three decisive frontiers

### 2.1 Backend-enforced role isolation (25% Judging Integrity + 40% Tier)

The website publishes a role isolation matrix, FIG. 02, and says it is
**"VERIFIED BY ACCEPTANCE SUITE T2.03."** The matrix is:

| Actor | Own scores | Peer scores | Other track | Aggregate | Audit log |
|---|---|---|---|---|---|
| VISITOR | ✗ | ✗ | ✗ | ✗ | ✗ |
| PARTICIPANT | ✗ | ✗ | ✗ | ✗ | ✗ |
| JUDGE | **+** | ✗ | ✗ | ✗ | ✗ |
| ORGANIZER | + | + | + | + | + |
| ADMIN | + | + | + | + | + |

Three things follow, and only the first is obvious:

1. **Peer scores must be refused at the API.** Non-negotiable, and the single
   most common way a good-looking project loses points.
2. **A judge must be refused across tracks, not just across judges.** The
   checker never tests this. A judge on `trk_03` reading a `trk_07` review is
   exactly as much a leak, and no automated check catches it. We enforce it
   anyway, and *say* that we enforce something untested — that is the mark of
   an engineer rather than a scorer-chaser.
3. **A judge must be refused the aggregate.** If judge A can read the current
   leaderboard, every other judge's scores are one inference away. Judges get
   their own scores and nothing else until results are published. This is the
   row the matrix marks ✗ that nobody thinks about.

Design consequence, and it is the core architectural decision of the project:
**isolation is enforced in the data-access layer, not the view layer.** A
judge-scoped queryset is the unit of authorization. Views never assemble
collections themselves; they ask a manager for an already-scoped queryset. This
makes leakage a *structural* impossibility rather than a remembered `if`.

### 2.2 Cross-judge normalization, defended (25% + Best Judging Engine prize)

The panel's stated position: *"Every commercial platform claims to do this and
none of them will tell you how."* Devfolio advertises "automatic score
normalization" as a headline feature and publishes nothing about it. The market
leader cannot weight its criteria at all and tells organizers to use a
spreadsheet.

So: **the normalization method is not a feature, it is the deliverable.** The
`JUDGING.md` document is read by judges and carries weight. "We averaged the
scores" is an answer and a weak one. *"Tell us what you did about the judge who
marks everything a 3."*

And the fixture set is built to make exactly that question unavoidable: there
is a judge in the data who gave **4/4/4 on every single project they touched**,
a load imbalance from 1 to 11 reviews per judge, and eight projects with only
two reviews while their neighbours have five. The data is a trap for tidy
implementations, and it is the trap we are going to spring on ourselves first
and document the result.

Full treatment in `06`.

### 2.3 The one command (20% Adoptability + 20% of the 40% perception)

> *"If it does not come up on a laptop with the network off, we cannot adopt
> it, and adoption is the entire point of the event."*

They closed the loopholes themselves, up front, by name:
hosted database service, auth-as-a-service, staging URL, "works on my machine."

Our reading, which drives the stack decision:

- **One service. One image. A file for a database.** A second service means a
  second image to pull, a healthcheck to get right, a migration race between
  app and DB, and a volume to get permissions on. Every one of those is a judge
  who gave up at minute three. SQLite with WAL handles a hackathon's judging
  load comfortably and removes an entire failure class.
- **Seeds itself on boot.** The portal must come up already populated, because
  the acceptance checker runs immediately afterwards and a judge will not wait.
- **Prints its own credentials.** The checker never logs in — it attaches
  headers we supply. Our seed step prints the exact `Cookie:` strings so
  populating `.dogfood.toml` takes a minute instead of an hour.
- **An escape hatch.** *"A platform you cannot leave is a trap."* Bulk import
  and export is listed under T4 but its real function is this sentence. An
  organizer must be able to get all of their data out in a format they own,
  and be able to bring their data in. This is the cheapest possible goodwill
  and it is explicitly asked for.

---

## 3. The nine ways to score zero

Taken verbatim from the site's "Out of Scope" and "Rules". Each has a guard.

| # | Automatic zero | Guard we implement |
|---|---|---|
| 01 | Design mockups, Figma, or a frontend with hardcoded data | No fixture data in templates. Gallery reads the DB. `docker compose down -v` then up must repopulate. |
| 02 | Needs a cloud account, hosted DB, or auth provider | No outbound network calls anywhere. Grep the codebase for `https://` in a request path before freeze. Zero env vars required to boot. |
| 03 | An auth demo that stops at the login screen | All five roles have real authenticated flows, not just a login form. |
| 04 | A gallery with no judging, or judging with no gallery | Both are built, both are linked, the demo video walks one lifecycle through both. |
| 05 | Role checks only in the frontend — *"if I can curl another judge's scores it is not isolation"* | Queryset-scoped access + an isolation test suite of our own that `curl`s every cell of the FIG. 02 matrix. |
| 06 | LLM dumps with no architecture document and nobody able to defend the schema in writing | `ARCHITECTURE.md` and `DATA-MODEL.md` are written by a human-usable argument, not generated boilerplate. Every schema decision in `05` has a stated reason and a stated cost. |
| 07 | Closed source or non-OSI license | MIT from commit one. |
| 08 | Requires custom hardware, GUI toolchains, or proprietary services | Laptop and Docker only. |
| 09 | A rewrite of an existing open-source platform with the name changed | New code. Django, DRF and drf-spectacular are libraries, not a platform rewrite. No Gavel, Dribdat, Devpost-clone lineage. |

Note #06 with care. They have said twice — in the rules and in the FAQ — that
**AI tools are expected** and are not scored. The thing being scored is whether
"somebody on the team can defend the schema in writing." The bible exists
partly to discharge that obligation.

---

## 4. Where the points actually are

Assume we clear T1 and verify T4 on the checker. Estimated contribution:

| Criterion | Weight | What earns a 5 | Our realistic | Cost to move +1 |
|---|---|---|---|---|
| Tier Completion | 40% | T4 verified, correct, no broken features | 5.0 | already maxed |
| Judging Integrity | 25% | Documented normalization with a worked proof, structural isolation, readable audit, abuse considered up front | 4.5–5.0 | the **Normalization Proof** bonus |
| Adoptability | 20% | One command, seeded, escape hatch, docs a stranger follows without asking | 4.5 | the demo video and the docs, not code |
| Code Quality | 15% | Idiomatic, defensible schema, one stealable decision | 4.0–5.0 | the pairwise engine, or a genuinely novel isolation primitive |

**Read that table as a work order.** The cheapest remaining points are *not*
in more features. They are in: a rigorous `JUDGING.md` with a normalization
proof run on the actual fixture data, an audit trail an organizer can read
without a database client, and documentation quality. All three are writing and
analysis, not engineering, and all three are read by judges rather than run by
a checker. Under a 69-hour clock that is the best possible ratio.

**The stealable decision.** Every criterion mentions one thing we cannot buy:
*"the decision that made a judge stop and say they would steal it."* Ranked
after the second research pass, in order of score-delta per hour:

**1. "We measured whether there was anything to fix, and we told you."** The
normalization proof leads with a **permutation test on the between-judge effect
(p = 0.234)**, a **variance decomposition showing the between-judge variance
(0.0217) sits below the sampling-noise floor (0.0971)**, a **power analysis**
(you could not have detected τ < 0.75 at this panel size), and a **recovery
experiment** on 200 synthetic panels built on the fixture's own graph with a
known injected severity. See `06` §4.1b and §4.4a.
*Why it wins:* ~2.5h, near-zero risk, lands on 25% + the Normalization Proof +
the $100 prize + 15%, and it is **the only framing where a null result is the
win.** Thirty-nine teams will build a normalization method; zero will publish a
power analysis against their own data. The method is stealable. The willingness
is not.

**2. "Feasible" and "provably impossible" are different answers, and we hand
you the min-cut."** The assignment solver's residual graph, read after the
max-flow, names the exact projects that cannot reach target, the exact judges
who are the bottleneck, the exact deficit, and three remedies **with arithmetic
attached** — from the same function call, no second algorithm. Ships the
*corrected* claim (`06` §2.1a): `trk_01`/`trk_08` are **zero-slack, not
infeasible** — feasible at capacity 6, **provably impossible at capacity 5**.
*Why it wins:* ~1.5h on a solver we build anyway, lands on 25% + T2 + the demo,
and it **removes a risk** — the current claim is false and falsifiable in five
minutes. max-flow min-cut ≡ Hall's marriage theorem, 1935.

**3. "The scope receipt: isolation you can read, not just isolation you have."**
`for_actor()` returns a queryset that also carries a human-readable reason, and
every list view renders it: *"You are seeing 3 of 126 reviews because you are a
judge on `trk_04` and these 3 are yours."* `05` §6.
*Why it wins:* ~1h, near-zero risk, and it **extends** our existing best idea
(refusal ≠ filter) from *enforced* to *legible*, which means a judge can verify
isolation without reading our code or trusting our test suite. One mechanism,
three consumers: the receipt, the audit entry, and `manage.py isolation_proof`.

**Honourable mention, and it is strong:** the audit chain head replicated into
every signed judge record (`05` §9). The only candidate that makes a claim about
*the organizer's own honesty*, one column, and the answer to the weakest status
in our threat table.

**What we are not dropping.** The scoped-accessor layer itself — authorization
in the data-access layer, never in views — is *still* the best architectural
decision we have made, and the refusal-not-filter distinction it enables is
required by the brief's own words. Candidate 3 is that idea taken further, not
a replacement for it.

---

## 5. Honest reporting as a scored behaviour

Three separate statements in the brief reward it:

- *"Honest gap reporting is rewarded, inflated claims are penalised here."*
- *"Claiming T2 and verifying T1 scores as T1 with a note about the gap."*
- *"A report with two honest FAIL lines reads better than a README claiming
  everything works."*

And `run.py` mechanically enforces it: it prints `claimed` against `verified`
and flags `note: claimed but not verified:`. There is no advantage in hiding
anything, because the panel runs the identical checker. **Inflated claims are
the only documented way to lose points for free.**

This creates an obligation on us: `.dogfood.toml` must reflect what the report
shows, and `README.md` must name the gaps in our own words. If T3 is half-built
at freeze, we say so in both places and score T2 honestly. The demotion gates in
`08` exist to make that a scheduled decision rather than a 40-minute panic.

Corollary, and it is free points: **if we finish a T4 feature, it must actually
work.** A claimed-but-broken endpoint is worse than an honest gap, because it
damages the credibility of everything else we say. Rule for the whole project:
*never claim a feature we have not exercised at least once against the running
portal.*

---

## 6. Stack decision and reasoning

**Chosen: Django 5 + Django REST Framework + SQLite (WAL) + gunicorn +
whitenoise, shipped as a single image and a single compose service.**

Against each criterion:

| Criterion | Why Django wins here |
|---|---|
| 40% Tier | Auth, sessions, permission framework, ORM, migrations and admin are the shortest path from zero to a *correct* role model. The tier where points are lost is correctness, and correctness is what batteries-included means. |
| 25% Integrity | DRF permission classes plus queryset-level scoping is the idiomatic, declarative way to make peer-score isolation survive a `curl`. Structural isolation is a two-file change here and a hand-rolled mess in a framework without an opinion. |
| 20% Adoptability | One service, one image, a file for a database. Nothing to pull but our image, nothing to race, nothing to orchestrate. The Django admin gives a working organizer dashboard, user management and much of the CSV story on day one — worth roughly a day of a 69-hour budget. |
| 15% Code | Reads as senior-reviewable to a Python reviewer. Conventions make an AI-assisted solo build the most reliable of any stack, which is the actual constraint here. |
| API First bonus | DRF + `drf-spectacular` produces a published OpenAPI spec nearly free. |

**Why SQLite despite "a schema one a database person would defend":** because
the schema is written Postgres-portable and the switch is a documented
`DATABASE_URL` read with psycopg already wired. We use `JSONField` (works on
both), explicit `CheckConstraint`s (works on both), and composite indexes (works
on both). We do **not** use Postgres-only features: no `jsonb` operators, no
`ArrayField`, no `DISTINCT ON`, no CTEs in migrations, no `pg_trgm`. The
full-text search is SQLite FTS5, which is available in the official image and
degrades to `icontains` elsewhere.

**Rejected, and why:**

- **Next.js + Prisma** — best-in-class gallery UX, but a heavier image, SSR and
  cookie footguns under time pressure, and the weakest default story for
  structural isolation. Adopting a platform we then cannot run in 69 hours is a
  worse trade than a slightly plainer stack that definitely runs.
- **FastAPI + SQLAlchemy** — the right answer if pairwise and statistics are the
  whole project. They are 10% of it. T1 assembly cost solo is brutal: sessions,
  admin, templates, forms all hand-rolled. Wrong risk for a 69-hour solo build.
- **Rails** — genuinely excellent here, conventions and migrations included.
  Django's admin plus DRF's declarative permission model is the larger solo
  multiplier, and switching stacks to get it would cost more than it saves.
- **Laravel** — same shape of argument, and a smaller surface for reliable
  AI-assisted generation under time pressure.

**The one-line version for `ARCHITECTURE.md`:** we chose the most opinionated
framework available so that the one thing that is scored most — correctness of
the role model — is the thing the framework is most opinionated about, and so
that the one command that is scored second needs the fewest moving parts.

---

## 7. T4 risk register

Full T4, solo, 69 hours, and the brief says a clean T2 beats a broken T4 three
times. We are proceeding at T4 anyway, as instructed. So we manage the risk
structurally rather than by hoping.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| T4 breadth dilutes T2 correctness | **High** — this is the default failure mode | Catastrophic: 40% + credibility | Tier-per-branch discipline. Every tier has its own verification gate. Nothing in T3/T4 touches the T2 code paths; features are additive modules. |
| Isolation is retrofitted at hour 60 and leaks | Medium | Fatal to 25% + acceptance | Build the scoped-accessor layer **first**, in the first six hours, before any feature exists to leak. Make it the only way to reach `Review`. |
| `docker compose up` is never tested cold | Medium | Fatal to 20% | Test from a clean clone with the network disabled, on a timer, twice: hour 48 and hour 66. |
| Acceptance suite first run is Sunday afternoon | Low (we control this) | Recoverable | Run it at hour 12, 24, 36, 48, 60 continuously. The checker takes 10 seconds. Never discover a failure at hour 67. |
| Normalization is hand-waved to save time | Medium | Loses 25% and the $100 prize | The math is analysis on data we already have, not new engineering. Budget it as writing time, protect it in the plan (`08`). |
| Docs written last, at hour 68, badly | **High** | Loses 20% + 15% | Docs are written *during* the build from this bible, not after. `05`, `06`, `07` are already the drafts. |
| Demo video not recorded | Medium | Loses part of 20%, damages impression | Slot it at hour 62, not "if there is time." Record against a scripted storyboard in `08`. |
| Feature is claimed but never exercised | Medium | Penalised as inflation | Definition of done for every feature: exercised once against the running portal, plus a test. No exceptions. |

**The demotion rule, stated once, in advance, so it is not a negotiation later:**

> At each gate in `08`, if the *next* tier is not verified green, we demote the
> claim in `.dogfood.toml` to the verified tier and document the gap in
> `README.md`. No exceptions, no "but it nearly works," no shipping a claim we
> have not seen pass.

This costs us at most half a tier of score in the worst case and protects the
entire 40% criterion plus our credibility with a panel that will read the repo
carefully. It is also, conveniently, exactly the behaviour they say they reward.

---

## 8. The demo video as a scoring artefact

Five minutes, one full lifecycle: create → submit → judge → publish. The site
lists it as a required deliverable, and it is the only deliverable a judge
watches instead of reading.

The five minutes are not a UI tour. They are an argument:

1. **0:00–0:30** — `docker compose up` from a clean clone, network off, ending
   on a seeded portal and the printed credentials. Proves 20% in thirty seconds.
2. **0:30–1:30** — create an event, tracks, prizes, a weighted rubric. Proves
   T1 and the thing the market leader cannot do.
3. **1:30–2:30** — team, invite link, draft submission, edit, deadline refusal.
   Proves the deadline *holds*, and we show the refusal deliberately.
4. **2:30–4:00** — the money shot. A judge scores. Then **we `curl` judge B
   against judge A's scores on camera and show the 403.** This is the moment
   that separates us from every other submission, because it is the check the
   spec calls out by name as the one that costs the most points.
5. **4:00–5:00** — normalization proof on real fixture data: raw σ, normalized
   σ, ranking deltas. Then publish results, export CSV, show the audit trail.

Step 4 is non-negotiable and must be a real terminal, not a screenshot. The
brief's own figure shows a judge's `curl` being refused. Showing ours is the
most persuasive thirty seconds available to us.

---

## 9. Success criteria at freeze

**Updated after the H+0 decisions.** We build to T4. The *claim* is decided at
four scheduled breaks (`08` §1b), not at kickoff. Nothing below the line is
worth an hour above the line.

**Must be true (blocking):**
- `docker compose up` from a clean clone, network off, seeded portal on `:8080`.
- `run.py` reports all seven checks PASS.
- `.dogfood.toml` claims exactly what the report verifies.
- Peer-score probe returns 403 as a raw `curl`, captured in the repo as evidence.
- **`manage.py isolation_proof` prints the FIG. 02 matrix with a status code per
  cell and exits 0.**
- Gallery shows fixture projects on page one, unauthenticated.
- Deadline refuses a late submission with the fixture's own close date.
- Organizer CSV export returns a comma-bearing header row.
- MIT `LICENSE`, `README.md`, `ARCHITECTURE.md`, `DATA-MODEL.md`, `JUDGING.md`.
- `acceptance-report.txt` committed, real output, whatever it says.
- Demo video recorded and linked.
- **The slippage ledger filled in honestly at all four breaks.**

**Should be true (order of preference if time remains):**
- Normalization implemented, documented, and proven on fixture data — **including
  the detectability analysis, which is what makes it a proof.**
- Audit trail an organizer can read without a database client, **hash-chained**.
- Full FIG. 02 role matrix enforced and proven, including the untested cells.
- OpenAPI spec published and covering every UI action.
- Bulk import and export — the escape hatch, with a round-trip **property test**.
- T3 public layer complete and honestly claimed, **including the anti-abuse
  influence report**.
- Threat model written, including the attacks we did not stop.

**Nice (only if everything above is green):**
- Signed, publicly verifiable judge participation records — **now firmly in T4,
  not "nice." See `08` §8 item 2; it is the block's best artefact.**
- `results_hash` + the chain head in the signed record. **Also firmly in.**
- Embeddable gallery widget.
- Pairwise Bradley-Terry — Break 4 candidate only.
- Ranked Borda ballot — Break 4 candidate only.

**Cut at H+0, and the README says so in one sentence:**
- **Webhook delivery.** Models, a 501 stub, and audit events ship. Delivery,
  retries and HMAC verification do not. Zero points on all four criteria, and the
  SSRF work is a real bug class under time pressure.

**Explicitly last, always:** anything that would require breaking a "must."
