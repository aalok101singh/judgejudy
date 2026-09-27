"""Root URL configuration.

Route naming has a hard constraint that is not obvious from the code: the
organizers' checker reads route paths out of ``.dogfood.toml`` at the repo
root, and T2 is scored by whether a judge is refused a URL it could otherwise
type. So the paths here are deliberately boring, and the security-relevant ones
are named after the *resource* rather than after the role -- because the
refusal has to be a decision inside the view, not a fact about the spelling of
a path.

This module is also the checklist for what exists. At FEAT-01 there are three
routes and none of them is a feature. That is the correct size for this
feature, not an omission.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from judge_judy import views

urlpatterns = [
    path("", views.home, name="home"),
    # The healthcheck polls this. It must stay unauthenticated, cheap and
    # database-free -- see the docstring in judge_judy/views.py.
    path("healthz", views.healthz, name="healthz"),
    path("healthz/", views.healthz),
    path("admin/", admin.site.urls),
]
