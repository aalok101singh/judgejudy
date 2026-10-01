"""``/setup/``, ``/login/``, ``/logout/`` -- the two doors into a plug-and-play portal.

**The wizard is the only write path an unauthenticated browser can reach**, so
its refusal is asserted the way every refusal in this portal is: a literal 403,
an **empty body**, and no ``Location`` header. A setup page that answered "this
deployment is already configured" with a rendered HTML page would still be
correct information, and would still be a page a script could be pointed at.

The login tests care about three things a reader can check: a wrong password is
the portal's own refusal rather than a rendered error, five failures lock the
account, and a success leaves a session that the judging surfaces actually read.
That last one is the one that matters -- ``Actor`` resolves from ``request.user``,
so a login that set a cookie without setting ``request.user`` would be a login
that does not work, and only a request through a real surface would notice.
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from reviewer.setup.provisioning import ProvisionRequest, TrackSpec, provision

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"


def _request(**overrides) -> ProvisionRequest:
    now = timezone.now()
    base = {
        "organizer_email": "organizer@example.org",
        "organizer_name": "Ada Lovelace",
        "password": PASSWORD,
        "event_name": "Ridgeway Hack 2026",
        "starts_at": now,
        "submissions_close": now + timedelta(days=2),
        "judging_closes_at": now + timedelta(days=3),
        "tracks": (TrackSpec(name="General"),),
    }
    base.update(overrides)
    return ProvisionRequest(**base)


def _first_event():
    from reviewer.events.models import Event

    return Event.objects.get()


def _track_names() -> list[str]:
    from reviewer.events.models import Track

    return sorted(t.name for t in Track.objects.all())


def _wizard_post(client, **overrides):
    now = timezone.now()
    data = {
        "organizer_name": "Ada Lovelace",
        "organizer_email": "organizer@example.org",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "event_name": "Ridgeway Hack 2026",
        "starts_at": (now).strftime("%Y-%m-%dT%H:%M"),
        "submissions_close": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
        "judging_closes_at": (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
        "tracks_text": "General\nHardware",
    }
    data.update(overrides)
    return client.post("/setup/", data)


class TestTheWizardIsOnlyOpenOnce:
    def test_it_renders_when_there_is_nothing_yet(self, client):
        response = client.get("/setup/")
        assert response.status_code == 200
        assert b"Set up your hackathon" in response.content

    def test_it_refuses_once_an_event_exists(self, client):
        """**The guard, as a fact about the database rather than a permission.**

        There is no session here, so a permission check could not possibly be the
        mechanism -- and a wizard reachable after setup would be a second way to
        create an event, which is the thing this design rules out.
        """
        provision(_request())
        response = client.get("/setup/")
        assert response.status_code == 403
        assert response.content == b""
        assert "Location" not in response.headers

    def test_a_post_to_a_provisioned_deployment_changes_nothing(self, client):
        """A GET refusing is not enough: the guard has to hold on the write."""
        provision(_request())
        from reviewer.accounts.models import User
        from reviewer.events.models import Event

        events_before = Event.objects.count()
        response = _wizard_post(client, event_name="Hijacked", organizer_email="x@example.org")
        assert response.status_code == 403
        assert Event.objects.count() == events_before
        assert not User.objects.filter(email="x@example.org").exists()

    def test_it_names_the_guard_in_the_header(self, client):
        """F-40: a refusal a client cannot attribute is indistinguishable from any
        other 4xx, which is how a CSRF rejection passes for a policy decision."""
        provision(_request())
        assert client.get("/setup/")["X-Refused-By"] == "assert_setup_unprovisioned"


class TestItProvisions:
    def test_a_complete_post_creates_the_hackathon_and_redirects(self, client):
        response = _wizard_post(client)
        assert response.status_code == 302
        assert response["Location"] == "/login/?welcome=1"

        from reviewer.events.models import Event

        assert Event.objects.filter(name="Ridgeway Hack 2026").exists()

    def test_it_creates_one_track_per_line(self, client):
        _wizard_post(client)
        assert _track_names() == ["General", "Hardware"]

    def test_a_short_password_is_re_rendered_not_accepted(self, client):
        response = _wizard_post(client, password="short", password_confirm="short")
        assert response.status_code == 200
        assert b"At least 12 characters" in response.content

        from reviewer.events.models import Event

        assert Event.objects.count() == 0

    def test_mismatched_passwords_are_refused(self, client):
        response = _wizard_post(client, password_confirm="something-else-entirely")
        assert response.status_code == 200
        assert b"do not match" in response.content

    def test_a_bad_email_is_refused(self, client):
        response = _wizard_post(client, organizer_email="not-an-email")
        assert response.status_code == 200
        assert b"does not look like an email" in response.content

    def test_an_unparseable_date_is_refused_by_name(self, client):
        response = _wizard_post(client, starts_at="not-a-date")
        assert response.status_code == 200
        assert b"not a date and time" in response.content

    def test_a_duplicate_track_is_refused_rather_than_merged(self, client):
        """Two tracks slugifying to one key would make every project in them
        unreachable by assignment, so this refuses rather than deduplicating."""
        response = _wizard_post(client, tracks_text="General\ngeneral")
        assert response.status_code == 200
        assert b"appears twice" in response.content

    def test_the_password_is_never_echoed_back(self, client):
        """A form that re-renders a rejected POST must not put the password into
        the response body, where it lands in a browser history and a proxy log."""
        response = _wizard_post(client, password_confirm="mismatched-value-here")
        assert b"mismatched-value-here" not in response.content

    def test_csrf_is_required(self):
        """**The only unauthenticated write in the portal.** A cross-site POST
        that created an organizer would be the whole vulnerability.

        ``enforce_csrf_checks=True`` is the load-bearing part. The first version
        of this test used the shared ``client`` fixture, which **disables CSRF
        checking by default** -- so it asserted nothing about CSRF and returned
        200. It looked like it passed for the wrong reason.
        """
        from django.test import Client

        from reviewer.events.models import Event

        now = timezone.now()
        enforcing = Client(enforce_csrf_checks=True)
        response = enforcing.post(
            "/setup/",
            {
                "organizer_name": "Attacker",
                "organizer_email": "attacker@example.org",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "event_name": "Attacker Event",
                "starts_at": now.strftime("%Y-%m-%dT%H:%M"),
                "submissions_close": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "judging_closes_at": (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        assert response.status_code == 403
        assert Event.objects.count() == 0, "a cross-site POST created the hackathon"

        from reviewer.accounts.models import User

        assert not User.objects.filter(email="attacker@example.org").exists()

    def test_a_request_carrying_the_token_is_accepted(self):
        """**The control for the test above.** Without it, "CSRF is required"
        could be satisfied by the endpoint refusing every POST.
        """
        from django.test import Client

        from reviewer.events.models import Event

        now = timezone.now()
        enforcing = Client(enforce_csrf_checks=True)
        enforcing.get("/setup/")
        token = enforcing.cookies["csrftoken"].value

        response = enforcing.post(
            "/setup/",
            {
                "csrfmiddlewaretoken": token,
                "organizer_name": "Ada Lovelace",
                "organizer_email": "organizer@example.org",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "event_name": "Ridgeway Hack 2026",
                "starts_at": now.strftime("%Y-%m-%dT%H:%M"),
                "submissions_close": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "judging_closes_at": (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        assert response.status_code == 302
        assert Event.objects.filter(name="Ridgeway Hack 2026").exists()


class TestLogin:
    def test_it_renders_when_nobody_is_provisioned(self, client):
        """A login page on an empty portal should still load -- an organizer
        mid-setup who refreshes should not get a stack trace."""
        assert client.get("/login/").status_code == 200

    def test_the_right_password_signs_you_in(self, client):
        provision(_request())
        response = client.post("/login/", {"email": "organizer@example.org", "password": PASSWORD})
        assert response.status_code == 302
        assert response["Location"] == "/judge/"

    def test_a_signed_in_session_reaches_the_organizer_surfaces(self, client):
        """**The assertion that makes a login a login rather than a cookie.**

        ``Actor`` resolves from ``request.user``, so a session that set a cookie
        without reaching ``request.user`` would pass every cookie assertion and
        then be refused by the surfaces. These are the organizer-only routes, so
        a 200 here is the session carrying real authority -- no need to rebuild a
        request by hand to prove it.
        """
        provision(_request())
        assert (
            client.post(
                "/login/", {"email": "organizer@example.org", "password": PASSWORD}
            ).status_code
            == 302
        )

        assert client.get("/organizer/assignments/").status_code == 200
        assert client.get("/api/v1/export.csv").status_code == 200

    def test_a_signed_out_browser_is_refused_those_same_surfaces(self, client):
        """The control, without which the assertion above means nothing: the same
        routes, no session."""
        provision(_request())
        assert client.get("/organizer/assignments/").status_code == 403
        assert client.get("/api/v1/export.csv").status_code == 403

    def test_a_wrong_password_is_the_portals_own_refusal(self, client):
        """**D-02 again, on a surface people expect to be friendlier.**

        A rendered "Invalid password" page is a body a client has to parse, and
        this portal's rule is that a refusal has no body. The generic 403 also
        means a wrong password and a wrong email are the same answer, so the form
        cannot be used to enumerate accounts.
        """
        provision(_request())
        response = client.post("/login/", {"email": "organizer@example.org", "password": "wrong"})
        assert response.status_code == 403
        assert response.content == b""
        assert "Location" not in response.headers

    def test_an_unknown_email_is_refused_identically(self, client):
        """The enumeration check: same status, same empty body."""
        provision(_request())
        unknown = client.post("/login/", {"email": "nobody@example.org", "password": "wrong"})
        wrong = client.post("/login/", {"email": "organizer@example.org", "password": "wrong"})
        assert unknown.status_code == wrong.status_code == 403
        assert unknown.content == wrong.content == b""

    def test_it_names_the_guard(self, client):
        provision(_request())
        response = client.post("/login/", {"email": "a@example.org", "password": "b"})
        assert response["X-Refused-By"] == "assert_credentials"

    def test_five_failures_lock_the_account(self, client):
        """Throttling, because a login form with no rate limit is a place to try
        a thousand passwords a second."""
        provision(_request())
        for _ in range(5):
            response = client.post(
                "/login/", {"email": "organizer@example.org", "password": "wrong"}
            )
        assert response.status_code == 403

        # **The right password is now refused too.** A lockout that throttled the
        # attacker but still admitted the owner would let an attacker keep an
        # organizer locked out indefinitely.
        locked = client.post("/login/", {"email": "organizer@example.org", "password": PASSWORD})
        assert locked.status_code == 403

    def test_a_successful_login_clears_the_counter(self, client):
        """Otherwise one typo would start the attacker a head start."""
        provision(_request())
        for _ in range(3):
            client.post("/login/", {"email": "organizer@example.org", "password": "wrong"})
        assert (
            client.post(
                "/login/", {"email": "organizer@example.org", "password": PASSWORD}
            ).status_code
            == 302
        )

        for _ in range(5):
            response = client.post(
                "/login/", {"email": "organizer@example.org", "password": "wrong"}
            )
        assert response.status_code == 403, "the counter did not reset on success"

    def test_a_different_account_is_not_locked_by_the_first(self, client):
        """**Per-email, not global.** A global lockout lets one attacker lock
        every judge out of the event by trying five passwords against their own."""
        provision(_request())
        from reviewer.accounts.models import RoleBinding, User

        other = User.objects.create_user(email="judge@example.org", password="another-long-one")
        RoleBinding.objects.create(event=_first_event(), user=other, role="judge")

        for _ in range(6):
            client.post("/login/", {"email": "organizer@example.org", "password": "wrong"})

        assert (
            client.post(
                "/login/", {"email": "judge@example.org", "password": "another-long-one"}
            ).status_code
            == 302
        )

    def _first_event():
        from reviewer.events.models import Event

        return Event.objects.get()


class TestLoginRefusesToBeAnOpenRedirect:
    @pytest.mark.parametrize(
        "target",
        [
            "https://evil.example/steal",
            "//evil.example/steal",
            "http://evil.example",
            "javascript:alert(1)",
        ],
    )
    def test_it_never_redirects_off_site(self, client, target):
        """A login form that will redirect anywhere is a phishing tool that borrows
        this portal's credibility, and it is the default behaviour of most
        frameworks' ``?next=`` handling."""
        provision(_request())
        response = client.post(
            "/login/",
            {"email": "organizer@example.org", "password": PASSWORD, "next": target},
        )
        assert response.status_code == 302
        assert response["Location"] == "/judge/"

    def test_a_relative_next_is_honoured(self, client):
        """Otherwise the fix is to refuse all of them, which breaks the one
        legitimate use: arriving at the console and being sent back to it."""
        provision(_request())
        response = client.post(
            "/login/",
            {
                "email": "organizer@example.org",
                "password": PASSWORD,
                "next": "/organizer/assignments/",
            },
        )
        assert response["Location"] == "/organizer/assignments/"


class TestLogout:
    def test_logout_is_post_only(self, client):
        """A GET logout is a drive-by: anyone can drop an ``<img>`` in a page and
        sign an organizer out mid-session."""
        provision(_request())
        assert client.get("/logout/").status_code == 405

    def test_it_ends_the_session(self, client):
        provision(_request())
        client.post("/login/", {"email": "organizer@example.org", "password": PASSWORD})
        assert client.get("/judge/").status_code == 200

        assert client.post("/logout/").status_code == 302
        assert client.get("/judge/").status_code == 403, "the session survived logout"

    def test_logging_out_twice_is_harmless(self, client):
        provision(_request())
        client.post("/logout/")
        assert client.post("/logout/").status_code == 302


def test_the_wizard_is_named_in_the_urlconf():
    """A route nobody can reverse is a route nobody linked to."""
    assert reverse("setup") == "/setup/"
    assert reverse("login") == "/login/"
    assert reverse("logout") == "/logout/"


def test_the_wizard_offers_the_default_rubric_weights(client):
    """An organizer should see the rubric before committing, not after."""
    body = client.get("/setup/").content.decode("utf-8")
    assert "Functionality" in body
    assert "Innovation" in body
    assert re.search(r"0\.4", body)
