# 07 · Security and Threat Model

**Purpose:** the Threat Model bonus, and the abuse thinking that the 25%
Judging Integrity criterion explicitly asks for: *"Did you think about vote abuse
before a judge asked?"*

**The standard we hold this to, from the brief:** *"Name the attacks you stopped,
and name the ones you did not. The honest list is worth more than the heroic
one."*

So this document has two halves of equal length: what we stopped, and what we did
not. A threat model that claims to have solved Sybil attacks in a self-hosted
Python web app is not defensible, and a panel of thirty-six engineers will read
it that way.

---

## 1. The asset being protected

Ranked by what actually hurts the organizer if it fails. This ordering is the
whole document; a threat model that does not say what matters is decoration.

| # | Asset | Why it matters most |
|---|---|---|
| 1 | **Judging integrity** — that scores mean what they appear to mean | The entire event is this. A leaked or altered score is a scandal, not a bug |
| 2 | **Judge confidentiality** — that no judge sees a peer's work | Judges stop being honest if they can compare notes. It also protects the panel from pressure |
| 3 | **Vote integrity** — that public voting reflects real sentiment | Determines prizes. A brigaded vote is a scandal |
| 4 | **Submission integrity** — the deadline really closed | A team that missed the deadline by an hour and submits at hour zero has broken the event's one hard rule |
| 5 | **Participant privacy** — emails, team membership | Breach liability, and the reason organizers will not adopt a platform that collects this |
| 6 | **Availability** — the portal works on judging day | An event that goes down while judges are scoring is an operational failure |

---

## 2. Trust boundaries

```
                    ┌── public internet ──┐
                              │
              ┌───────────────▼────────────────┐
   B1  │  reverse proxy / TLS / rate limit    │   ← untrusted input
              └───────────────┬────────────────┘
                              │
              ┌───────────────▼────────────────┐
   B2  │  request → session → RoleBinding      │   ← identity boundary
              │  DRF permission  → 403 or 200   │
              └───────────────┬────────────────┘
                              │
              ┌───────────────▼────────────────┐
   B3  │  ReviewQuerySet.for_actor(actor)      │   ← the isolation boundary
              │  every read of Review passes     │      THE load-bearing one
              └───────────────┬────────────────┘
                              │
              ┌───────────────▼────────────────┐
   B4  │  SQLite file on disk                  │   ← data at rest
              └────────────────────────────────┘
```

**B3 is the boundary this whole project is judged on.** B1 and B2 are competent
framework behaviour. B3 is our design and it is the one the brief singles out.

**B4 deserves an honest sentence:** a SQLite file is readable by anyone with
filesystem access, and there is no encryption at rest. For a self-hosted portal
on an organizer's own machine that is the normal and acceptable posture, and it
is the direct price of the single-command, no-second-service decision in
`01` §6. For an event with genuine confidentiality requirements — NDA'd
sponsors, unblindable research, military or medical judges — **this deployment
is not appropriate and the README must say so.** Recommending a deployment
inappropriate for the data is worse than not supporting it.

### 2b How many enforcement layers, and how to justify the number in writing

> **Two layers. A third is theater, and the reason is specific rather than
> rhetorical.**

- **B2's permission class decides.** It answers "is this actor allowed to perform
  this action at all?" It *raises*, so it produces the 403.
- **B3's scoped queryset constrains.** It answers "which rows may this actor
  see?" It *filters*, so it **cannot** produce a 403 and therefore cannot
  accidentally become one.

**They fail independently and in opposite directions, and that is the entire
justification.** B2 failing open gives a 200 with unfiltered data. B3 failing
open gives a 403 where a 200 was owed. Neither failure masks the other.

**Why not three.** Any third layer must be *derived* from one of the first two,
or it is a second source of truth. A middleware that re-checks roles is a
second source of truth. A decorator is a second source of truth. The moment you
have three, a reviewer must verify they agree — and **there is no mechanical way
to do that.**

