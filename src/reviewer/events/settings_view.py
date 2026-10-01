"""``/organizer/settings/`` -- the lifecycle, in a browser, without a shell.

**This is the last thing between "set up" and "run an event".** Before it, an
organizer finished ``/setup/`` in a browser and then had to drop to
``docker compose exec`` to open the submission window, open voting, or publish
results -- because ``publish_results`` is a management command and the deadlines
have no editable surface at all. A tool whose lifecycle ends in a shell is a tool
for the person who built it.

**What is editable, and why that list and not a bigger one.**

- **The windows** (start, submissions close, judging close). These are the only
  thing gating submissions, so they have to be reachable.
- **The voting mode and its window.** Provisioning creates an event with
  ``voting_mode="closed"`` -- the safe default, because a public vote nobody can
  deduplicate is the free-for-all REQ-T3-01 names. **An organizer has to be able
  to open it**, and the three modes are genuinely different products: ``open_link``
  needs no account, ``email_gated`` and ``authenticated`` do.
- **Publishing results.** Goes through :func:`reviewer.audit.publication.publish`,
  **not** a direct field write, so the ``results_hash`` and the audit entry are
  produced by the same code the CLI uses. A settings page that flipped
  ``results_state`` behind the hash's back would be the F-92 defect in a new
  place.

**What is deliberately not editable here**, and it is worth being explicit:

- **The rubric's criteria and weights.** A judge who has already scored under one
  rubric must not see the board move underneath them; ``rubric_weights_locked_at``
  exists for that, and unlocking it is a deliberate act rather than a field in a
  form.
- **Track membership of a project**, because it decides which judges can see it.
- **Anything about isolation.** No setting here can widen what an actor reads.
  That is the point of the whole design and a settings page is exactly where that
  would be tried.

**Every change is an audit entry.** The chain is append-only and exists so
"when did judging close" is answerable; a settings page that changed a deadline
without writing one would make the chain a record of everything except the only
thing anybody asks it about.
"""

from __future__ import annotations

import datetime as dt

from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from reviewer.events.models import (
    VOTING_AUTHENTICATED,
    VOTING_CLOSED,
    VOTING_EMAIL_GATED,
    VOTING_OPEN_LINK,
)
from reviewer.isolation import Actor
from reviewer.isolation.refusal import deny

REFUSED_BY_ROLE = "organizer_settings.role"

#: The modes a form may set, with the wording an organizer needs. **The constant
#: is imported, never re-typed**, so a new mode in the schema cannot be
#: unselectable here without this list failing.
VOTING_MODES = (
    (VOTING_CLOSED, "Closed — nobody can vote"),
    (VOTING_OPEN_LINK, "Open link — anyone can vote, no account needed"),
    (VOTING_EMAIL_GATED, "Email gated — voters must sign in"),
    (VOTING_AUTHENTICATED, "Authenticated — only existing accounts can vote"),
)

LABEL = "organizer_settings"


def _event(request):
    from reviewer.projects.views import current_event

    return current_event()


def _actor(request, event) -> Actor:
    return Actor.for_request(request, event)


def _dt(raw: str, label: str):
    """Parse a ``datetime-local`` value into an aware datetime.

    **Naive in, aware out, always.** A ``datetime-local`` input carries no zone,
    and reading one as UTC is how an organizer in UTC+5:30 gets a submission
    window that closed five and a half hours before it opened. We attach the
    *server's* zone because it is the only one we can honestly claim to know, and
    the form says so.
    """
    from django.utils import timezone

    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def _fmt(value) -> str:
    return value.strftime("%Y-%m-%dT%H:%M") if value else ""


def _record(event, actor, action: str, before, after) -> None:
    """One audit entry per changed setting, with the old and new value.

    **Not one entry per form submit.** A settings form that changes nothing should
    not write to an append-only chain -- a chain full of no-op entries is a chain
    nobody reads, which is the F-80 shape for a log.
    """
    from reviewer.audit.chain import append

    for name, new_value in sorted(after.items()):
        old_value = getattr(event, name, None)
        # **Compared at the precision the form can express.** A `datetime-local`
        # input carries whole minutes, so a stored `starts_at` with microseconds
        # comes back without them -- and an organizer who opened the page and hit
        # Save having changed nothing would write an audit entry for a change that
        # is only the loss of sub-second precision. The rendered values are what
        # the organizer believes they are editing, so those are what get compared.
        shown_old = _fmt(old_value) if hasattr(old_value, "year") else old_value
        shown_new = _fmt(new_value) if hasattr(new_value, "year") else new_value
        if shown_old == shown_new:
            continue
        append(
            event,
            f"{action}.{name}",
            # **`actor.user`, not `actor`.** `AuditEntry.actor` is a FK to
            # `accounts.User`; `chain.append` takes the resolved user. The first
            # draft passed the Actor, which raises `ValueError: must be a "User"
            # instance` -- and it raised on *every* save, so the page was a 500 for
            # exactly the people allowed to use it.
            actor=actor.user,
            object_type="events.Event",
            object_id=str(event.pk),
            before={"value": shown_old},
            after={"value": shown_new},
        )


