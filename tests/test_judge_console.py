"""The judge console: who sees what, and what a refusal actually is.

**Two things are being tested here and they are not the same thing.**

The first is **reachability**: can judge_a open judge_b's review? The second is
**the refusal itself**: is it a literal 403, with an empty body, and with no
``Location`` header? A console can pass the first and fail the second, and the
second is the one `run.py` actually scores. ``run.py`` follows redirects, so a
refusal implemented as "redirect to the login page" returns **200** through the
checker and fails a scored check while looking completely correct in a browser
(D-02). So every refusal in this module is asserted on all three properties
separately, because a test that only asserts the status code would have passed
against the redirect.

**The CSRF note, because it has cost this project three versions of a wrapper.**
Django's test ``Client`` does **not** enforce CSRF unless you pass
``enforce_csrf_checks=True``. A test that posts without it is observing no CSRF
behaviour at all, which is indistinguishable from a working exemption. Every
POST in this module that is *meant* to be refused goes through a client built
with ``enforce_csrf_checks=True``, so a refusal cannot be passing for the wrong
reason -- which is the F-40 lesson applied to our own suite.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from django.test import Client
from django.urls import reverse

from reviewer.reviews import console as console_module
from reviewer.reviews.models import REVIEW_IN_PROGRESS, REVIEW_SUBMITTED, Review

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def raw_fixture() -> dict:
    return json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture):
    from reviewer.importer import loader as loader_module

    loader_module.load(raw_fixture)


@pytest.fixture
def event(loaded):
    from reviewer.events.models import Event

    return Event.objects.get(pk="evt_01")


def _client_for(email: str) -> Client:
    """A client whose ``request.user`` is this fixture identity.

    **Not** ``client.force_login``, because the demo-token backend is what
    actually authenticates the organizers' checker, and a test that used a
    different door would not be testing the door in production.
    """
    from reviewer.accounts.demo_tokens import mint

    return Client(HTTP_AUTHORIZATION=mint(email))


def _identities(event) -> dict:
    """The identities the checker authenticates as, resolved to users.

    **Derived through ``reviewer.importer.demo``, never typed.** The five demo
    identities are three promoted from the fixture's 121 and two created by the
    seed; typing their addresses here would be a second source of truth that
    silently rots the first time the chooser picks a different judge, and a test
    that skips itself is worse than no test.
    """
    import json as _json

    from reviewer.accounts.models import User
    from reviewer.importer import census as census_module
    from reviewer.importer import demo as demo_module

    fixture = _json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))
    chosen = demo_module.choose(census_module.census(fixture))
    out = {}
    for identity in chosen:
        user = User.objects.filter(email=identity.email).first()
        if user is not None:
            out[identity.key] = user
    return out


def _assignment_of(user, event):
    """One of this judge's reviews, found **through their own scope**.

    Routed through ``for_actor`` rather than ``Review.objects.filter(judge=...)``
    for two reasons. The lint rule (JJ01) forbids the unscoped form everywhere
    including tests, and it is right to: a test helper that reaches around the
    scope is a helper that can quietly hand a test the wrong row. And a helper
    that goes through the scope cannot return a review its subject is not allowed
    to see, so a test using it is automatically testing something reachable.
    """
    from reviewer.isolation import Actor

    actor = Actor.for_user(event, user)
    return Review.objects.for_actor(actor).order_by("pk").first()


# ------------------------------------------------------------------ reachability


class TestTheJudgeSeesOnlyTheirOwn:
    def test_a_judge_sees_their_own_reviews_and_the_receipt_says_so(self, event, loaded):
        judge = _identities(event)["judge_a"]
        client = _client_for(judge.email)
        response = client.get("/judge/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Your assignments" in body
        # The receipt is RENDERED, not merely available. bible/05 §6a.
        assert "Scope:" in body, "the scope receipt is not in the markup"

    def test_a_judge_cannot_open_a_peers_review(self, event, loaded):
        identities = _identities(event)
        mine = _assignment_of(identities["judge_a"], event)
        theirs = _assignment_of(identities["judge_b"], event)
        if mine is None or theirs is None:
            pytest.skip("the fixture did not give both judges a review")
        response = _client_for(identities["judge_a"].email).get(
            f"/judge/review/{theirs.assignment_id}/"
        )
        _assert_refusal(response, console_module.REFUSED_BY_ASSIGNMENT)

    def test_a_participant_is_refused_the_console(self, event, loaded):
        identities = _identities(event)
        if "participant" not in identities:
            pytest.skip("no participant identity")
        response = _client_for(identities["participant"].email).get("/judge/")
        _assert_refusal(response, console_module.REFUSED_BY_ROLE)

    def test_an_anonymous_requester_is_refused_not_redirected(self, event, loaded):
        """The redirect trap, as a test rather than a warning.

        ``run.py`` follows redirects. A 302 to a login page is a 200 to the
        checker, so this is the single assertion that would catch a console
        written the way most consoles are written.
        """
        response = Client().get("/judge/")
        _assert_refusal(response, console_module.REFUSED_BY_ROLE)

    def test_the_organizer_can_see_the_whole_event_through_the_same_scope(self, event, loaded):
        identities = _identities(event)
        if "organizer" not in identities:
            pytest.skip("no organizer identity")
        response = _client_for(identities["organizer"].email).get("/judge/")
        assert response.status_code == 200

    def test_the_organizers_plan_screen_is_refused_to_a_judge(self, event, loaded):
        identities = _identities(event)
        response = _client_for(identities["judge_a"].email).get("/organizer/assignments/")
        _assert_refusal(response, console_module.REFUSED_BY_ROLE)

    def test_the_plan_screen_shows_the_certificate_to_an_organizer(self, event, loaded):
        identities = _identities(event)
        if "organizer" not in identities:
            pytest.skip("no organizer identity")
        response = _client_for(identities["organizer"].email).get("/organizer/assignments/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Assignment plan" in body
        # The certificate is the same string the verifier prints.
        assert "tightest capacity" in body
        assert "judge-project edges" in body


def _assert_refusal(response, expected_refused_by: str) -> None:
    """Assert all three properties of D-02, separately and by name.

    Split into three assertions on purpose. A single ``assert response.status_code
    == 403`` would pass against a 302 that something upstream follows, which is
    the exact failure this project has been bitten by.
    """
    # 1. The status. Not 302, not 404, not 200.
    assert response.status_code == 403, (
        f"expected a literal 403, got {response.status_code}. A 302 is followed "
        f"by run.py and comes back 200."
    )
    # 2. The body is empty, so a refusal cannot confirm that the row exists.
    assert response.content == b"", (
        f"refusal body was {response.content!r} -- it must be empty so a "
        f"refused judge cannot learn that the review they asked for exists"
    )
    # 3. No Location header, so nothing can be followed.
    assert "Location" not in response.headers, (
        f"refusal carried a Location header: {response.headers.get('Location')}"
    )
    # ...and the reason is in a header that is identical for every refused caller.
    assert response.headers.get(console_module.REFUSED_BY_HEADER) == expected_refused_by


# --------------------------------------------------------------------- the form


class TestTheReviewForm:
    def _draft_review(self, event, loaded):
        """A review that is **not** yet submitted, created by rewinding one.

        **The fixture has no drafts, and that is a property of the fixture, not
        of the console.** All 126 reviews are derived from score rows, so every
        one of them is `submitted` -- the file is a record of judging that
        already happened. A test of draft behaviour therefore has to rewind one
        row, and saying so is better than skipping: a skipped test is a test
        that quietly stops testing anything the day the seed changes.
        """
        judge = _identities(event)["judge_a"]
        review = _assignment_of(judge, event)
        if review is None:
            pytest.skip("judge_a has no review on the fixture")
        review.status = "assigned"
        review.submitted_at = None
        review.save(update_fields=["status", "submitted_at"])
        review.assignment.status = "assigned"
        review.assignment.save(update_fields=["status"])
        return review

    def test_the_form_renders_the_rubric_with_its_own_scale(self, event, loaded):
        review = self._draft_review(event, loaded)
        client = _client_for(review.judge.email)
        response = client.get(f"/judge/review/{review.assignment_id}/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "functionality" in body.lower()
        assert "weight" in body.lower()

    def test_a_draft_is_saved_without_submitting(self, event, loaded):
        review = self._draft_review(event, loaded)
        client = _client_for(review.judge.email)
        payload = {
            "action": "draft",
            "overall_comment": "partly done",
        }
        payload.update({f"score_{c.pk}": "4" for c in console_module._criteria_for(event)})
        response = client.post(f"/judge/review/{review.assignment_id}/", payload)
        assert response.status_code == 200
        review.refresh_from_db()
        assert review.status == REVIEW_IN_PROGRESS
        assert review.overall_comment == "partly done"

    def test_a_score_outside_the_rubric_is_refused_by_name(self, event, loaded):
        """A 400 naming the criterion -- not a silent clamp.

        A clamped score is a score the judge did not give, and it is the kind of
        bug that only shows up in a leaderboard three tracks later.
        """
        review = self._draft_review(event, loaded)
        client = _client_for(review.judge.email)
        criteria = console_module._criteria_for(event)
        payload = {"action": "submit", "overall_comment": ""}
        payload.update({f"score_{c.pk}": "4" for c in criteria})
        payload[f"score_{criteria[0].pk}"] = "99"
        response = client.post(f"/judge/review/{review.assignment_id}/", payload)
        assert response.status_code == 400
        body = response.content.decode()
        assert criteria[0].label in body, "the refusal must name the criterion"
        review.refresh_from_db()
        assert review.status != REVIEW_SUBMITTED, "a rejected score was stored anyway"

    def test_submitting_requires_every_criterion(self, event, loaded):
        review = self._draft_review(event, loaded)
        client = _client_for(review.judge.email)
        criteria = console_module._criteria_for(event)
        payload = {"action": "submit", "overall_comment": ""}
        payload[f"score_{criteria[0].pk}"] = "4"
        response = client.post(f"/judge/review/{review.assignment_id}/", payload)
        assert response.status_code == 400
        assert "missing" in response.content.decode().lower()
        review.refresh_from_db()
        assert review.status != REVIEW_SUBMITTED

    def test_a_submitted_review_is_locked(self, event, loaded):
        review = self._draft_review(event, loaded)
        client = _client_for(review.judge.email)
        criteria = console_module._criteria_for(event)
        payload = {"action": "submit", "overall_comment": "done"}
        payload.update({f"score_{c.pk}": "3" for c in criteria})
        assert client.post(f"/judge/review/{review.assignment_id}/", payload).status_code == 200
        review.refresh_from_db()
        assert review.status == REVIEW_SUBMITTED

        # A second submit is refused, and the first score survives.
        again = client.post(
            f"/judge/review/{review.assignment_id}/",
            {**payload, "overall_comment": "changed my mind"},
        )
        assert again.status_code == 409
        review.refresh_from_db()
        assert review.overall_comment == "done", "a locked review was overwritten"

    def test_a_judge_cannot_post_to_a_peers_review_even_with_valid_csrf(self, event, loaded):
        """The scope refuses, not CSRF -- so this test sends a *valid* CSRF token.

        **This is the trap the project has already been bitten by three times.**
        Django's test ``Client`` does not enforce CSRF unless asked
        (``enforce_csrf_checks=True``), and when you do ask, the CSRF rejection
        happens in middleware *before* the view runs -- so a strict client with
        no token gets a 403 for the wrong reason and the test passes without ever
        exercising the scope.

        So: a strict client, a real token obtained from a GET of the form, and an
        assertion that the refusal is the **assignment scope** and not a CSRF
        page. If the scope check were deleted, this test would fail rather than
        pass for the wrong reason.
        """
        identities = _identities(event)
        theirs = _assignment_of(identities["judge_b"], event)
        if theirs is None:
            pytest.skip("judge_b has no review")

        from reviewer.accounts.demo_tokens import mint

        client = Client(
            HTTP_AUTHORIZATION=mint(identities["judge_a"].email),
            enforce_csrf_checks=True,
        )

        # Fetch a real token by rendering a form judge_a is allowed to open.
        # **The same client instance must do the GET and the POST**, because
        # Django's CSRF check rejects a POST whose request carries no CSRF
        # *cookie* at all -- before it ever compares the token. A fresh client
        # for the POST would be refused for the wrong reason, which is the exact
        # shape of bug this test exists to rule out.
        own = _assignment_of(identities["judge_a"], event)
        own.status = "assigned"
        own.submitted_at = None
        own.save(update_fields=["status", "submitted_at"])
        page = client.get(f"/judge/review/{own.assignment_id}/")
        assert page.status_code == 200
        assert client.cookies.get("csrftoken"), "no CSRF cookie was set by the form"
        token = page.context["csrf_token"]
        assert token, "no CSRF token on the form, so the strict POST proves nothing"

        response = client.post(
            f"/judge/review/{theirs.assignment_id}/",
            {"action": "submit", "csrfmiddlewaretoken": token},
        )
        _assert_refusal(response, console_module.REFUSED_BY_ASSIGNMENT)

    def test_a_strict_client_with_no_token_is_refused_by_csrf_not_by_scope(self, event, loaded):
        """The control for the test above, and the reason it is worth having.

        Without this, "a strict client gets a 403" looks like evidence the scope
        works. It is not: CSRF alone produces a 403. This pins down that the two
        refusals are distinguishable, which is what makes the other test mean
        something.
        """
        identities = _identities(event)
        own = _assignment_of(identities["judge_a"], event)
        if own is None:
            pytest.skip("judge_a has no review")
        from reviewer.accounts.demo_tokens import mint

        response = Client(
            HTTP_AUTHORIZATION=mint(identities["judge_a"].email),
            enforce_csrf_checks=True,
        ).post(f"/judge/review/{own.assignment_id}/", {"action": "submit"})
        assert response.status_code == 403
        assert b"CSRF" in response.content, "expected a CSRF rejection"
        assert response.headers.get(console_module.REFUSED_BY_HEADER) is None, (
            "a CSRF rejection must not carry our refusal header, or the two "
            "refusals are indistinguishable to anyone reading the response"
        )

    def test_no_event_is_a_403_not_a_404(self, event, loaded, monkeypatch):
        """A 404 here would be indistinguishable from a mistyped URL.

        The acceptance gate's route-existence probes cannot tell those apart,
        which is the false-pass class F-40 exists to close -- so a missing event
        is a refusal that names itself.
        """
        import judge_judy.urls as urls_module

        monkeypatch.setattr(urls_module, "current_event", lambda: None)
        response = Client().get("/judge/")
        _assert_refusal(response, "judge_console.no_event")


# ------------------------------------------------------------------- the routes


class TestTheRoutesResolve:
    """A route that 404s is inside the 4xx range every relevant check accepts.

    That is the F-40 lesson again: the judge's own URL has to return 200 to its
    owner before a refusal from it means anything.
    """

    @pytest.mark.parametrize(
        "url,name",
        [
            ("/judge/", "judge_console"),
            ("/organizer/assignments/", "organizer_assignments"),
        ],
    )
    def test_the_named_url_is_the_one_the_path_serves(self, url, name):
        assert reverse(name) == url

    def test_every_documented_judge_path_resolves(self):
        from django.urls import resolve

        assert resolve("/judge/") is not None
        assert resolve("/organizer/assignments/") is not None
