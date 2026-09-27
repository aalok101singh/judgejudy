# 03 · The Acceptance Contract

**Purpose:** a line-referenced reverse engineering of `run.py`, the program that
produces the artefact a judge reads before anything else. 268 lines,
standard library only, identical for all ~40 teams.

Everything in this document was read out of the source, not inferred. Where a
line number is given, it refers to the local copy at
`C:\Users\Aalok\Desktop\Judge Judy\run.py`.

---

## 1. How the contract is formed

Three parties, four files:

```
fixtures.json ──▶ your portal ──▶ HTTP on localhost:8080
                                     ▲
.dogfood.toml ──▶ run.py ────────────┘
                     │
                     ▼
             acceptance-report.txt   ← committed; read first by every judge
```

The spec is explicit about the philosophy: forty teams, forty stacks, so
*"If we demanded that everyone expose `/api/v1/projects` with a fixed JSON
shape, we would be designing your API for you, and that is your work, not
ours."* Hence `.dogfood.toml`: we declare our own routes and our own
credentials, and the checker binds to them.

**The checker never logs in.** Line 118 of `spec.md`: *"Logging in is the single
thing no two stacks do alike."* It attaches the headers we hand it and nothing
more. Our login page can be however we like; the only requirement is that the
four headers in `[auth]` are real and role-bearing.

---

## 2. The seven checks, in issue order

Numbering used consistently across this bible. `run.py` prints them in this
order (lines 101–187).

| # | Tier | Label | Method | Route key | Auth header | Expects | Lines |
|---|---|---|---|---|---|---|---|
| T1-1 | T1 | gallery is public | GET | `gallery` | *none* | `200` | 102–110 |
| T1-2 | T1 | project from fixtures shown | GET | `gallery` | *none* | a fixture title in the body | 112–126 |
| T1-3 | T1 | closed event refuses submissions | POST | `submit` | `participant` | `4xx` (400≤s<500) | 128–141 |
| T2-4 | T2 | judge sees own scores | GET | `judge_scores` | `judge_a` | `200` | 144–150 |
| **T2-5** | T2 | **judge cannot see peer scores** | GET | `peer_scores` | `judge_b` | **`401` or `403`** | **153–163** |
| T2-6 | T2 | participant blocked | GET | `judge_scores` | `participant` | `401` or `403` | 165–172 |
| T2-7 | T2 | csv export works | GET | `csv_export` | `organizer` | `200` and `,` in line 1 | 174–185 |

### 2.1 Request mechanics (lines 60–75)

```python
req = urllib.request.Request(url, method=method)
if header:
    name, _, value = header.partition(":")
    req.add_header(name.strip(), value.strip())
```

Consequences:

- The header string is split on the **first** colon only. `Cookie: session=x`
  works. A value containing a colon is fine.
- `Content-Type: application/json` and a JSON body are set automatically for
  POST (line 71). We do not need to handle form encoding.
- **`urllib.request.urlopen` is used with default handlers, which means
  `HTTPRedirectHandler` is active. 301, 302, 303, 307 and 308 are all followed
  transparently, and the returned status is the status of the *final* URL.**
  This is the single most dangerous property in the file. See §4.1.
- `TIMEOUT = 10` seconds (line 57). Every request must answer in under ten.
  **This is tighter than it looks, and §4.7 now carries the arithmetic.**
- On a transport failure the function returns `(0, "<ExceptionType>: <msg>")`
  (line 75) rather than raising — so a dead portal reports `got no response`,
  not a crash.
- No session, no cookie jar, no connection reuse. Seven independent requests.

### 2.2 Route resolution (lines 96–97)

```python
def url(key, suffix=""):
    return base + routes.get(key, "")
```

**A missing key yields `base + ""`, i.e. a request to the site root.** There is
no validation that the config is complete, and no warning. A typo in
`judge_scores` produces a confusing `got 200/403` on `/` rather than an error
about the config. Every key must be present and correct.

