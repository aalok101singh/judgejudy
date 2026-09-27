# 02 · Requirements Traceability

**Purpose:** every demand in the brief, as an ID, with the acceptance check that
verifies it (or the explicit statement that nothing verifies it), our
implementation intent, the evidence artefact a judge reads, and the risk.

This document exists so that "did we miss something?" is answerable by reading
one table instead of re-reading the website at hour 60.

**Columns**
- **ID** — stable reference. Use it in commit messages and in the code as a comment where relevant.
- **Req** — the demand, in the brief's own terms.
- **Check** — the `run.py` assertion that verifies it, or `—` (human/judge verified only).
- **Evidence** — the artefact a judge reads to confirm it.
- **Risk** — H / M / L, and the one-word failure mode.

Legend for **Check**: `T1-1`…`T1-3` and `T2-4`…`T2-7` are the seven acceptance
checks, numbered in `03` and in the order `run.py` issues them.

---

## 1. T1 · Core  *(the gate — clear this or we are not scored)*

| ID | Req | Check | Evidence | Risk |
|---|---|---|---|---|
| REQ-T1-01 | Authentication and sessions | — | Login/register flow; `README` credentials table | L |
| REQ-T1-02 | Real role model: visitor, participant, judge, organizer, admin | — | `05` §3 role bindings; five seeded identities | M — role-as-a-column on `User` cannot express "judge on trk_03 only" |
| REQ-T1-03 | Event creation with configurable dates, tracks and prizes | — | Organizer event editor; `DATA-MODEL.md` | L |
| REQ-T1-04 | Team formation by invite link | — | Invite flow + redeem path; test in `tests/` | M — invite tokens leak team membership |
| REQ-T1-05 | Project submission with draft-and-edit until the deadline | — | Draft/publish states in `05` §4 | M — draft leaking into the public gallery |
| REQ-T1-06 | **Deadline enforcement that actually holds** | **T1-3** | `acceptance-report.txt`; `curl` transcript in repo | **H — the one thing the checker actually tests about the deadline** |
| REQ-T1-07 | Public gallery with search and filter | **T1-1**, **T1-2** | Gallery UI; FTS search; track/tag filters | **H — see `03` §4.2, the first-three-titles trap** |

**Acceptance checks T1-1 … T1-3, restated:**
- **T1-1** `GET {gallery}` no auth header → `200`.
- **T1-2** `GET {gallery}` → a fixture project title appears in the body.
- **T1-3** `POST {submit}` as `participant` → `4xx`.

**Notes that matter more than they look:**
- REQ-T1-06 is verified by *not* faking the date. The spec says plainly: *"Seed
  with the fixture's close date rather than one of your own and this passes on
  the first try."* The fixture's `submissions_close` is `2026-03-01T18:00:00Z`,
  which is in the past relative to the event. Seeding honestly means the portal
  is born closed. We must therefore also ship a way for an organizer to *open* a
  new event so the product is not just permanently refusing submissions.
- REQ-T1-07's search and filter are **not** verified by the checker. They are
  verified by a judge looking at the gallery. Build them well but not first.

---

## 2. T2 · Judging  *(where the real engineering starts; 25% of score lives here)*

| ID | Req | Check | Evidence | Risk |
|---|---|---|---|---|
| REQ-T2-01 | Judge invitation and assignment, by batch or algorithmically | — | `06` §2; one flow over all tracks; min-max capacity search; min-cut infeasibility certificate with arithmetic remedies | M — nine of thirty fixture judges are dual-track, so per-track flows are wrong |
| REQ-T2-02 | **Weighted**, organizer-configurable scoring rubric | — | Rubric editor; weights in `JUDGING.md`; `weight_applied` snapshotted | **H — the market leader cannot do this. It is our differentiator.** |
| REQ-T2-03 | **Role isolation enforced in the backend** | **T2-5**, **T2-6** | `05` §6 scoped accessors; `05` §6a scope receipt; `05` §6b `manage.py isolation_proof` + four Hypothesis invariants; `curl` transcript | **H — the single most-cited failure mode in the entire brief** |
| REQ-T2-04 | Live progress dashboard: who has not started | — | `06` §5.1, ordered so every row ends in a task: unfixable projects, sole-cover judges, long tail, per-judge, severity-with-p, percentage last | L |
| REQ-T2-05 | Cross-judge normalization, method documented and defended | — | `06` §3–§4; `JUDGING.md`; `docs/normalization-proof.{md,csv}`, `sensitivity.csv`, `feasibility-report.md` — all **generated** | **H — the $100 prize and most of 25%** |
| REQ-T2-06 | CSV export at every stage | **T2-7** | `05` §8 seven named exports, streamed; plus canonical JSON + signed archive | M — "at every stage" means registration, teams, submissions, assignments, scores, results, votes |

