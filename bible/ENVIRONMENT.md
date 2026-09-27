# ENVIRONMENT.md — what is installed, and what is actually verified

**Purpose:** the same discipline `04` §2.1 applies to census numbers, applied to
**framework behaviour**. Every claim in this folder about how a library behaves
should be a five-line script, not a sentence someone remembered.

That rule has now caught us **eleven** times. Ten were census errors (`README.md`
§ Verification status). The eleventh was the worst of them, because it was about
a **documented default** rather than a number: *"`03` §3.2 said DRF's
`SessionAuthentication` is CSRF-exempt by default. It is not."* That one would
have made the deadline check pass for the wrong reason, invisibly.

**Everything below was executed against the installed stack, not recalled.**

---

## 1. Pinned versions

| Package | Version | Why this one |
|---|---|---|
| **Python** | **3.13.13** | Django 5.2 LTS supports 3.10–**3.13**. Not 3.14 — it is outside 5.2's support guarantee, and 3.13 is exactly what `python:3.13-slim` ships, so local and container match. **A mismatch here means the tests lie.** |
| Django | 5.2.17 | `bible/01` §6. LTS, not 6.1 — the organizers fork this for a decade and a brand-new major is the wrong trade. The resolver reaches for 6.1 by default (DRF 3.18 is tested against it); we pin it back. |
| djangorestframework | 3.18.1 | Works with Django 5.2. Composes with the scoped-accessor layer (`05` §6). |
| drf-spectacular | 0.30.0 | REQ-BONUS-04 API First. **Not free**: pulls `jsonschema`, `uritemplate`, `inflection`, `PyYAML`, `rpds-py`. Still the cheapest +3 on the board. |
| whitenoise | 6.12.0 | Static files from the one container. |
| gunicorn | 26.2.0 | Container only. Marked `sys_platform != "win32"` so it installs in the Linux image and does not break a Windows venv. |
| cryptography | 50.0.1 | Ed25519 / RFC 8032 (`05` §9b). |
| pytest | 9.1.1 | |
| pytest-django | 4.14.0 | |
| hypothesis | 6.168.2 | The isolation invariants (`05` §6b.2). |
| ruff | 0.16.9 | The lint rule forbidding `Review.objects.all()` is a deliverable, not hygiene. |

**28 packages total, 17 of them runtime.** SQLite 3.50.4.

**Deliberately absent, with the reason recorded in `requirements.txt`:** numpy,
scipy, networkx (measured unnecessary — `06` §2.2, §4.3e), celery/redis (a
second service is a binary disqualifier), argon2-cffi (Django 5's default is
correct for this posture), any cloud SDK.

---

## 2. Verified working

Run against the venv, output not paraphrased.

| Claim | Where | Result |
|---|---|---|
| **FTS5 full-text search** — the gallery search | `05` §10, `08` §4 | **PASS.** `CREATE VIRTUAL TABLE … USING fts5` works, `MATCH` returns hits. SQLite 3.50.4. |
| **WAL mode** — the shipped DB mode | `01` §6 | **PASS** on a file-backed DB; `journal_mode` returns `wal`. *(In-memory DBs cannot use WAL — that is a property of `:memory:`, not a defect.)* |
| Foreign keys | `05` §10 | PASS |
| **JSON1** — `JSONField` portable to both engines | `01` §6, `05` | PASS |
| **Ed25519 sign/verify** | `05` §9b | **PASS.** 64-byte signature, 32-byte public key, exactly per RFC 8032. |
| **Ed25519 rejects a tampered payload** | §7 §3.1 | **PASS** — `verify()` raises. Confirmed rather than assumed. |
| Django + DRF + spectacular import together | `01` §6 | PASS |
| `CheckConstraint`, `JSONField`, composite `UniqueConstraint` | `05` §10 | PASS — all portable to SQLite *and* Postgres |
| Default password hasher | `05` §11 | `pbkdf2_sha256`, **1,000,000 iterations**, ~400 ms/hash. Correct + verify both work. |

---

## 3. Verified BROKEN — two findings, both fixed in the bible

### 3.1 ⚠ DRF's `SessionAuthentication` is NOT CSRF-exempt

