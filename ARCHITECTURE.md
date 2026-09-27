# Architecture

> **Status: FEAT-01, the skeleton.** The container, the boot order, the
> layering and the health contract below are built, measured and shipping. The
> application layers underneath are named and decided; they are not written yet,
> and this document says which is which so a reviewer is never misled.

---

## 1. The shape of it

```
                        docker compose up
                               │
                               ▼
        ┌──────────────────────────────────────────────────┐
        │  python:3.13-slim  (pinned by digest)            │
        │  uid 10001, non-root, no shell                    │
        │                                                  │
        │  entrypoint.sh                                    │
        │    1. migrate --noinput                          │
        │    2. collectstatic --noinput                    │
        │    3. load_fixtures          (FEAT-03)           │
        │    4. gunicorn  2 workers × 2 threads            │
        │                                                  │
        │  /app/src/judge_judy/     settings, urls, wsgi   │
        │  /app/src/reviewer/        ← the application     │
        │  /app/data/                ← named volume        │
        │      instance/db.sqlite3   WAL                   │
        │      media/  staticfiles/                        │
        │                                                  │
        │  whitenoise   static files, no CDN               │
        │  cryptography Ed25519 (FEAT-07)                  │
        └──────────────────────────────────────────────────┘
```

**One container. One process manager. One volume.** No redis, no Celery, no
managed database, no object store — a second service is a disqualification, and
every one of them is a thing that cannot start with the network off.

---

## 2. The boot order is a contract, not a preference

```
migrate → collectstatic → seed → gunicorn binds
```

**Nothing binds the port until the database is ready.** This is not tidiness.
The organizers' checker has a **10-second timeout per request**
(`run.py: TIMEOUT = 10`). If gunicorn accepts a connection before seeding
finishes, the checker's first request races the loader, gets an empty gallery,
and T1-2 fails for a reason that has nothing to do with the portal's logic.
A green report must mean the portal was ready, not that it started first.

The same 10 seconds dictates the seeding budget. `fixtures.json` contains **121
distinct people**. At roughly 400 ms per `pbkdf2_sha256` hash, hashing all of
them costs **~48 seconds — 4.8× the checker's timeout**, inside the process
gunicorn is waiting on. So only the **five seeded test identities** get a real
password hash; the other ~116 get `UNUSABLE_PASSWORD` and cannot log in. They
are synthetic fixture people, and an account nobody can use is a smaller
liability than one with a guessable password.

Every step is idempotent. `docker compose up` runs many times against the same
volume, and a second run must converge.

---

## 3. The health contract

`/healthz` is what `docker compose up --wait` polls, and it has one
non-obvious property:

> **It does not touch the database.**

A liveness probe that queries a table queries a table that may not exist yet —
which is exactly the moment the portal most needs to be distinguished from a
broken one. The database check exists, at `?deep=1`, and it is for a human
debugging a stuck boot. The container's healthcheck never calls it.

Three consumers, one definition: the Dockerfile `HEALTHCHECK`, the compose
`healthcheck`, and `tools/prove_offline.py` all call `docker/healthcheck.py`.
A definition of "healthy" that lives in three places is three places to forget
to update.

`start_period` is 45 s, which is longer than a real cold start (measured: 6.2 s
to a serving page, budget 60 s). It is set for the *reviewer's* machine, which
is slower and may be pulling the base image for the first time. A start period
shorter than the real cold start reports the portal unhealthy during normal
operation, and a healthcheck that cries wolf is one people stop reading.

---

## 4. Offline, and how we know

**Requirement 1 of 5** is that `docker compose up` brings up a working, seeded
portal with the network off.

`tools/prove_offline.py` proves it with `--network none` — an empty network
namespace: no interfaces but loopback, no route off the host, no DNS. The
container boots under the real entrypoint, the container's own healthcheck is
polled until it passes, and four content-asserting probes run from inside the
same namespace.

Probes assert on **content, not just status.** A healthcheck alone passes for a
process serving an empty page, a proxy error, or a redirect to nowhere.
Requiring our own title in the body is what makes the result mean something.

This is strictly stronger than switching off the host's Wi-Fi, and it is the
right test for a different reason too: a test that depends on the machine's
connection state is a test a judge cannot run on a train.

What makes it true rather than aspirational:

| Decision | Consequence |
|---|---|
| whitenoise, not a CDN | a static asset fetched from elsewhere fails the moment the network is off |
| SQLite on a volume, not Postgres | no connection string, no host to resolve |
| Generated `SECRET_KEY`, persisted | no required environment variable, so nothing to supply and nothing to leak |
| No cloud SDK in `requirements.txt` | nothing in the portal can make an outbound call |
| One stylesheet, no build step | the front door has no `npm` and no fetcher |

---

## 5. Configuration

**There are no required environment variables.** The acceptance criteria say
`docker compose up` works with nothing configured, so demanding
`DJANGO_SECRET_KEY` would fail criterion 1.