**Acceptance checks T2-4 … T2-7, restated:**
- **T2-4** `GET {judge_scores}` as `judge_a` → `200`.
- **T2-5** `GET {peer_scores}` as `judge_b` → `401` or `403`. **The one that matters.**
- **T2-6** `GET {judge_scores}` as `participant` → `401` or `403`.
- **T2-7** `GET {csv_export}` as `organizer` → `200` and a comma in line 1.

**Three subtleties the website's own matrix forces and the checker does not:**
- **T2-03 extends to tracks.** A judge on `trk_03` reading a `trk_07` review is a
  leak of exactly the same kind. The checker will never test it. Enforce anyway.
- **T2-03 extends to aggregates.** FIG. 02 marks "aggregate" ✗ for judges. If a
  judge can read the leaderboard mid-window, peer scores are one inference away.
  Lock aggregates to organizers until publication.
- **T2-05 is invisible to the checker.** A portal with zero normalization passes
  all seven checks. This is precisely why it is worth doing: it is scored
  entirely by human judgement of whether we handled the judge who marks
  everything the same. The fixture contains one.

---

## 3. T3 · Public

| ID | Req | Check | Evidence | Risk |
|---|---|---|---|---|
| REQ-T3-01 | Community voting, configurable access: open link, email-gated, or authenticated | — | Three modes in `05` §7; organizer toggle | M — open-link mode plus no rate limit is a free-for-all |
| REQ-T3-02 | Comments on gallery projects | — | Comment model, moderation affordance | L — XSS surface, see `07` |
| REQ-T3-03 | Results hidden from everyone but organizers during the voting window | — | Window state in `05` §3; a test asserting 403 for participants | **H — leaks the judging outcome and skews voting** |
| REQ-T3-04 | Randomised project ordering on ballots | — | Seeded permutation per ballot, stable across requests; **claim is zero-*mean*, not zero**; mirrored-order consistency + binomial test published **with its sample size** | M — must be per-voter stable, not per-request |
| REQ-T3-05 | Anti-abuse: rate limits, duplicate detection, audit trail | — | `07` in full; **published influence report** before results (distinct identities, first-preference share, vote-mass Gini, flagged identities) | M — see the "honest list" standard in `07` §7 |

**Notes.** T3 is entirely unverified by the checker. Every point here is a
human judgement. The brief's own framing — *"Community voting is universally
conceded to be gameable"* — means a T3 that engages the problem honestly beats
a T3 that adds a like button.

**Two things this section got wrong and now says correctly, and both are the
kind of thing a knowledgeable reviewer would catch in one search:**

- **Quadratic voting is not Sybil resistance.** The mechanism (Lalley & Weyl
  2011) is truthful because there is a quadratic **cost on acquiring
  influence**; with free identity acquisition, quadratic voting is
  Sybil-vulnerable (Bennett 2025) and in fact *every* nontrivial weighting rule
  is, with Sybil-adjusted power growing at least linearly (arXiv:2605.18990).
  `06` §6.1 states the boundary precisely instead of claiming the mechanism.
- **Randomising order makes position bias zero-*mean*, not zero.** Averaging
  over all permutations does not recover the underlying preference; it just
  randomises who benefits (arXiv:2506.14092). And at a real event's size
  (100–1,000 votes) **we cannot measure a 5-point side preference at all** —
  that needs ~4,556 mirrored comparisons — so we publish the measurement *and
  the sample size* rather than a percentage we cannot defend. `06` §6.3.

