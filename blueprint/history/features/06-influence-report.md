# FEAT-06 — Public surface: the influence report (increment 2)

> **The anti-abuse answer (D-13), and two findings that were both about tests
> that could not fail.** Voting, comments and randomized ballot order are *not*
> in this increment; the bias-attack harness is not either. The influence report
> went first because the harness needs an attack to be *visible* against, and
> building the detector after the test would have meant writing them in the wrong
> order.

**Date:** 2026-09-29 · **Phase F** · **Gate:** none (BREAK-3 is next, `v-t3-verified`)

---

## What shipped

| Piece | Where | What it is |
|---|---|---|
| The report | `src/reviewer/ballots/influence.py` | per-project concentration: distinct identities, first-preference share, vote-mass Gini, clustered identities |
| The cluster detector | `identical_ballot_clusters()` | byte-identical vote vectors — a **structural** signal, not a threshold |
| The render | `manage.py influence_report` | the table, the method, and the caveat — every run |
| The API | `GET /api/v1/influence` | organizer/admin only, **never gated on `results_state`** |

**Three detectors became two, and the third was cut after measurement.** See
F-76 — the cut is the interesting part of this increment.

---

## The acceptance line, observed

`build-plan.md` Phase F: *"the influence report renders for a synthetic attack."*
Run in the real container on a clean volume, with a brigade of 12 identical
ballots on `prj_01` and five organic projects:

```
  57 distinct identities, 147 votes, 8 project(s) voted for

  project       ids    1st%   gini  clustered
  -------------------------------------------
  prj_01         12    0.0%    0.0         12     <- the brigade
  prj_02          9   15.8% 0.2963          0
  prj_03          9   15.8% 0.2963          0
  prj_04          9   15.8% 0.2963          0
  prj_05          9   15.8% 0.2963          0
  prj_06          9   15.8% 0.2963          0
  prj_07         45    0.0%    0.0          0
  prj_08         45    0.0%    0.0          0

  Most suspicious first: an exact-match brigade, then a
  lopsided weight distribution, then first-preference share.
  'clustered' counts identities voting a byte-identical ballot.

  Concentration is not proof. Identical ballots may be a brigade, an
  enthusiastic table of friends, a shared browser profile, or a genuinely
  aligned preference; this report ranks projects by how concentrated their
  support is and does not name a culprit.
```

**The brigade is first; every organic project reads `clustered 0`.** That last
part is not decoration — see F-77, where it was *not* true and the suite was
still green.

**The first clause of the acceptance line — the bias-attack harness — is not
built.** This increment delivers one of the two clauses, and the archive says so
rather than letting a reader assume the feature is done.

---

## Three design decisions worth keeping

**1. The report is not gated on `results_state`, and that is the whole point.**
`/api/v1/results` is refused to everyone but an organizer while results are
hidden, because a ranking during judging leaks. The influence report answers a
different question — *how concentrated is this support* — and the organizer has
to be able to answer it **before** deciding to publish. Gating it behind
publication would turn a preventive report into a post-mortem. There are two
tests pinning the contrast, so a future change cannot quietly share the guard.

**2. No threshold anywhere.** Gini and cluster size are reported and *ranked*;
the report never says "this project is brigaded". A tunable constant would have
been the easiest thing in the report for a panelist to attack, and D-04 already
taught this project what a defensible constant costs. The cluster detector is
exact-match, so it needs no cut-off at all: identical is identical.

**3. The caveat is part of the output, not a docstring.** A person skimming a
table does not read docstrings, and a report that shows a Gini without saying
what it cannot conclude is a machine for accusing an enthusiastic table of
friends. `INTERPRETATION` travels with every payload and is printed on every run.

**The empty case is the fifth F-61 and it is the one this feature would have
shipped.** The fixture has zero votes. `report()` returns `None`, the command
prints *"NO VOTES HAVE BEEN CAST … this is NOT a finding of 'no brigade'"*, and
the API says `status: no_votes`. A test asserts the word `gini` never appears on
an empty event.

---

## Two findings, and both are about verification

### F-76 — a metric I invented was structurally constant, and the attack scored it 1.0

`lift = first_preference_share / voter_share`. Every voter casts one first
preference, so a project's backers *are* its first-preferencers in the common
case and the ratio is identically 1. It would have been a column that looks like
a detector and carries no information — the F-32 shape, wearing a decimal point.

**Cut**, recorded in the module docstring with the arithmetic, and pinned by
`TestTheDegenerateMetricStaysCut` so the next session cannot re-derive it from
`bible/06`'s phrasing. **D-04's lesson, applied to abuse instead of
normalization:** a metric you cannot show discriminates is a tunable constant
with a decimal point.

### F-77 — the control was itself a brigade, and 24 green tests did not notice

Every "organic" voter backed one project at weight 1, so nine of them had
byte-identical vote vectors. The control was flagged `9` on every row. **pytest
passed, and mutation testing passed, because the code was right and the
*scenario* was degenerate.**

This is F-41 from the other side: not a test that cannot fail, but a **fixture
that cannot separate the subject from its control**. It was found by running the
command in the container — which is the general lesson, and the reason
`verify_audit`-style commands exist at all. The missing assertion now exists:
organic rows must read `clustered == 0`.

---

## What it cost, and what is left

| | |
|---|---|
| Tests | 404 → **428** (24 new in `tests/test_influence.py`) |
| Mutations | 50 → **59** (9 new, each naming its detecting test) |
| Suite | 428 pass · `just check` GATE GREEN at 7/7 · spec 71/71 · lint clean |
| The other acceptance clause | **the bias-attack harness — not built** |
| Still unstarted | voting, comments, randomized ballot order, public result hiding |

**Nine mutations, and one of them earned its keep immediately:** the first
version of the acceptance test ranked the brigade first *by accident*, because
the fixture also made it the first-preference leader, so deleting the cluster key
from the sort still passed. That is the F-41 shape and the harness caught it
(58/59). The fixture now puts every first preference on the organic side, so only
the cluster detector can produce the ranking.

---

## Do not

- **Do not add the `lift` column back.** It is pinned by a test and the reason
  is in the docstring.
- **Do not make `clustered` a threshold** without also writing down why. Exact
  match is what makes it need no constant.
- **Do not gate `/api/v1/influence` on `results_state`.** Two tests exist for
  exactly that.
- **Do not claim this feature is done.** One acceptance clause is built and one
  is not.