But a *hardcoded* key is worse: it would be in git, so every fork would share
it, and a signed judge record is only as trustworthy as the key that signed it.
So the key is **generated once into the instance volume and read back on later
boots**. Sessions and signatures survive `restart`; `down -v` is a deliberate
reset, and a reset that also rotates the key is correct for a self-hosted
portal.

`ALLOWED_HOSTS = ["*"]` is deliberate. Nothing in this application makes a
security decision from the `Host` header — one tenant, no host-based routing —
so restricting it buys nothing and would turn a judge's LAN address into a 400
that reads as a broken install.

**HSTS is deliberately absent**, and this is the one that looks like a mistake.
A browser that has once seen `Strict-Transport-Security` refuses plain HTTP to
that host for a year. The portal is documented to be reached over
`http://localhost:8080`; enabling HSTS would convert a working `docker compose
up` into a portal the judge cannot open. The honest control for a localhost
deployment is a bound port, not a remember-forever header.

---

## 6. Database

SQLite in **WAL**, on the named volume.

WAL is what makes a single-file database safe for gunicorn's several workers:
readers do not block the writer and the writer does not block readers. The
rollback journal instead serialises every read behind every write, turning a
two-worker configuration into a one-worker one.

`transaction_mode = "IMMEDIATE"` takes the write lock at `BEGIN` rather than on
first write. Without it, two workers that both decide to write part-way through
a transaction get `SQLITE_BUSY` at `COMMIT` — after doing the work, which is
the worst place to lose. Taking the lock up front makes them queue.

Both keys were read out of the installed Django 5.2.17 source rather than
recalled, because the alternative was a settings file that silently accepted a
typo. That is finding F-11's lesson applied before it cost anything.

The schema will be **Postgres-portable**: no SQLite-only types, no
`JSONField`-index assumptions. We develop on SQLite because the brief requires
it, and the schema has to survive a port.

---

## 7. The application layers (designed, not yet written)

`reviewer/` is the centre of gravity, and one folder in it is the
architectural claim the whole submission rests on:

```
reviewer/isolation/     for_actor() + the scope receipt + the lint rule
```

The claim is that **there is exactly one place where the authorization rules
live.** `Review.objects.for_actor(actor)` returns a queryset that is *already
scoped*, and carries a human-readable reason for the scope. A permission
**decides** and raises; a queryset **constrains** and cannot. They fail in
opposite directions, which is the argument for having exactly two layers and
not three.

It is the portable equivalent of Postgres RLS, it works on SQLite, and it is
about a hundred lines instead of a migration and a pool-safety argument. That
last clause is not a consolation prize — the rejected alternatives (RLS,
Casbin, OPA) each introduce a *second source of truth* for the same rules,
which is the exact opposite of the claim.

**A denial is a literal 403 with an empty body and no `Location` header. Never
a 302.** `run.py` follows redirects, so a redirect returns 200 and fails the
check while looking correct in a browser. It is the single highest-value line
in this project.

The rest, all designed and documented in `blueprint/` and `bible/`, not yet
built: `reviewer/audit/` (hash chain, chain head), `reviewer/crypto/`
(Ed25519, in-toto Statement v1 in DSSE), `reviewer/normalization/`
(the estimator and its proof), `reviewer/io/` (export/import, `source_key`).

---

## 8. What the container does not contain

- **Dev dependencies.** `pytest`, `hypothesis` and `ruff` are not in the image.
  The test suite runs on the host against the same pinned versions. Dev
  dependencies in a production image are an attack surface for no benefit.
- **A compiler.** Every runtime package ships a manylinux wheel for cp313. If
  one ever did not, that is a finding to fix in `requirements.txt`, not a
  ~150 MB toolchain to paper over it in the image.
- **Key material.** Keys live on their own volume. A key baked into a layer
  cannot be un-written, and layers are readable by anyone who pulls the image.
- **Anything the app did not need at boot.** One stylesheet, one landing page,
  two health endpoints.

---

## 9. Build and image hygiene

The base is pinned **by digest**, not by tag. `python:3.13-slim` is a moving
target, and the submission is a claim that a judge can reproduce; a tag would
let the base change underneath the numbers in this repository.

`uid 10001` is fixed rather than allocated, because a named volume inherits
its ownership from the image at the mount point. A random uid would make
`down -v && up` fail to write to a fresh volume roughly half the time — which
is precisely the "healthcheck must pass from a **clean** volume, not a warm
one" acceptance line.

Static files are collected **at build time**, as the app user, with a
`test -f` assertion. Doing it in the entrypoint would spend the 60-second
budget on the filesystem instead of the port.

`PYTHONUNBUFFERED=1` because a buffered portal that logs nothing for two
minutes is indistinguishable from one that hung. The boot sequence and the
seed banner are visible while you are still watching the build.
