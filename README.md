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

## ⚠ Status: this is the skeleton milestone (FEAT-01)

**Read this before judging anything else on this page.** The container,
the healthcheck, the offline guarantee and the acceptance harness are real,
measured and passing. The features they host are not built yet.

| | State |
|---|---|
| `docker compose up` → serving page | ✅ **6.2 s** from an empty volume, budget 60 s |
| Boots with `--network none` | ✅ **proved** — 4.0 s, four probes pass |
| Healthcheck from a clean volume | ✅ green |
| Gallery, login, teams, submissions | ❌ **not built** (FEAT-03) |
| Judge console, rubric, assignment | ❌ **not built** (FEAT-04) |
| Isolation enforcement, exports | ❌ **not built** (FEAT-05) |
| Voting, comments, influence report | ❌ **not built** (FEAT-06) |
| Bulk IO, signed records, OpenAPI | ❌ **not built** (FEAT-07) |
| Normalization engine + proof | ❌ **not built** (FEAT-08) |

The two numbers above are **generated, not typed**: `just coldstart` and
`just prove-offline` re-measure them. Nothing in this README is a number
somebody remembered.

`.dogfood.toml` therefore claims nothing yet, and `acceptance-report.txt` is
committed with its honest failures rather than a flattering summary. The tier
claim is made at a scheduled verification break, against what is actually
green — not here, and not in advance.

---

## What works right now

Three routes, and none of them is a feature:

| Route | Purpose |
|---|---|
| `/` | Landing page. Server-rendered, one stylesheet, no JS. |
| `/healthz` | Liveness probe. `?deep=1` also checks the database. |
| `/admin/` | Django admin. |

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
just logs         # follow the container
just clean        # down -v: a real reset
```

`just check` is the only command a reviewer needs. It steps through the spec
gate, a clean `down -v`, the build, `up --wait`, the organizers' checker, the
isolation proof, the census, and the test suite.

### Why the gate is not just `run.py`

**`run.py` always exits 0.** It prints `FAIL` and returns 0, in every
situation, by design — it is the same program for every team in the
hackathon. A `just check` that gated on its exit code would report a green
checkpoint for a completely broken portal.

So `tools/run_acceptance.py` runs it unmodified, prints its output verbatim,
and counts the `PASS`/`FAIL` markers **in the body**. The count is read out of
the real report rather than recomputed, so the wrapper cannot disagree with the
program it wraps.

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
src/judge_judy/        settings, urls, wsgi, the two project-level views
src/templates/         server-rendered HTML
src/static/            one stylesheet, no CDN, no build step
docker/entrypoint.sh   migrate -> collectstatic -> seed -> THEN bind the port
docker/healthcheck.py  the single definition of "healthy"
tests/                 the suite
tools/                 the gates: spec verify, acceptance wrapper, coldstart,
                       offline proof, interpreter guard, docker resolver
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
| [`DATA-MODEL.md`](DATA-MODEL.md) | the schema and the fixtures it holds *(FEAT-02)* |
| [`JUDGING.md`](JUDGING.md) | rubric, assignment, isolation, normalization *(FEAT-04…08)* |
| [`blueprint/context/findings.md`](blueprint/context/findings.md) | **39 findings**: what we got wrong, what we declined to fix, and why |

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