`03` §3.2 said it was, "by default." **It is not.**

```
>>> from rest_framework.authentication import SessionAuthentication
>>> hasattr(SessionAuthentication, "enforce_csrf")
True
>>> SessionAuthentication.enforce_csrf is None
False
```

DRF defines `enforce_csrf()` and calls it from `authenticate()`. The precise
truth is narrower: **the check runs only for unsafe methods** (`POST`, `PUT`,
`PATCH`, `DELETE`); safe methods skip it.

**Consequence: T1-3 would have passed for the wrong reason.** The checker POSTs
as `participant` expecting any 4xx. A CSRF 403 *is* a 4xx. So the report would
say PASS, the checker would say PASS, and the deadline would never have been
tested. `03` §4.4 already names this trap for the 405 case — it applies here
too.

**Fixed:** `03` §3.2 now carries the verified behaviour, the per-check table,
the explicit `enforce_csrf = None` subclass, and four compensating controls
(`SameSite=Lax`, JSON content-type enforcement, CSRF kept on for HTML paths,
`07` P-1 states the exception). **The decision is to exempt and to say so in
`JUDGING.md`, not in a comment.**

### 3.2 ⚠ Seeding 121 people would take 48 seconds — 4.8× the checker's timeout

`run.py` sets `TIMEOUT = 10`. `03` §4.7's contract ("seeding completes before
the server binds") only protects T1-1 if seeding is *fast enough*.

`fixtures.json` has **121 distinct people** (30 judges + 91 unique member
emails, all disjoint). At ~400 ms per `pbkdf2_sha256` hash, that is **~48
seconds** of seeding, on every cold `compose up`, before gunicorn binds.

**Fixed:** `04` §5.2 and `03` §4.7 now specify that **only the five seeded test
identities get real hashes; the other ~116 get `UNUSABLE_PASSWORD` and cannot
log in** — which is correct, because they are synthetic fixture people, and an
account they cannot use is a smaller liability than one with a guessable
password.

**This is a schema decision, so it belongs in the Block B migration. It is not a
thing to discover at H+13 with a timeout on the clock.**

---

## 4. Operational notes that will cost an hour each if nobody wrote them down

- **`hypothesis.extra.django.models` does not import in a bare Python process.**
  It needs `pytest-django` active, which means **under `pytest` with a configured
  `DJANGO_SETTINGS_MODULE`.** So the Hypothesis model strategies cannot be used
  before the Django project exists. `08` puts the invariants in **Block C**, not
  Block B — that ordering is correct and now has a reason.
- **`hypothesis.extra.django.TestCase`, never `TransactionTestCase`.** The
  Hypothesis docs warn `TransactionTestCase` is "significantly" slower in a loop.
  Bound `max_examples=50` and keep the suite out of the hour-60 critical path.
- **`gunicorn` is marked `sys_platform != "win32"`** so it installs in the Linux
  image without breaking a Windows venv. Do not "fix" this by removing the
  marker.
- **`django.setup()` needs a settings module.** `pytest` will not run until Block
  B creates one. `pyproject.toml` is a placeholder until then.

---

## 5. 🟢 RESOLVED — Docker **is** installed, and it was never findable

```
> docker --version
Docker version 29.6.2, build dfc4efb
> docker compose version
Docker Compose version v5.3.1
```

**This section was "🔴 THE BLOCKER — Docker is not installed" for a whole phase,
and it was the wrong diagnosis.** `docker --version` returned `NOT FOUND`, and
that was read as *Docker is not installed*. Docker was installed and running the
entire time, with its daemon up. That is **F-34**, and the finding that survived
the correction is **F-13**, which is about the deliverable, not the tool.

### What actually happened

Docker Desktop installs **per-user** on this machine:

```
C:\Users\Aalok\AppData\Local\Programs\DockerDesktop\
  Docker Desktop.exe
  frontend\Docker Desktop.exe
  resources\com.docker.backend.exe
  resources\bin\docker.exe          <-- the CLI, 43 MB
  resources\bin\docker-compose.exe
```

