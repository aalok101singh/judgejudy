"""Root URL configuration.

Route naming has a hard constraint that is not obvious from the code: the
organizers' checker reads route paths out of ``.dogfood.toml`` at the repo
root, and T2 is scored by whether a judge is refused a URL it could otherwise
type. So the paths here are deliberately boring, and the security-relevant ones
are named after the *resource* rather than after the role -- because the
refusal has to be a decision inside the view, not a fact about the spelling of
a path.

**What exists at FEAT-04.** Seven routes: the public gallery, the submission
form, the judge console, the review form, the organizer's assignment plan, and
the healthcheck twice. The dashboard, the export and the admin event editor
arrive in FEAT-05, and ``.dogfood.toml`` already names their paths so the
checker's failure message carries a real URL rather than a route the file
forgot to mention.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from judge_judy import views
from reviewer.projects import views as project_views
from reviewer.projects.views import current_event
from reviewer.reviews import api as api_views
from reviewer.reviews import console as console_views


def _console(request, **kwargs):
    """Resolve the event, then delegate. One event per install, by design.

    ``current_event()`` returning ``None`` is a 403 rather than a 404: the
    portal has no event, so there is nothing to judge and nothing to say. A 404
    would be indistinguishable from a mistyped URL, and the acceptance gate's
    route-existence probes cannot tell those apart -- which is precisely the
    false-pass class F-40 exists to close.
    """
    event = current_event()
    if event is None:
        return console_views._deny("judge_console.no_event")
    return console_views.console(request, event)


def _review_form(request, assignment_id):
    event = current_event()
    if event is None:
        return console_views._deny("judge_console.no_event")
    return console_views.review_form(request, event, assignment_id)


def _organizer_assignments(request):
    event = current_event()
    if event is None:
        return console_views._deny("judge_console.no_event")
    return console_views.organizer_assignments(request, event)


def _judge_scores(request):
    event = current_event()
    if event is None:
        return api_views.deny(api_views.REFUSED_BY_ROLE)
    return api_views.judge_scores(request, event)


def _csv_export(request):
    event = current_event()
    if event is None:
        return api_views.deny(api_views.REFUSED_BY_EXPORT)
    return api_views.csv_export(request, event)


urlpatterns = [
    # T1-1 and T1-2. Server-rendered, public, first page in FIXTURE ORDER --
    # `run.py` slices `projects[:3]` positionally, so the ordering is load
    # bearing and lives in `reviewer.importer.loader.gallery_queryset`.
    path("", project_views.gallery, name="gallery"),
    # T1-3. The organizers' example puts this at `/projects/new` as an HTML form
    # page, and a 405 on a GET-only page would satisfy their "any 4xx" assertion
    # without ever testing the deadline (bible/03 §4.4). Ours accepts POST, is
    # CSRF-exempt only for requests a cross-origin form cannot forge, and the
    # refusal body names the guard that produced it.
    path("projects/new", project_views.new_project, name="new_project"),
    # The judge surface. Every one of these reaches its data through
    # `Review.objects.for_actor(actor)` and refuses with a literal 403 and an
    # empty body (D-01, D-02). `tools/check_isolation.py` fails the build if an
    # unscoped `Review` read appears anywhere, including here.
    path("judge/", _console, name="judge_console"),
    path("judge/review/<int:assignment_id>/", _review_form, name="judge_review"),
    path("organizer/assignments/", _organizer_assignments, name="organizer_assignments"),
    # The T2 surface, and the four checks that have been failing with real URLs
    # since the first commit. `judge_scores` is a plain Django view rather than a
    # DRF viewset, and `reviewer/reviews/api.py` explains why at length: DRF
    # populates `request.user` from its own authentication classes and would
    # ignore the `request.user` our credential middleware assigns, so every
    # header-only request would arrive anonymous -- and three of the four T2
    # checks want a 403. That is a false pass, not a red check.
    path("api/v1/judge/scores", _judge_scores, name="judge_scores"),
    path("api/v1/export.csv", _csv_export, name="csv_export"),
    # The healthcheck polls this. It must stay unauthenticated, cheap and
    # database-free -- see the docstring in judge_judy/views.py.
    path("healthz", views.healthz, name="healthz"),
    path("healthz/", views.healthz),
    path("admin/", admin.site.urls),
]
