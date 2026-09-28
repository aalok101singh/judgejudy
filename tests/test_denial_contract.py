"""The denial contract for ``POST /projects/new``, and why it is its own file.

**This is the file the acceptance check lives or dies by, and it exists as a
separate module because the failure it guards against is a check that reports
PASS while testing nothing.**

``run.py`` builds the "closed event refuses submissions" assertion like this::

    status, _ = request(url("submit"), header=auth.get("participant"),
                        method="POST", body={...})
    c.ok = 400 <= status < 500

**Any** 4xx satisfies it. So a 404, a 405, a CSRF rejection, a 401 for "you did
not log in" and a genuine deadline refusal are indistinguishable *to the
checker*. That is F-11 -- a documented default recalled rather than executed,
which would have made the deadline check pass without ever testing the deadline
-- turned on ourselves, and it is the most expensive shape of bug in this
project: a red check is obviously red, a green one is believed.

So every refusal on this path is asserted on **the mechanism that produced it**,
and the CSRF exemption is asserted from both directions:

* a JSON POST as the participant is refused by ``assert_open_for_submission``,
  asserted on the guard's name appearing in the body rather than on a status;
* a form-encoded POST *is* refused by CSRF, so the narrowness of the exemption
  is measured rather than assumed and a blanket ``@csrf_exempt`` fails here;
* no refusal on this path carries a ``Location`` header (D-02, because
  ``urlopen`` follows redirects and a 302 comes back as a 200).

**One trap for whoever writes the next test here.** Django's test ``Client``
sets ``request._dont_enforce_csrf_checks`` unless you pass
``enforce_csrf_checks=True``, and ``CsrfViewMiddleware.process_view`` honours
that flag by accepting early. Every client in this file is built with the flag
on. A test that forgets observes *no CSRF behaviour at all*, which is
indistinguishable from a working exemption -- and that is how the first version
of the wrapper shipped.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from reviewer.accounts import demo_tokens
from reviewer.events import deadlines
from reviewer.events.deadlines import GUARD_NAME, SubmissionClosed
from reviewer.importer import loader as loader_module

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent
SUBMIT_URL = "/projects/new"
VALID_PAYLOAD = {"title": "probe", "summary": "probe", "track": "1"}


# ------------------------------------------------------------------ fixtures


@pytest.fixture(scope="module")
def raw_fixture() -> dict:
    return json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture) -> loader_module.LoadReport:
    return loader_module.load(raw_fixture)


@pytest.fixture
def demo(loaded) -> dict:
    """The five identities, keyed the way `.dogfood.toml` keys them."""
    return {i.key: i for i in loaded.demo_identities}


def csrf_client() -> Client:
    """A client that actually enforces CSRF. See the module docstring."""
    return Client(enforce_csrf_checks=True)


def post_json(
    email: str | None = None,
    *,
    client: Client | None = None,
    payload: dict | None = None,
    raw_header: str | None = None,
    content_type: str = "application/json",
    data: str | None = None,
    **headers: str,
):
    """POST the submit route, as whoever, in whatever shape."""
    client = client or csrf_client()
    sent = dict(headers)
    if raw_header is not None:
        sent["Authorization"] = raw_header
    elif email is not None:
        sent["Authorization"] = demo_tokens.mint(email)
    body = data if data is not None else json.dumps(payload or VALID_PAYLOAD)
    return client.post(SUBMIT_URL, data=body, content_type=content_type, headers=sent)


def _open_the_window(days: int = 1) -> None:
    """Move the close date forward, so the open branch is reachable at all.

    The shipped fixture closes in the past and that date is never moved by the
    loader -- which is the point. A test that needs the open window has to move
    it deliberately, and this is the one place that happens.
    """
    from reviewer.events.models import Event

    event = Event.objects.get()
    event.submissions_close = timezone.now() + timezone.timedelta(days=days)
    event.save(update_fields=["submissions_close", "updated_at"])


def _csrf_token_in(html: str) -> str:
    """The rendered ``{% csrf_token %}`` value, read the way a browser reads it."""
    import re

    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
    assert match, "the open-event form rendered no CSRF token"
    return match.group(1)


# ------------------------------------------------------------------ the guard


class TestRefusedByTheDeadlineGuard:
    """The one the acceptance checker exercises, and the one it cannot verify."""

    def test_the_route_resolves(self, loaded):
        """F-40's precondition. A 404 is a 4xx, so before this route existed the
        check was passing on a missing route and the guard was never called."""
        assert reverse("new_project") == SUBMIT_URL
        assert csrf_client().get(SUBMIT_URL).status_code == 200

    def test_it_is_a_403_and_not_a_302(self, loaded, demo):
        """D-02. ``run.py`` follows redirects, so a 302 arrives as a 200 and
        fails the check while looking correct in a browser."""
        response = post_json(demo["participant"].email)

        assert response.status_code == 403
        assert response.status_code != 302
        assert "Location" not in response.headers

    def test_the_refusal_names_the_guard(self, loaded, demo):
        """**The assertion this feature exists for.**

        Not "403" -- a 403 is what CSRF, a 401 and a 404 would also have
        produced. The body carries ``refused_by`` and it has to name
        ``assert_open_for_submission`` specifically, because that string is what
        distinguishes "the deadline held" from "something else refused first".
        """
        body = post_json(demo["participant"].email).json()

        assert body["refused_by"] == GUARD_NAME == "assert_open_for_submission"

    def test_the_refusal_carries_the_date_that_decided_it(self, loaded, demo, raw_fixture):
        """A refusal a reader cannot act on is a refusal they work around."""
        body = post_json(demo["participant"].email).json()

        assert body["reason"] == deadlines.STATE_CLOSED
        assert body["event"] == raw_fixture["event"]["id"]
        assert body["submissions_close"] == raw_fixture["event"]["submissions_close"]
        assert "2026-03-01" in body["detail"]

    def test_the_request_is_otherwise_valid(self, loaded, demo):
        """It must be a submission that WOULD have succeeded.

        If the payload were invalid the view would answer 400, and if the user
        were on no team it would answer 403 -- both for a different reason. This
        pins that the only thing refusing the request is the clock.
        """
        from reviewer.accounts.models import User
        from reviewer.teams.models import TeamMembership

        user = User.objects.get(email=demo["participant"].email)

        assert TeamMembership.objects.filter(user=user).exists()
        assert post_json(demo["participant"].email).json()["refused_by"] == GUARD_NAME

    def test_nothing_was_written(self, loaded, demo):
        from reviewer.projects.models import Project

        before = Project.objects.count()
        post_json(demo["participant"].email)

        assert before == 41
        assert Project.objects.count() == before

    def test_an_organizer_is_refused_by_the_guard_too(self, loaded, demo):
        """The guard is a property of the EVENT, not of a role.

        An organizer with every permission in the world still cannot submit to a
        closed event, and that is what makes it a deadline rather than a role
        check -- and the reason the view calls it before the team check.
        """
        assert post_json(demo["organizer"].email).json()["refused_by"] == GUARD_NAME

    def test_a_visitor_is_refused_before_the_guard(self, loaded):
        """A visitor never reaches the guard, and the gate can tell.

        This is the ordering property, asserted: unauthenticated is a different
        answer from closed, and the two bodies are distinguishable.
        """
        response = post_json(None)

        assert response.status_code == 401
        assert GUARD_NAME not in response.content.decode()


# ------------------------------------------------------------------ the 401


class TestRefusedForANonDeadlineReason:
    """The other 4xx on this path, so the two can never be confused."""

    def test_an_anonymous_post_is_401_not_403(self, loaded):
        """ "Who are you" and "you may not" are different answers.

        The same reasoning ``tests/test_health.py::TestAdmin`` applies to
        ``/admin/`` redirecting rather than forbidding.
        """
        response = post_json(None)

        assert response.status_code == 401
        assert response.json()["refused_by"] == "new_project"

    def test_a_forged_token_is_anonymous(self, loaded):
        response = post_json(raw_header="JJ1.deadbeefdeadbeefdeadbeefdeadbeef.ghost@example.org")

        assert response.status_code == 401

    def test_a_foreign_bearer_token_is_ignored_not_misread(self, loaded):
        response = post_json(raw_header="Bearer some-other-tool-token")

        assert response.status_code == 401

    def test_a_token_for_an_address_with_no_row_is_anonymous(self, loaded):
        """The backend does not create users. This portal has no registration,
        and inventing one on the strength of a header is the sort of thing that
        survives into production."""
        response = post_json("nobody-at-all@example.org")

        assert response.status_code == 401

    def test_a_method_the_route_does_not_serve_is_405(self, loaded, demo):
        response = csrf_client().put(
            SUBMIT_URL,
            data="{}",
            content_type="application/json",
            headers={"Authorization": demo_tokens.mint(demo["participant"].email)},
        )

        assert response.status_code == 405
        assert "Location" not in response.headers


# ----------------------------------------------------------------- the CSRF gap


class TestTheCsrfExemptionIsNarrow:
    """Asserted from both directions, because an exemption only tested for "it
    does not fire" is an exemption nobody has measured."""

    def test_a_json_post_is_exempt(self, loaded, demo):
        """``run.py`` sends ``Content-Type: application/json`` and no token, and
        a cross-origin HTML form cannot set that content type."""
        response = post_json(demo["participant"].email)

        assert response.status_code == 403
        assert response.json()["refused_by"] == GUARD_NAME

    def test_a_form_post_is_still_refused_by_csrf(self, loaded, demo):
        """The half that fails if this were ever a blanket ``@csrf_exempt``.

        Asserted on Django's own CSRF failure text, not merely on "the body is
        not the guard's" -- a test that only told the two apart could be
        satisfied by a view that refused everything.
        """
        response = post_json(
            demo["participant"].email,
            content_type="application/x-www-form-urlencoded",
            data="title=probe&summary=probe",
        )

        assert response.status_code == 403
        body = response.content.decode()
        assert "CSRF" in body
        assert GUARD_NAME not in body

    def test_a_multipart_post_is_still_refused_by_csrf(self, loaded, demo):
        response = post_json(
            demo["participant"].email,
            content_type="multipart/form-data",
            data="title=probe&summary=probe",
        )

        assert response.status_code == 403
        assert "CSRF" in response.content.decode()

    def test_an_xhr_header_is_exempt_too(self, loaded, demo):
        response = post_json(demo["participant"].email, **{"X-Requested-With": "XMLHttpRequest"})

        assert response.status_code == 403
        assert response.json()["refused_by"] == GUARD_NAME

    def test_a_get_is_never_csrf_checked(self, loaded):
        assert csrf_client().get(SUBMIT_URL).status_code == 200

    def test_the_browser_form_carries_a_token_when_the_event_is_open(self, loaded, demo):
        """The form a human uses is CSRF-protected by construction, so the
        exemption costs the browser nothing. ``{% csrf_token %}`` is all of it.

        The shipped event is closed, so the form is not rendered at all -- which
        is correct, and which means the token is invisible from a plain request.
        This test opens the window, signs in as the participant (the form is
        only rendered for someone with a team), and looks.
        """
        _open_the_window()
        body = (
            csrf_client()
            .get(SUBMIT_URL, headers={"Authorization": demo_tokens.mint(demo["participant"].email)})
            .content.decode()
        )

        assert 'name="title"' in body
        assert "csrfmiddlewaretoken" in body

    def test_the_same_form_post_is_refused_only_by_the_clock(self, loaded, demo):
        """**The strongest statement of the whole feature, in one test.**

        One browser-shaped request with a real CSRF token, sent twice:

        1. with the window **open** it succeeds (201) and writes a project --
           so CSRF passed, the identity resolved, the team resolved, validation
           passed, and the only thing that can ever have refused it was the
           clock;
        2. with the window **closed** -- the shipped state -- the identical
           request is refused, and the body names ``assert_open_for_submission``.

        A 403 on its own proves nothing, because CSRF and a missing team also
        produce one. This proves the guard is what refuses, by showing the same
        request succeeding the moment the guard stops.
        """
        from reviewer.projects.models import Project

        client = csrf_client()
        headers = {"Authorization": demo_tokens.mint(demo["participant"].email)}

        # 1. open window -> accepted
        _open_the_window()
        token = _csrf_token_in(client.get(SUBMIT_URL, headers=headers).content.decode())
        form = {
            "title": "probe",
            "summary": "probe",
            "track": "1",
            "csrfmiddlewaretoken": token,
        }
        accepted = client.post(SUBMIT_URL, data=form, headers=headers)

        assert accepted.status_code == 201, accepted.content[:300]
        assert Project.objects.filter(title="probe").count() == 1

        # 2. closed window -> refused, and by the guard
        _open_the_window(days=-1)
        refused = client.post(SUBMIT_URL, data=form, headers=headers)

        assert refused.status_code == 403
        assert refused["Content-Type"].startswith("application/json"), (
            "a CSRF rejection is text/html, so this also asserts the token travelled"
        )
        assert refused.json()["refused_by"] == GUARD_NAME