`base` is `cfg["portal"]["base_url"].rstrip("/")` (line 92). A trailing slash in
the TOML is handled.

### 2.3 Fixture discovery (lines 195–211)

Search order: explicit `--fixtures`, then `fixtures.json` in the CWD, then
beside `run.py`, then beside the config, then `beside_config/data/fixtures.json`.
The path actually loaded is printed in the report header, so a mis-seeded run is
visible at a glance.

If no fixture is found, the program prints a note and **T1-2 cannot pass** —
with no fixture there are no titles to look for. Keep `fixtures.json` beside
`run.py` in the repo and this cannot happen.

Only the **first three** projects' titles are used (lines 190–192,
`fixture_titles(fixture, n=3)`).

### 2.4 Verdicts and the prefix lock (lines 245–254)

```python
verified = [t for t in TIERS if any(c.tier == t for c in checks)
            and all(c.ok for c in checks if c.tier == t)]
solid = []
for t in TIERS:
    if t in verified: solid.append(t)
    else: break
```

Three facts, all important:

1. A tier is *verified* only if **every** check at that tier passed.
2. `solid` is **prefix-locked**: the first tier that fails to verify ends the
   list. A hypothetical T3 failure would cap the report at T2 even with a
   perfect T4. (Only T1 and T2 are actually implemented, so in practice the cap
   is T2 — but the logic is the logic, and the docs describe it as a ladder.)
3. The report prints `claimed …, verified …` and then, lines 260–262, an
   explicit `note: claimed but not verified: …`.

Overclaiming is the only way to lose points for free, and it is mechanically
visible in the committed artefact.

---

## 3. `.dogfood.toml` — the exact shape

The parser has two implementations and this matters.

- **Python ≥ 3.11**: `tomllib` (line 15). Real TOML, strict.
- **Older**: `parse_toml` (lines 23–46), a hand-rolled subset.

The hand-rolled parser has two behaviours to respect even though most judges
will run 3.11+:

- **Line 31: `line = raw.split("#")[0].strip()` — everything after a `#` is
  discarded, including inside a quoted string.** A `#` in a `pitch` value would
  silently truncate the string on older Pythons. Avoid `#` in values entirely.
- Only `[section]` headers, `key = "string"`, and `key = ["a", "b"]` are
  understood. **No nested tables, no bare keys, no multi-line arrays, no
  integers-as-arrays, no dotted keys.** Keep it flat.
- `value.strip().strip('"').strip("'")` — quotes are stripped, so an unquoted
  value also works.

**The safe subset: `[portal]`, `[tiers]`, `[auth]`, `[routes]`, string values,
one-line string arrays, `#` comments on their own lines.** Our file will be
valid under both parsers, and we will verify it under both by running the
checker on 3.11+ and on an older interpreter if one is available.

### 3.1 Target file

```toml
# DOGFOOD 2026 · tier claim and route map
# Regenerate [auth] from the credentials the seed step prints on boot.

[portal]
base_url = "http://localhost:8080"

[tiers]
claimed = ["T1", "T2", "T3", "T4"]
pitch = "One line. What the portal is and the one decision it is built around."

[auth]
organizer   = "Cookie: sessiondogfoodorg01"
judge_a     = "Cookie: sessiondogfoodjda01"
judge_b     = "Cookie: sessiondogfoodjdb01"
participant = "Cookie: sessiondogfoodprt01"

[routes]
gallery      = "/projects"
submit       = "/api/projects"
judge_scores = "/api/judge/scores"
peer_scores  = "/api/judge/scores?judge=jdg_08"
csv_export   = "/api/export/results.csv"
```

Notes on the choices, all deliberate:

- `peer_scores` points at `?judge=jdg_08` — `jdg_08` is a real fixture judge
  with three reviews. It must be a URL that **would return another judge's
  scores if the check were absent**, i.e. one our API genuinely supports, so the
  403 is a refusal rather than a 404 for a route that never existed. Declaring
  a nonexistent path would pass the check while proving nothing, and would be
  exactly the kind of thing a careful judge notices. `spec.md` line 122 says
  plainly: *"This is the url that would return judge A's scores."*
- `submit` is a `POST`-capable API route. The spec's example uses
  `/projects/new`, an HTML form page, and a `405` would technically satisfy the
  4xx assertion — but a 405 on a form page means the check is passing for the
  wrong reason. Ours will be a real API endpoint that genuinely evaluates the
  deadline and genuinely returns 403.
- `csv_export` is `.csv` so the route is self-describing, and it returns a
  comma-bearing header row on line 1 by construction.
- Session values are stable strings, printed by the seed step. They are not
  secrets — this is a local demo fixture. Say so in the README rather than
  pretending otherwise.

### 3.2 Why the auth values are cookies and not bearer tokens

Either works: the parser splits on the first colon and attaches whatever we
give it. Cookies are the natural fit for Django sessions and mean the same
header string works for the browser demo and for the checker.

> ### ⚠ CORRECTION — verified against the installed DRF 3.18.1, not recalled
>
> An earlier revision of this section said: *"exempt DRF's `SessionAuthentication`
> from CSRF (**DRF does this by default for session auth**)."*
>
> **That is false, and it would have bitten us at hour 66.** DRF's
> `SessionAuthentication` **does** enforce CSRF. It defines `enforce_csrf()` and
> calls it from `authenticate()`. Verified:
>
> ```
> >>> from rest_framework.authentication import SessionAuthentication
> >>> hasattr(SessionAuthentication, "enforce_csrf")
> True
> >>> SessionAuthentication.enforce_csrf is None
> False
> ```
>
> The precise truth is narrower and less comfortable: **DRF's CSRF check only
> runs for unsafe methods** (`POST`, `PUT`, `PATCH`, `DELETE`). Safe methods
> (`GET`, `HEAD`, `OPTIONS`) skip it.
>
> **What that means for each check, precisely:**

| Check | Method | CSRF enforced? | Consequence |
|---|---|---|---|
| T1-1, T1-2 | `GET` | no | fine |
| T2-4 judge sees own scores | `GET` | no | fine |
| T2-5, T2-6 | `GET` | no | fine |
| T2-7 csv export | `GET` | no | fine |
| **T1-3 closed event refuses submissions** | **`POST`** | **YES** | **⚠ A CSRF 403 is a 4xx, so this check would PASS — for the wrong reason.** |

> **T1-3 passing on a CSRF rejection instead of a deadline rejection is exactly
> the failure §4.4 already names for the 405 case, and it is the most expensive
> kind of quiet failure we have: the report says PASS, the checker says PASS,
> and a judge reading `acceptance-report.txt` concludes the deadline holds. It
> would not.**

**The decision, and it is ours to make deliberately:**

```
# judging/api/auth.py
class CookieOrTokenSessionAuthentication(SessionAuthentication):
    """Session auth that does NOT enforce CSRF.

    Deliberate. See bible/03 3.2. The acceptance checker attaches a session
    cookie to a POST with no CSRF token (run.py line 71 sets only
    Content-Type), and a CSRF 403 satisfies T1-3's "expect 4xx" for the wrong
    reason. The cost of exempting is that the API is CSRF-open for
    cookie-authenticated unsafe methods.
    """
    enforce_csrf = None
```

**And then the compensating controls, because a CSRF-open API is a real cost and
we are not pretending otherwise:**

1. **`SameSite=Lax` on the session cookie** (`07` §3.4 P-2). This is the primary
   defence against cross-site form POSTs and it does not depend on DRF.
2. **All unsafe API methods require an explicit `X-Requested-With` or a
   `Content-Type: application/json` check** — cheap, and it is what actually
   blocks the HTML-form CSRF vector, because a cross-origin HTML form cannot set
   either.
