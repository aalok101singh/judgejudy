# Judge Judy

A self-hostable submission and judging platform for hackathons. Built for
**DOGFOOD 2026** as a submission *and* as a judging system, because the two
halves share one schema and the judging half is where the hard problems are.

Offline by construction: **one command, no network, no cloud account, no
hosted database, no external API, no API key.**

```
docker compose up
```

That is the whole setup. Then open <http://localhost:8080>.

---

## ⚠ Status: T1 is green, T2 is not built yet

**Read this before judging anything else on this page.** The container, the
healthcheck, the offline guarantee, **the gallery**, **the seeded fixture** and
**the deadline guard** are real, measured and passing. The judge surface is not
built yet.

| | State |
|---|---|
| `docker compose up` → serving page | ✅ **11.6 s** from an empty volume, budget 60 s |
| Boots with `--network none` | ✅ **proved** — healthy at **8.0 s**, four probes pass |
| Healthcheck from a clean volume | ✅ green |
| **Acceptance: T1** (gallery public · fixture projects shown · closed event refuses) | ✅ **3 of 3 PASS** — `run.py` prints `claimed nothing, verified T1` |
| Acceptance: T2 (judge console, peer refusal, export) | ❌ **not built** (FEAT-04/05) |
| Judge console, rubric, assignment | ❌ **not built** (FEAT-04) |
| Isolation enforcement, exports | ❌ **not built** (FEAT-05) |
| Voting, comments, influence report | ❌ **not built** (FEAT-06) |
| Bulk IO, signed records, OpenAPI | ❌ **not built** (FEAT-07) |
| Normalization engine + proof | ❌ **not built** (FEAT-08) |

The numbers above are **generated, not typed**: `just coldstart`,
`just prove-offline` and `just check` re-measure them. Nothing in this README is
a number somebody remembered.

`acceptance-report.txt` is committed with its honest failures rather than a
flattering summary, and the panel runs the identical program. **The tier claim
is made at a scheduled verification break, against what is actually green** —
not here, and not in advance. At this milestone `.dogfood.toml` claims nothing,
and every T2 check reports `FAIL` with a real URL in its message.

**One more thing about that T1 pass, because it is the part worth reading.** The
checker accepts **any** 4xx for "closed event refuses submissions", so a missing
route, a CSRF rejection and a bad password all report PASS. Until this milestone
that is exactly what was happening — the check was green on a 404, and the
deadline guard was never called. It is green now for the right reason, and
`tools/run_acceptance.py` re-sends the checker's own request and requires
`assert_open_for_submission` in the response body, so a CSRF rejection, a 401, a
404 or an emptied `[auth]` block can no longer stand in for the deadline.

---

## What works right now

Four routes, and two of them are features:

| Route | Purpose |
|---|---|
| `/` | **The gallery.** 41 fixture projects, first page in fixture order, 24 per page, server-rendered, no JS. Public. |
| `/projects/new` | **Submit a project.** `GET` is a form; `POST` evaluates the deadline and refuses. The event is born closed, so it refuses — with a 403 that names the guard. |
| `/healthz` | Liveness probe. `?deep=1` also checks the database. |
| `/admin/` | Django admin. |

Plus the seed and the harness:

```bash
docker compose logs portal   # the census, the anomalies, and the [auth] block
```

The container **seeds itself on every boot** — `load_fixtures` runs between
`collectstatic` and gunicorn binding, so nothing is half-initialised when the
port opens — and prints its own reconciliation: every table's row count, both
census invariants, and the six awkward things in the fixture it deliberately
kept (the duplicate submission, the nine dual-track judges, the 51 empty
comments, the team names that collapse onto one slug). `verify_census`
re-derives the same numbers from `fixtures.json` and **exits non-zero on a
disagreement**.

Plus the harness: `just check` runs the whole gate, and
`tools/verify_spec.py` re-derives 67 numbers from the organizers' own files.

---

## The gate

