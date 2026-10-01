"""The first-run wizard at ``/setup/`` -- and the only unauthenticated write path.

**One deployment, one hackathon, so provisioning happens once.** The wizard's
authorisation is therefore not a permission check but a fact about the database:
*no event exists*. The moment one does, ``/setup/`` refuses with the same bare
403 everything else in the portal uses -- empty body, no ``Location`` -- because
the whole surface is the same shape of "you may not do this here".

**Why the CSRF token and the password confirmation are not optional.** This is
the only endpoint an unauthenticated browser can POST to, so it is the only place
a cross-site request could create an organizer. Django's middleware requires the
token on every POST, and the form carries it like every other form in the portal.

The password is never logged, never echoed back, and never included in an error
message. ``ProvisionRequest`` takes it as an argument so it exists in exactly one
place for exactly as long as it takes.
"""

from __future__ import annotations

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from reviewer.isolation.refusal import deny
from reviewer.setup.provisioning import (
    DEFAULT_CRITERIA,
    MIN_PASSWORD_LENGTH,
    ProvisioningError,
    ProvisionRequest,
    TrackSpec,
    already_provisioned,
    default_window,
    provision,
)

#: The guard name a refusal reports, matching the portal's convention that a 403
#: must say WHICH rule refused (F-40) so a client can tell it from a 400.
GUARD = "assert_setup_unprovisioned"


def _tracking(field: str) -> str:
    """Use the browser's own validation first; this is the server's version."""
    if not field:
        return "This field is required."
    if len(field) > 200:
        return "Keep this under 200 characters."
    return ""


def _parse_dt(raw: str, label: str):
    """Parse ``YYYY-MM-DDTHH:MM`` from a ``datetime-local`` input.

    **Parsed as naive-local and made aware immediately.** ``datetime-local`` sends
    no timezone, and treating that string as UTC is how an organizer in UTC+5:30
    ends up with a window that closed five and a half hours before it opened.
    Django's ``timezone.make_aware`` attaches the *server's* zone, which is the
    only zone we can honestly claim to know -- so the form states it.
    """
    import datetime as dt

    try:
        parsed = dt.datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None, f"{label} is not a date and time. Use the picker."
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed, ""


@require_http_methods(["GET", "POST"])
def setup(request):
    """Provision the deployment, or explain why it already exists."""
    if already_provisioned():
        return deny(GUARD)

    window = default_window()
    errors: dict[str, str] = {}
    values = {
        "event_name": "",
        "organizer_name": "",
        "organizer_email": "",
        "starts_at": window["starts_at"].strftime("%Y-%m-%dT%H:%M"),
        "submissions_close": window["submissions_close"].strftime("%Y-%m-%dT%H:%M"),
        "judging_closes_at": window["judging_closes_at"].strftime("%Y-%m-%dT%H:%M"),
        "tracks_text": "",
        "description": "",
    }

    if request.method == "GET":
        return render(
            request,
            "setup/setup.html",
            {"values": values, "criteria": DEFAULT_CRITERIA, "errors": {}},
        )

    values.update(
        {key: (request.POST.get(key) or "").strip() for key in values if key != "tracks_text"}
    )
    values["tracks_text"] = request.POST.get("tracks_text") or ""

    if values["organizer_email"] and "@" not in values["organizer_email"]:
        errors["organizer_email"] = "That does not look like an email address."

    password = request.POST.get("password") or ""
    confirm_field = "password_confirm"
    if len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = f"At least {MIN_PASSWORD_LENGTH} characters."

    if password and request.POST.get(confirm_field) != password:
        errors[confirm_field] = "The two passwords do not match."

    for field in ("event_name", "organizer_name", "organizer_email"):
        message = _tracking(field)
        if message:
            errors[field] = message

    parsed = {}
    for field, label in (
        ("starts_at", "Start"),
        ("submissions_close", "Submissions close"),
        ("judging_closes_at", "Judging closes"),
    ):
        moment, message = _parse_dt(values[field], label)
        parsed[field] = moment
        if message:
            errors[field] = message

    if errors:
        return render(
            request,
            "setup/setup.html",
            {"values": values, "criteria": DEFAULT_CRITERIA, "errors": errors},
        )

    # One track per line, blanks dropped, duplicates refused rather than merged:
    # two tracks with one slug would make assignment unreachable for both.
    tracks: list[TrackSpec] = []
    seen: set[str] = set()
    for line in values["tracks_text"].splitlines():
        name = line.strip()
        if not name:
            continue
        from reviewer.setup.provisioning import slugify

        key = slugify(name)
        if key in seen:
            errors["tracks_text"] = f"{name!r} appears twice."
            break
        seen.add(key)
        tracks.append(TrackSpec(name=name))
    if errors:
        return render(
            request,
            "setup/setup.html",
            {"values": values, "criteria": DEFAULT_CRITERIA, "errors": errors},
        )

    try:
        provision(
            ProvisionRequest(
                organizer_email=values["organizer_email"],
                organizer_name=values["organizer_name"],
                password=password,
                event_name=values["event_name"],
                description=values.get("description", ""),
                starts_at=parsed["starts_at"],
                submissions_close=parsed["submissions_close"],
                judging_closes_at=parsed["judging_closes_at"],
                tracks=tuple(tracks),
            )
        )
    except ProvisioningError as exc:
        errors["form"] = str(exc)
        return render(
            request,
            "setup/setup.html",
            {"values": values, "criteria": DEFAULT_CRITERIA, "errors": errors},
        )

    return HttpResponseRedirect("/login/?welcome=1")


def setup_done(request) -> HttpResponse:
    """Where the wizard sends you. Says one useful sentence, then gets out of the way."""
    return render(request, "setup/done.html", {})