# ------------------------------------------------------------------- the guard


class TestTheGuardItself:
    """The service function, exercised directly for all three windows.

    ``bible/05`` §4's reason for a service function rather than a ``save()``
    override or a view decorator is that both of those can be bypassed by a
    write path that did not think to call them. That is only worth anything if
    the function is right, so it is tested on its own.
    """

    def test_it_raises_on_a_closed_event(self, loaded):
        from reviewer.events.models import Event

        with pytest.raises(SubmissionClosed) as caught:
            deadlines.assert_open_for_submission(Event.objects.get())

        assert caught.value.refused_by == GUARD_NAME
        assert caught.value.state == deadlines.STATE_CLOSED

    def test_it_returns_the_window_on_an_open_event(self, loaded):
        from reviewer.events.models import Event

        event = Event.objects.get()
        inside = event.submissions_close - timezone.timedelta(days=1)

        window = deadlines.assert_open_for_submission(event, now=inside)

        assert window.is_open
        assert window.state == deadlines.STATE_OPEN

    def test_a_null_opening_date_means_no_opening_gate(self, loaded):
        """The fixture configures a close and no open. Inventing an opening date
        would be inventing policy."""
        from reviewer.events.models import Event

        event = Event.objects.get()
        assert event.submissions_open is None

        inside = event.submissions_close - timezone.timedelta(days=1)
        assert deadlines.assert_open_for_submission(event, now=inside).is_open

    def test_it_refuses_before_the_window_opens(self):
        from tests.factories import make_event

        soon = timezone.now() + timezone.timedelta(days=1)
        event = make_event(
            event_id="evt_future",
            submissions_open=soon,
            submissions_close=soon + timezone.timedelta(days=1),
        )
        event.save(update_fields=["submissions_open", "submissions_close", "updated_at"])

        with pytest.raises(SubmissionClosed) as caught:
            deadlines.assert_open_for_submission(event)

        assert caught.value.state == deadlines.STATE_NOT_YET_OPEN

    def test_the_boundary_is_inclusive_at_the_close(self, loaded):
        """``now >= close`` is closed. A deadline that is open for the instant it
        expires is a deadline with a race in it."""
        from reviewer.events.models import Event

        event = Event.objects.get()

        assert (
            deadlines.submission_window(event, now=event.submissions_close).state
            == deadlines.STATE_CLOSED
        )

    def test_the_refusal_body_is_json_serialisable(self, loaded):
        from django.core.serializers.json import DjangoJSONEncoder

        from reviewer.events.models import Event

        with pytest.raises(SubmissionClosed) as caught:
            deadlines.assert_open_for_submission(Event.objects.get())

        json.dumps(caught.value.as_dict(), cls=DjangoJSONEncoder)

    def test_the_guard_is_where_the_docstring_says_it_is(self):
        """A guard that has been renamed is a guard the acceptance gate's
        ``body_must_contain`` string no longer matches, and the gate would report
        a false pass while the code looked correct."""
        from pathlib import Path

        source = Path(deadlines.__file__).read_text(encoding="utf-8")

        assert 'GUARD_NAME = "assert_open_for_submission"' in source
        assert callable(deadlines.assert_open_for_submission)
