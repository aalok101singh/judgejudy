"""The health endpoint, and the contract the container depends on.

`/healthz` is load-bearing in a way that is easy to miss: `docker compose up
--wait` blocks on it, the Dockerfile's HEALTHCHECK calls it, and
`tools/prove_offline.py` polls it to prove the portal boots with no network. If
it starts querying the database, the portal becomes un-reportable during the
migration that is creating the database — which is exactly when it most needs
to be distinguishable from a broken one.

So "does not touch the database" is a test, not a comment.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestHealthz:
    """`/healthz` — the liveness probe."""

    def test_returns_200_without_authentication(self) -> None:
        """The container's healthcheck sends no credentials at all.

        If this ever needed a session, the container would report itself
        unhealthy forever while being perfectly able to serve.
        """
        response = Client().get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "checks": {}}

    def test_resolves_by_name(self) -> None:
        """Both the named URL and the bare path must work.

        The compose healthcheck uses the literal path; anything else in the
        codebase uses reverse(). If only one of them resolved, one of the two
        callers would be broken in a way that only shows up at a break.
        """
        assert reverse("healthz") == "/healthz"

    def test_tolerates_a_trailing_slash(self) -> None:
        """A judge typing the host by hand should not get a 404."""
        assert Client().get("/healthz/").status_code == 200

    def test_does_not_touch_the_database(self) -> None:
        """The liveness probe must not query anything.

        This is the property the whole health contract rests on, and it is
        asserted rather than assumed: `django_assert_num_queries(0)` fails the
        test if a single query is issued. It passes here because the view
        returns a literal dict.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            response = Client().get("/healthz")

        assert response.status_code == 200
        assert captured.captured_queries == [], (
            "/healthz issued SQL. The healthcheck runs before and during "
            "migrations, when the schema may not exist yet. Use ?deep=1 for "
            "the database check instead."
        )


class TestDeepHealthz:
    """`/healthz?deep=1` — the human's diagnostic."""

    def test_reports_the_database_as_ok(self) -> None:
        """A human debugging a stuck boot needs the real answer, not a guess."""
        response = Client().get("/healthz?deep=1")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["checks"]["database"] == "ok"

    def test_reports_degraded_rather_than_crashing(self) -> None:
        """A broken database must be reported, not raised.

        A 500 from the diagnostic endpoint turns "the database is unreachable"
        into "the portal is crashing", which is a different bug report and a
        slower diagnosis. So the failure is caught, named and returned as 503.
        """
        from unittest.mock import patch

        with patch("judge_judy.views.connection.cursor", side_effect=OSError("gone")):
            response = Client().get("/healthz?deep=1")

        assert response.status_code == 503
        payload = response.json()
        assert payload["status"] == "degraded"
        assert "OSError" in payload["checks"]["database"]


class TestHome:
    """`/` — the first thing a judge sees."""

    def test_is_public(self) -> None:
        """No authentication. A judge opens this before logging in."""
        assert Client().get("/").status_code == 200

    def test_is_server_rendered_html(self) -> None:
        """The body must contain the content, not just load a bundle.

        This is the acceptance-relevant part: the front door has to work with
        no network and no JavaScript. A portal whose landing page is an empty
        <div> that a script fills in shows a judge a blank page while the
        container reports itself healthy.
        """
        body = Client().get("/").content.decode()

        assert "<!doctype html>" in body.lower()
        assert "Judge Judy" in body

    def test_links_the_healthcheck(self) -> None:
        """The page points at the one endpoint that proves it is alive."""
        body = Client().get("/").content.decode()

        assert "/healthz" in body


class TestAdmin:
    """`/admin/` — reachable, and correctly refusing an anonymous visitor."""

    def test_redirects_anonymous_visitors_to_login(self) -> None:
        """302, not 403.

        An unauthenticated visitor is not a forbidden role. Answering 403 here
        would be the same category error as the isolation design is careful to
        avoid elsewhere — conflating "who are you" with "what may you do".
        """
        response = Client().get("/admin/")

        assert response.status_code == 302
        assert "/login" in response["Location"]
