"""The two surfaces a hackathon actually opens the portal for.

FEAT-03 owns exactly these: the **gallery** at ``/`` and the **submit** form at
``/projects/new``. The judge console, the dashboard and the export arrive later,
and the module docstring in ``judge_judy/views.py`` is where that separation is
recorded.

## The gallery's ordering is load-bearing, so it is written out

``run.py`` calls ``fixture_titles(fixture, n=3)``, which is ``projects[:3]``, and
asserts ``any(title in body for title in titles)`` over the whole response. So
the slice is **positional**: the first page of this route has to be in the
fixture's own order, or all three of ``Glass Signal``, ``Small Meadow`` and
``Deep Compass`` fall off page one and T1-2 fails for a reason that reads like a
data problem. ``importer.loader.gallery_queryset`` is the single place that
ordering is written, and it is not left to ``Meta.ordering``.

## The submit route is the highest-value 4xx in the project

``run.py`` accepts **any** 4xx for "closed event refuses submissions". Every
refusal that is not the deadline -- a 404, a CSRF rejection, a 401, a 405 --
reports PASS. That is F-11 turned on ourselves, and it is the failure this module
is shaped around:

* the refusal is a **403**, never a 302 (``run.py`` follows redirects);
* it is produced by :func:`reviewer.events.deadlines.assert_open_for_submission`
  and the body **names the guard**, so a test and the acceptance gate can tell
  "the deadline held" from "something else refused first";
* the CSRF exemption is **narrow** and asserted from both sides, because the
  alternative -- a blanket ``@csrf_exempt`` -- buys the right 403 by opening a
  real hole in the browser form on the same path.
"""

from __future__ import annotations

import json
from functools import wraps

from django.core.exceptions import ValidationError
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.middleware.csrf import CsrfViewMiddleware
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt

from reviewer.events.deadlines import (
    STATE_CHOICES,
    SubmissionClosed,
    assert_open_for_submission,
    submission_window,
)
from reviewer.events.models import Event
from reviewer.importer.loader import gallery_queryset
from reviewer.projects.models import Project
from reviewer.reviews.models import Review
from reviewer.teams.models import TeamMembership

#: Projects per gallery page. The brief is "at least 24", and the reason it
#: matters is arithmetic rather than taste: 41 projects across pages of 24 puts
#: the first 24 fixture ids on page one, which is where all three greppable
#: titles live. A page size of 8 or 10 would push ``Deep Compass`` onto page two
#: for no benefit a reader would notice.
GALLERY_PAGE_SIZE = 24

#: The two things a cross-origin HTML form cannot fake. A form can set neither
#: ``Content-Type: application/json`` nor a custom header without CORS, and
#: SameSite=Lax already blocks the cookie on a cross-site POST -- so a request
#: carrying one of these is a programmatic client, not a forged form post.
JSON_CONTENT_TYPE = "application/json"
XHR_HEADER = "X-Requested-With"
XHR_VALUE = "XMLHttpRequest"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Refusal bodies name the mechanism that refused. `new_project` means this
#: module; anything else names the layer below it. A reader debugging "the
#: checker says PASS" needs to know which of the two said no.
REFUSED_BY_VIEW = "new_project"


# --------------------------------------------------------------------- gallery


def current_event() -> Event | None:
    """The event this portal is showing. Lowest id, or ``None``.

    A single-tenant self-hosted portal has exactly one event, and a resolver that
    took an id from the URL would imply a second one. Ordered by id rather than
    an unordered ``.first()`` so the answer is the same on every call.
    """
    return Event.objects.order_by("id").first()


