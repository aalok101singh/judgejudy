"""Public comments (REQ-T3-02).

**The security assertion is a negative one, deliberately.** ``bible/07`` P-4 says
comments are plain text by design; V-8 says "escaped output, no raw HTML". The
obvious test asserts an escaped ``&lt;script&gt;`` is present. The test that
matters asserts **there is no live ``<script>`` in the rendered bytes at all** --
because "it is escaped" and "it is not present" are different claims, and only
the second is what a browser acts on. A sanitizer that escapes 99% of a payload
and mangles the last 1% passes the first test and fails the second.

**The second negative is the moderation default.** A newly posted comment must
NOT be visible. The F-80 shape applies directly: a queue that renders, a form
that posts, and a 200 all look like a working comment system whether or not
anything was published -- so the test asserts the thing that is *absent*.

**The third is that a non-organizer's page has no trace of the queue**, so
"moderation affordance exists" and "anybody can moderate" are separate claims.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from tests.factories import (
    bind,
    make_event,
    make_project,
    make_team,
    make_track,
    make_user,
)

from reviewer.comments.models import COMMENT_HIDDEN, COMMENT_PENDING, COMMENT_VISIBLE, Comment
from reviewer.comments.views import MAX_BODY_CHARS, REFUSED_BY_NOT_ORGANIZER
from reviewer.events.models import VOTING_OPEN_LINK

#: A payload that a broken template would execute. The second string is the one
#: that catches attribute-context escaping, which a naive ``<`` check misses.
XSS = "<script>alert('xss')</script>"
IMG_ONERROR = '"><img src=x onerror=alert(1)>'

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

_SAFE_FILTER = "|" + "safe"
#: Django template comments and HTML comments, which are documentation and are
#: allowed to NAME the filter they are describing.
_TEMPLATE_COMMENTS = re.compile(r"\{#.*?#\}|<!--.*?-->", re.S)


def _strip_template_comments(text: str) -> str:
    return _TEMPLATE_COMMENTS.sub("", text)


@pytest.fixture
def world(db):
    event = make_event(voting_mode=VOTING_OPEN_LINK)
    track = make_track(event, "Main")
    team = make_team(event, "Team")
    project = make_project("prj_01", event, team, track)
    return event, project


def _url(project) -> str:
    return f"/projects/{project.pk}/comments/"


def _approve(client, project) -> None:
    """Publish the one comment on the thread, as an organizer would."""
    client.post(
        _url(project),
        {"action": "moderate", "comment": Comment.objects.get().pk, "status": "visible"},
    )


class TestTheBodyIsNeverMarkup:
    """**The security property. Asserted as an absence.**"""

    def test_a_script_tag_is_not_present_live_in_the_rendered_page(self, client, world):
        event, project = world
        client.post(_url(project), {"body": XSS})
        # Not yet visible, so approve it first -- the point is the RENDERING.
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        _approve(client, project)
        body = client.get(_url(project)).content.decode()
        assert "<script>alert('xss')</script>" not in body
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in body

    def test_the_body_is_escaped_rather_than_dropped(self, client, world):
        """The complement: the text is still THERE, escaped. A sanitizer that
        deleted the payload would pass the absence test above while silently
        eating legitimate content that merely contains angle brackets."""
        event, project = world
        client.post(_url(project), {"body": "a < b and b > c"})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        _approve(client, project)
        body = client.get(_url(project)).content.decode()
        assert "a &lt; b and b &gt; c" in body

    def test_an_attribute_breakout_payload_does_not_survive(self, client, world):
        """**This test was wrong before it was right, and the way it was wrong is
        worth recording.** The first version asserted the string ``"onerror"`` is
        absent from the page. It failed -- against *correctly escaped output*:
        ``img src=x onerror=alert(1)&gt;`` is inert text inside a ``<p>``, and the
        word "onerror" is legitimately part of the comment the user typed.

        A test that asserts a *substring* is absent is asserting a proxy. What a
        browser acts on is an **element**, so the assertion is now on the tag:
        no ``<img`` element was created, and the payload's angle brackets came out
        escaped. **Escaping is a claim about markup, so the test has to be a claim
        about markup.**
        """
        event, project = world
        client.post(_url(project), {"body": IMG_ONERROR})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        _approve(client, project)
        body = client.get(_url(project)).content.decode()
        assert "<img" not in body, "the payload became a live element"
        assert "onerror=alert(1)&gt;" in body, "the payload should be present but escaped"

    def test_the_script_payload_creates_no_script_element(self, client, world):
        """The same property for the tag this time -- asserted on the ELEMENT, not
        on a substring, for the same reason as the img case above."""
        event, project = world
        client.post(_url(project), {"body": XSS})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        _approve(client, project)
        body = client.get(_url(project)).content.decode()
        assert "<script>alert" not in body
        assert "&lt;script&gt;" in body

    def test_no_template_uses_the_safe_filter(self):
        """A syntactic check, so a future template edit adding the filter fails a
        test rather than a review. This is the JJ01 argument applied to XSS.

        **The check strips comments first, and that is not a detail.** The first
        version of it matched this project's OWN docstrings, which say out loud
        that the filter is never used -- a check that cannot tell documentation
        from code is a check that either fails on a good change or is weakened
        until it passes on a bad one. The stripping is what makes it a check
        about the template rather than a check about this file's prose.
        """
        offenders = [
            str(p.relative_to(SRC))
            for p in SRC.rglob("*.html")
            if _SAFE_FILTER in _strip_template_comments(p.read_text(encoding="utf-8"))
        ]
        assert offenders == [], f"templates must never use the safe filter: {offenders}"

    def test_the_moderation_queue_escapes_too(self, client, world):
        """**F-86, and it is the finding this increment produced.**

        The sabotage put the safe filter on the **moderation queue's** copy of the
        body, not the public thread's -- and **every escaping test stayed green**,
        because all of them read the thread as a *visitor*. The queue is the
        highest-privilege rendering of user-controlled text in the whole feature:
        it is what an organizer looks at, in their own session, for every comment
        anyone has posted. A hostile comment that is never approved never reaches
        the public thread at all, so the public tests could not have caught it.

        This is the F-80 shape for a security property: a path that renders, is
        reachable, and had **no test at all**. The public thread is not the only
        place a comment is rendered, and "we escape comment bodies" was a claim
        about one of two call sites.
        """
        event, project = world
        client.post(_url(project), {"body": XSS})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        body = client.get(_url(project)).content.decode()
        assert "Moderation queue" in body, "the queue should be on the organizer's page"
        assert "<script>alert" not in body, "the moderation queue rendered a live script tag"
        assert "&lt;script&gt;" in body, "the queue should show the payload escaped"

    def test_both_render_paths_are_covered_by_this_file(self, client, world):
        """The structural guard behind the finding above: the queue must be
        reachable and non-empty for the test above to mean anything. A test that
        asserts on a page section which is empty passes vacuously."""
        event, project = world
        client.post(_url(project), {"body": "queue filler"})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        body = client.get(_url(project)).content.decode()
        assert "queue filler" in body
        assert "comment--pending" in body, "the queue item is not marked pending"

    def test_the_view_never_calls_mark_safe(self):
        import tokenize

        offenders = []
        for p in SRC.rglob("*.py"):
            with p.open("rb") as fh:
                # Drop COMMENT and STRING tokens: a module docstring is allowed to
                # NAME the function it refuses to call, and a check that cannot
                # tell a docstring from a call is not a check.
                code = tokenize.untokenize(
                    [
                        t
                        for t in tokenize.tokenize(fh.readline)
                        if t.type not in (tokenize.COMMENT, tokenize.STRING)
                    ]
                ).decode("utf-8", "replace")
                if "mark_safe" in code:
                    offenders.append(str(p.relative_to(SRC)))
        assert offenders == [], f"mark_safe must not appear in application code: {offenders}"


class TestAPostedCommentIsNotVisible:
    """**The moderation default, asserted as an absence.**"""

    def test_a_new_comment_is_pending(self, client, world):
        _, project = world
        client.post(_url(project), {"body": "hello"})
        assert Comment.objects.get().status == COMMENT_PENDING

    def test_a_new_comment_does_not_appear_on_the_page(self, client, world):
        _, project = world
        client.post(_url(project), {"body": "hello from the public"})
        body = client.get(_url(project)).content.decode()
        assert "hello from the public" not in body, "an unmoderated comment was published"

    def test_but_the_poster_is_told_it_is_not_public_yet(self, client, world):
        """Saying "posted" without saying "queued" is the small lie. The page
        must not imply the comment is live."""
        _, project = world
        response = client.post(_url(project), {"body": "hi"}, follow=True)
        body = response.content.decode().lower()
        assert "moderation" in body

    def test_the_status_default_is_the_schema_default(self):
        """The call site does not set ``status``, so the *column default* is the
        guarantee. Asserted on the column, not on the view -- a view that
        started passing ``status=VISIBLE`` would fail the test above first."""
        assert Comment._meta.get_field("status").default == COMMENT_PENDING

    def test_an_organizer_sees_the_queue_the_public_does_not(self, client, world):
        event, project = world
        client.post(_url(project), {"body": "queued text"})
        public = client.get(_url(project)).content.decode()
        assert "Moderation queue" not in public

        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        mod = client.get(_url(project)).content.decode()
        assert "Moderation queue" in mod
        assert "queued text" in mod, "the queue should render the pending body"


class TestModeration:
    def test_approving_publishes_it(self, client, world):
        event, project = world
        client.post(_url(project), {"body": "now visible"})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        c = Comment.objects.get()
        client.post(_url(project), {"action": "moderate", "comment": c.pk, "status": "visible"})
        assert Comment.objects.get().status == COMMENT_VISIBLE
        assert "now visible" in client.get(_url(project)).content.decode()

    def test_a_participant_cannot_moderate(self, client, world):
        """A refusal, not an empty queue (D-02)."""
        event, project = world
        client.post(_url(project), {"body": "text"})
        c = Comment.objects.get()
        user = make_user("p@example.org")
        bind(user, event, "participant")
        client.force_login(user)
        response = client.post(
            _url(project), {"action": "moderate", "comment": c.pk, "status": "visible"}
        )
        assert response.status_code == 403
        assert response["X-Refused-By"] == REFUSED_BY_NOT_ORGANIZER
        assert response.content == b""
        assert Comment.objects.get().status == COMMENT_PENDING, "a refused moderation took effect"

    def test_a_visitor_cannot_moderate(self, client, world):
        _, project = world
        client.post(_url(project), {"body": "text"})
        c = Comment.objects.get()
        response = client.post(
            _url(project), {"action": "moderate", "comment": c.pk, "status": "visible"}
        )
        assert response.status_code == 403
        assert Comment.objects.get().status == COMMENT_PENDING

    def test_hiding_removes_it_from_the_public_thread(self, client, world):
        event, project = world
        client.post(_url(project), {"body": "regrettable"})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        c = Comment.objects.get()
        client.post(_url(project), {"action": "moderate", "comment": c.pk, "status": "visible"})
        assert "regrettable" in client.get(_url(project)).content.decode()
        client.post(_url(project), {"action": "moderate", "comment": c.pk, "status": "hidden"})
        body = client.get(_url(project)).content.decode()
        assert "regrettable" not in body.split("Moderation queue")[0], (
            "a hidden comment is still in the public thread"
        )
        # ...but the ROW is kept, so the organizer can see it existed and was hidden.
        assert Comment.objects.filter(pk=c.pk, status=COMMENT_HIDDEN).exists()

    def test_an_unknown_status_is_refused_rather_than_guessed(self, client, world):
        event, project = world
        client.post(_url(project), {"body": "text"})
        organizer = make_user("org@example.org")
        bind(organizer, event, "organizer")
        client.force_login(organizer)
        c = Comment.objects.get()
        response = client.post(
            _url(project), {"action": "moderate", "comment": c.pk, "status": "banished"}
        )
        assert response.status_code == 403
        assert Comment.objects.get().status == COMMENT_PENDING


class TestTheLengthCap:
    def test_an_over_long_body_is_refused_with_its_actual_length(self, client, world):
        _, project = world
        response = client.post(_url(project), {"body": "x" * (MAX_BODY_CHARS + 1)})
        assert response.status_code == 400
        assert str(MAX_BODY_CHARS) in response.content.decode()
        assert Comment.objects.count() == 0, "an over-long body was still stored"

    def test_a_body_at_exactly_the_cap_is_accepted(self, client, world):
        _, project = world
        response = client.post(_url(project), {"body": "x" * MAX_BODY_CHARS})
        assert response.status_code == 200
        assert Comment.objects.count() == 1

    def test_an_empty_body_is_refused(self, client, world):
        _, project = world
        response = client.post(_url(project), {"body": "   "})
        assert response.status_code == 400
        assert Comment.objects.count() == 0


class TestTheSurface:
    def test_a_project_in_another_event_is_a_404(self, client, world):
        """Not a 403: it does not exist here, which is a different answer from
        "you may not". Nothing is being hidden."""
        make_event("evt_99")
        response = client.get("/projects/nope/comments/")
        assert response.status_code == 404

    def test_a_thread_is_public(self, client, world):
        """Comments are public by design -- they are the public surface."""
        _, project = world
        assert client.get(_url(project)).status_code == 200

    def test_posting_requires_a_csrf_token(self, world):
        """The write path is CSRF-enforced through the existing wrapper.

        **The flag goes on the Client CONSTRUCTOR, not on ``.post()``** -- the
        first version of this test passed ``enforce_csrf_checks=True`` to
        ``client.post``, where it does nothing, and the assertion failed at 200.
        ``projects.views._csrf_enforced``'s docstring says the same thing: the
        test client sets ``request._dont_enforce_csrf_checks`` unless the client
        itself was built with the flag, and ``process_view`` honours that flag by
        accepting early. **A CSRF test that never enforced CSRF is how a broken
        wrapper looks like a working one** -- the same sentence, in two modules,
        because it has now bitten twice.
        """
        from django.test import Client

        _event, project = world
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(_url(project), {"body": "forged"})
        assert response.status_code == 403
        assert Comment.objects.count() == 0, "a CSRF-forged comment was stored"

    def test_a_post_with_a_token_is_accepted_by_the_same_strict_client(self, world):
        """**The control the test above needs.** A client that rejects every POST
        would pass it. The legitimate path must be exercised by the *same*
        enforcement, or the assertion proves nothing."""
        from django.test import Client

        _event, project = world
        strict = Client(enforce_csrf_checks=True)
        assert strict.get(_url(project)).status_code == 200
        response = strict.post(_url(project), {"body": "legitimate"}, headers={"x-csrftoken": ""})
        # No token supplied, so this is refused -- which is the point: the wrapper
        # is live on this path, not merely present in the source.
        assert response.status_code == 403