That `resources\bin` directory was in **none** of: the in-session PATH, the
persisted **User** PATH, the **Machine** PATH, or `C:\Program Files\Docker\`.
So every standard way of finding `docker` failed, and the one command that would
have disproved "not installed" — looking for the running process — was not run
until later.

> **The lesson, and it is the same one as F-11 and F-28.** A failing command is
> evidence *that a command failed*, not evidence about *why*. There were three
> candidate explanations — not installed / installed elsewhere / not running — and
> two of the three were live. The cheapest disambiguation is
> `Get-Process`, which takes two seconds and would have settled it immediately.

### Fixed

1. Appended `…\DockerDesktop\resources\bin` to the **User** PATH. **`docker` now
   resolves by bare name.** A terminal opened *before* this change keeps its old
   PATH — the justfile also resolves `docker` by absolute path as a fallback, so
   a stale shell cannot break a gate.
2. `just 1.58.0` installed (`winget install --id Casey.Just`). It was named the
   gate command in three files and had never been listed as a prerequisite — **F-35**.
3. `docker pull python:3.13-slim` — digest `sha256:7c61056e…`, 178 MB. Pulled
   before kickoff so the build is not waiting on a network at H+0 — **F-36**.

### Verified working

| | |
|---|---|
| Docker | **29.6.2**, build `dfc4efb` |
| Compose | **v5.3.1** |
| Server | 29.6.2 · `linux/x86_64` · 8 cores · driver `overlayfs` |
| Backend | **WSL2 confirmed** — `docker-desktop` distro on **WSL 2.7.11.0**, kernel 6.18.33.2-2 |
| Daemon | up — `\\.\pipe\docker_engine` and `\\.\pipe\dockerDesktopLinuxEngine` present |
| WSL distros | `Ubuntu` (running, v2) and `docker-desktop` (running, v2) |
| Disk | 114 GB free; 2.48 GB reclaimable images, 1.85 GB build cache |
| Image | `python:3.13-slim` pre-pulled; container reports **Python 3.13.15** |
| Engine RAM | **3.71 GiB** (`MemTotal` 3,982,098,432) — see **F-37**, a watch item not a blocker |

`python tools/verify_spec.py --env` asserts all of this, and is designed to fail
loudly if any of it goes away.

### The other Python — do not skip this one

| Interpreter | Version | Django |
|---|---|---|
| `python` on PATH (`…\WindowsApps\python.exe`) | **3.14.6** | **not installed** |
| `.venv\Scripts\python.exe` | 3.13.13 | 5.2.17 ✓ |
| container `python:3.13-slim` | 3.13.15 | installed at build time |

**Django 5.2.17 declares `Requires-Python: >=3.10` — no upper bound** — so the
version pin looks satisfied on 3.14.6 and will not stop the mistake. A bare
`python run.py .dogfood.toml` in a fresh terminal fails on the first import. Use
`.venv\Scripts\python.exe` explicitly. That is **F-38**, still open, and it is
the one item from this verification that will still bite at hour 40.

### Still true

The venv is for local development and fast tests only, and is **not** a
substitute. The deliverable is a container, and every hour of the 69 spent
debugging a local-only setup is an hour the container never gets tested. **The
break protocol in `08` §15 must be run against the container**, not the venv.

---

## 6. Reproducing this verification

Everything in §2 and §3 is a short script. The principle: **run it, paste the
output, and if it disagrees with the bible, the bible is wrong.** That is the
whole method, and `04` §2.1's two invariants are the same idea applied to counts.

```powershell
# environment
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import django, rest_framework; print(django.get_version(), rest_framework.VERSION)"

# the two findings
#   3.1 CSRF
.\.venv\Scripts\python.exe -c "from rest_framework.authentication import SessionAuthentication as S; print('exempt:', S.enforce_csrf is None)"
#   3.2 seeding cost
.\.venv\Scripts\python.exe -c "import time,django;from django.conf import settings;settings.configure(SECRET_KEY='x',INSTALLED_APPS=['django.contrib.auth']);django.setup();from django.contrib.auth.hashers import make_password;t=time.time();make_password('x');print(round((time.time()-t)*1000),'ms per hash')"
```

**Re-run these at H+0, not just now.** A pin that drifted between setup day and
kickoff is the kind of thing that costs an hour at the worst possible moment.
