<div align="center">

<img src="docs/logo.svg" width="128" alt="Judge Judy — a balance scale with the beam level">

# Judge Judy

### The bench that keeps its own records.

**A self-hostable submission and judging platform for hackathons.**
Submissions, a defensible assignment, isolated judging, public voting, and a
published verdict you can prove you did not change afterwards.

**One command. No network. No cloud account. No hosted database. No API key.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB.svg)](https://www.python.org/)
[![Django 5.2 LTS](https://img.shields.io/badge/Django-5.2-092E20.svg)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/docker-29.6.2-2496ED.svg)](https://www.docker.com/)
[![No network required](https://img.shields.io/badge/network-none%20required-8B0000.svg)](#operating-it)
[![T1 + T2 verified](https://img.shields.io/badge/acceptance-7%2F7%20PASS-2E7D32.svg)](#for-reviewers)

</div>

---

```bash
docker compose up
```

That is the whole installation. Open <http://localhost:8080>, and the container
comes up with an **empty database** — deliberately, because that is what leaves the
first-run wizard open for your own event.

**To run your own hackathon**, open <http://localhost:8080/setup/>. Prefer to look
at a finished example first? See [the demo is opt-in](#the-demo-is-opt-in).

---

## Why Judge Judy

Three things this project is actually about, in the order they mattered.

**1. A judge never reads another's work.** A judging portal is only worth running
if that is a property of the *query layer* rather than of each view — so there is
exactly one way to read a review, it takes an actor, and a lint rule fails the
build on any other read, **including inside tests**. See
[what each role can see](#what-each-role-can-see).

**2. A refusal is a refusal.** Every denial is a **403 with an empty body — never
a redirect.** This sounds pedantic and is the single most important behaviour in
the system, because a client that follows redirects gets a 200 from a login page.
A portal that "protects" a score by bouncing you to sign-in passes every manual
test and leaks to every automated one.

**3. The verdict is provable.** You can take the entire database away and bring it
back, byte-identical. You can hand judges signed records and detect equivocation
*from outside* the organizer's database. And you can re-derive the published hash
from the raw scores yourself. See
[proof you did not change the numbers after publishing](#proof-you-did-not-change-the-numbers-after-publishing).

**And it runs offline.** `just prove-offline` starts the image with
`--network none` and probes it, so the claim is *measured* rather than asserted.

---

## Rules of order

Judge Judy has five rules, and every refusal in the portal traces back to one of
them.

**I. The bench does not read each other's papers.**
Isolation lives in the data-access layer, not in the views, so a view *cannot*
forget to apply it. The lint rule is not advisory: it fails the build on an
unscoped read, including in a test.

**II. A refusal is final, visible, and empty.**
A bare 403. No login page, no redirect, no helpful error page that confirms the
resource exists. A redirect returns 200 to any client that follows it, which
turns a correct refusal into a leak that still *looks* right in a browser.

**III. The record is append-only, and it cannot lie.**
Entries are hash-chained, deleting one raises, and **an entry is written in the
same transaction as the change it describes** — so the chain can never claim a
deadline moved when it did not.

**IV. The verdict carries its own seal.**
Publishing freezes a ranking, hashes it, mixes in a digest of the scores behind
it, and replicates the chain head into every judge's signed record. Equivocation
is detectable from outside the database.

**V. No cloud, no network, no key.**
A self-hosted tool that phones home is a tool you do not control. The offline
container is *proved*, and the widget is rendered with `--network none`.

### The vocabulary

Judge Judy brands its nouns in **prose only**. `results_state` is not renamed
`verdict`, and `for_actor` is not renamed something courtly — a reader who cannot
grep the identifier has been lied to. These names are how the documentation talks
about the parts:

| | What it is | Where |
|---|---|---|
| **The Roll** | Everyone in the event: organizers, judges, participants. Imported, never typed in by hand. | `invite`, `import_projects` |
| **The Gallery** | The public front page. Every project, server-rendered, no JS. | `/` |
| **The Bench** | The judges, and the console they work in. | `/judge/` |
| **The Docket** | The assignment plan, with the certificate that defends it. | `/organizer/assignments/` |
| **The Chambers** | The organizer's settings: windows, voting mode, publication. | `/organizer/settings/` |
| **The Ballot** | Public voting, one weighted opinion per project. | `/vote/` |
| **The Record** | The hash-chained audit trail. Append-only, and it cannot lie. | `/api/v1/audit` |
| **The Seal** | The published hash, its input digest, and the chain head. | `publish_results` |
| **The Verdict** | The ranking, labelled with how it was computed. | `/results/` |
| **The Archive** | The byte-identical export/import escape hatch. | `export_run`, `import_run` |

---

## Run your own hackathon

**This is the part that makes it a tool rather than a demo.** One deployment runs
one hackathon, and it starts from an empty database.

```bash
git clone https://github.com/aalok101singh/judgejudy.git
cd judgejudy
docker compose up
```

Then open <http://localhost:8080/setup/>. That page creates your hackathon: you,
your event, your dates, your tracks, and a starting rubric. It **refuses once an
event exists** — a bare 403, Rule II — so it cannot quietly add a second event to
a deployment. You are signed in as the organizer when it finishes.

### First-run answers

| Field | What it does |
|---|---|
| **Name, email, password** | You become the organizer, with an organizer binding. At least 12 characters. |
| **Event name** | Also becomes the URL slug. Any hackathon. |
| **Starts / submissions close / judging closes** | The windows every other page reads. Times are read in the server's timezone. |
| **Tracks** | One per line, optional. Judges are assigned per track and a project is only ever compared inside its own. |
| **Rubric** | Three criteria, weights summing to 1. Editable, and **locked** once a judge has scored — otherwise a leaderboard would move underneath the people who produced it. |

### Fill the Roll

Add judges and participants from the admin, or paste a roster — one email per
line:

```bash
docker compose exec portal python src/manage.py invite judges.txt --role judge
```

Each person gets an account with an **unusable password**, because this
deployment has no mail service on purpose — so they set one themselves at
`/login/`, or you set it for them:

```bash
docker compose exec portal python src/manage.py set_password judge@example.org
```

### Fill the Gallery

An organizer with forty projects should not fill in forty forms. Export them from
whatever you already used to collect them, and:

```bash
docker compose exec portal python src/manage.py import_projects entries.csv
```

```csv
source_key,title,summary,track,team,repo_url
ext_1,Glass Signal,A neat thing,General,Ada,https://example.org/glass
```

Only `title` and `track` are required; extra columns are **ignored rather than
rejected**, because a Google Forms export carries a dozen of them. It is
**idempotent** — a row with a `source_key` updates that project, so re-running
after adding three entries does not duplicate the first thirty. Each bad row is
**skipped and named with its line number** while the rest import, and an unknown
track is refused rather than invented: a track with no judges bound to it is an
event where some projects can never be judged. `--dry-run` reports without
writing.

**Nothing here needs the organizers' data.** There is no `fixtures.json` in the
path, no seed step, and no assumption about track names, rubric criteria, or how
many judges you have. `just check` runs against their fixture because that is the
acceptance gate; **nothing in the application requires it.**

### The demo is opt-in

A fresh `docker compose up` starts empty, which is what leaves `/setup/` open. If
the demo hackathon were seeded on every boot, every deployment would already have
an event and the wizard — whose entire authorisation is *"no event exists"* —
would be unreachable in the shipped product.

To see the demo instead, ask for it:

```bash
JJ_SEED_DEMO=1 docker compose up
```

That loads the 41-project, 121-person fixture. **`just check` sets this for you**,
because the acceptance checker scores exactly that data. If you have never run a
real event, this is the interesting thing to look at.

---

## Running an event

The lifecycle an organizer actually walks through.

**1 — Open the doors.** The event is **born closed**: submissions are refused until
you open the window in [the Chambers](#the-chambers-and-what-they-cannot-change),
and the refusal is a 403 that names the guard rather than a form that quietly
disappears.

**2 — Seat the Bench.** `/organizer/assignments/` runs the assignment engine and
shows **the Docket with its certificate**. The certificate is the part that
matters: when the instance is feasible it names the tightest per-judge capacity it
had to satisfy (6, on the seeded data), and when it is infeasible it names *which
judges and which projects* are short, with three remedies that carry arithmetic.
**An assignment you cannot explain to a judge who disagrees with it is not an
assignment.**

**3 — Judge.** `/judge/` is a console of assigned reviews with a rubric, drafts,
and a lock on submit. A judge who is not the assignee is **refused** — Rule I — not
shown a blank page.

**4 — Read the room.** `/api/v1/influence` reports where public support is
concentrated: distinct identities per project, first-preference share, vote-mass
Gini, and identical-ballot clusters. It is deliberately **not** gated on the
verdict being published — you need to see concentration *before* deciding to
publish, or the report is a post-mortem. There is no threshold anywhere in it, and
it never says "brigaded": a report that accuses a table of friends on a number
alone is a machine for making enemies.

**5 — Open the Ballot.** `/vote/` gives every visitor one weighted opinion per
project. Weight 1 across the board *exactly* exhausts the identity budget, so
favouring one project means giving another less — there is no way to vote twice
for your favourite without paying for it elsewhere.

**6 — Publish the Verdict.** `/results/` is refused to everyone but an organizer
until you publish, and **every row says how it was computed** — see
[the verdict is unnormalized](#the-verdict-is-unnormalized-and-why). Publishing
computes **the Seal**: a content hash, mixed with a digest of the scores behind it,
replicated into every judge's signed record.

**7 — Keep the Archive.** `manage.py export_run` writes the whole database as a
portable archive; `import_run` reads it back. See
[leaving with your data](#leaving-with-your-data).

---

## What each role can see

Isolation is the product, and it has to be a property of the query layer rather
than of each view.

**There is one way to read reviews, and it takes an actor.**

```python
Review.objects.for_actor(actor)
```

A lint rule (**JJ01**) fails the build on any other read of `Review.objects` —
**including inside tests**. Two further accessors exist and are named for what they
expose: `for_cross_judge_analysis(event_id)` for the normalization proof, and
`for_bulk_transfer()` for the Archive. Each has a test asserting who is allowed to
call it, because a sanctioned accessor with a growing list of callers is a rule
that has stopped meaning anything.

**A refusal is a 403 with an empty body. Never a redirect.** One shared function
produces every denial in the portal, so no view can invent its own softer answer.

**Scope when it protects somebody.** A published judge sees a ranking over their
*own* reviews, because their five scores would otherwise carry the standing. A
visitor sees the whole event, because they have nothing of their own to protect
and an empty board is worse than a full one.

| | judge | participant | visitor | organizer |
|---|---|---|---|---|
| own reviews | yes | — | — | yes |
| a peer's reviews | **403** | **403** | **403** | yes |
| the verdict, while sealed | **403** | **403** | **403** | yes |
| the verdict, once published | own only | yes | yes | yes |
| the full export | **403** | **403** | **403** | yes |
| the Record | **403** | **403** | **403** | yes |
| the influence report | **403** | **403** | **403** | yes |

### The Chambers, and what they cannot change

The settings page edits the windows, the voting mode, and publication — and
nothing else. **No setting there can widen what any actor reads.** Not the rubric's
weights (a leaderboard must not move under the judges who produced it), not a
project's track (that decides which judges can see it), and not anything about
isolation. That is asserted as an **absence** — the tests read the rendered form
and fail if a field reaching any of them ever appears.

---

## Leaving with your data

*A platform you cannot leave is a trap.* This is the Archive, and it is built to be
checked rather than trusted.

```bash
docker compose exec portal python manage.py export_run /app/data/archive
docker compose exec portal python manage.py import_run /app/data/archive --dry-run
docker compose exec portal python manage.py import_run /app/data/archive
```

**`export → import → export` is byte-identical, including every natural key.** Not
"equivalent" — byte-identical, and the suite proves it by wiping the database in
between. Primary keys travel too, which is stricter than portable and is the point:
an archive whose ids may differ cannot detect a dropped column.

Four behaviours, each a refusal rather than a guess:

1. **An unknown `schema_version` is refused.** Not guessed at — a wrong guess
   silently drops data, and a refusal costs an afternoon.
2. **`compatible_with` is an explicit list.** A v1 archive is readable by a v3
   portal *because the v3 importer says so*.
3. **Unknown columns are preserved**, values included, and handed back to the next
   export. Your custom field survives a round trip through a portal that has never
   heard of it. This is the single most valuable importer behaviour and almost
   nothing ships it.
4. **Unmatchable and malformed rows are quarantined with a reason**, never silently
   discarded, and one bad row does not abort the other ten thousand.

**The keys are on their own volume.** Signing keys live in `judgejudy-keys`,
separate from the database, because `docker compose down -v` is how you reset the
portal — and a shared volume would mean every reset destroyed every signature,
taking the evidence with it. It also means a backup of `judgejudy-data` is safe to
hand to somebody, because it contains no key material at all.

### Proof you did not change the numbers after publishing

```bash
docker compose exec portal python manage.py publish_results --show-only
docker compose exec portal python manage.py publish_results
docker compose exec portal python manage.py sign_records
```

`publish_results` freezes the ranking, hashes it, mixes in a digest of the raw
scores behind it, and **copies the Record's head into every judge's signed
record**. The point of that last part is that it makes equivocation detectable
*from outside* your own database: N judges who are not the organizer each hold a
copy, so publishing two different verdicts is a five-line diff between any two of
them.

Both hashes are **re-derivable by anyone holding the export** — the digest from the
raw scores, the ranking by running the published method. An organizer who alters a
result and leaves the hash alone has produced a mismatch any third party can check
without touching your database.

Judges sign with **Ed25519** keys over an **in-toto Statement v1** inside a **DSSE**
envelope. The record commits to *digests of their reviews*, never to scores — a
record carrying scores is not shareable with a judge who was not the organizer,
and an unshareable record replicates nothing.

**Publication always goes through one function**, whether you press the button in
the Chambers or run the command, so a verdict published by a browser and one
published by a shell produce the same Seal and the same audit entry.

---

## Routes and API

| Route | Purpose |
|---|---|
| `/setup/` | **First-run wizard.** Creates your hackathon: you, the event, the dates, the tracks, a starting rubric. Refuses with a bare 403 once an event exists. The only write path an unauthenticated browser can reach, and CSRF-protected for exactly that reason. |
| `/login/` | Sign in. Five wrong tries in five minutes locks that account for fifteen, per-email so one attacker cannot lock every judge out. No password reset: there is no mail service on purpose. |
| `/logout/` | Sign out. POST-only — a GET logout is a drive-by. |
| `/` | **The Gallery.** Server-rendered, no JS, public. |
| `/projects/new` | Submit a project. Refused while the event is closed. |
| `/judge/` | **The Bench.** Draft, submit, lock. |
| `/judge/review/<int:assignment_id>/` | The rubric form for one assignment. |
| `/organizer/assignments/` | **The Docket**, and its min-cut certificate. |
| `/organizer/settings/` | **The Chambers.** The submission window, the voting mode and its window, and publishing. Every change is an audit entry with its old and new value. The rubric is deliberately *not* editable here. |
| `/vote/` | **The Ballot.** A per-voter order, stable across requests, rendered with its seed. |
| `/projects/<str:project_id>/comments/` | Comments on a project. Plain text, never markup. Everything is **held for moderation**; nothing is public until a human approves it. |
| `/results/` | **The Verdict**, refused while sealed. Always labelled with how it was computed. |
| `/healthz` | Liveness probe. |
| `/healthz/` | The same probe, trailing slash. |
| `/admin/` | Django admin. |
| `/api/v1/judge/scores` | **A judge's own scores, and nobody else's.** Any other role gets a 403 with an empty body. |
| `/api/v1/export.csv` | The full review export, carrying every row's natural key so an Archive round-trips. Organizer only. |
| `/api/v1/results` | The Verdict as JSON, with `results_state` and how it was computed. Refused to everyone but an organizer while sealed. |
| `/api/v1/audit` | **The Record** — the hash-chained trail, plus `chain_head` and the verdict of re-walking it. |
| `/api/v1/influence` | Vote concentration: distinct identities, first-preference share, vote-mass Gini, identical-ballot clusters. No thresholds. |
| `/widget/results/` | **The embeddable widget.** One self-contained HTML document — no script, no stylesheet link, no CDN, no webfont — so it renders inside somebody else's page with no network at all. Refused with a bare 403 while sealed. Carries standings only, never scores, and labels the method on every row. |
| `/widget/results.json` | The same ranking as canonical JSON, for an embedder that would rather draw it than paste it. Same gate, same fields. |

**Embedding it.** Once the verdict is published, an organizer can paste

```html
<iframe src="https://your-host/widget/results/" width="520" height="720"
        style="border:0" title="Results"></iframe>
```

into any page. Nothing is fetched on the organizer's behalf and no credential is
involved — which is why the widget is public, why it is refused until the event is
published, and why it carries no scores. `just prove-offline` renders it inside a
container started with `--network none`, so the claim is measured rather than
asserted.

**`?deep=1` on `/healthz`** also checks the database.

**[`openapi.yaml`](openapi.yaml) is the full reference** — generated from
`reviewer/api/documents.py` and **refused if it has drifted from `urls.py`**, so a
route cannot ship undocumented. Regenerate with `just schema`; `just schema
--check` fails if the committed copy is stale.

The ballots, the vote tally, the bias-attack harness and the influence report all
call the *same* functions the tests attack, so a claim and the code that backs it
cannot drift apart.

---

## Operating it

```bash
just check         # the full gate: clean volume, build, up, checks, proofs, suite
just doctor        # is the toolchain intact?
just logs          # follow the container
just clean         # down -v, a real reset
just schema        # regenerate openapi.yaml
```

**It boots with no network at all** — `just prove-offline` runs the image with
`--network none` and probes it, including rendering the widget. A cold start from
an empty volume measures **11.8–20 s** against a 60 s budget.

**The container reconciles itself on every boot**, between `collectstatic` and the
server binding, so nothing is half-initialised when the port opens. It prints every
table's row count, both census invariants, and the awkward things in the fixture it
deliberately kept. `verify_census` re-derives the same numbers from `fixtures.json`
and **exits non-zero on a disagreement**.

### Demo credentials

The container prints a ready-to-paste `[auth]` block on every boot — one identity
per role (admin, organizer, two judges, a participant). They are HMAC-signed demo
tokens derived from the seeded fixture, **not secrets**: anyone holding this
repository can mint one, which is the point of a demo. Set `DJUDGE_DEMO_TOKEN_KEY`
to rotate them; `docker compose logs portal` prints the new ones.

### Stack

Python 3.13 · Django 5.2 LTS · Django REST Framework · drf-spectacular ·
whitenoise · gunicorn · cryptography · SQLite (WAL) on a named volume.

**Six direct dependencies, eighteen packages installed** — measured in the shipped
image, and every one of them is commented in
[`requirements.txt`](requirements.txt) with the reason it is there and the
dependencies that were deliberately left off.

---

## Decisions that change behaviour

The ones an organizer would notice.

### The verdict is unnormalized, and why

It is a raw weighted mean, and the page says so on every render. We built the
normalization engine the brief asked for and then measured whether it was needed:
between-judge variance is **0.0217** against a **0.0971** sampling-noise floor for
30 judges scoring 4 projects each, permutation **p = 0.227**. **There is no
severity effect to correct.** Applying the estimator anyway would move all 126
scores by ~0.57 rubric points for a measured null, so we do not. Full generated
tables in [`docs/REAL-FIXTURE-RESULTS.md`](docs/REAL-FIXTURE-RESULTS.md).

We would rather ship the disappointing number than the comfortable one.

### Ballot order is randomised, which makes position bias zero-*mean*, not zero

The bias-attack harness attacks the same function the ballot renders. Under a fixed
order the harness detects the attack; under a randomised one the mean drift is ~0
while the standard deviation is not. Anyone claiming position bias was *removed* is
overstating it.

### The Record is append-only, and it cannot lie

`AuditEntry.delete()` raises. Deleting an entry is indistinguishable from rewriting
history, which is the attack the chain exists to make detectable. The one exception
is the restore path in the Archive, which re-verifies the chain afterwards — and
that is the price of the exception, not a caveat on it.

A chain entry and the change it describes are written **in one transaction**. An
earlier version let the chain commit independently of the event, so a failed save
left a permanent entry claiming a deadline had moved when it had not — a falsified
row in the evidence the whole design rests on. That was found by review, not by a
test, which is why `fixed` findings stay open until somebody re-reads them.

### Comments are rate limited, and the anonymous version is weak

Five per hour per identity, refused with the portal's bare 403. A **signed-in**
poster is keyed by their account, so the limit follows them across browsers. An
**anonymous** poster is keyed by a hash of their session, so **clearing cookies
resets the budget** — IP would be the alternative, and this project refuses it
everywhere else because it is a poor identity that gets innocent people in trouble.
A limit that a private window resets is still a limit against the naive case, and
the strong case is reachable by giving people accounts.

This was cut for most of the build and disclosed rather than quietly missing. It is
the control our own threat model names, and shipping it honestly — including the
bypass, which is also a test — beat leaving it out.

### The fifteen decisions, itemized

Every one of these changes behaviour, and none is revisited in a hurry. Full
reasoning in [`blueprint/project-plan.md`](blueprint/project-plan.md) §6.

| | Decision | The one-line reason |
|---|---|---|
| D-01 | **Isolation in the data-access layer.** `Review.objects.for_actor(actor)` returns an already-scoped queryset. | No code path from a view to an unscoped query is possible to write by accident. |
| D-02 | **Denial is a literal 403, never a 302.** Empty body, no `Location` header, one shared function. | `run.py` follows redirects, so a redirect returns 200 and fails the check while looking correct in a browser. |
| D-03 | **Two enforcement layers, not three.** Permission *decides* and raises; the queryset *constrains* and cannot. | They fail in opposite directions, so neither can mask the other. |
| D-04 | **Normalization: robust median/MAD + shrinkage `k=3`, `ε=0.5`; empirical Bayes as the constant-free estimator.** | The constants are a priori and legible, chosen without seeing outcomes. `k = 0` scores better and we do not use it. |
| D-05 | **Detectability analysis *first*.** Is there an effect to remove? | A normalization claim that never tests for the effect it removes is a subtler overclaim than doing nothing. |
| D-06 | **Assignment: one flow over all tracks**, min-max capacity by search, load-imbalance + seeded tiebreak, min-cut certificate. | 9 of 30 judges are dual-track, so per-track flows are simply wrong. |
| D-07 | **Infeasibility is diagnosed, never asserted.** The min-cut names the projects, the bottleneck judges, the deficit and three remedies with arithmetic. | "Feasible" and "provably impossible" are different answers deserving different code paths. |
| D-08 | **Audit is hash-chained**, with `omitted_since_prev` *inside* the chain. | Sampled auditing plus a chain is incoherent — a gap is indistinguishable from an edit. |
| D-09 | **No Merkle transparency log.** Publish one chain head and replicate it into every signed judge record. | A transparency log's value is *witnessing*, and we run the container. |
| D-10 | **Signed records: Ed25519 in an in-toto Statement v1 inside a DSSE envelope.** Keys on their own volume. | DSSE signs bytes, so no third party reimplements our canonicalisation. |
| D-11 | **`source_key` on every importable table.** Round-trip is byte-identical *including natural keys*. | "Modulo generated IDs" is not a testable property — a dropped column passes it. |
| D-12 | **Voting claims cost amplification inside an identity budget, not Sybil resistance.** Randomised order makes bias zero-*mean*, not zero. | A report that flags everything flags nothing, and a biased ballot nobody noticed is the real failure. |
| D-13 | **Anti-abuse is the published influence report**, not a fancier ballot. | The brief asks for an answer to people trying to cheat it, and an *explanation* is one. |
| D-14 | **Webhooks cut.** Models, a `501` stub and audit events still ship. | 2 h, zero points on all four criteria, and SSRF is a real bug class to write from scratch. |
| D-15 | **No LLM scoring.** Measured and closed. | A hosted API breaks the offline guarantee, and it deletes the thing a quarter of the rubric is about. |

### What we did not build

- **Webhook delivery.** Models and a `501` stub ship; delivery, retries and HMAC
  verification do not. A webhook URL is also a live SSRF bug class to write from
  scratch.
- **A Merkle transparency log.** We run the container, so a root we compute proves
  internal consistency — which the hash chain already proves, for a third of the
  code. What we have instead is the chain head replicated into every signed record,
  which needs no witness.
- **No IRT/MFRM, no TrueSkill.** Measured to lose against the raw mean on this data
  shape.
- **No Postgres RLS, Casbin or OPA.** A scoped-accessor layer is the portable
  equivalent and keeps the rules in one readable place.
- **No simultaneous events in one deployment.** One deployment runs one hackathon,
  deliberately. The wizard's entire authorisation is "no event exists", and a
  multi-tenant version would need a tenancy story this one does not have.

---

## For reviewers

Everything above is the product. This is the rest, condensed.

**Status: T1 and T2 are green, and T2 is claimed.** All seven of the organizers'
machine checks pass. `run.py` prints `claimed T1 T2, verified T1 T2` — **both
words are deliberate.**

**`verified` cannot exceed T2, whatever we build**, because `run.py` contains no T3
or T4 checks at all: three T1, four T2, seven in total, and `verified` is
prefix-locked to the tiers it has checks for. A flawless build prints exactly that
string.

**T3 is built, tested and documented, and deliberately not claimed.** All five
REQ-T3 requirements ship — voting with an identity budget and a Borda tally,
moderated comments, results hidden on both the API and the public page, randomised
ballot order, and the influence report. Nothing in this repository can *verify* T3,
and our own gate enforces the organizers' rule `overclaim = claimed − verified`, so
entering T3 in the field their program parses turns the gate red with the word
**OVERCLAIM** in it. **T3 being built is not the same as T3 being entered in the
scoring field**, and only the first is ours to decide. Proved by running it, then
reverted; recorded as F-91, accepted by decision, with the arithmetic in
`blueprint/history/features/break-3-t3-claim.md`. A T4 claim is blocked the same
way.

**`run.py` always exits 0.** It prints `FAIL` and returns 0 in every situation, by
design — it is the same program for every team. Our gate parses its **body**; a gate
on its exit code would report a green checkpoint for a completely broken portal. It
is also **unmodified**, so the panel runs the identical program.

**The gate is more than `run.py`.** `just check` runs the spec layer, a clean
`down -v`, the build, the organizers' checker, the isolation proof, the census and
the suite. Two more run at every verification break because each needs a clean
volume: `just prove-offline` and `just mutation-test`, which **corrupts 116 things
on purpose and requires every one to be caught** by a named test.

**Findings.** [`blueprint/context/findings.md`](blueprint/context/findings.md) is
the full record: **126 findings**, what was wrong, what was fixed with a test, and
what was declined and why. Several are the same class of defect in a new medium — a
min-cut certificate that named no judges, a leaderboard that would have been refused
for the wrong reason, a CSV column of nothing, an acceptance criterion that passed
with the importer writing nothing at all, and a test suite whose fixture omitted a
precondition so three "passing" publication tests executed nothing whatsoever.

**Every number in this file is generated, not transcribed**, and a spec gate
re-derives the counts from the ledger and the harness — it caught three stale
tallies within a minute of writing them, and caught this file breaching its own
size budget. Two defects it does *not* yet check are named in the FEAT-13 archive
rather than left for the next session to assume.

| | |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | the container, boot order, layering |
| [`DATA-MODEL.md`](DATA-MODEL.md) | the schema and the fixture it holds |
| [`JUDGING.md`](JUDGING.md) | rubric, assignment, isolation, normalization |
| [`docs/REAL-FIXTURE-RESULTS.md`](docs/REAL-FIXTURE-RESULTS.md) | the normalization proof, fully generated and asserted in CI |
| `blueprint/history/features/` | one file per feature, including the ones that were wrong |

**Repository layout.** `src/reviewer/` holds the domain apps; `isolation/` (the
accessor), `importer/` (loader and census) and `io/` (the Archive) are non-app
packages. `blueprint/` is the plan and the ledger, `bible/` is 330 KB of research to
be read by section, never whole.

---

<div align="center">

<img src="docs/logo.svg" width="64" alt="">

**Judge Judy** — *the bench that keeps its own records.*

Rules of order above. MIT licensed. Built for the DOGFOOD 2026 hackathon.

</div>

## Licence

MIT. See [`LICENSE`](LICENSE).