```bash
just              # list every recipe
just doctor       # is the toolchain intact? (interpreter, Docker, just)
just check        # THE GATE — clean volume, build, up, checks, proofs, suite
just spec         # the 67-check spec gate; stdlib only, no Docker, no venv
just coldstart    # measure a cold start against the 60 s budget
just prove-offline # boot the image with --network none and probe it
just mutation-test # corrupt 18 things on purpose; every one must be caught
just accept       # the organizers' checker, against the running container
just lint         # ruff + formatter + the isolation rule (JJ01)
just logs         # follow the container
just clean        # down -v: a real reset
```

`just check` is the only command a reviewer needs. It steps through the spec
gate, a clean `down -v`, the build, `up --wait`, the organizers' checker, the
isolation proof, the census, and the test suite. `just prove-offline` and
`just mutation-test` are **not** in it — they each need a clean volume, and
`check` has to stay the one command — so they are run at every verification
break.

### Why the gate is not just `run.py`

**`run.py` always exits 0.** It prints `FAIL` and returns 0, in every
situation, by design — it is the same program for every team in the
hackathon. A `just check` that gated on its exit code would report a green
checkpoint for a completely broken portal.

So `tools/run_acceptance.py` runs it unmodified, prints its output verbatim,
and counts the `PASS`/`FAIL` markers **in the body**. The count is read out of
the real report rather than recomputed, so the wrapper cannot disagree with the
program it wraps.

It also holds the report to **two** further things, and the second one is the
interesting one.

**1. A ratchet.** Every check carries an expectation in
`tools/expected_checks.json`. Expected-to-pass-and-failed is red. Expected-to-
fail-and-passed is **also** red, because a stale expectation teaches a reader to
discount the file.

**2. Preconditions — a `PASS` that does not test what it names is a false pass,
and it fails the gate.** The checker accepts any 4xx for the deadline check, so
until now a 404, a 405, a CSRF rejection and a bad password all reported PASS.
The gate now:

* probes whether the route exists at all, **and**
* **re-sends the checker's own request** — same method, same JSON body, and the
  same `[auth]` credential read out of the same `.dogfood.toml` the checker
  read — and requires `assert_open_for_submission` in the **response body**.

An emptied `[auth]` value is caught there, *before a request is even sent*,
because the probe cannot present the credential the checker used. That is the
case that is invisible from inside the portal and the case that mattered most.

### About the demo credentials, plainly

`.dogfood.toml`'s `[auth]` values are HMAC-SHA256-signed tokens
(`Authorization: JJ1.<hmac>.<email>`) and **the signing key is published in this
repository**, in `src/reviewer/accounts/demo_tokens.py`. So: **anyone holding
this repo can mint a token for any of the 121 fixture identities.** That is a
deliberate trade, not an oversight, and it is worth stating rather than
discovering:

* The alternative — signing with `SECRET_KEY` — breaks `down -v`, because that
  key is generated per volume. The committed `.dogfood.toml` would go stale on
  every reset and the participant probe would **silently become an anonymous
  request**, which is a check passing for the wrong reason. That is the exact
  failure this project treats as its worst one, and it is not worth trading for
  a cosmetic improvement.
* The organizers' own example uses a guessable fixed session value, so this is
  the same posture.
* The real secrets — the signed judge records in T4 — come from
  `cryptography`'s own key management, not from this token.
* Set `DJUDGE_DEMO_TOKEN_KEY` to rotate it. That invalidates every pasted value,
  and `docker compose logs portal` prints the new ones.

**The five demo identities are three of the fixture's 121 people plus two
portal-created organizers**, and the split is deliberate: the fixture's census is
a number a panel can check without running anything, so six synthetic accounts
would have quietly changed it. The identities are *derived* from the fixture by a
stated rule, not hard-coded, and `tests/test_demo_credentials.py` asserts the
committed values against whatever the rule currently produces.

---

## Two environment traps, both already paid for once

These are documented because they cost this project real time, and because
both of them produce a *misleading* error rather than an honest one.

