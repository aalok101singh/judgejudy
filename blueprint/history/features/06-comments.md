# FEAT-06 increment 6 - public comments (REQ-T3-02)

**Date:** 2026-09-29 - **Phase F** - **Gate:** none

`/projects/<id>/comments/`. Plain text, moderated, public. **25 tests, 4 new
mutations.** Two findings, and the first is the most useful thing this feature
produced.

---

## The four controls, and the one we did not ship

`bible/07` V-8 names four controls for comment spam and XSS: **escaped output,
no raw HTML, `pending` moderation queue, rate limits, length caps.**

| | |
|---|---|
| Escaped output | **ships**, asserted on the *element* not a substring |
| `pending` by default | **ships** — the schema default, never named at the call site |
| Length cap | **ships**, 2000 chars, with the real length in the refusal |
| **Rate limits** | **DO NOT SHIP** — cut, and disclosed in `bible/08` §13, the README, and this module's docstring |

That last row is the one worth a reviewer's attention. It is the **only place this
project has written a control down in its own threat model and then not shipped
it**, and a reader of `07` would reasonably expect all four. Saying so three
times is the mitigation; quietly shipping three of four would not be.

---

## F-86 [P2] - the queue rendered unescaped, and every escaping test was green

The sabotage put the safe filter on the **moderation queue's** copy of
`comment.body`, not the public thread's. **All four rendering tests stayed
green.**

They were green because every one of them read the page as a **visitor**, and the
queue renders only for an **organizer**.

**The queue is the highest-privilege rendering of user-controlled text in the
whole feature.** It is what an organizer looks at, in their own authenticated
session, for every comment anyone has ever posted — and a hostile comment that is
*never approved* never reaches the public thread at all. The public tests were
structurally incapable of catching it. That is stored XSS against the person
whose job is to review the content, triggered by the content itself.

### The lesson, and it generalises past comments

> **Escaping is a property of every render path, not of the data.**

A test that proves a payload is escaped on page A has proved nothing about page
B. The number that matters is the **count of places user-controlled text reaches
HTML**, and the assertion has to be enumerated over that count — not written once
and trusted. This is F-80's shape applied to a security property: a path that
exists, is reachable, renders user input, and had **no test at all**.

Pinned by `test_the_moderation_queue_escapes_too` (reads the page *as an
organizer*, asserts the queue is present, non-empty, and escaped) plus a
companion proving the queue is non-empty so the first cannot pass **vacuously**.

---

## F-87 [P2] - "Approve" updated the row and re-rendered the stale page

`_moderate` rebuilt only the **queue** in the context after acting, re-rendering
the **public thread** from a context built *before* the write. The organizer
pressed Approve, the row went visible, and the page said it had not happened.
F-85's shape, one module over.

**Found immediately, unlike F-85** — because the moderation tests **re-render the
page after acting**. That is the whole difference between the two findings, and
it is a habit worth naming:

> **A write test that re-reads the page is a test about the product. One that
> asserts on the database is a test about storage.**

---

## A test that was wrong before it was right

The first escaping test asserted the string `"onerror"` is absent from the page.
It failed — against **correctly escaped output**, where `img src=x
onerror=alert(1)&gt;` is inert text inside a `<p>` and the word "onerror" is
legitimately part of the comment the user typed.

A test asserting a *substring* is absent is asserting a proxy. What a browser
acts on is an **element**, so the assertion is now on the tag: no `<img` was
created, and the payload's angle brackets came out escaped.

---

## Not on the gallery, deliberately

`run.py` reads `projects[:3]` **positionally** from `/` and checks that one of
those titles appears in the body. The gallery markup is a page the T1 checks
read. Comments live on their own route so adding them **cannot move the gallery's
ordering**; the gallery carries only a link, which is additive and inert.

---

## What it cost

| | |
|---|---|
| Tests | 528 -> **553** (25 in `tests/test_comments.py`) |
| Mutations | 77 -> **81** (4 new) |
| Findings | **F-86 [P2]**, **F-87 [P2]** |
| Cuts recorded | comment rate limiting; comment threading |