3. **HTML form paths keep full Django CSRF protection.** We are exempting the
   *API*, not the site.
4. **`07` §3.4 P-1 states the exception explicitly**, with the reason, rather
   than shipping an undocumented hole.

**Alternatively** — and this is defensible too — leave CSRF enforced and accept
that T1-3 passes on a CSRF 403, *provided* the isolation transcript in the repo
shows the real deadline 403 from a browser with a token. **We choose the
exemption** because a checker that passes for the wrong reason is a liability we
do not need, and because the `SameSite` + content-type controls above close the
gap it opens. But the decision goes in `JUDGING.md` and `07`, not in a comment.

> **The transferable lesson, and it is the eleventh trap:** *verified against the
> installed library, not recalled.* Every framework-behaviour claim in this
> document should be a five-line script, not a sentence someone remembered. We
> have now been wrong about a documented DRF default, and it was a scored check.

---

## 4. The seven silent-failure traps

Each of these produces a FAIL, or a falsely-passing check, with no hint from
the program's own diagnostics.

### 4.1 Redirects are followed — the big one

`urlopen` follows 3xx. So:

| Implementation | Peer-scores probe as `judge_b` | Result |
|---|---|---|
| `302 → /login?next=…` then `200` login page | final status `200` | **FAIL** — "the backend returned another judge's scores" |
| `200` with a filtered, empty JSON array | `200` | **FAIL** |
| `403` with a JSON error body | `403` | **PASS** |
| `404` because the route does not exist | `404` | **FAIL** |

**Hard requirement: every denied request returns a literal `401` or `403` with
no redirect.** DRF does this by default for `PermissionDenied` /
`NotAuthenticated` (it returns 403/401 directly), which is one more reason the
framework choice is the right one. But it must be verified with a raw `curl`,
not through a session-aware client that follows redirects:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Cookie: session=<judge_b>' \
  'http://localhost:8080/api/judge/scores?judge=jdg_08'
# must print 403
```

This transcript goes in the repo. It is the evidence artefact for REQ-ZERO-05
and for T2-5, and it is the shot in the demo video.

### 4.2 The gallery grep only looks at the first three projects

`fixture_titles(fixture, n=3)` takes `projects[:3]`. The titles are
**`Glass Signal`, `Small Meadow`, `Deep Compass`**.

- The comparison is `any(...)` and case-insensitive: `t.lower() in haystack`,
  where `haystack` is the whole lowercased response body. One match is enough.
- The fixture's project order is fixed, so we know exactly which three titles
  count. Sorting our gallery by title or by track can push all three off page
  one, and the checker's own failure message warns about this (line 123).
- Any of the three is sufficient. **The cheapest robust fix: keep the first
  page unsorted in fixture order and page at 24+, so all three appear.** Even
  better: make the default gallery ordering stable and documented, and assert in
  our own test suite that at least one of the first three fixture titles is on
  page one.
- The response must be HTML we render server-side, or a route that includes the
  titles in the body. A client-side-only gallery that fetches after load will
  fail, because `urlopen` does not run JavaScript. **This rules out an SPA-only
  gallery route.** Server-rendered, or a route that returns the titles inline.

### 4.3 A missing `[routes]` key silently retargets the site root

Covered in §2.2. Symptom: `GET http://localhost:8080/` appears in a failure
message where a specific route was expected. Fix: validate the TOML ourselves —
assert all five route keys are non-empty before running the checker.

### 4.4 `POST` to an HTML form route may pass for the wrong reason

T1-3 accepts any 4xx. A framework returning `405 Method Not Allowed` for a
`GET`-only page satisfies it. That is a *pass* that proves nothing about
deadline enforcement, and a judge reading `JUDGING.md`/`ARCHITECTURE.md` will
find out. Our `submit` route accepts `POST` and enforces the deadline itself.

### 4.5 The CSV assertion is only a comma in the first line