**`docker` is installed per-user.** It lives at
`…\AppData\Local\Programs\DockerDesktop\resources\bin\`, which was in no PATH
at all. `docker --version` returned `NOT FOUND` while the daemon was up and
healthy, and "not installed" was the wrong conclusion for an entire phase of
the build. `tools/docker.py` resolves the binary by absolute path first, and
`just doctor` tells you which `docker` it found and how.

> A failing command is evidence that a command failed, not evidence about why.

**The ambient `python` is 3.14.6 and has no Django.** The venv is 3.13.13.
Django 5.2 declares `Requires-Python: >=3.10` with no upper bound, so the pin
cannot catch this. Every recipe names `.venv\Scripts\python.exe` explicitly and
`tools/guard_interpreter.py` asserts the version.

---

## Stack

| | |
|---|---|
| Python | 3.13.13 (venv) · 3.13.15 (container, `python:3.13-slim` pinned by digest) |
| Django | 5.2 LTS — LTS, not 6.1, because this is meant to be forked and run for a decade |
| DRF | 3.18.1 |
| drf-spectacular | 0.30.0 |
| whitenoise · gunicorn · cryptography | 6.12.0 · 26.2.0 · 50.0.1 |
| Database | SQLite, WAL, on a named volume |

**17 runtime packages. Deliberately absent, with reasons in
[`requirements.txt`](requirements.txt):** numpy, scipy, networkx (measured
unnecessary — 126 rows, a 40-node graph), celery/redis (a second service is a
disqualification), any cloud SDK.

The local venv is a fast inner loop and **not a substitute for the container**.
The deliverable is the container.

---

## Repository layout

```
.dogfood.toml          routes + honest tier claims, read by the checker
acceptance-report.txt  the checker's output, committed whatever it says
docker-compose.yml     one service, one volume, one healthcheck
Dockerfile             pinned base digest, non-root, runtime deps only
justfile               the gate
src/judge_judy/        settings, urls, wsgi, the healthcheck
src/reviewer/          twelve domain apps + isolation/ (the accessor) and
                       importer/ (census, demo identities, loader) — the two
                       non-app packages hold no model, and say so
src/templates/         server-rendered HTML
src/static/            one stylesheet, no CDN, no build step
docker/entrypoint.sh   migrate -> collectstatic -> seed -> THEN bind the port
docker/healthcheck.py  the single definition of "healthy"
tests/                 the suite, including the four Hypothesis invariants
tools/                 the gates: spec verify, acceptance wrapper, coldstart,
                       offline proof, interpreter guard, docker resolver,
                       mutation test, isolation lint (JJ01)
blueprint/             the plan, the ledger, the in-flight feature
bible/                 330 KB of research. Read by section, never whole.
```

`run.py` and `fixtures.json` are the organizers' files. **`run.py` is
unmodified** — the panel runs the identical program, and any edit to it would
invalidate every result in `acceptance-report.txt`.

---

## Documents

| | |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | the container, the boot order, the layering, the decisions |
| [`DATA-MODEL.md`](DATA-MODEL.md) | the schema and the fixtures it holds *(FEAT-02, corrected by FEAT-03)* |
| [`JUDGING.md`](JUDGING.md) | rubric, assignment, isolation, normalization *(FEAT-04…08)* |
| [`blueprint/context/findings.md`](blueprint/context/findings.md) | **55 findings**: what we got wrong, what we declined to fix, and why |

### What we did not build, and why

Recorded rather than quietly omitted, because a gap you can see is better
than one you discover:

- **Webhook delivery** — models and a `501` stub ship; delivery, retries and
  HMAC verification do not. 2 hours, zero points on all four criteria, and
  SSRF via a webhook URL is a real bug class to write from scratch under time
  pressure.
- **No Merkle transparency log** — a hash chain plus one published chain head
  replicated into every signed judge record is strictly stronger here, for a
  third of the code. Certificate transparency's value is *witnessing* and this
  project has no witness.
- **No IRT/MFRM, no TrueSkill** — measured to lose. See `bible/06` §4.3e.
- **No Postgres RLS, Casbin or OPA** — a scoped-accessor layer is the portable
  equivalent and keeps the rules in one place.

---

## Licence

MIT. See [`LICENSE`](LICENSE).
