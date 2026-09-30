# FEAT-07 — Bulk IO, signed records, `results_hash`, widget, OpenAPI

**Status: COMPLETE.** Five increments, five commits, one shipped surface. The plan
line was *"Embeddable results widget, pure static HTML + JSON"* and the acceptance
was *"the widget renders offline"* — so that is what this file is mostly about.

**The widget is complete, and "complete" is a measured claim.** `just
prove-offline` now boots the container with `--network none` and runs
`manage.py verify_widget_offline` **inside that empty network namespace**: publish,
fetch, assert, restore. It fetches 41 rows in 6,658 bytes with no `<script>`, no
`<link>`, no `<img>`, no `http://`, no `https://`, no `@import`, and no `url()` in
the inlined CSS. The pytest suite proves the document contains no external
reference; the container proves the *server* produced it with no way to reach
anything else while doing so.

**At this checkpoint, measured not transcribed:** 721 tests passing (1 skipped),
113/113 mutations, spec 72/72, `just check` GREEN at 7 of 7 with
`claimed T1 T2, verified T1 T2`, `acceptance-report.txt` unchanged, and
`just prove-offline` PASS.

---

## What shipped, in five increments

| # | Commit | What it added |
|---|---|---|
| 1 | `46ccf84` | Byte-identical `export_run` / `import_run`. Natural keys and passthrough columns. F-93…F-96. |
| 2 | `d10bb70` | `audit/publication.py`, `manage.py publish_results`, recomputable `input_digest` and `results_hash`, D-09 replication. F-97, F-98. |
| 3 | `9932096` | `credentials/keys.py`, `in_toto.py`, `signing.py`, `manage.py sign_records`, separate `judgejudy-keys` volume. F-97 closed. |
| 4 | `2f910d6` | Hand-enforced OpenAPI 3.1 generator, `openapi.yaml`, product-first README. F-99, F-100. |
| 5 | this one | **The widget**: `reviewer/widget/{build,views}.py`, two routes, `verify_widget_offline`, 19 tests. |

---

## The widget

```
/widget/results/        one self-contained HTML document
/widget/results.json    the same ranking as canonical JSON
```

Public once `event.results_state == RESULTS_PUBLISHED`, and refused with a
**403 and an empty body** before then — the same primitive as everywhere else, so
an embedder's browser gets the same answer a judge would.

Four decisions worth keeping:

1. **The ranking comes from `results.leaderboard(actor)`, not a second
   implementation.** Two renderings of one question is a liability, and F-84 and
   F-89 were both exactly that — two shipped artefacts answering "what is the
   ranking" differently. The HTML and the JSON are now the *third* and *fourth*
   renderings of a single call, and a test compares them row by row.
2. **The public board is read with `Actor.anonymous(event)`.** An unscoped `Review`
   read would be the isolation bug the whole project is built around, so JJ01 has
   opinions about this file and it passes.
3. **It carries standings, never scores.** A widget embedded in a sponsor's page
   is the least controlled surface in the system, so what it carries is what we
   would publish anyway. A test asserts the exact field set.
4. **It labels its own method on every row.** A widget is read by people who never
   see the portal, so `normalization` travels with the data rather than being one
   click away somewhere else.

---

## Two things I got wrong, and the ledger already said so

### 1. The escaping test asserted a proxy

The first version of `test_the_title_is_escaped_not_rendered` asserted
`"onerror=" not in html`. It **failed against correctly escaped output**, where
`onerror=&quot;` is inert text inside a `<td>`.

F-86's lesson, which I had already written down: *a test that asserts a substring
is absent is asserting a proxy, and what a browser acts on is an element.* I
walked into it anyway, one session after writing it. The test now asserts the
**escaping** (`&lt;img`, `onerror=&quot;`) and a sibling asserts the **element**
(`<img` absent). The payload was never wrong; the assertion was.

I then added a third assertion — that no `="` survived in the body — and it failed
on `<p class="meta">` and the `<meta>` tag, which is our own markup, escaped
correctly. **An assertion that trips on the template is an assertion about the
template, not about the payload.** Both are recorded in the test's docstring so the
next person does not re-add either.

### 2. I registered an app with no models, against a rule I had written myself

The widget's verification command has to live inside a Django app to be
discovered. The obvious move was to add `reviewer.widget` to `INSTALLED_APPS`.
`tests/test_schema_contract.py` immediately failed: *"the build plan says 13 apps,
Django has 14 registered."*

`DATA-MODEL.md` already had the answer, written for `reviewer/isolation/` and
`reviewer/normalization/`: **packages, not apps**, because *"listing an app with
no models would add a `models` module that does not exist and a migration that
creates nothing."*

So I reverted it. `reviewer/widget/` is a package, like its two predecessors, and
the command lives in `reviewer.audit` — which owns the `ResultPublication` gate the
widget obeys, so it is a defensible home rather than a convenient one. **The
alternative was to keep the fourteenth app and rewrite the paragraph to excuse
it**, and that is goalpost-moving: changing a documented rule so your own addition
fits is how a spec stops being a spec. The build plan said *"13 apps"* and it is
still true.

