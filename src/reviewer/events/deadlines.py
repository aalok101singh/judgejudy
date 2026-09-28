"""The deadline guard: one service function, called by every write path.

``bible/05`` §4 specifies this shape and the reasoning is worth repeating here,
because the two obvious alternatives are both wrong for reasons that are not
obvious until you have shipped one of them:

* **A ``Model.save()`` override** is bypassed by ``bulk_create``, by
  ``QuerySet.update()``, and by every future import path. A guard that the bulk
  importer can walk straight past is not a guard.
* **A view decorator** is bypassed by the admin, by the API, and by the import
  command. Those are three of the four write paths the spec names.
* **A service function** called by every caller is one ``if``-equivalent that
  the acceptance checker exercises for real and that our own tests exercise for
  both the open and the closed case.

**Why the exception names the function that raised it.** ``SubmissionClosed``
carries ``refused_by = "assert_open_for_submission"``, and the HTTP layer puts
that in the response body. This is not decoration. ``run.py`` accepts *any* 4xx
for "closed event refuses submissions" (F-11), so a request refused by CSRF, or
by "you are not logged in", or by a route that 404s, all report PASS. Naming
the guard in the body is what lets a test -- and now the acceptance gate
itself -- distinguish "the deadline held" from "something else refused first",
and it is the single highest-value line in this module.

**Why ``submissions_open = NULL`` means "no opening gate" and not "open".** The
fixture supplies only ``submissions_close`` (``bible/04`` §5.1), and the loader
leaves the opening gate unset rather than inventing a date for it. A NULL
opening gate is the permissive branch, which is the correct default for a field
whose absence is a statement about what the operator chose to configure: they
configured a close, so the window is open until it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from django.utils import timezone

#: The guard's own name, carried in every refusal so a response body can say
#: which mechanism refused the request. See the module docstring -- this is the
#: difference between a passing check and a passing check that means something.
GUARD_NAME = "assert_open_for_submission"

#: The three states a submission window can be in. Named rather than inferred
#: from a pair of booleans so a caller cannot read "open" off the wrong branch.
STATE_NOT_YET_OPEN = "not-yet-open"
STATE_OPEN = "open"
STATE_CLOSED = "closed"

STATE_CHOICES = [STATE_NOT_YET_OPEN, STATE_OPEN, STATE_CLOSED]


class SubmissionClosed(Exception):
    """Raised by :func:`assert_open_for_submission`. Maps to HTTP 403 (D-02).

    **403 and never a 302.** ``run.py`` follows redirects, so a redirect comes
    back as a 200 and fails the check while looking correct in a browser. An
    empty body is permitted but a *named* body is better: the guard's name is
    what makes the refusal auditable.
    """

    def __init__(
        self,
        message: str,
        *,
        event_id: str,
        state: str,
        closes_at: datetime | None = None,
        opens_at: datetime | None = None,
        now: datetime | None = None,
    ) -> None:
        super().__init__(message)
        self.event_id = event_id
        self.state = state
        self.closes_at = closes_at
        self.opens_at = opens_at
        self.now = now

    @property
    def refused_by(self) -> str:
        return GUARD_NAME

    def as_dict(self) -> dict:
        """The refusal as JSON. Every field is one a reader can act on."""
        return {
            "refused_by": GUARD_NAME,
            "reason": self.state,
            "detail": str(self),
            "event": self.event_id,
            "submissions_close": _iso(self.closes_at),
            "submissions_open": _iso(self.opens_at),
            "at": _iso(self.now),
        }


@dataclass(frozen=True)
class SubmissionWindow:
    """Where ``now`` sits in an event's submission window, and why."""

    state: str
    opens_at: datetime | None
    closes_at: datetime
    now: datetime

    @property
    def is_open(self) -> bool:
        return self.state == STATE_OPEN

    def explain(self) -> str:
        """One sentence a human can read, naming the date that decided it."""
        if self.state == STATE_NOT_YET_OPEN:
            return f"Submissions have not opened yet; they open at {_iso(self.opens_at)}."
        if self.state == STATE_CLOSED:
            return f"Submissions closed at {_iso(self.closes_at)}."
        return f"Submissions are open until {_iso(self.closes_at)}."


def submission_window(event, *, now: datetime | None = None) -> SubmissionWindow:
    """Where ``now`` sits in ``event``'s submission window. Pure; raises nothing.

    Read-only, so the gallery, the organizer's dashboard and the guard itself
    all ask the same question of the same function. Three callers asking three
    separate "is it closed" questions is how a portal ends up with a badge that
    says open and a form that says closed.
    """
    moment = now or timezone.now()
    opens_at = event.submissions_open
    closes_at = event.submissions_close

    if opens_at is not None and moment < opens_at:
        state = STATE_NOT_YET_OPEN
    elif moment >= closes_at:
        state = STATE_CLOSED
    else:
        state = STATE_OPEN

    return SubmissionWindow(state=state, opens_at=opens_at, closes_at=closes_at, now=moment)


def assert_open_for_submission(event, *, now: datetime | None = None) -> SubmissionWindow:
    """Raise :class:`SubmissionClosed` unless ``event`` is accepting submissions.

    The one function every write path calls. Returns the window on success so a
    caller that wants to record the decision has it without asking twice.
    """
    window = submission_window(event, now=now)
    if window.is_open:
        return window

    raise SubmissionClosed(
        window.explain(),
        event_id=event.pk,
        state=window.state,
        closes_at=window.closes_at,
        opens_at=window.opens_at,
        now=window.now,
    )


def _iso(value: datetime | None) -> str | None:
    """ISO-8601 in UTC, or None. Never a bare ``str(datetime)``.

    A timestamp in a response body is something a human reads and something a
    test asserts on, and ``str(datetime)`` renders a space and a microsecond
    offset that neither of those can rely on.
    """
    if value is None:
        return None
    if timezone.is_naive(value):
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