---

## 4. T4 · Stretch

| ID | Req | Check | Evidence | Risk |
|---|---|---|---|---|
| REQ-T4-01 | REST API and webhooks covering **every action the UI can take** | — | OpenAPI spec; `05` §9. **Webhooks CUT at H+0** — models + 501 stub + audit events ship; delivery, retries and signature verification do not, and `README.md` says so | **H — "every action" is the whole requirement. A partial API is a partial T4.** The API half is structural on DRF; the webhook half is the cut, and it is a zero-point cut |
| REQ-T4-02 | Certificate and record generation | — | Render the existing signed record as a PDF. **Cut from 1.5h to 30min** — free marginal cost once the signing primitive exists, and near-zero scored value | L |
| REQ-T4-03 | Signed, publicly verifiable judge participation records | — | **in-toto Statement v1 inside a DSSE envelope**, Ed25519 (RFC 8032) via `cryptography`, keys on their own volume, public verification endpoint + offline CLI verifier, **exposing no scores** | M — `06` §6 style conformance, not invented PKI. **Two traps:** PAE `len()` is in bytes not characters; test one hardcoded vector |
| REQ-T4-04 | Embeddable gallery widget | — | One `<script>` tag, no build step for consumers | L |
| REQ-T4-05 | Bulk import and export — the escape hatch | — | `05` §8: 7 CSVs + canonical JSON + signed archive; byte-identity property test **including `source_key`**, driven by a Hypothesis `world()` strategy; unknown columns preserved in a passthrough table | **M — "a platform you cannot leave is a trap"** |

**REQ-T4-01 is the real T4.** Because we are on DRF, every viewset we write
*is* an API endpoint, and the "every action in the UI" requirement becomes a
property of the architecture rather than a second implementation. That is a
large part of why the stack was chosen. The discipline it demands: **do not
write a UI action that is not also a viewset action.** No bespoke form-post
endpoints. If it mutates state, it goes through the API. **Webhooks are CUT**
(`08` §13): zero points on all four criteria, and the SSRF mitigation (P-8) is
a real bug class written from scratch under time pressure. The schema ships; the
delivery machinery does not, and the README says so in one sentence.

**REQ-T4-05 is under-rated.** It is filed under stretch, but the sentence that
gives it weight is in Adoptability: *"A migration path in and out, because a
platform you cannot leave is a trap."* Full round-trip import/export of every
table, documented, is the cheapest goodwill available. Do it even if other T4
items slip. **The round-trip property test is the product, not a test** — it is
a command an organizer can run.

**REQ-T4-03 is the best "steal it" candidate in T4,** and the second research
pass made it both cheaper and stronger. Three changes:

1. **DSSE instead of "a signature over the canonical form."** The envelope spec
   says implementations *should avoid depending on canonicalization for
   security* and *should not require the verifier to parse the payload before
   verifying.* We sign **bytes**, so no third party has to reimplement our JSON
   canonicalisation to check us. That eliminates an entire class of
   interoperability bug for about the same code, and means `cosign` can verify
   our records with tooling that already exists.
2. **Keys on a volume separate from the database.** Our own hour-66 checklist
   runs `docker compose down -v` twice; keys on the DB volume would invalidate
   every issued record, including ones quoted in the README and the demo video.
3. **The audit chain head goes *into* the record.** One column, and it is what
   makes the signed records survive the organizer's own database being
   untrusted: N parties outside the trust boundary hold a copy of the hash the
   log must produce. **We deliberately did not build a Merkle transparency log**
   — CT's value is witnessing and we have no witness, so a root we compute
   ourselves proves only what the 30-line hash chain already proves, for three
   times the code.

---

## 5. Rules — nine items, all binary

