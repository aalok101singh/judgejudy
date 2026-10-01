# FEAT-11 — Making it a tool: provisioning, login, roster

**Status: COMPLETE.** The build was a judging *engine* with no way to run one.
This is the increment that makes it a portal, and the finding in it is worth more
than the code.

## What shipped

| | |
|---|---|
| `reviewer/setup/provisioning.py` | An empty database → organizer, event, tracks, rubric. Atomic. |
| `/setup/` | The first-run wizard. **Refused with a bare 403 once an event exists.** |
| `/login/`, `/logout/` | Real sessions. Throttled per-email. `next` restricted to same-site. |
| `reviewer/setup/roster.py` + `manage.py invite` | A file of emails → accounts and role bindings. Idempotent. |
| `manage.py set_password` | The other half of `invite`, because there is no mail service. |
| The demo becomes opt-in | `${JJ_SEED_DEMO:-0}`. **The product is the default.** |

## F-111: the feature was unreachable in the shipped product

The wizard's authorisation is *"no event exists"*. The image seeded the
organizers' demo hackathon **unconditionally on every first boot**, because the
acceptance checker needs it.

So every deployment — including a real one — began with an event already in the
database, and `/setup/` returned its bare 403 forever. The feature was built,
tested, documented, and **completely unreachable**, and nothing inside Django
could see it, because Django was behaving exactly as specified.

> A correct component, defeated by a default outside its own boundary. Every test
> in `test_setup_wizard.py` passed, because every one of them provisioned its own
> event on an empty database. The bug lived in a shell script, a compose file and
> a justfile.

The fix inverts the default and both halves are pinned by
`tests/test_demo_is_opt_in.py`, which **reads** the entrypoint, the compose file
and the justfile rather than calling code — because the code was never the problem.

Asserting only "the image no longer seeds" would have been a fix that quietly
broke the acceptance gate, so that file also asserts `just check` sets the flag
*before* `compose up`, and that `prove-offline` passes `-e JJ_SEED_DEMO=1` to its
own `docker run` — it boots the raw image, so the compose default never reaches it.

**The generalisation is the part to keep:** a test suite covers the code you
wrote. A bug that lives in the wiring around it needs a test that reads the
wiring, and until this increment existed there was no way for the suite to know
that the product's entry point existed at all.

## The result that matters most, measured in the shipped container

Not "the tests pass" — the actual product path, on a fresh volume, through HTTP:

```
docker compose up
  starting with an empty database; open /setup/ to create your hackathon
GET  /setup/                     200
POST /setup/                     302      (Ridgeway Hack 2026, 3 tracks, 3-criterion rubric)
GET  /setup/                     403      (wizard correctly shut)
POST /login/ (organizer)         302
GET  /organizer/assignments/     200  signed in   /  403  anonymous
manage.py invite judges.txt      3 created, 3 bound   →  rerun: 0 created, 3 existed
manage.py set_password …         Password set
POST /login/ (judge)             302
GET  /judge/                     200
GET  /api/v1/export.csv          403      a judge may not read the export
GET  /                           200      public gallery, naming the new event
```

**Isolation holds on a database that was never the fixture's.** Every isolation
test in this project runs against the organizers' data; until now that was the
only evidence there was. A signed-in judge reaches their console and is refused
the export on a portal nobody had ever seen before, which is the strongest
statement about the isolation layer this repository can make — and it is a
statement about the *product*, not about a fixture.

## Four bugs the tests found, all real

- **F-104 (P1)** — the login lockout fired on the **first** failure, not the fifth.
  `n` was compared against `MAX_ATTEMPTS` nowhere, so the second attempt was
  refused: a portal where one typo locks you out. *A rate limit is only tested by
  the attempt it refuses.*
- **F-105 (P1)** — `test_csrf_is_required` asserted nothing about CSRF, because
  Django's test `Client` **disables CSRF enforcement by default**. It now builds
  one with `enforce_csrf_checks=True`, **plus a control proving the same request
  succeeds with a token** — without that, "CSRF is required" is satisfied by an
  endpoint that refuses everything.
- **F-106 (P2)** — the wizard **500'd on every request**: `{{ errors.__all__ }}`
  is illegal in a Django template, so the first page a new user sees was a stack
  trace. F-88's shape, reached from the other direction.
- **F-107 (P2)** — `set_password` could not be driven from a pipe.
  `getattr(self, "stdin")` is not reliably set in this Django version, so `--stdin`
  silently fell through to an interactive prompt — the one thing it existed for.

Plus **F-108** (a roster comment became an error about a person who did not
exist), **F-109** (`Decimal` weights returned as strings, now asserted at
provisioning time rather than only in a test) and **F-110** — the "no fixture
knowledge" guard tripped on its own docstring, which says out loud that the module
does not know the fixture. *A guard that fails on the thing it is guarding is a
guard that gets commented out.*

## What this did not do

- **No multi-event.** One deployment, one hackathon, by decision. It keeps every
  URL, the isolation matrix and the census exactly as they were, and a second
  event is a configuration error rather than a feature.
- **No email, and no password reset.** D-14's reasoning holds: no third-party
  service, ever. `set_password` exists instead, and `invite` creates accounts with
  an **unusable** password — the honest state when nothing could have delivered a
  credential.
- **No comments rate limiting.** Still the one control our own threat model names
  that we do not ship, still disclosed in the cut ledger.
- **No participant self-signup.** A participant still arrives by `invite`, which
  means an organizer who wants strangers voting has to know their addresses. That
  is a real limitation of a portal with no mail service, not a design choice.
- **`manage.py invite` binds judges event-wide by default**, and says so on
  stdout. Event-wide is the leaky choice; `--track` is the safe one.