```python
first_line = body.splitlines()[0] if body.splitlines() else ""
c.ok = status == 200 and "," in first_line
```

- Line 1 must be the header row and must contain a comma. A JSON body with no
  newline fails. An empty body fails. A header row without commas fails.
- The `Content-Type` is not checked, so `text/csv` is optional — but send it.
- Multi-line values containing newlines are fine, since only line 1 is read.
- Serve it from a streaming response so a 40-project export is not buffered
  into memory, and so the header row is emitted first.

### 4.6 The `#` comment-stripping fallback parser

Covered in §3. Avoid `#` in any value. Our `pitch` will not contain one.
Verified by running the checker under both parsers.

### 4.7 Ten-second timeout, seven cold requests — and a seeding bill that does not fit

`TIMEOUT = 10`. The first request after boot competes with migrations, seeding
and worker startup. If seeding happens in the entrypoint and the checker is run
immediately, T1-1 can time out. **The contract we adopt: the container is only
considered up once the HTTP port is serving, and seeding completes before the
server binds.** `docker compose up` should return to a prompt with a portal
already answering, and the seed step prints the credentials last.

> ### ⚠ The seeding bill, measured — and it does not fit in 10 seconds
>
> The contract above says "seeding completes before the server binds," which
> protects T1-1 **only if seeding is fast enough that a judge running the
> checker immediately afterwards still has the port open.** It is not fast
> enough by default, and the reason is password hashing.
>
> **Measured on the installed stack** (Django 5.2.17, `pbkdf2_sha256`,
> **1,000,000 iterations**, ~**400 ms per hash**):
>
> | | count | hashing cost |
> |---|---|---|
> | People in `fixtures.json` | **121** (30 judges + 91 unique member emails, all disjoint — `04` §1) | **~48 s** |
> | Seeded identities that actually log in | **5** (`04` §5.2) | **~2 s** |
>
> **48 seconds is 4.8× the timeout.** And it is worse than that in practice: the
> hash cost is inside a single `manage.py` process that gunicorn waits on, so
> every `compose up` on a cold volume pays it.
>
> **The fix, and it is a schema decision so it belongs in Block B, not
> discovered at H+13:**
>
> 1. **The other ~116 fixture people get `password=UNUSABLE_PASSWORD`** (or
>    `None` on a field we allow to be null). They exist as `TeamMembership`
>    participants and judge records. **They do not have accounts and cannot
>    log in** — which is correct, because they are synthetic.
> 2. **Only the five seeded test identities get a real hash**, and they are
>    created with `set_unusable_password()` then one explicit `check_password`
>    in the loader's self-test, rather than five redundant hashes.
> 3. **Alternative if we want it even cheaper:** compute one hash at seed time
>    and reuse the string for all five, since they are documented non-secret
>    demo credentials anyway (`04` §5.2, `07` §3.4 P-12).
>
> **Cost of the fix: one field default and three lines in the loader. Cost of
> not fixing it: the acceptance checker times out on T1-1 and we do not know
> whether it is our fault, the spec's fault, or the fixture's.**

---

## 5. The report

`python3 run.py .dogfood.toml > acceptance-report.txt` (spec line 269).

Expected shape on a fully green run:

```
DOGFOOD 2026 acceptance report
portal: http://localhost:8080
claimed: T1 T2 T3 T4
fixtures: fixtures.json

T1  gallery is public ................. PASS
T1  project from fixtures shown ....... PASS
T1  closed event refuses submissions .. PASS
T2  judge sees own scores ............. PASS
T2  judge cannot see peer scores ...... PASS
T2  participant blocked ............... PASS
T2  csv export works .................. PASS

claimed T1 T2 T3 T4, verified T1 T2
```

Read the last line carefully. It will say `verified T1 T2` **even on a flawless
build**, because `run.py` implements checks for T1 and T2 only. Anyone who
misreads this as a T3/T4 failure has misread the tool. `README.md` must state
this explicitly, or it looks like a gap. Our own extended suite covers the T3
and T4 requirements the official one does not, and we commit its output too, as
a clearly-labelled separate file — never mixed into `acceptance-report.txt`.