| ID | Rule | How we satisfy it | Risk |
|---|---|---|---|
| REQ-RULE-01 | Open source, OSI-approved; MIT or Apache-2.0 preferred; no assignment, no CLA | `LICENSE` = MIT, from commit one. Nothing to sign. | L |
| REQ-RULE-02 | One command to running, offline, no external service | One image, one service, SQLite file, seeds on migrate. Verified from a clean clone with the network off. | **H — the single most-tested rule** |
| REQ-RULE-03 | Clear T1 or not judged | T1 is the first six hours. See `08`. | L |
| REQ-RULE-04 | New code only, written in the window | New Django project created at kickoff. Libraries and AI are explicitly fine. | M — do not clone an existing platform; see zero #09 |
| REQ-RULE-05 | No hosted-service dependency | No outbound HTTP in any request path. No env var required to boot. | **H — verify with a grep before freeze** |
| REQ-RULE-06 | Claim tiers honestly | `.dogfood.toml` mirrors the report. Demotion gates in `08`. | **H — the only documented way to lose points for free** |
| REQ-RULE-07 | Team size 1–4 | Solo. Permitted. | L |
| REQ-RULE-08 | Source public, team reachable | Public repo; a contact address in the README. | L |
| REQ-RULE-09 | AI tools expected; judged on whether it holds up and whether someone can defend the schema | Not scored for AI use. Scored for `ARCHITECTURE.md` / `DATA-MODEL.md` / `JUDGING.md` quality. This bible is the defence. | **H — quality of writing is the deliverable** |

**REQ-RULE-04 deserves a note, because it is the one rule teams misread.** It
does **not** mean "no framework" — Django, DRF and drf-spectacular are fine. It
means we do not arrive with a finished portal or fork an existing one. The
forbidden thing is *"a rewrite of an existing open-source platform with the
name changed"* (zero #09). We are writing a new application on top of
libraries, which is unambiguously allowed.

---

## 6. Deliverables — the eight files and one video

| ID | Deliverable | Source for it | Owner hours | Risk |
|---|---|---|---|---|
| REQ-DEL-01 | `.dogfood.toml` | `03` §3 — ~10 lines, generated from seed output | 0.2 | L |
| REQ-DEL-02 | `acceptance-report.txt` — real `run.py` output, whatever it says | `run.py` redirection. **Never hand-edited.** | 0.1 | **H — a fabricated report is worse than a failing one** |
| REQ-DEL-03 | `docker-compose.yml` — one command to a seeded, working portal | `01` §6 | 0.5 | **H** |
| REQ-DEL-04 | `README.md` — what it does, how to run, **honest limits** | `01` §9, `08` cut ledger | 1.5 | **H** |
| REQ-DEL-05 | `ARCHITECTURE.md` — the shape of the system and why | `01` §6, `05`, `07` | 2 | M |
| REQ-DEL-06 | `DATA-MODEL.md` — schema, plus import and export paths | `05` in full | 2 | M |
| REQ-DEL-07 | `JUDGING.md` — assignment, scoring maths, normalization, **defended** | `06` in full | 3 | **H — highest doc value** |
| REQ-DEL-08 | `LICENSE` — MIT or Apache-2.0 | — | 0.1 | L |
| REQ-DEL-09 | `src/` — all code written this weekend | — | — | L |
| REQ-DEL-10 | `tests/` — our own tests, beyond the acceptance suite | `08` §12 | 5 | M — low scoring weight, high debugging value. The **proof's own numbers are asserted in CI**, so a refactor that silently changes the method fails a test instead of quietly weakening the document |
| REQ-DEL-11 | 5-minute demo video: create, submit, judge, publish | `01` §8 storyboard | 2 | **H — never recorded if left to the end** |

**On REQ-DEL-02, stated once and unambiguously:** the report is generated by
redirecting `run.py` output. It is never edited, never curated, never
regenerated on a machine other than the one running the portal. If it contains
FAIL lines, it ships with FAIL lines and `README.md` explains them. The brief
says this three times and the checker is the same program the panel runs, so
there is no scenario in which a doctored report helps.

