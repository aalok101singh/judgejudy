"""Project-wide views that belong to no domain app.

Only two, and neither is a feature:

``healthz``
    The liveness probe the container healthcheck polls. It must answer from a
    cold start without touching the database, because the healthcheck is what
    tells `docker compose up` that the portal is ready -- and a probe that
    queries a table which does not exist yet would report the portal unhealthy
    during the very migration that is creating it.

``home``
    The page a judge sees when they open the portal for the first time. Its
    job at this stage is to be unmistakably *ours* and unmistakably *working*,
    so that a 200 from this route is never confused with a 200 from a proxy or
    a placeholder.

The gallery, the dashboard and everything a judge touches arrive in later
features. This module is the right size for FEAT-01 and it should not grow
past it without a reason recorded here.
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def healthz(request: HttpRequest) -> JsonResponse:
    """Report that the WSGI stack is serving requests.

    Deliberately does not touch the database. See the module docstring: the
    healthcheck gates readiness, and readiness has to be answerable while the
    schema is still being built.

    ``?deep=1`` is available for a human debugging a stuck boot. It runs a
    trivial query and is never used by the healthcheck, so a broken database
    shows up in a log line a human asked for rather than in a container that
    restart-loops on a probe.
    """
    payload: dict[str, object] = {"status": "ok", "checks": {}}

    if request.GET.get("deep"):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            payload["checks"]["database"] = "ok"
        except Exception as exc:
            payload["status"] = "degraded"
            payload["checks"]["database"] = f"{type(exc).__name__}: {exc}"
        return JsonResponse(payload, status=200 if payload["status"] == "ok" else 503)

    return JsonResponse(payload)


def home(request: HttpRequest) -> HttpResponse:
    """The landing page.

    Server-rendered HTML on purpose. It is the first thing a judge loads, it
    must work with the network off, and it must not depend on a JavaScript
    bundle having parsed. A portal whose front door needs JavaScript is a
    portal that shows a blank page to the person deciding whether it works.
    """
    return render(
        request,
        "home.html",
        {
            "tier": "FEAT-01",
            "status": "skeleton",
        },
    )