---

## 6. Pre-submission checklist

Run in order. Any red line is a blocker.

**Config**
- [ ] `.dogfood.toml` at repo root, parses under `tomllib` **and** the fallback parser
- [ ] All five `[routes]` keys present, non-empty, and each is a real route in our app
- [ ] `base_url` is exactly where compose publishes the app, with no trailing path
- [ ] No `#` inside any value
- [ ] `claimed` matches what we actually built, per the gate in `08`

**Credentials**
- [ ] All four `[auth]` headers are current, produced by this build's seed step
- [ ] `organizer` is an organizer, `judge_a`/`judge_b` are **two different judges with reviews**, `participant` is a participant and not a judge
- [ ] `judge_b` differs from `judge_a` in identity, not just in cookie value
- [ ] Values contain no characters needing TOML escaping

**Behaviour, verified by hand before trusting the checker**
- [ ] `curl` gallery unauthenticated → `200`, body contains a first-three fixture title
- [ ] `curl` `peer_scores` as `judge_b` → `403` and **no redirect** (`curl` without `-L` by definition)
- [ ] `curl` `judge_scores` as `judge_a` → `200` with that judge's own rows
- [ ] `curl` `judge_scores` as `participant` → `403`
- [ ] `POST` `submit` as `participant` → `403` from the deadline check, not a 405 from routing
- [ ] `curl` `csv_export` as `organizer` → `200`, line 1 contains a comma
- [ ] A judge requesting **another track's** review → `403` (never tested by the checker; we enforce anyway)
- [ ] A judge requesting the **aggregate leaderboard** mid-window → `403` (never tested; we enforce anyway)

**Infrastructure**
- [ ] `docker compose down -v` then `up` from a clean clone, **network disabled** → seeded portal
- [ ] Portal answers on the first request after `up` returns (seeding precedes bind)
- [ ] No required environment variables
- [ ] No outbound network call in any request path
- [ ] `fixtures.json` committed beside `run.py`; a second `down -v && up` is idempotent

**Report**
- [ ] `acceptance-report.txt` produced by redirection, not edited — `git diff` on it after regeneration must be empty
- [ ] Header shows the expected `fixtures:` path
- [ ] `claimed`/`verified` gap, if any, is explained in `README.md` in our own words
- [ ] Our own extended suite output committed as a separate, clearly-named file

**Repository**
- [ ] `README.md`, `ARCHITECTURE.md`, `DATA-MODEL.md`, `JUDGING.md`, `LICENSE` (MIT) all present
- [ ] Demo video recorded and linked
- [ ] Repo public, contact address in the README
- [ ] No secrets, no `.env` with real values, no credentials that matter (fixture sessions are not secrets — say so)

---

## 7. Design rules this contract imposes on the codebase

The checker is a sample of our API's contract, and if we design the API to
satisfy it honestly, several requirements fall out for free.

1. **Denied means `403`, never a redirect.** A blanket rule in the exception
   handler: any authorization failure on an API path returns 403 with a JSON
   body and no `Location` header.
2. **The gallery must be server-rendered.** Not a preference — `urlopen` does
   not execute JavaScript, so a client-fetched gallery cannot pass T1-2.
3. **A judge-scoped scores endpoint is mandatory**, and its peer-scoped sibling
   must exist and be refused. We build the honest pair, not just the refusal.
4. **Every export starts with a header row.** One shared CSV writer, one
   convention.
5. **Deadline enforcement lives in the write path, not the form.** A single
   guard in the project-creation service, called by every entry point — API,
   admin, bulk import. The checker is testing the same guard our own code
   depends on.
6. **Seeding is idempotent and runs before the server binds.** Two
   `compose up`s produce the same state; the checker never sees a half-seeded
   portal.