`DATA-MODEL.md` now names the widget in the packages-not-apps list and records why,
so the next person re-derives it instead of re-deriving my mistake.

---

## The offline proof has to be able to fail

The obvious offline test is `assert "<script" not in html`. That is necessary and
worthless on its own, because a document that renders **nothing** also passes it.
F-61's shape: an empty leaderboard that is correct because it is empty. So the
proof is a pair:

- **absence** — no external reference, in the markup *or* in the inlined CSS,
  because a `url()` inside a `<style>` block is the one external reference a
  tag-scanning test misses;
- **presence** — **41 rows are in the bytes**, and a `No scores yet` row renders a
  dash instead of crashing the builder.

And the container probe publishes the event first, because the shipped fixture is
born `hidden` and **a probe against a hidden event would fetch a 403 with an empty
body** — a trivially-satisfiable pass for a widget that 403s everything. The
command **restores the original state in a `finally`**, and that restore is
verified: after the run, `results_state = hidden` and the widget is a bare 403. A
verification step that left the demo published would break the next T1 check for a
reason that has nothing to do with the code.

---

## The mutation harness found a real defect in the builder

The widget shipped with **zero** mutations, because `MUTATIONS` is a hand-maintained
list. Five were added. Two came back **MISSED** on the first run, and both misses
were findings — neither was a flaky test.

**F-101, and it is the important one.** I mutated the `html.escape` in `_cell` —
the XSS mutation, the single most valuable one in the file — and the suite stayed
green. The cause was not a weak test. **The builder implemented the escaping rule
twice**: the title was escaped in its own f-string, and every other cell went
through `_cell`. The hostile fixture put its payload in the title, so deleting
`_cell`'s escape changed nothing the fixture reached.

That is a code defect the mutation harness found and the tests could not, and the
repair was a collapse rather than a new test: the title is a `_cell` now, so one
rule is written once and one hostile input per cell exercises it. **Two copies of
one rule means one of them is untested**, and no amount of coverage on the copy you
happen to be reading will tell you that.

It is the **fourth** recorded instance of a mutation aimed at the wrong line — and
the first where the wrong line was a *duplication* rather than a near-equivalent
edit.

**F-102.** The footer test asserted `NORMALIZATION in html`. The string appears in
the meta line, on all 41 rows, and in the footer, so deleting the footer's copy was
invisible. Three renderings of one fact, one presence assertion — F-84's shape. The
assertion is now scoped to the `<footer>` element.

A third finding came out of writing the fixture: `project.track.slug = …` followed
by `project.save()` **never persisted the slug**, because assigning to a related
object mutates it in memory and `project.save()` writes the Project. The hostile
track payload silently never arrived, so the new `_cell` test was passing for the
wrong reason. **A test that passes because its fixture did nothing has not run.**

Final: **113/113**, and the widget's five are all caught.

---

## Two more ways to be wrong, both avoided by construction

**A verification step that corrupts the demo.** `verify_widget_offline` publishes
the event to fetch it. If it failed midway, the shipped fixture would be left
published and the next T1 check would fail for a reason with nothing to do with the
code. The restore is in a `finally`, and it is **verified**: after the run,
`results_state = hidden` and the widget is a bare 403.

**An app with no models.** Registering `reviewer.widget` in `INSTALLED_APPS` was the
obvious way to get the management command discovered, and it immediately tripped
`test_schema_contract.py` at 13 vs 14. `DATA-MODEL.md` had already answered this for
`isolation/` and `normalization/`: packages, not apps, because a model-less app
adds a `models` module that does not exist and a migration that creates nothing. So
the widget is a package, the command lives in `reviewer.audit`, and the plan's "13
apps" is still true. The alternative — amending the rule to excuse my own addition
— is the kind of edit that turns a spec into a rationalisation.

---

## What this did not do

- **No T3 or T4 claim.** `run.py` has no T3 or T4 checks, so either claim produces
  `OVERCLAIM` and a red gate. The T3 *feature* is built and unclaimed (F-91).
- **No auth on the widget.** Deliberate. An organizer pasting an iframe into a
  sponsor's page is not going to authenticate anybody, and pretending otherwise
  would have meant shipping a widget nobody can embed.
- **No light/dark preference, no sorting, no pagination.** The document is 6.6 KB
  and the ranking is 41 rows. Adding controls would mean adding script, and script
  is the dependency this feature exists to avoid.
- **`/widget/results.json` is not in `openapi.yaml`.** The OpenAPI document
  describes the `/api/v1/` surface; the widget is a public embed surface with no
  credential and no version negotiation. The route table in the README documents
  both routes, and `verify_spec.py` enforces that the table is complete — it caught
  the omission at 71/72 before anything else did.