**The exception that proves the rule, and we already have it: the lint rule**
forbidding `Review.objects.all()` outside the manager. That *is* a fourth
enforcement point and it is not theater, because it enforces a **syntactic**
property ("there is no code path") rather than a **semantic** one ("this check
is right"). **Syntactic invariants can be checked mechanically; semantic ones
cannot.** That distinction is the answer to "how do we justify the number in
writing," and it is what separates a design from a pile of middleware.

### 2c What we deliberately did not put in the authorization path

| Rejected | Why — with the practitioner consensus, not our opinion |
|---|---|
| **PostgreSQL Row-Level Security** | RLS is a **row predicate** evaluated per row. It cannot express workflow state or "may this actor perform this business action." The recommended split is explicit: **application decides the business action, the database constrains the rows.** RLS also requires `SET LOCAL app.current_user_id` per transaction — if misapplied, one user's identity persists into the next request on a pooled connection. **Views bypass RLS by default** because Postgres creates them `SECURITY DEFINER`, so a view over a protected table hands out every row its policies withheld (Postgres 15+ has `security_invoker = true`; earlier versions have no fix). Recursive policies fail with `42P17`. And it would break the single-service, single-file story that carries 20% of the score. **Our scoped-accessor layer is the portable equivalent and is stronger here:** "a judge on `trk_04`" is one `.filter(judge=actor.user)` on an index scan, where in RLS it is a correlated subquery per row. |
| **Casbin / OPA** | Excellent tools, and adopting one would be *worse* for us. Our best architectural claim is "there is exactly one place where the rules live." A Casbin model file is a **second schema, in a DSL**, that a reviewer must learn and that can drift from the ORM layer. Our policy is 5 roles × 6 resources and it already lives in the ORM. We would trade a single source of truth — a real asset — for a policy engine we do not need. |
| **A third layer** (middleware or decorator) | §2b. Derived, therefore a second source of truth. |
| **Timing-equalising response padding** | §3.1 J-14 and §6. The short version: padding to a fixed budget makes a legitimate 403 look like a slow database, burns a gunicorn worker per denial (turning our rate limiter into our DoS), and is still defeated by averaging over many samples, which is the only thing a timing attacker does anyway. **It is not constant-time, and would be called that regardless.** Real constant-time shaping is padding to the *maximum* observed latency with a monotonic clock and no early exit — a research project, and getting it wrong is worse than not claiming it. **Keep the narrow claim and quantify the residual instead.** |

---

## 3. Attacks, and what we do

### 3.1 Judge and scoring integrity

| # | Attack | Vector | Response | Status |
|---|---|---|---|---|
| J-1 | **Read a peer's scores** | `GET /api/judge/scores?judge=<other>` | Permission layer returns 403; `for_actor_and_subject` returns `none()` for a judge asking about anyone else. Never a 200, never a redirect | **Stopped — twice** |
| J-2 | **Read another track's reviews** | Query with a `track` parameter, or infer from a project ID | Judge bindings are track-scoped; the scoped queryset intersects the actor's tracks. Parameterised filters are intersected with the scope, never unioned into it | **Stopped** |
| J-3 | **Read the aggregate leaderboard mid-judging** | `GET /api/results` | FIG. 02 marks aggregate ✗ for judges. Results endpoints require organizer, or `results_state = published` | **Stopped** |
| J-4 | **Enumerate judge IDs to confirm who exists** | ID probing | The 403 does not distinguish "no such judge" from "not yours." Same status, same body, same timing shape | **Stopped** |
| J-5 | **Alter a submitted score** | `PATCH /api/reviews/<id>` as the owning judge | `Review.status` is `submitted` → immutable. Edits require an organizer and are logged with a before/after diff | **Stopped** |
| J-6 | **Edit the rubric mid-judging** | `PATCH /api/rubric` | `rubric_weights_locked_at` once the first review is submitted; plus `Score.weight_applied` snapshotted, so even a forced change cannot alter an existing review's meaning | **Stopped, two layers** |
| J-7 | **Judge collusion** | Two judges discussing offline | **Not technically preventable.** We detect the *statistical* signature instead: abnormally high agreement beyond chance, corrected for rank distance, surfaced in the organizer view. A conversation in a hallway leaves no trace in our data | **Detected, not prevented** — see §6 |
| J-8 | **Judge rushes** | Submitting 40 reviews in 4 minutes | `Review.duration_seconds` recorded; a flag when a judge's median time is an order of magnitude below the panel's. Informational — some judges are just fast | **Flagged** |
| J-9 | **Judge self-conflict** | A judge scores their own team's project | Hard constraint: a `TeamMembership` user is ineligible for that team's projects. Enforced in assignment eligibility *and* re-checked at review submission, because eligibility can change after assignment | **Stopped** |
| J-10 | **Organizer alters a result** | Direct DB or admin action | **Three layers.** (1) Hash-chained append-only audit with before/after diffs (`06` §5.2). (2) `ResultPublication.results_hash` over the canonical ranking **and** a digest of the raw score rows (`05` §9) — the organizer's own database is the thing we do not trust, so the hash is a claim and **the export is the evidence**. (3) The chain head at publication is replicated into **every judge's signed participation record**, so N parties who are not the organizer hold a copy. To tamper the organizer must forge Ed25519 signatures or produce two records that disagree, and any two record holders diff it in five lines. `manage.py verify_results` and `manage.py verify_record` both work offline against a downloaded archive | **Stopped — detectable by a third party with no access to our database** (was: "Detected") |
| J-11 | **Read scores through the CSV export** | `GET /api/export/scores_raw` as a judge | Export is organizer-only. Every export is itself an audited event | **Stopped** |
| J-12 | **Read scores through a webhook payload** | Payload includes score data | Webhook payloads are typed per event and **scores are never in a public or webhook payload** — only status changes | **Stopped** |
| J-13 | **Read scores from the certificate** | Certificate embeds results | Certificates carry names and track only. The signed participation record carries counts, hashes and the results hash — **never scores** | **Stopped** |
| J-14 | **Timing side channel on peer scores** | Response time differs for "exists" vs "not yours" | See the block below. Same code path, same statement count, same status, same body length; **residual risk quantified rather than waved at** | **Partially — quantified, not claimed away** |

#### J-14 in detail: quantifying the timing residual instead of claiming it away

An earlier draft said "timing is not fully equalised and we do not claim it."
**That is an admission, not an analysis.** Here is the analysis, and it is a
better answer precisely because it is specific.

**What we do (all three are cheap and all three are checkable):**

1. **The scope check runs before any existence check**, so "no such judge" and
   "not yours" execute the same statements in the same order. Not "similar
   code" — *the same code path*.
2. **The same number of queries either way.** A denial and a permitted-but-empty
   both issue 2 queries. **This is the part that actually matters and it is
   measurable, so we measure it** — asserted in the isolation test suite and
   visible in `manage.py isolation_proof`.
3. **Identical `Content-Length` on every denial**, by serving one fixed-size JSON
   error document. Three lines, and it removes the length channel, which is the
   one channel that is trivially observable and that most teams forget.

**The residual, stated quantitatively rather than dismissed:**

| | |
|---|---|
| What the attacker needs | a local timing oracle; N repeated requests to average out scheduler noise; a per-request difference far below the noise floor |
| What the difference actually is | at 41 projects the whole table is in the page cache. A B-tree probe measuring "row exists" vs "row does not exist" is **nanoseconds**. A gunicorn round trip on a laptop running SQLite WAL is **milliseconds** — and its variance across requests is orders of magnitude larger than the signal. |
| Separation | roughly **four orders of magnitude below the noise you would have to average away** |
| Verdict | **not exploitable at our scale by any attacker we can construct, and it gets worse for them as the event grows** (more rows, colder cache — both favour the defender's constant code path) |

> **"We measured the attack surface" is a defensible claim. "We gave up" is
> not.** And note the last row: this is one of the very few security properties
> that **improves with scale**, which is a good reason to say so out loud.

**We still do not claim constant-time behaviour**, and `manage.py
isolation_proof` asserts status + body + headers on every denial, not timing. If
a future deployment moves to Postgres over a network — where the round trip is
milliseconds and the DB does the filtering — this analysis must be redone, and
`05` §2c's RLS discussion becomes relevant. **Recorded as a constraint on future
work, not a solved problem.**

### 3.2 Voting abuse

The brief's position: *"Community voting is universally conceded to be gameable:
the standard advice is to keep the prize small and hide results until you have
manually reviewed the votes."* We are asked to do better with engineering.

| # | Attack | Response | Status |
|---|---|---|---|
| V-1 | **Ballot stuffing** — one person, many votes | Per-`voter_key` unique constraint, per-voter vote budget, and quadratic influence `√n` so 100 votes = 10 influence against 100 single votes. **Claimed precisely:** this is *cost amplification inside an identity budget*, not Sybil resistance — see `06` §6.1 for why, with three citations | **Partially — raises cost within an identity, does not address Sybil** |
| V-2 | **Sybil** — many identities, one person | `email_gated` requires verification; `authenticated` requires an account. Rate limits per IP and per fingerprint. **We do not claim quadratic voting helps here**, and the literature says it does not: Sybil resistance comes from a quadratic **cost on acquiring an identity**, which a self-hosted portal with email verification does not have. An attacker with a plus-addressing domain gets unlimited budgets | **Not stopped — stated as the first entry in §6** |
| V-3 | **Duplicate detection evasion** — new identity per vote | Cross-voter signals: IP hash, UA hash, timing, and behavioural similarity (all votes within seconds, identical ordering). Flagged for organizer review, not auto-blocked | **Detected** |
| V-4 | **Vote ring / brigade** | Coordinate off-platform, vote in bursts, rotate. We detect burst patterns and identity clustering and surface them for review | **Detected, not prevented** |
| V-5 | **Bot via headless browser** | Rate limits, UA and header fingerprinting, challenge on anomaly | **Weak** — see §6 |
| V-6 | **Result manipulation via early visibility** | `results_state = hidden` during the voting window; every results endpoint 403 for non-organizers | **Stopped** |
| V-7 | **Vote flipping after the fact** | Votes immutable once cast; a change is a new vote recorded with both timestamps and logged | **Stopped, auditable** |
| V-8 | **Comment spam / XSS** | Escaped output, no raw HTML, `pending` moderation queue, rate limits, length caps | **Stopped** |
| V-9 | **Comment-based collusion or vote trading** | Free text carries no enforceable rule | **Not prevented** — moderation is human work |

### 3.3 Submission abuse

| # | Attack | Response | Status |
|---|---|---|---|
| S-1 | **Submit after the deadline** | Single service guard (§`05` §4) called by API, admin and import. Server clock only; the client never sends a timestamp. **403, never a redirect** | **Stopped** |
| S-2 | **Change the clock** | No client-supplied time is ever trusted. The checker's own note confirms it does not manipulate a clock — the test is that our comparison is real | **Stopped** |
| S-3 | **Backdate `submitted_at`** | Set server-side at creation. Immutable afterwards; edits are organizer-only and logged | **Stopped** |
| S-4 | **Impersonate a team** | Only `TeamMembership` users or team owners can write to a team's project. Invite codes are random, expiring, use-limited | **Stopped** |
| S-5 | **Scrape the gallery** | Public by design — that is the point of a gallery. Rate limited, no personal data in project records, and repo/demo URLs are supplied by teams, not fetched by us | **Accepted, not a vulnerability** |
| S-6 | **Submit a project with a hostile URL** | URLs are stored and rendered as escaped text with `rel="nofollow noopener noreferrer"`. **Never fetched, never rendered as a link source, no image proxying** — which also satisfies the offline requirement | **Stopped** |
| S-7 | **Duplicate submission flooding** | The `prj_07` / `prj_41` case is modelled explicitly (`supersedes`), so duplicates are a supported state rather than an error. Gallery deduplicates by team, latest-wins | **Handled** |
| S-8 | **Withdraw after the deadline to remove a bad entry** | `withdrawn` is distinct from `deleted` in the schema; withdrawal after the deadline is organizer-only and logged | **Stopped** |

### 3.4 Platform

| # | Attack | Response | Status |
|---|---|---|---|
| P-1 | **CSRF** | **A stated exception, verified rather than recalled.** Django CSRF is on for all HTML form paths. The API's session authentication is **CSRF-exempt** (`enforce_csrf = None`) and this is deliberate — see `03` §3.2. **Compensating controls:** (1) `SameSite=Lax` on the session cookie, the primary defence against cross-site form POST and independent of DRF; (2) unsafe API methods require `Content-Type: application/json`, which a cross-origin HTML form cannot set; (3) CSRF stays fully on for HTML paths — we exempt the API, not the site; (4) `README.md` says so in one sentence | **Stopped for HTML, with a deliberate and compensated API exception** |
| P-1a | **API is CSRF-open for cookie-authenticated unsafe methods** | This is the cost of the P-1 exemption, stated rather than buried. Mitigated by SameSite=Lax + JSON content-type enforcement. **Residual:** a cross-site `fetch` with `credentials: include` and a JSON content-type is not reachable without CORS preflight approval, which we never grant. If we ever did, the exemption would have to be revisited | **Partial, with the residual named** |
| P-2 | **Session fixation / theft** | New session key on login; `HttpOnly`, `SameSite=Lax`, `Secure` under TLS; session rows revocable server-side; rotation on privilege change | **Stopped** |
| P-3 | **SQL injection** | ORM parameterised queries throughout. No raw SQL. The one place raw SQL is justified — the min-cost flow solve — uses bound parameters and is a read-only aggregation | **Stopped** |
| P-4 | **XSS** | Templates auto-escape. No `|safe` outside a deliberate rich-text renderer that sanitises with an allowlist. Comments are plain text by design | **Stopped** |
| P-5 | **Privilege escalation via mass assignment** | DRF serializers with explicit fields; no `fields = "__all__"` on any write serializer | **Stopped** |
| P-6 | **IDOR on user-scoped objects** | Every detail route goes through `for_actor`. Ownership is a filter, never a `get_object_or_404` that finds it first | **Stopped** |
| P-7 | **Webhook forgery** | **CUT at H+0** — webhook delivery is not built, so this attack has no surface in the shipped portal. The models and a 501 stub ship, and `README.md` states that delivery, retries and signature verification are not implemented. **Recorded as "not applicable because the feature is absent," not "not applicable because we forgot"** | **N/A by omission — stated** |
| P-8 | **SSRF via webhook URL** | Same as P-7: no delivery, no surface. **Recorded so the next person to extend it knows the work is not done** — scheme allowlist, DNS resolution checked against private ranges before delivery, redirect limit | **N/A by omission — recorded as required future work** |
| P-9 | **Supply chain** | Locked dependency versions, no install-time scripts in the image, no network calls at build time beyond package installation | **Partially** — see §6 |
| P-10 | **Audit log tampering** | Append-only; no update or delete path; the manager raises. **Hash-chained** (`06` §5.2) with a 20-line offline verifier, and the chain head at publication **replicated into every judge's signed record** so the chain is not solely in the organizer's hands. **Residual: anyone with filesystem access can rewrite the whole chain from the genesis hash** — a hash chain detects *edits*, not *wholesale replacement*; only an external witness or the independently-signed replicas fix that | **Partially** — residual is a deployment limitation, stated in §6 |
| P-11 | **Denial of service** | Rate limits on auth, submission, voting and commenting. gunicorn worker count bounded. SQLite serialises writes, which caps throughput honestly | **Partial** |
| P-12 | **Secret leakage in the repo** | No secrets. Fixture session values are explicitly documented as non-secret demo credentials | **Stopped** |
| P-13 | **Organizer's data held hostage** | Full export at every stage, documented round-trip, no encryption key we could lose | **N/A by design** — this is the escape hatch working |

---

## 4. Data handling

Privacy, stated plainly, because organizers ask and because it is cheap to be
better here than every incumbent.

| Data | Stored | Retention | Notes |
|---|---|---|---|
| Email | Plaintext (it is the login) | Account lifetime | Needed for magic links and judge invitations |
| Password | Argon2 or PBKDF2 via Django | — | Never logged, never in an export |
| IP address | **Never.** Salted per-event hash only | Rotatable salt | We need duplicate detection, not an address database |
| User agent | Hashed, vote path only | 90 days | Same reasoning |
| Votes | `voter_key` — a hash, not an identity | Event lifetime | For `email_gated` it is a hash of a normalised email, not the email |
| Scores | Full, for organizer and admin | Event lifetime + archive | The archive is the point: *"an archive somebody can query two years later"* |
| Audit log | Actor, action, object, IP hash | Event + 1 year | Append-only |
| Session | Server-side row | Expiry | Revocable |

**The one arguable decision:** we store project `repo_url` and `video_url`
verbatim, which is personal data in the sense that a URL can identify a person.
We never fetch them. That is a deliberate position — an event platform that
fetches participant URLs is a platform that can be used to probe internal
networks, and the offline requirement forbids fetching anyway.

---

## 5. What the audit trail records

**The fourteen actions.** Append-only, filterable in plain HTML, exportable as
text, and **hash-chained** (`06` §5.2). The requirement is *"an audit trail an
organizer can actually read"* — so it is readable without a database client, in
sentences rather than column names.

1. Signed in  2. Role granted  3. Role revoked  4. Assignment created
5. Assignment overridden  6. Review started  7. Review submitted
8. **Score edited**  9. Rubric weights changed  10. Results published
11. Results hidden  12. Export run  13. Import run  14. **Access denied**

Entries 8, 9 and 14 are the ones that matter and the ones existing platforms do
not have:

- **8 — score edited.** A score changed after submission is the end of the
  event's credibility. Logged with a before/after diff, always.
- **9 — weights changed.** Legal before the lock, refused after, logged either
  way.
- **14 — access denied.** Free, and the highest-value security signal an
  organizer can have. A burst of refused peer-score requests from one session is
  either a confused judge or someone probing the isolation boundary. **We log
  the actor, the target object, and the scope that refused** — the scope string
  comes from the same `ScopeReason` object that renders the receipt in the UI
  (`05` §6a), so the audit trail and the screen cannot disagree.

**And two properties that make the log more than a list.**

**It is hash-chained**, per `06` §5.2: `entry_hash = SHA256(domain ‖ seq ‖
prev_hash ‖ JCS(payload))`. Append-only stops being a promise and becomes a
verifiable claim. A 20-line offline verifier walks the chain and reports the
first broken link, gap, or edit.

**Rate-limited denial sampling and a hash chain are incoherent, and this is the
fix.** A gap in a chain is cryptographically indistinguishable from an edit, so
omitting entries 412–418 because an actor was rate-limited produces a log a
verifier must report as tampered. **So the dropped count goes inside the chain,
not beside it:** every entry carries `omitted_since_prev: int`, and a verifier
that sees `seq 419, prev_hash = hash(411), omitted_since_prev = 7` can state, as
a **provable** fact, that entries 412–418 were intentionally not recorded and
here is the count. The chain stays valid and the omission is disclosed rather
than hidden — strictly better than either extreme, and a detail nobody else
will have.

**One honest cost, recorded because it is a real tension between two of our own
controls.** A chain makes every audit insert a synchronous write. At 126 reviews
that is nothing. On a real event with denial logging enabled it becomes write
amplification, and an attacker in a loop of denied requests can make the log
expensive to write — **which is the exact DoS the sampling was introduced to
prevent.** We have created a tension between J-14's completeness and P-11's
availability. Resolution: chain at a **bounded rate per actor** (a counter, not
every denial) and state the bound in the manifest. Recorded as a deliberate
trade, not an oversight.

---

## 6. What we did *not* stop

**This is the half that makes the other half credible.**

| Attack | Why we did not stop it | What we do instead |
|---|---|---|
| **Sybil at scale** | A self-hosted Python app with email verification is not an identity system. Anyone with a plus-addressing email domain gets unlimited identities. **This is the first entry deliberately, and the literature is explicit:** quadratic influence is not Sybil resistance — a quadratic *cost on acquiring an identity* is (Lalley & Weyl 2011), and with free identity acquisition *every* nontrivial weighting rule is Sybil-vulnerable, with Sybil-adjusted power growing at least linearly (Bennett 2025; arXiv:2605.18990). We say this rather than claim otherwise | We state the exact boundary: quadratic influence gives **cost amplification inside an identity budget**, nothing more. Per-voter budgets; clustering detection for human review. **And we say which side of the line we are on** — a team that claims Sybil resistance for an email-gated ballot is selling something |
| **Organizer-level collusion** | A malicious organizer owns the database. We cannot defend an organizer from themselves, and pretending otherwise would be dishonest | Hash-chained audit; `results_hash` over the ranking *and* a digest of the raw scores, so the export is the evidence; **the chain head at publication is replicated into every judge's signed participation record**, so N parties outside the trust boundary hold a copy. Forging those requires breaking Ed25519 or producing two records that disagree |
| **A determined ballot stuffer** | Fingerprinting and rate limits raise cost; they do not make it impossible. A patient attacker with residential IPs defeats both | Detection, flagging, manual review, hidden results, and a **published influence report** before publication — per project: distinct verified identities, first-preference share, vote-mass Gini, identities flagged by clustering. **The brief asks for "an answer to people trying to cheat it," and an answer is a report, not a mechanism** (`06` §6.2). The industry answer is still "small prizes and manual review" and we are honest that it still is |
| **Judge collusion via a channel we cannot see** | Two judges talking in a hallway produce no trace in our data | Statistical detection only: agreement beyond chance, corrected for rank distance. Weak signal, many false positives, presented as a flag and never as a verdict |
| **Timing and traffic analysis** | A determined attacker can distinguish a 403-that-means-forbidden from a 403-that-means-absent by timing even when the response is identical | **Quantified, not waved at** (§3.1 J-14): identical code path, identical statement count, identical `Content-Length`; the residual is a B-tree probe in nanoseconds against a gunicorn round trip in milliseconds, **roughly four orders of magnitude below the noise an attacker must average away.** **We do not claim constant-time behaviour.** This is one of the few properties that *improves* with scale, and it must be redone if we ever move to Postgres over a network — recorded as a constraint on future work |
| **Physical access to the host** | The SQLite file is plaintext on disk | Filesystem permissions and full-disk encryption, which are the host's job. Stated as a deployment limitation, not solved |
| **Dependency compromise** | We pin versions, but transitive dependencies are transitive | Pinned lockfile, minimal dependency set, no install-time scripts. **We do not claim supply-chain integrity** |
| **XSS via a rich text field** | We have no rich text field — by design | If one is added later, an allowlist sanitiser is a prerequisite, not a follow-up. Recorded as a constraint on future work rather than a solved problem |
| **The audit log filling up** | An attacker in a loop of denied requests can flood it — and a hash chain turns every entry into a synchronous write, so sampling and chaining are in tension (§5) | Denials are **rate-limited per actor**, with the per-actor dropped count recorded **inside** the chain as `omitted_since_prev`, so the gap is disclosed and provable rather than being a tamper signal. **A log that can be DoS'd by being written to is not a log, and a log whose gaps look like tampering is worse than no log** |
| **A judge who is genuinely bad at judging** | No statistical method detects consistently wrong judgement, only inconsistency | Low-variance flagging **with its `n` attached**, per-review time signals, and the normalization shrinkage — which reduces the damage without pretending to correct the person. **And the dashboard reports the detectability p-value next to the bars** (`06` §4.1b), because a severity chart with no p-value beside it is actively misleading |

**The honest one-paragraph version, for `ARCHITECTURE.md`:**

> We stop the attacks that live inside the application: authorization, deadline
> enforcement, and the isolation of judging data are enforced in the data-access
> layer and verified both by a test suite and by **one command that prints the
> published role matrix against live data**, so they fail closed. We also stop
> the one attack nobody else bothers with: we made our normalization method
> measurable, and published the result — **including that on this panel there was
> almost nothing to correct.**
>
> We do not stop attacks that live outside it. Sybil voting, offline collusion
> between judges, and a malicious organizer are not solvable by a self-hosted web
> application, and any platform claiming otherwise is selling something. **We are
> precise about the one we might have been tempted to claim: quadratic vote
> influence gives cost amplification inside an identity budget, and the
> mechanism-design literature is unambiguous that this is not Sybil resistance.**
> What we offer instead is engineering that raises the cost of those attacks —
> quadratic influence, rate limits, clustering detection, **a published influence
> report before results are announced**, statistical collusion signals, hidden
> results, and a hash-chained audit trail whose head is **replicated into
> independently-signed records held outside the trust boundary** — plus a written
> account of exactly which attacks those measures do and do not address, and
> **a power analysis showing which attacks we could not have detected at our
> scale even if we had tried.**

---

## 7. Controls we can demonstrate on demand

Because a threat model that cannot be demonstrated is a document, not a
control. Each of these is a command in the repo, reproducible by a judge in
under a minute:

```bash
# ONE COMMAND. The published FIG. 02 matrix, reproduced with live data.
# Exits nonzero on any mismatch. This is the evidence artefact for the 25%.
python manage.py isolation_proof

# J-1  the check that costs the most points
curl -s -o /dev/null -w '%{http_code}\n' -H 'Cookie: session=<judge_b>' \
  'http://localhost:8080/api/judge/scores?judge=jdg_08'
# expect: 403

# J-3  no leaderboard for a judge while judging is open
curl -s -o /dev/null -w '%{http_code}\n' -H 'Cookie: session=<judge_a>' \
  'http://localhost:8080/api/results'
# expect: 403

# J-2  cross-track isolation, never tested by the official suite
curl -s -o /dev/null -w '%{http_code}\n' -H 'Cookie: session=<judge_a>' \
  'http://localhost:8080/api/projects/prj_03/reviews'
# expect: 403   (judge_a is trk_04, prj_03 is trk_03)

# S-1  the deadline holds
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Cookie: session=<participant>' \
  -H 'Content-Type: application/json' \
  -d '{"title":"probe","summary":"probe"}' \
  'http://localhost:8080/api/projects'
# expect: 403

# V-6  results hidden during the voting window
curl -s -o /dev/null -w '%{http_code}\n' \
  'http://localhost:8080/api/results'
# expect: 403 while results_state = hidden

# Tamper evidence, offline, against a downloaded archive
python manage.py verify_audit   --archive audit-chain.jsonl
# expect: OK: N entries, head <hash>...   (first broken link/gap/edit on failure)

# A published result set is re-derivable years later, by a third party
# with no access to our database
python manage.py verify_results evt_01 --published 2026-03-02T10:00:00Z
# expect: results_hash matches (recomputed from the raw scores in the export)
```

**And the one that is ours.** `manage.py isolation_proof` prints the matrix with
a **status code per cell** (not ✓/✗ — the number is the evidence), asserts
**403 + empty body + no `Location` header** on every denial three separate ways,
prints **visible-of-total row counts** per actor (`3 of 126`) with the scope
reason, and prints the **raw `curl` equivalent of the peer probe** so its output
and the acceptance transcript cannot disagree. Full output shape in `05` §6b.1.

**Each of these is also an automated test, so the claim is enforced rather than
asserted.** The test suite is the control; the document is the explanation.

---

## 8. Reporting a vulnerability

A one-paragraph policy, in the README, that a security-minded organizer will
actually read:

> Security issues are handled as normal pull requests, or privately by email to
> the address in the README, whichever you prefer. Please do not open a public
> issue for a live vulnerability in a running event. There is no bug bounty; we
> are one person after a hackathon, and we would rather fix your report than
> litigate it.