**Documentation is 5.5 hours of the 69 and carries 35% plus the whole
credibility surface.** In a 69-hour solo build that is the most under-budgeted
item in any plan. `08` interleaves it with the build rather than deferring it,
because these files *are* the drafts.

---

## 7. Scoring criteria — what each one reads

| ID | Criterion | Weight | What the reader opens first | Our doc |
|---|---|---|---|---|
| REQ-SCORE-01 | Tier Completion & Correctness | 40% | `acceptance-report.txt` | `03` |
| REQ-SCORE-02 | Judging Integrity | 25% | `JUDGING.md`, then the isolation code | `06`, `07` |
| REQ-SCORE-03 | Adoptability & Operability | 20% | `README.md`, then `docker compose up` | `01` §6, `05` §8 |
| REQ-SCORE-04 | Code Quality & Innovation | 15% | the schema, then the one stealable decision | `05`, `01` §4 |

**Two of these are read in a specific order that we control.** A judge scoring
Tier Completion opens the acceptance report first, so it is the first line of
the repo's visible surface. A judge scoring Judging Integrity opens `JUDGING.md`
first, so it must open with a claim and a table, not with background.

---

## 8. Bonus challenges — all four as options

Bonuses **do not change the score**. They break ties and decide the $100 Best
Judging Engine prize. Costed in `06` §8; **gate 3 at hour 62** in `08`.

| ID | Bonus | Difficulty | Points | Feeds criterion | Decision |
|---|---|---|---|---|---|
| REQ-BONUS-01 | Normalization Proof | Hard | +5 | Judging Integrity | **Build first, protected, H+56→H+62.** The second research pass made it *cheaper to be right and stronger to present*: detectability first, then the held-out harness, then recovery. Also the $100 prize artefact |
| REQ-BONUS-02 | Pairwise Mode (Bradley-Terry) | Hard | +5 | Judging Integrity, Innovation | **Last** — pure upside only. **New reason, measured:** the fixture's comparison graph is one connected component (71 nodes) and all 8 per-track graphs are connected, so the disconnected-graph caveat **will not fire and cannot be demonstrated on the published data.** Do not spend hours hardening an undemoable path |
| REQ-BONUS-03 | Threat Model | Medium | +3 | Integrity + Quality | **Second** — near-free, feeds two criteria. Second pass made it better: the quadratic-voting claim corrected, the timing residual quantified rather than admitted, the hash chain added |
| REQ-BONUS-04 | API First (OpenAPI) | Medium | +3 | Adoptability | **Third** — mostly free on DRF |

**"One done properly beats four started."** Our reading, after the second pass:
a normalization proof that **measures whether there was an effect to remove,
proves the method works out of sample, recovers a known injected effect, and
publishes its own sensitivity curves** is worth more than four checkbox bonuses.
But the API is nearly free on our stack, so the realistic plan is *three* —
Normalization Proof, Threat Model, API First — and Pairwise only as upside.

**The one sentence that defends it, and it changed:**

> On DRF the API is an architectural property we inherit rather than a project
> we fund. And the normalization proof is no longer "a method plus a σ number" —
> it is a **null result with a p-value, a power analysis, an out-of-sample
> validation, a parameter-recovery experiment, and a disclosure of the constants
> we chose not to optimise.** That is not something a team can produce in a
> weekend by trying harder; it requires being willing to publish the null.

---

## 9. Out of scope — the nine zero-scoring items

Full text and guards in `01` §3. Cross-referenced here so the traceability
table is complete:

| ID | Zero-scoring item | Guard |
|---|---|---|
| REQ-ZERO-01 | Design mockups or hardcoded-data frontend | `compose down -v && up` must repopulate |
| REQ-ZERO-02 | Needs cloud account, hosted DB, or auth provider | grep for outbound hosts before freeze; zero required env vars |
| REQ-ZERO-03 | Auth demo that stops at the login screen | five real role flows |
| REQ-ZERO-04 | Gallery with no judging, or judging with no gallery | both built and linked; video walks both |
| REQ-ZERO-05 | Frontend-only role checks | `curl` transcript committed as evidence |
| REQ-ZERO-06 | LLM dump, no architecture doc, undefendable schema | four documents written to a standard, not generated |
| REQ-ZERO-07 | Closed source / non-OSI license | MIT |
| REQ-ZERO-08 | Custom hardware, GUI toolchains, proprietary services | laptop and Docker only |
| REQ-ZERO-09 | Rewrite of an existing platform, renamed | new application on libraries |

