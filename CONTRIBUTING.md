# Contributing to Judge Judy

Judge Judy is a self-hostable submission and judging platform. It is the kind of
software where the interesting failures are **quiet**: a portal that returns 200
to a client it just refused, a leaderboard that ranks correctly for the wrong
reason, a test that passes because it never executed anything.

So contributions here are judged less on what they add and more on **what they
prove**. A pull request that adds a feature and a test asserting the feature's
behaviour is good. One that adds a feature, a test, and a *mutation* showing the
test notices when the feature breaks is better.

---

## Getting set up

You need Python 3.13 and Docker. Everything else is pinned.

```bash
git clone https://github.com/aalok101singh/judgejudy.git
cd judgejudy

python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt   # .venv\Scripts\pip.exe on Windows
```

`just doctor` will tell you what is missing and what it resolved.

> **Use the venv's interpreter, not the ambient `python`.** It is named
> explicitly in every command below for a reason: a bare `python` on a typical
> machine is a different minor version with no Django installed, and the tests
> will then quietly run against something other than what ships.

Run it:

```bash
docker compose up          # http://localhost:8080
```

That gives you an **empty portal** and a first-run wizard at `/setup/`. To get
the demo event instead — 41 projects, 126 reviews, five usable logins:

```bash
JJ_SEED_DEMO=1 docker compose up
```

---

## The gates

There is one command that matters:

```bash
just check
```

It is the whole gate: the spec layer, a clean `down -v`, a build, the
organizers' acceptance checker, the isolation proof, the census, the assignment
certificate, and the suite inside the image. If you only run one thing, run that.

The fast inner loop, while you are editing:

```bash
just lint           # ruff check, ruff format --check, and the isolation rule
just test           # the suite on the host
just spec-quiet     # the spec layer, and only its failures
```

Two more, each needing a clean volume, so they belong to a checkpoint rather than
a save:

```bash
just prove-offline     # the image starts with --network none and is probed
just mutation-test     # corrupt every registered thing; each must be caught
```

**Every one of these prints its own check count.** Please do not type a number
from one into a document, a commit message or a comment. A count that was
transcribed instead of measured is a count that is one edit from being a lie, and
`tools/verify_spec.py` exists specifically because this repository has been
burned by that before.

---

## House rules

### 1. Isolation lives in the query layer

There is one way to read a review:

```python
Review.objects.for_actor(actor)
```

`tools/check_isolation.py` (**JJ01**) fails the build on any other read of
`Review.objects` — **including inside tests**. If you need a differently-scoped
read, add an accessor that is named for what it exposes and give it a test
asserting who may call it. Do not add an ignore.

### 2. A refusal is a 403 with an empty body. Never a redirect.

This is not a style preference. A client that follows redirects receives a 200
from a login page, so "protecting" a score by bouncing someone to sign-in passes
every manual test and leaks to every automated one. Use the shared refusal
helper so no view can invent a softer answer.

### 3. The audit chain is append-only and transactional

`AuditEntry.delete()` raises. More importantly, **a chain entry and the change
it describes are written in one transaction** — otherwise a failed save leaves a
permanent entry claiming something happened that did not, which is a falsified
row in the evidence the whole design rests on.

### 4. Assert values, not shapes

A min-cut certificate that renders perfectly and names no judges is a pass. A
ranking of 41 rows that is structurally valid and scores the wrong projects is a
pass. **Assert the number, and assert that your control does not fire.**

### 5. A fixture that omits a precondition converts a suite into a lie

If your test's fixture cannot reach the code path, the test passes by asserting
the refusal instead. When a test passes, ask what it actually executed.

---

## Adding a mutation

`tools/mutation_test.py` holds a list of deliberate corruptions, each with the
command that must notice it. If you add logic worth protecting, add one:

```python
(
    "src/reviewer/<module>.py",
    "<the exact text to corrupt>",
    "<the corrupted text>",
    "what goes wrong, and why it matters",
    [sys.executable, "-m", "pytest", "tests/test_x.py::TestY", "-q"],
),
```

The `find` string must match the source **exactly**. If a formatter moves it,
the harness reports the mutation as *never applied* rather than silently passing
— that distinction is deliberate, and a stale pattern is a finding about the
harness rather than a gate that survived.

---

## Pull requests

The template asks what could break, and it is worth answering honestly. If you
changed a view, `just lint-isolation` applies to you too.

Good commits explain **why**. The diff already says what changed.

## Reporting a vulnerability

Please do not open a public issue. See [SECURITY.md](SECURITY.md).

## Licence

MIT. By contributing you agree that your contribution is licensed under it.