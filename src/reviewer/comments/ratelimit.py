"""How many comments one identity may post, and what happens when it says no.

**This is V-8's fourth control, and the one this project disclosed as missing**
in the module docstring of ``comments/views.py``, the README and the cut ledger.
It is built here rather than described further, and the disclosure is amended by
the commit that lands it.

The design is count-derived on purpose. A rate limiter needs to answer one
question -- *has this identity produced too much, recently?* -- and the rows that
already exist answer it exactly. A separate counter table would be a second
source of truth that can disagree with the comments it counted, and it would
need a cleanup job. Counting is a query, and on SQLite with one writer that is
cheap.

**Two keys, and the honest asymmetry between them.**

- A **signed-in** poster is keyed by ``author``. Strong: they cannot shed it
  without losing their account.
- An **anonymous** poster is keyed by a **hash of their session key**. Weak, and
  the weakness is stated rather than hidden: clearing cookies resets the limit.

The alternative was keying on IP, which this project has refused everywhere else
because it is a poor identity that gets innocents in trouble. **A limit that can
be reset by opening a private window is still a limit against the naive case,
and the strong case is reachable by giving people accounts** -- which is what
``manage.py invite`` is for. Shipping a real control, named honestly, beats
shipping none and calling it a decision.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from django.utils import timezone

#: Comments per identity per hour.
#:
#: **Five is a legibility constant, and it is chosen to be legible rather than
#: clever.** An organizer moderating by hand wants a queue of a size a person can
#: work through; a limit of fifty protects the database and destroys the queue. A
#: limit of one breaks a conversation. Five is enough for somebody genuinely
#: discussing a project across several threads and small enough to read.
COMMENTS_PER_HOUR = 5

#: The window. Shorter than the hour would make the constant mean something else,
#: so the two are named together and the number is stated in the error.
WINDOW = dt.timedelta(hours=1)


def session_hash(request, *, create: bool = False) -> str | None:
    """A stable, non-replayable key for this browser's session, or ``None``.

    Returns ``None`` when there is no session and ``create`` is false.

    **``create=True`` is what makes the anonymous limit real.** Django's
    ``SessionMiddleware`` saves a session only when something *modifies* it, and an
    anonymous visitor who reads a thread and posts a comment modifies nothing --
    so ``session_key`` stays ``None`` forever, this function returns ``None``, and
    **the anonymous rate limit never fires**. The first draft shipped exactly
    that: it looked correct, every test that exercised it used a session that
    something else had saved, and in production the control this project had
    disclosed as missing for most of its life would have been decorative.

    So a comment from an anonymous poster *creates* the session that identifies
    it. The cost is one row in ``django_session`` per anonymous commenter -- and
    the limit is what bounds it. It is not created for page views, only for
    comments, so a reader costs nothing.
    """
    session = getattr(request, "session", None)
    if session is None:
        return None
    key = getattr(session, "session_key", None)
    if not key:
        if not create:
            return None
        session.create()
        key = session.session_key
        if not key:
            return None
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def identity_filter(request, actor) -> dict:
    """The queryset filter naming *this* poster, or an impossible one.

    **Creates the session if it has to**, because an identity that was never
    minted cannot be counted -- see :func:`session_hash`.

    An empty dict would count the whole table and lock out every visitor at once,
    so the fallback is a filter that matches nothing: an uncountable poster gets
    the benefit of the doubt rather than everyone else's quota.
    """
    if actor.is_authenticated and actor.user is not None:
        return {"author": actor.user}
    digest = session_hash(request, create=True)
    if digest:
        return {"author_session_hash": digest}
    return {"author_session_hash": "\x00uncountable"}


def window_start(now=None) -> dt.datetime:
    return (now or timezone.now()) - WINDOW


def too_many_recently(request, actor, *, now=None) -> bool:
    """True when this poster has already spent its budget inside the window."""
    from reviewer.comments.models import Comment

    cutoff = window_start(now)
    # **`**identity_filter(...)`, not a positional dict.** The first draft passed
    # the dict as `filter()`'s first positional argument, which Django rejects
    # with `FieldError: Cannot parse keyword query as dict` -- so *every comment
    # post 500'd*. A whole comment thread was unreachable the moment this shipped,
    # and the failure was a 500 rather than a refusal, which is the worst shape a
    # rate limiter can take.
    return (
        Comment.objects.filter(created_at__gte=cutoff, **identity_filter(request, actor)).count()
        >= COMMENTS_PER_HOUR
    )


def message() -> str:
    """The sentence an organizer sees. Says the number and the way out."""
    return (
        f"You have posted {COMMENTS_PER_HOUR} comments in the last hour. "
        "Comments are held for moderation, so the limit keeps the queue "
        "readable -- come back in a while, or sign in as an account."
    )