---

## 10. Assumptions log

Every place we had to interpret something, and what we decided. **Anything in
this table that a Discord answer contradicts gets updated in the same hour.**
The spec's own instruction: *"An ambiguity found on Wednesday is a fixed spec.
The same ambiguity found on Saturday is three teams building three different
things."*

| # | Ambiguity | Our reading | Severity | Resolve by |
|---|---|---|---|---|
| A-01 | Does "results hidden" mean hidden from participants only, or from the public gallery too? | Hidden from everyone except organizers and admins, for the whole voting window, per the site wording. Public ranking endpoints return 403 in that state. | Low | Build organizer-only; the strict reading is a superset |
| A-02 | "CSV export at every stage" — which stages? | Seven named exports: registrations, teams, submissions, assignments, raw scores, normalized results, public votes. | Med | Cheap to satisfy fully |
| ~~A-03~~ | ~~Are judges assigned per track, or globally?~~ | **SELF-ANSWERED.** Track-scoped. The fixture settles it: 30 judges, **0 off-track scores** in 126 rows. Global assignment would let a judge see another track, which is the leak `01` §2.1 calls out and the checker never tests | **CLOSED** | Closed 2026-09-27. There is no reading under which we assign globally |
| A-04 | Must a project belong to exactly one track? | Yes, `CheckConstraint`, with an `other` track option for untracked submissions. Fixture agrees: every project has exactly one track. | Low | Self-evident from data |
| ~~A-05~~ | ~~Can a team have more than one project?~~ | **SELF-ANSWERED by the fixture.** Yes — `tm_07` has `prj_07` and `prj_41`, identical title and `repo_url`, 13h28m apart. One-to-many on `Project`, results aggregate by team | **CLOSED** | Closed 2026-09-27. The fixture is authoritative; see `04` §3.3 |
| A-06 | Is the duplicate pair one project with a revision, or two projects? | Store two `Project` rows plus an explicit `supersedes` link, so the raw fixture stays lossless and the semantics are explicit. Aggregate by team. | Med | Our design, defensible either way |
| A-07 | Does the checker need a login flow at all? | No — it never logs in. But the product needs one, and T1 requires it. | Low | Settled by `run.py` |
| A-08 | Is `admin` a role or a flag? | A role binding like the others, seeded, and a separate `is_staff` for Django admin. Keeping them separate avoids Django-admin privilege leaking into the product role model. | Med | Our design |
| ~~A-09~~ | ~~Normalization: over judges, or over projects?~~ | **SELF-ANSWERED.** **Judges only.** No second pass over projects: 8 of 41 projects have 2 reviews, and shrinking those toward a project mean estimated from those same 2 reviews would move them toward nothing | **CLOSED** | Closed 2026-09-27. This was never an open question — it *is* the deliverable, and `06` §4.3e now explains why we do not also fit the project facet (measured: held-out RMSE 0.9097 vs 0.6753) |
| ~~A-10~~ | ~~Should we claim T4 given the checker only verifies T1/T2?~~ | **Superseded by A-24** and by the four-break protocol (`08` §1b). We build T4; **the claim is decided at H+54**, not at kickoff, and the README states which check covers which tier | **CLOSED** | Closed 2026-09-27. The strategy question is settled by process; only the *factual* question (is the ceiling final?) is still open, and that is A-24 in the master message |
| A-11 | Webhook delivery semantics — at-least-once, retries, signatures? | At-least-once, exponential backoff, HMAC-signed payloads, per-endpoint secret, visible delivery log. | Med | Our design, documented |
| A-12 | Do certificates need to be cryptographically verifiable? | Not required. Make them verifiable anyway via the same Ed25519 primitive as REQ-T4-03, at near-zero marginal cost. | Low | Free |
| A-13 | ~~**Which statistic is the site's illustrative σ = 0.94?**~~ | ✅ **ANSWERED.** **Confirmed a bug in the website description, most likely a cosmetic landing line not in `/spec`. Homepage corrected to σ = 0.42 = stdev of per-judge means, and we were asked to build the proof against the actual fixture values.** Our 0.4323 is the same number to 2dp. See `06` §4.4c and `README.md` § Findings we contributed upstream (U-1) | **CLOSED — became a contribution** | **Closed 2026-09-27.** Consequence: the comparison is now available and we are entering it, not declining it |
| A-25 | ~~**Is the normalized figure now 0.31, and is it a target or illustrative?**~~ | **SELF-ANSWERED.** It changes nothing we publish: we report our own numbers with definitions either way. We treat it as illustrative, note that three global standardizations reproduce it (0.3174 / 0.3240 / 0.3301), and **do not tune to it** — `06` §4.4b. Raised in the master message as an *optional* note with an explicit offer to drop it | **CLOSED** | Closed 2026-09-27. Kept in the message because it is a finding worth sharing, not a question |
| A-14 | ~~**Does the Normalization Proof bonus expect a *visible* effect, or a demonstration of correctness?**~~ | **SELF-ANSWERED — we do both, so it was never a question.** The `k` curve gives 0.4323 → 0.2547; the held-out test gives 0.7952 → 0.6753 with a paired-bootstrap CI excluding zero. Whichever the bonus wants, we have it. Asking would have been asking permission to do less | **CLOSED** | Closed 2026-09-27 |
| A-15 | Is `reviews_per_project` event-level or per-track? | Per-track, nullable, inheriting from the event. Two fixture tracks are zero-slack at 3 and provably impossible at capacity 5, which a single integer cannot express. Stated in the master message as a decision, because the data makes the choice and there is no alternative worth asking about | **High** | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| ~~A-16~~ | ~~Are synthetic / simulated data permitted in the proof artefact, provided they are labelled?~~ | **ANSWERED — YES, with a condition, and it is met by construction.** "Yes, synthetic data is fine for validation as long as the proof also runs on the real fixtures. Showing it recovers a known effect is exactly the kind of rigour the bonus is looking for." Three of the proof's four components are computed on the published 126 reviews with nothing simulated; the recovery experiment is a *validation* of the method, not a claim about the data | **CLOSED — positive** | Closed 2026-09-27. Condition mapped to a data source per component in `06` §4.4a, and a real-fixture-only artefact `docs/REAL-FIXTURE-RESULTS.md` now exists so the condition can be read on its own (`06` §4.4d). See `README.md` U-4 and U-5 |
| A-17 | Is the normalized ranking expected per **project**, per **team**, or per **submission**? | Team, latest-wins, with both rows retained and a `counted` flag in the export so the exclusion is auditable and reversible. The fixture's duplicate submission makes any other reading wrong, so it is stated in the master message rather than asked | Med | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| A-18 | Must bulk import be **symmetric** with export (round-trippable), or is one-way ingestion of the `fixtures.json` shape enough? | Both, plus a byte-identity property test over a canonical JSON form with a Hypothesis `world()` strategy | Med | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| A-19 | Do verifiable judge records require a **published public-key directory**, or is a self-certifying record acceptable? | Self-certifying: public key inside the record plus a published `judge-keys.json` keyring. Standard, sufficient, verifiable offline. The alternative is ~1h for a discovery endpoint we do not need | Low | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| A-20 | Is a participation record issued **per event** or per **portal lifetime**? | Per event, per the `JudgeCredential` schema | Med | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| A-21 | What is the intended behaviour for a **draft** after the deadline? | New submissions refused (403); an existing draft still savable, never submittable. A platform that freezes every write fails an organizer fixing a typo | Med | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| A-22 | Is a judge who is **also a team member** hard-blocked, or overridable with a recorded justification? | Hard-blocked in assignment eligibility **and** re-checked at review submission | Med | **Master message, as a decision to correct** — not a question. "Fine" answers it. See `DISCORD-QUESTIONS.md` |
| A-23 | Are the four bonuses graded **independently** or as a **portfolio**? | **Dropped — it would not change a line of code.** The normalization proof ships whether the bonuses are graded independently or as a portfolio, so there is nothing to decide | Med | **Dropped — it would not change a line of code.** The proof ships either way |
| ~~A-24~~ | ~~Will a *fuller* acceptance checker arrive, or is the prefix-lock to T1/T2 final?~~ | **DROPPED by reasoning — it fails the filter on both counts.** (1) The answer is already in the published material: `run.py` is a shared suite, so if more checks were coming they would be published, and `spec.md` line 303 says the checker does not look at HTML, framework, database, layout or history — it verifies 6 of 60 demands and is a gate, not a ceiling. (2) Nothing branches on it: we build T4, claim T4 and explain the prefix-lock either way. | **DROPPED — answered from the spec** | Dropped 2026-09-27. The underlying concern is real and is handled in the README instead: one plain paragraph stating the prefix-lock mechanic, the unedited `acceptance-report.txt`, and a separately labelled extended test suite as the evidence for the T3/T4 demands the checker does not cover (`03` §5, `08` §6). No question spent on a non-question |

