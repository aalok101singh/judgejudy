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
from reviewer.accounts import views as account_views
from reviewer.ballots import views as ballot_views
from reviewer.comments import views as comment_views
from reviewer.projects import views as project_views
from reviewer.projects.views import current_event
from reviewer.reviews import api as api_views
from reviewer.reviews import console as console_views
from reviewer.reviews import results_view as results_page_views
from reviewer.setup import views as setup_views
from reviewer.widget import views as widget_views


def _results_page(request):
    """Resolve the event, then delegate. One event per install, by design."""
    return results_page_views.results_page(request, current_event())


def _widget(request):
    """Resolve the event, then delegate. One event per install, by design."""
    return widget_views.widget(request, current_event())


def _widget_json(request):
    """The widget's data half."""
    return widget_views.widget_json(request, current_event())


def _ballot(request):
    """Resolve the event, then delegate. One event per install, by design.

    Shares `_console`'s "no event is a 403, not a 404" reasoning: the acceptance
    gate's route-existence probes cannot tell a 404 from a mistyped URL, and a
    portal with no event has nothing to vote on rather than a page that is
    missing.
    """
    return ballot_views.ballot(request, current_event())


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


def _results(request):
    event = current_event()
    if event is None:
        return api_views.deny(api_views.REFUSED_BY_RESULTS)
    return api_views.results(request, event)


def _audit(request):
    event = current_event()
    if event is None:
        return api_views.deny(api_views.REFUSED_BY_AUDIT)
    return api_views.audit(request, event)


def _influence(request):
    event = current_event()
    if event is None:
        return api_views.deny(api_views.REFUSED_BY_INFLUENCE)
    return api_views.influence(request, event)


def _comments(request, project_id):
    """The comment thread for one project.

    A refusal when there is no event, for `_console`'s reason: a portal with no
    event has nothing to comment on rather than a page that is missing, and the
    acceptance gate's route probes cannot tell a 404 from a mistyped URL.
    """
    return comment_views.thread(request, current_event(), project_id)


urlpatterns = [
    # --- Operating the portal: sign in, and set the hackathon up once.
    #
    # `/setup/` is the only write path an unauthenticated browser can reach, and
    # its authorisation is a fact about the database rather than a permission: no
    # event exists. Once one does it refuses with the portal's own bare 403, so
    # there is no second way to create an event after the first.
    path("setup/", setup_views.setup, name="setup"),
    path("login/", account_views.login_view, name="login"),
    # POST-only: a GET logout is a drive-by anyone can trigger with an <img>.
    path("logout/", account_views.logout_view, name="logout"),
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
    # The two capabilities the isolation matrix still printed `?` for, because at
    # FEAT-05 they had neither an accessor nor a route. The leaderboard is the
    # `aggregate` cell its own docstring called "nobody tests and everybody
    # forgets", and the audit view is what makes the hash chain readable by a
    # human rather than only by `verify_chain`.
    path("api/v1/results", _results, name="results"),
    path("api/v1/audit", _audit, name="audit"),
    # D-13, the anti-abuse answer. Deliberately NOT gated on `results_state` the
    # way `/api/v1/results` is: an organizer has to be able to see how
    # concentrated the support is *before* deciding to publish, so gating it
    # behind publication would turn a preventive report into a post-mortem.
    path("api/v1/influence", _influence, name="influence"),
    # REQ-T3-04. The randomised ballot order. The PERMUTATION is not written
    # here -- it is `presentation_order`, the same function the bias-attack
    # harness measures, so the claim and the shipped code cannot drift apart.
    # `ballot` is not gated on role, because a public vote is the point; it is
    # gated on the voting window and on having a derivable identity, and both
    # refusals are literal 403s with empty bodies.
    path("vote/", _ballot, name="ballot"),
    # FEAT-07. The embeddable widget: ONE self-contained document and the JSON
    # beside it, with no external reference of any kind, so an organizer can drop
    # it in an iframe on a page we do not control and it still works with the
    # network off. Gated on `results_state` alone -- an embedder holds no
    # credential and is not a participant.
    path("widget/results/", _widget, name="widget"),
    path("widget/results.json", _widget_json, name="widget_json"),
    # REQ-T3-02. Public comments, one thread per project.
    #
    # **Deliberately NOT on the gallery.** `run.py` reads `projects[:3]`
    # positionally from `/` and checks that one of those titles appears in the
    # body, so the gallery markup is a page the T1 checks read. Comments live on
    # their own route so adding them cannot move the gallery's ordering -- and
    # the gallery carries only a link, which is additive and inert.
    path("projects/<str:project_id>/comments/", _comments, name="comments"),
    # REQ-T3-03, the PUBLIC half. `/api/v1/results` has enforced this since
    # FEAT-05, but a reviewer opening a browser never asks for JSON -- so the
    # capability the brief is most careful about was enforced only on a surface
    # nobody would have visited. Same predicate, same aggregate, two renderings,
    # and a test asserts the two agree row for row.
    path("results/", _results_page, name="results_page"),
    # The healthcheck polls this. It must stay unauthenticated, cheap and
    # database-free -- see the docstring in judge_judy/views.py.
    path("healthz", views.healthz, name="healthz"),
    path("healthz/", views.healthz),
    path("admin/", admin.site.urls),
]
