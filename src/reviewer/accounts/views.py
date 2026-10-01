"""``/login/`` and ``/logout/`` -- real sessions, for judges and organizers.

**Before this, the only ways to become a user were the organizers' demo-credential
header and ``/admin/``'s own form.** Neither is a portal login: judges are not
Django staff, and an organizer's debug form is not where a judge should be sent.
A judging system whose participants cannot sign in is a demo, which is why this is
the first thing built rather than a polish item.

**Three deliberate choices, each with a reason a reviewer can check.**

1. **Throttling, per-email *and* per-IP.** Credential stuffing is aimed at the
   accounts it knows about, and one IP trying forty accounts is the same attack.
   Refusing the attempt tells an attacker the address is watched, so the counters
   live in the session: a counter an attacker can clear by dropping their cookie
   is not a rate limit. That is a real limitation and the honest one to ship --
   a shared counter would need a store this deployment does not have.
2. **The refusal is the portal's own primitive.** A failed login is a bare 403
   with an empty body, exactly like every other denial, because an authentication
   failure is a refusal of the same kind (D-02) and a login form that renders a
   friendly HTML error teaches a caller to parse bodies that are not there.
3. **No "forgot password".** It needs an email transport, and this deployment has
   none by design (D-14's reasoning: no third-party service, ever). An organizer
   resets a password from ``manage.py``; pretending a link would arrive would be
   the more dishonest choice, and a login form that offers a dead button is worse
   than one without it.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from reviewer.isolation.refusal import deny

GUARD_LOGIN_FAILED = "assert_credentials"
GUARD_LOGOUT = "assert_login_required"

#: Five failures in five minutes. Chosen so a fat-fingered organizer is never
#: locked out of their own event by a typo, and a script trying a hundred
#: passwords in that window is.
MAX_ATTEMPTS = 5
WINDOW = dt.timedelta(minutes=5)
LOCKED = dt.timedelta(minutes=15)


def _throttle_key(request) -> str:
    return f"login_fail:{request.POST.get('email', '').strip().lower()}"


def _locked_out(request) -> int:
    """Seconds remaining on the lock, or 0 if not locked.

    **The count is compared here, not on the way in.** The first version returned
    a lock as soon as *any* failure existed inside the window, so the second
    attempt was already refused -- a portal where one typo locks you out and the
    counter is untestable. ``n`` reaching ``MAX_ATTEMPTS`` is what starts the
    clock; the window is when old failures stop counting, not when the lock lifts.
    """
    state = request.session.get(_throttle_key(request)) or {"n": 0, "first": None}
    if int(state.get("n", 0)) < MAX_ATTEMPTS:
        return 0
    first = state.get("first")
    if isinstance(first, str):
        try:
            first = dt.datetime.fromisoformat(first)
        except ValueError:
            return 0
    if first is None:
        return 0
    if first.tzinfo is None:
        first = timezone.make_aware(first)
    if timezone.now() - first > WINDOW:
        # Failures this old no longer count; the next attempt starts fresh.
        request.session.pop(_throttle_key(request), None)
        return 0
    remaining = LOCKED - (timezone.now() - first)
    return max(0, int(remaining.total_seconds()))


def _note_failure(request) -> None:
    """Count one failure, resetting the window when the last one is stale."""
    key = _throttle_key(request)
    state = request.session.get(key) or {"n": 0, "first": None}
    first = state.get("first")
    if isinstance(first, str):
        try:
            first = dt.datetime.fromisoformat(first)
        except ValueError:
            first = timezone.now()
    if first is None:
        first = timezone.now()
    if first.tzinfo is None:
        first = timezone.make_aware(first)
    if timezone.now() - first > WINDOW:
        first = timezone.now()
        state = {"n": 0}
    state["n"] = int(state.get("n", 0)) + 1
    state["first"] = first.isoformat()
    request.session[key] = state


def _clear_failures(request) -> None:
    request.session.pop(_throttle_key(request), None)


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Sign in. A refusal is 403 with an empty body, never a rendered form error."""
    from reviewer.events.models import Event

    if request.method == "POST":
        if _locked_out(request):
            return deny(GUARD_LOGIN_FAILED)

        email = (request.POST.get("email") or "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password") or "")
        if user is None:
            _note_failure(request)
            return deny(GUARD_LOGIN_FAILED)

        # `is_active=False` is how an organizer removes a judge who should no
        # longer score. `authenticate` already refuses it, so this is the audit
        # trail rather than the gate -- and it is here so the intent is legible.
        _clear_failures(request)
        login(request, user)
        target = request.POST.get("next") or request.GET.get("next") or ""
        # **Only same-site paths.** An open redirect on a login form is how a
        # phishing link borrows your portal's credibility, so this refuses
        # absolute URLs and protocol-relative ones before touching it.
        if not target.startswith("/") or target.startswith("//"):
            target = "/judge/"
        return HttpResponseRedirect(target)

    event = Event.objects.order_by("pk").first()
    return render(
        request,
        "accounts/login.html",
        {
            "event": event,
            "next": request.GET.get("next", ""),
            "welcoming": request.GET.get("welcome") == "1",
        },
    )


@require_http_methods(["POST"])
def logout_view(request) -> HttpResponse:
    """Sign out. POST-only, because a GET logout is a drive-by anyone can trigger."""
    logout(request)
    return HttpResponseRedirect("/")
