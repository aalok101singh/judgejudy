"""Root URL configuration.

Route naming has a hard constraint that is not obvious from the code: the
organizers' checker reads route paths out of ``.dogfood.toml`` at the repo
root, and T2 is scored by whether a judge is refused a URL it could otherwise
type. So the paths here are deliberately boring, and the security-relevant ones
are named after the *resource* rather than after the role -- because the
refusal has to be a decision inside the view, not a fact about the spelling of
a path.

**What exists at FEAT-03.** Four routes: the public gallery, the submission
form, and the healthcheck twice. The judge surface, the dashboard, the export
and the admin event editor arrive in FEAT-04 and FEAT-05, and
``.dogfood.toml`` already names their paths so the checker's failure message
carries a real URL rather than a route the file forgot to mention.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from judge_judy import views
from reviewer.projects import views as project_views

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
    # The healthcheck polls this. It must stay unauthenticated, cheap and
    # database-free -- see the docstring in judge_judy/views.py.
    path("healthz", views.healthz, name="healthz"),
    path("healthz/", views.healthz),
    path("admin/", admin.site.urls),
]