**All open questions are consolidated into ONE Discord message**
(`DISCORD-QUESTIONS.md`): two real questions, plus seven decisions we have
already made — where "fine" from the organizers settles seven things, and they
only need to name the ones that are wrong. **Nine further ambiguities were
dropped by reasoning, not by forgetting** — the table in that file gives the
reason for each, which is the part that matters at hour 50 when someone wants
to re-open one.

**The two that remain genuinely open, and why only two:**

| # | Ambiguity | Why it survives | Cost of being wrong |
|---|---|---|---|
| **A-24** | Is the `run.py` T1/T2 ceiling final? | A fuller checker arriving at freeze is a failure we cannot recover from, and it is the only item here that could cost a tier on arrival | **High — 40%** |
| **A-16** | Is labelled synthetic data allowed in the proof artefact? | It decides whether the *recovery* experiment ships — the part that proves correctness rather than absence of harm. Everything else in the proof is unaffected either way | **Med — the $100 prize artefact** |

**Nine dropped by reasoning** (per-team results, per-track target, proof framing,
0.31-as-target, round-trip import, key directory, per-event records, drafts
after the deadline, judges on their own team) plus one moot (webhooks, cut).
**A-13 is closed and became a contribution** (`README.md` § Findings we
contributed upstream, U-1): we found a discrepancy in the published spec,
reported it with evidence, and it was corrected. **The remaining ambiguity is not
the number, it is what the number is a measurement of** — which is a better
question and a more valuable answer.

---

## 11. Coverage check

| Category | Demands | Traced | Verified by checker | Human-verified only |
|---|---|---|---|---|
| T1 | 7 | 7 | 2 of 7 (T1-1, T1-2) + deadline via T1-3 | 5 |
| T2 | 6 | 6 | 4 of 6 (T2-4…T2-7) | 2 (rubric weighting, normalization) |
| T3 | 5 | 5 | 0 | 5 |
| T4 | 5 | 5 | 0 | 5 |
| Rules | 9 | 9 | 0 | 9 |
| Deliverables | 11 | 11 | — | 11 |
| Scoring | 4 | 4 | — | 4 |
| Bonuses | 4 | 4 | 0 | 4 |
| Zero-scoring | 9 | 9 | — | — |
| **Total** | **60** | **60** | **6** | **54** |

**The number at the bottom right is the strategic finding of this entire
document.** The acceptance suite verifies **6 of 60 demands**. It is a
disqualification gate and a credibility signal, not a score. Ninety percent of
what earns the 40% — and effectively all of the 25%, 20% and 15% — is read by
a human with a rubric. **Build for the judge, not for the checker.** The
checker's job is to keep a dishonest team from winning; ours is to be
undeniably honest and unmistakably deep.
