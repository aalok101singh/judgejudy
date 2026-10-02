# Changelog

All notable changes to Judge Judy are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Judge Judy is pre-1.0. There is no released version yet; `main` is the supported
line and fixes are not backported to older commits.

### Added

- **`/organizer/settings/`** — the event lifecycle in a browser: the submission
  and judging windows, the voting mode and its window, and publishing results.
  Publishing goes through the same code path as the management command, so the
  hash and the audit entry are identical either way. The rubric, project track
  membership and anything touching isolation are deliberately *not* editable here,
  and a test asserts that absence so a convenient-looking checkbox cannot be
  added quietly.
- **`manage.py import_projects`** — bulk entry import from a CSV. Idempotent via
  `source_key`, unknown columns ignored rather than rejected, per-row refusals
  reported with line numbers, and `--dry-run`.
- **Comment rate limiting** — five per hour per identity. A signed-in poster is
  keyed by account; an anonymous one by session hash, so clearing cookies resets
  the budget. That weakness is documented in `SECURITY.md` and covered by a test.
- **A first-run wizard at `/setup/`** — an empty deployment can become a runnable
  event in a browser: event, dates, tracks, a starting rubric, and the
  organizer's own account. Refuses with a bare 403 once an event exists.
- **Demo seeding is now opt-in** (`JJ_SEED_DEMO=1`). A fresh `docker compose up`
  starts empty, which is what leaves `/setup/` reachable in the shipped product.
- **An embeddable results widget** at `/widget/results/`, one self-contained HTML
  document with no script, stylesheet, CDN or webfont, proved to render with
  `--network none`.
- **Continuous integration.** The fast gates run on every push; the container
  gate runs the acceptance checker, the isolation proof, the census, the offline
  proof and the suite inside the image; the mutation harness runs on `main`,
  weekly and on demand. Every gate is invoked through `just`, so CI cannot drift
  away from what the project actually proves with.
- **`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`**,
  issue and pull-request templates, and Dependabot.

### Changed

- **`just` recipes are now portable.** The interpreter and the shell fork with the
  host, and two `cmd.exe`-only constructs were removed. This is what lets CI run
  the real gate on a Linux runner instead of a hand-written copy of it.
- **`tools/verify_spec.py` treats the planning layer as optional.** Checks whose
  subject is a document this distribution does not ship are reported as **SKIPPED,
  with the reason**, and are excluded from the count it prints. Previously they
  would have crashed on a clone that had never seen them.
- The repository no longer ships internal build process — the planning corpus and
  the agent working notes. It remains in git history.

### Fixed

- **The audit chain could record a change that never happened.** A chain entry and
  the event write were committing independently, so a failed save left a permanent
  entry claiming a deadline had moved. They now share one transaction. This was
  found by review rather than by a test, which is why fixed findings stay open
  until somebody re-reads them.
- **A settings form could null a required column.** Any partial submit wrote
  `None` into a `NOT NULL` deadline, and the Publish button — whose form
  deliberately carried fewer fields — triggered it. Absent now means unchanged.
- **The settings validation path raised `KeyError`** instead of rendering its 400
  for an unparseable date.
- **An organizer's description was silently truncated** at 5000 characters, a
  limit nothing in the schema asked for.
- **Publishing an event with no rubric returned a 500**, behind a button that
  offered it.

### Security

- Dependency updates are tracked automatically by Dependabot.
- The offline guarantee is now proved on every container-gate run, not asserted in
  a document.

[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html