"""Project-wide views that belong to no domain app.

**One, and it is not a feature.**

``healthz``
    The liveness probe the container healthcheck polls. It must answer from a
    cold start without touching the database, because the healthcheck is what
    tells `docker compose up` that the portal is ready -- and a probe that
    queries a table which does not exist yet would report the portal unhealthy
    during the very migration that is creating it.

The landing page used to live here too. It moved to
``reviewer/projects/views.py`` when the gallery replaced it, because a gallery
is a domain surface and a module that "belongs to no domain app" is the wrong
home for one. Keeping it here would have meant this file growing past the
"should not grow past it" rule its own docstring sets, and the gallery needs a
``projects/`` template directory anyway.

Everything a judge touches -- the judge console, the dashboard, the export,
the event editor -- arrives in later features and lands in the app that owns
the domain, not here.
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse


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