@require_http_methods(["GET", "POST"])
def settings_view(request):
    """Edit the event. Organizer only, and a refusal is the portal's own."""
    from reviewer.events.models import RESULTS_PUBLISHED

    event = _event(request)
    if event is None:
        return deny("organizer_settings.no_event")

    actor = _actor(request, event)
    if not (actor.is_organizer or actor.is_admin):
        return deny(REFUSED_BY_ROLE)

    if request.method == "GET":
        return render(
            request,
            "organizer/settings.html",
            {
                "event": event,
                "voting_modes": VOTING_MODES,
                "values": {
                    "name": event.name,
                    "description": event.description,
                    "starts_at": _fmt(event.starts_at),
                    "submissions_open": _fmt(event.submissions_open),
                    "submissions_close": _fmt(event.submissions_close),
                    "judging_closes_at": _fmt(event.judging_closes_at),
                    "voting_mode": event.voting_mode,
                    "voting_opens_at": _fmt(event.voting_opens_at),
                    "voting_closes_at": _fmt(event.voting_closes_at),
                },
                "errors": {},
                "published": event.results_state == RESULTS_PUBLISHED,
                "has_rubric": event.rubrics.exists(),
            },
        )

    errors: dict[str, str] = {}
    after: dict[str, object] = {}

    # **`action=publish` short-circuits, before any field is parsed.**
    # The first draft ran the same save path for both buttons, and the publish
    # form only carried the fields a publication needs -- so it nulled
    # `starts_at`, hit `NOT NULL`, and returned a 500. Two buttons on one path
    # means the weaker form's omissions are the stronger form's bugs, so
    # publishing does not touch the settings at all.
    if request.POST.get("action") == "publish":
        return _publish(request, event, actor)

    name = (request.POST.get("name") or "").strip()
    if not name:
        errors["name"] = "The event needs a name; it is the title on every page."
    else:
        after["name"] = name[:200]

    after["description"] = (request.POST.get("description") or "")[:5000]

    for field, label in (
        ("starts_at", "Start"),
        ("submissions_open", "Submissions open"),
        ("submissions_close", "Submissions close"),
        ("judging_closes_at", "Judging closes"),
        ("voting_opens_at", "Voting opens"),
        ("voting_closes_at", "Voting closes"),
    ):
        # **Absent means unchanged, and only a key the form actually sent is ever
        # written.** Two defects shared this line. The first wrote `None` for any
        # date missing from the POST, so the publish button -- whose form
        # deliberately carried fewer fields -- nulled `starts_at`, hit `NOT NULL`,
        # and 500'd; and the second read `after[field]` for an unparseable date
        # that had never been assigned, which is a `KeyError` on the 400 path
        # itself. Leaving an absent key out of `after` fixes both: a partial POST
        # preserves what it did not mention, and a full form still clears a window
        # by submitting it empty.
        if field not in request.POST:
            continue
        raw = request.POST.get(field) or ""
        moment = _dt(raw, label)
        if raw and moment is None:
            errors[field] = f"{label} is not a date and time."
            continue
        after[field] = moment

    mode = request.POST.get("voting_mode") or VOTING_CLOSED
    if mode not in dict(VOTING_MODES):
        errors["voting_mode"] = "Pick one of the listed modes."
    else:
        after["voting_mode"] = mode

    # **Ordering is checked against the values that would result, not the ones
    # posted.** A partial POST carries none of these, so validating `after` alone
    # would silently skip every ordering check -- the form would accept a
    # submissions window that closes before the event starts, by simply not
    # mentioning the start. Each message names the two fields involved.
    def _will_be(field):
        return after.get(field, getattr(event, field, None))

    if not errors:
        start = _will_be("starts_at")
        close = _will_be("submissions_close")
        judging = _will_be("judging_closes_at")
        voting_open = _will_be("voting_opens_at")
        voting_close = _will_be("voting_closes_at")

        if close and start and close <= start:
            errors["submissions_close"] = "Submissions must close after the event starts."
        if judging and close and judging < close:
            errors["judging_closes_at"] = (
                "Judging cannot close before submissions close -- judges score "
                "what was submitted, not what has not arrived yet."
            )
        if voting_close and voting_open and voting_close <= voting_open:
            errors["voting_closes_at"] = "Voting must close after it opens."

    if errors:
        return render(
            request,
            "organizer/settings.html",
            {
                "event": event,
                "voting_modes": VOTING_MODES,
                "values": request.POST,
                "errors": errors,
                "published": event.results_state == RESULTS_PUBLISHED,
                "has_rubric": event.rubrics.exists(),
            },
            status=400,
        )

    _record(event, actor, "event.settings", None, after)

    for field, value in after.items():
        setattr(event, field, value)
    event.save()

    messages.success(request, "Settings saved.")
    return HttpResponseRedirect("/organizer/settings/")


def _publish(request, event, actor) -> HttpResponse:
    """Publish through the publication module, never by writing the field.

    The hash and the audit entry have to come from the same code the CLI uses, or
    a published result exists that ``verify_audit`` cannot account for -- which is
    the F-92 shape moved into a browser.

    **An event with no rubric is refused in words, not by raising.**
    ``publication.publish`` signals this with ``ValueError``, and letting it escape
    turns the one button on the page into a 500 -- for the organizer, who is the
    only person who can see it. The check is duplicated here deliberately: the
    precondition is a *product* fact (there is nothing to publish yet), and it is
    also what lets the template hide the button.
    """
    from reviewer.audit.publication import publish

    if not event.rubrics.exists():
        messages.error(
            request,
            "There is no rubric on this event yet, so there is nothing to publish. "
            "Add one before publishing.",
        )
        return HttpResponseRedirect("/organizer/settings/")

    publish(event, actor)
    return HttpResponseRedirect("/organizer/settings/?published=1")