def gallery(request: HttpRequest) -> HttpResponse:
    """The public project gallery. No authentication, and never any.

    This is T1-1 ("gallery is public") and T1-2 ("project from fixtures shown"),
    and it is the one route a judge loads before they log in, so it must not
    depend on JavaScript having parsed: the titles are in the server-rendered
    body, which is the only thing ``urlopen`` ever sees.
    """
    event = current_event()
    if event is None:
        return render(
            request,
            "gallery.html",
            {
                "event": None,
                "projects": [],
                "counts": {},
                "tracks": [],
                "window": None,
                "window_state": "",
                "state_choices": STATE_CHOICES,
                "page": 1,
                "page_count": 1,
                "total": 0,
                "page_size": GALLERY_PAGE_SIZE,
                "empty_reason": "no event has been created yet",
            },
        )

    everything = gallery_queryset(event.pk)
    total = everything.count()
    page = _page_number(request, page_count=max(1, -(-total // GALLERY_PAGE_SIZE)))
    window = submission_window(event)
    on_page = list(everything[(page - 1) * GALLERY_PAGE_SIZE : page * GALLERY_PAGE_SIZE])
    counts = review_counts(on_page)

    # One query for the page, then an attribute per card. A template filter for a
    # dict lookup by a variable key would be the alternative, and a filter is
    # global state; a plain attribute on the instance the loop already has is not.
    for project in on_page:
        project.review_count = counts.get(project.pk, 0)

    return render(
        request,
        "gallery.html",
        {
            "event": event,
            "projects": on_page,
            "tracks": list(event.tracks.all()),
            "window": window,
            "window_state": window.state,
            "state_choices": STATE_CHOICES,
            "page": page,
            "page_count": max(1, -(-total // GALLERY_PAGE_SIZE)),
            "total": total,
            "page_size": GALLERY_PAGE_SIZE,
            "empty_reason": "",
        },
    )


def _page_number(request: HttpRequest, *, page_count: int) -> int:
    """The requested page, clamped into range. Never raises on ``?page=abc``."""
    try:
        wanted = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        return 1
    return min(max(1, wanted), page_count)


def review_counts(projects) -> dict:
    """Review counts for a page of projects, through the public accessor.

    One query for the whole page rather than one per card. The accessor is
    named ``public_review_counts`` and returns counts only; see
    ``reviewer.reviews.queryset`` for why it lives beside the scoped accessor
    rather than in this view.
    """
    if not projects:
        return {}
    return Review.objects.public_review_counts(projects[0].event_id, [p.pk for p in projects])


# ---------------------------------------------------------------------- submit


@csrf_exempt
def new_project(request: HttpRequest) -> HttpResponse:
    """``GET`` a form, ``POST`` a submission, and refuse both when the event is closed.

    **The CSRF exemption is conditional and that is the whole design.** A blanket
    ``@csrf_exempt`` would give the acceptance checker its 4xx -- and open a
    cross-site form-post hole on the same path, which is a real vulnerability in
    a portal whose only content is other people's work. So the view is exempt at
    the top level and re-enters Django's own ``CsrfViewMiddleware`` for any
    request that could have come from a browser form:

    ====================================  ===============
    request                                CSRF
    ====================================  ===============
    ``GET``                                not applicable
    ``POST`` + ``application/json``        exempt (a cross-origin form cannot send it)
    ``POST`` + ``X-Requested-With``        exempt (same reason)
    ``POST`` form-encoded or multipart     **enforced**
    ====================================  ===============

    ``bible/03`` §3.2 proposes exactly this and names the same compensating
    controls. The table is asserted from both directions in
    ``tests/test_denial_contract.py``, because an exemption only tested for "it
    does not fire" is an exemption nobody has measured.

    **The order of the refusals matters more than it looks.** Authentication,
    then the **deadline guard**, then the team check, then the write. The guard
    comes before the per-actor work on purpose: the deadline is a property of
    the event and the same answer is true for everyone, and putting it first
    means no authorization bug can shadow it. A check that passes because
    something *else* refused the request is the failure this feature exists to
    avoid.
    """
    if _requires_csrf(request):
        return _csrf_enforced(_new_project)(request)
    return _new_project(request)


def _requires_csrf(request: HttpRequest) -> bool:
    """Whether this request is one a cross-origin form could have sent."""
    if request.method in SAFE_METHODS:
        return False
    if (request.content_type or "").split(";")[0].strip() == JSON_CONTENT_TYPE:
        return False
    return request.headers.get(XHR_HEADER) != XHR_VALUE


def _csrf_enforced(view):
    """Run ``view`` behind Django's CSRF check, from inside an exempt view.

    **Two things had to be got right here, and the first version of this got
    both wrong.** Each is recorded because the failure mode in both cases was
    *silent*: a guard that does not fire looks exactly like a guard that has
    nothing to refuse.

    1. ``process_view`` is called **by hand**. ``MiddlewareMixin.__call__``
       only runs ``process_request`` and ``process_response``;
       ``CsrfViewMiddleware`` performs its check in ``process_view``, which
       Django's handler invokes and the middleware does not. Wrapping the view
       in the middleware and returning its result verifies nothing.
    2. ``request.csrf_processing_done`` is **cleared first**, defensively. The
       measured reason it is not load-bearing today: for an exempt callback
       ``process_view`` returns at its own ``csrf_exempt`` check *before*
       ``_accept`` is reached, and ``_accept`` is what sets the flag -- so on
       this path the flag is unset. It was written here on the belief that the
       outer middleware sets it, which was a library claim recalled rather than
       executed, and it would have become load-bearing the moment anything
       upstream called ``_accept``. A one-line guard against a plausible future
       is cheaper than the hour that finding would cost.

    A third mistake is in the call site rather than here: the wrapper must be
    applied to ``_new_project`` and not to the exempt ``new_project``, or the
    view calls itself and every form post dies with a ``RecursionError`` about
    1000 frames deep.

    **Read this before writing a test for it.** Django's test ``Client`` sets
    ``request._dont_enforce_csrf_checks`` unless constructed with
    ``enforce_csrf_checks=True``, and ``process_view`` honours that flag by
    accepting early. So a test that does not pass it observes *no CSRF
    behaviour at all* and a broken wrapper looks like a working one. That is
    how the first version of this function survived being run.

    The rejection goes back through ``process_response`` so the CSRF token is
    rotated on the way out; a client that failed once should not fail forever.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        middleware = CsrfViewMiddleware(lambda r: view(r, *args, **kwargs))
        request.csrf_processing_done = False
        middleware.process_request(request)
        rejection = middleware.process_view(request, view, args, kwargs)
        if rejection is not None:
            return middleware.process_response(request, rejection)
        return middleware.process_response(request, view(request, *args, **kwargs))

    return wrapper


def _new_project(request: HttpRequest) -> HttpResponse:
    event = current_event()
    if event is None:
        return _refuse("no event exists", status=403)

    if request.method == "GET":
        window = submission_window(event)
        return render(
            request,
            "projects/new_project.html",
            {
                "event": event,
                "window": window,
                "window_state": window.state,
                "teams": teams_for(request, event),
                "tracks": list(event.tracks.all()),
                "error": "",
            },
        )

    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    # 1. Who is asking. 401 and not 403: "you did not say who you are" and "you
    #    may not do this" are different answers, and conflating them is the
    #    category error tests/test_health.py::TestAdmin already guards against.
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return _refuse("a submission needs an authenticated team member", status=401)

    # 2. THE GUARD. This is the line the acceptance check exists to exercise, and
    #    `refused_by` in the body is what proves it was this line that refused.
    try:
        window = assert_open_for_submission(event)
    except SubmissionClosed as exc:
        return JsonResponse(exc.as_dict(), status=403)

    # 3. What this user may submit, which is a fact about their team.
    team = first_team_for(user, event)
    if team is None:
        return _refuse(
            "you are not on a team in this event, so there is nothing to submit on behalf of"
        )

    # 4. The write itself.
    project, error = create_project(_payload(request), event=event, team=team)
    if error:
        return _refuse(error, status=400)

    return JsonResponse(
        {
            "created": True,
            "id": project.pk,
            "title": project.title,
            "status": project.status,
            "submitted_at": project.submitted_at.isoformat().replace("+00:00", "Z"),
            "event": event.pk,
            "team": team.pk,
            "window": window.explain(),
            "url": reverse("gallery"),
        },
        status=201,
    )


def _refuse(detail: str, *, status: int = 403) -> JsonResponse:
    """A refusal from this module, named so it cannot be confused with the guard's."""
    return JsonResponse({"refused_by": REFUSED_BY_VIEW, "detail": detail}, status=status)


def _payload(request: HttpRequest) -> dict:
    """The request body, from JSON or from a form. Never raises on bad input."""
    if (request.content_type or "").split(";")[0].strip() == JSON_CONTENT_TYPE:
        try:
            decoded = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return request.POST.dict()


def create_project(payload: dict, *, event, team):
    """Validate and write one project. Returns ``(project, "")`` or ``(None, why)``.

    Validation is explicit rather than left to the model's own field validators,
    because the response has to name *which* field was wrong in a JSON body a
    person is reading. ``full_clean`` still runs at the end: it is what checks
    the model constraints, and a hand-built row that violates one raises
    ``IntegrityError`` at COMMIT otherwise -- which under
    ``transaction_mode = IMMEDIATE`` surfaces as a 500 rather than a 400.
    """
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    track_id = str(payload.get("track") or "").strip()
    repo_url = str(payload.get("repo_url") or "").strip()

    if not title:
        return None, "title is required"
    if not summary:
        return None, "summary is required"
    for field, value in (("title", title), ("summary", summary), ("repo_url", repo_url)):
        if value and len(value) > Project._meta.get_field(field).max_length:
            return None, f"{field} is longer than its column allows"

    track = event.tracks.filter(pk=track_id).first() if track_id else None
    if track is None:
        return None, f"track {track_id!r} is not a track of {event.pk!r}"

    default_slug = f"{slugify(title)[:60]}-{_next_suffix(event, team)}"
    slug = str(payload.get("slug") or "").strip() or default_slug
    if len(slug) > Project._meta.get_field("slug").max_length:
        return None, "slug is longer than its column allows"
    if Project.objects.filter(team=team, slug=slug).exists():
        return None, f"this team already has a submission at {slug!r}"

    project = Project(
        id=str(payload.get("id") or "").strip() or _next_project_id(event),
        event=event,
        team=team,
        track=track,
        slug=slug,
        title=title,
        summary=summary,
        repo_url=repo_url,
        tags=[],
        status="submitted",
        submitted_at=timezone.now(),
    )
    try:
        project.full_clean(exclude=["supersedes"])
    except ValidationError as exc:
        return None, "; ".join(exc.messages)
    project.save()
    return project, ""


def _next_project_id(event) -> str:
    """The next free ``prj_NN`` id for this event.

    A portal that lets a submitter pick their own primary key is a portal where
    one submission can overwrite another's, so the id is derived and collision
    checked rather than taken from the payload when the payload does not supply
    one. Derived rather than a sequence because the fixture's ids are the ones a
    judge's ``curl`` and a signed record refer to.
    """
    highest = 0
    for existing in Project.objects.filter(event=event).values_list("id", flat=True):
        tail = str(existing).rsplit("_", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"prj_{highest + 1:02d}"


def _next_suffix(event, team) -> int:
    """A small integer to keep an auto-slug unique within a team."""
    return team.projects.count() + 1


def first_team_for(user, event):
    """The team this user submits for: their first membership in this event.

    First by team id, not "the one they joined most recently" -- the fixture
    carries no join order worth trusting, and a deterministic answer is what a
    test can assert. A user on no team in this event gets ``None`` and is
    refused.
    """
    membership = memberships_of(user, event).first()
    return membership.team if membership else None


def teams_for(request: HttpRequest, event) -> list:
    """The teams the current request's user may submit for. Empty for a visitor."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return []
    return [membership.team for membership in memberships_of(user, event)]


def memberships_of(user, event):
    """This user's team memberships in this event, in a stable order."""
    return (
        TeamMembership.objects.filter(user=user, team__event=event)
        .select_related("team")
        .order_by("team_id")
    )
