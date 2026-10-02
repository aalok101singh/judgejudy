<!--
One paragraph on what changed. Then the gates you ran. Then the invariant you
think is at risk, if any. That last part is the one reviewers here actually read,
because the defects this project has found in itself were almost never found by
reading the diff.
-->

## What this changes

<!-- One paragraph. What is different after this merge, and why. If the diff is
larger than the change, say so here rather than letting a reviewer discover it. -->

## Gates

<!-- Tick what you ran. If you did not run one, leave it unticked and say why
below — an honest unticked box costs less than a ticked one that lies. -->

- [ ] `just lint`
- [ ] `just spec-quiet` (or `python tools/verify_spec.py -q`)
- [ ] `.venv\Scripts\python.exe -m pytest -q` (`.venv/bin/python` on POSIX)
- [ ] `just check`
- [ ] `just mutation-test` — only if you touched logic. It corrupts every
      registered thing on purpose and requires each one to be caught by a named
      test, so it is the gate that tells you whether your test actually asserts
      anything. **It prints its own count** — copy that from the output rather
      than quoting a number here, which is the one thing in this repository that
      is guaranteed to go stale.

Not run, and why:

<!-- e.g. "just check — the Docker socket is not available in this environment;
     ran the spec layer and the suite instead." -->

## What could break

<!-- Name the invariant you think is at risk, in one line, and say why you think
     this change touches it. If none apply, write "none of the four, as far as I
     can tell" — that is a useful answer and much better than silence. -->

- [ ] **Isolation.** Whether this change adds a second way to read something that
      already has one, or makes an existing scoped accessor easier to bypass. If
      you touched a view, see the note below.
- [ ] **A refusal is a 403 with an empty body, never a redirect.** A denial that
      redirects returns 200 to any client that follows it, so it passes every
      manual test in a browser and leaks to every automated one.
- [ ] **The audit chain is append-only, and an entry is written in the same
      transaction as the change it describes.** A chain that can commit
      independently can claim a deadline moved when it did not.
- [ ] **`export_run` to `import_run` to `export_run` stays byte-identical,
      including every natural key.** Not "equivalent". A column that stops
      round-tripping is invisible until somebody needs the archive.
- [ ] None of the above, as far as I can tell.

## Numbers

**`tools/verify_spec.py` prints its own check count, and no number in this
repository may be transcribed by hand.** It re-derives counts from
`fixtures.json` and `run.py` rather than believing the documents, and it has
caught stale tallies in files written minutes earlier. If you changed a count,
a threshold or a timing anywhere, run it and paste the output rather than the
number you remember. Same rule for `acceptance-report.txt`: it is generated, and
the panel runs the identical program.

## If you changed a view

`just lint-isolation` applies to you too. Rule JJ01 fails the build on any
unscoped read of `Review.objects`, **including inside tests**, so a test that
reads a peer's review to set up state will fail lint the same way a view would.