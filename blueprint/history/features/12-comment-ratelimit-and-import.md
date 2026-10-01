# FEAT-12 — Comment rate limiting, and bulk entry import

**Status: COMPLETE.** Two things a real hackathon needs that the build could not
do, plus four findings — two of which are the most interesting in the project.

## Comment rate limiting: the control we named and did not ship

`bible/07` V-8 lists four controls for comment spam. Three shipped and were
tested. **Rate limiting was the one that did not**, and the cut ledger recorded
that as *"the only place we have written a control down in our own threat model
and then not shipped it, which is worse than never having written it."*

It now ships: **five comments per hour per identity**, refused with the portal's
bare 403. The ledger row is **reversed rather than annotated**, because a row
saying "we cut this" is a claim about the past, and an annotation reads as "we
thought about it" when what happened is "we changed our minds".

**Count-derived, on purpose.** No counter table: the question is "how many comments
does this identity have in the last hour?", and the rows already answer it. A
separate counter is a second source of truth that can disagree with the comments
it counted, and it needs a cleanup job. One column,
`Comment.author_session_hash`, plus an indexed count.

**Two keys, and the asymmetry is stated rather than hidden.** A signed-in poster
is keyed by account — they cannot shed it without losing the account. An anonymous
poster is keyed by a **hash of the session key**, so **clearing cookies resets the
budget**. IP is the alternative and this project refuses it everywhere else,
because it is a poor identity that gets innocent people in trouble. That bypass is
in the README, in the module docstring, **and in a test named for it**, because a
limiter whose weakness is only in a comment is one people come to trust more than
it deserves.

### F-113: the anonymous limit would never have fired at all

The finding that matters. Django's `SessionMiddleware` saves a session only when
something **modifies** it — and an anonymous visitor who reads a thread and posts a
comment modifies nothing. So `session_key` stayed `None`, the hash returned `None`,
the filter became the "matches nothing" fallback, and **the anonymous rate limit
would not have fired once in production.**

It looked correct. The tests passed, because the fixtures happened to have sessions
something else had saved. The control this project had disclosed as missing for
most of its life would have shipped as decorative.

The fix is `session.create()` when an anonymous poster has no key: **an identity
that was never minted cannot be counted.** One `django_session` row per anonymous
commenter, created only when someone actually comments, bounded by the limit.

> Every earlier rate-limit decision in this project argued about *who counts as an
> identity*. This one failed because the identity was never **created** — a step
> earlier, and much easier to miss. A control that degrades to "cannot count" must
> be checked for whether it ever reaches the counting path at all.

### F-114 and F-115: two bugs that both made comments 500

Both shipped within an hour, in the same feature's only user-visible entry point:

- **F-114** — the call site passed `None` for a `NOT NULL` column that had
  `default=""`. Passing `None` explicitly *bypasses the default*. **This is the
  trap the model's own comment records:** the field was changed from `null=True` to
  `default=""` precisely because null-and-blank is two ways to say "absent", and
  the caller reached for `None` anyway. A single-valued invariant has to be
  enforced at the boundary too, because a reviewer reading the model cannot know
  which of two spellings the caller uses.
- **F-115** — `filter(identity_filter(...), created_at__gte=...)` passes a dict as
  the first *positional* argument, which Django rejects with `FieldError`.

### A test that asserted the wrong property, and the code was right

I wrote a test asserting the comment limit was **per project**. The code is
**per event**, and that is correct: an organizer moderating by hand reads *one*
queue for the whole event, so ten comments across two projects are still ten items
in that single queue, and a per-project budget would let somebody fill it twice
over.

**A test asserting the weaker property is how a stricter control gets "fixed" into
a weaker one** — the same shape as F-66, where a stale document was corrected in
the wrong direction. The test now asserts the stricter property and the module
docstring says why.

## Bulk entry import

`manage.py import_projects entries.csv`. Before this the only bulk path was the
escape hatch — a **whole-database** archive round trip, which is right for backup
and terrible for onboarding an event.

Only `title` and `track` are required. Extra columns are **ignored, not rejected**,
because a Google Forms export carries a dozen. It is **idempotent** on
`source_key`, with the title as a within-event fallback only — `Project.title` is
deliberately not unique (`bible/04` §3.3), so the title is never a global key. Each
bad row is **skipped and named with its line number** while the rest import, and an
unknown track is **refused rather than invented**: a track with no judges bound to
it is an event where some projects can never be judged.

**F-116** — `submitted_at=timezone.now()` sat in the shared `fields` dict, so every
re-import restamped and rewrote all forty rows and reported them as "updated". F-61
at the level of a report: the data was equivalent and the one number an organizer
reads to decide whether to re-run was wrong in the loud direction.

**F-117** — the exception was named `ImportError`, then `ImportError_` when lint
caught the shadowing. The second is the same problem with a cosmetic fix. Now
`RowRefused` and `FileRefused`, which are also **two failure kinds**: fatal for a
file, skip-and-report for a row.

## F-112: a stale mutation string, in a third file

Refactoring `tools/docker.py` for `--seed-demo` collapsed the `subprocess.run(...)`
call onto one line, and the mutation targeting it stopped having a pattern. The
harness reported **SKIPPED** rather than passing — F-98's lesson, in a third file.

**The reason it keeps recurring is structural:** the harness is a list of strings
into source, so *every reformat is a potential silent disarmament*. The only
defence is a harness that fails loudly, and this one does. Re-pointed, plus a new
mutation for `--seed-demo` — the flag that has already failed to take effect twice.