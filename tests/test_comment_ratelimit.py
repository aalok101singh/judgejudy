"""The comment rate limit: V-8's fourth control, and the one we cut.

**The test that matters most is not the one that refuses the sixth comment.** It
is the one that says what the limit is *worth*, because this control is weaker
than a reader might assume and the honest thing to test is the weakness:

- a **signed-in** poster is keyed by account and cannot shed the key without
  losing the account;
- an **anonymous** poster is keyed by a hash of their session, so **clearing
  cookies resets the limit**, and there is a test asserting exactly that.

A rate limiter whose weakness is only in a docstring is a rate limiter nobody
reasons about. Stating the bypass in a test makes it a property of the code
rather than a caveat in prose.

The refusal itself is the portal's own bare 403 with an empty body, because a
rate limit refuses a *well-formed* claim and must be distinguishable from the 400
a malformed one gets (F-40).
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from tests.factories import bind, make_event, make_project, make_team, make_track, make_user

from reviewer.comments import ratelimit
from reviewer.comments.models import Comment
from reviewer.events.models import VOTING_OPEN_LINK

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(db):
    """A real event with two projects, built by the factories.

    **Not the shipped fixture.** A rate limit is about counting rows, and a test
    that borrows 41 projects and 126 reviews is partly testing the fixture's
    census. Two projects is enough to prove the limit is per-project and nothing
    else.
    """
    event = make_event(voting_mode=VOTING_OPEN_LINK)
    track = make_track(event, "Main")
    team = make_team(event, "Team")
    first = make_project("prj_01", event, team, track)
    second = make_project("prj_02", event, team, track)
    return event, first, second


@pytest.fixture
def other_thread(world):
    _event, _first, second = world
    return f"/projects/{second.pk}/comments/"


@pytest.fixture
def thread(client, world):
    """The comments URL on the first project, proven reachable first.

    Asserting 200 here means every later failure is the limiter's doing and not a
    403 from a missing project -- the F-40 discipline applied to a fixture.
    """
    _event, project, _second = world
    url = f"/projects/{project.pk}/comments/"
    assert client.get(url).status_code == 200, "the thread is not reachable"
    return url


@pytest.fixture
def organizer(world):
    event = world[0]
    user = make_user("organizer@ridgeway.example")
    bind(user, event, "organizer")
    return user


@pytest.fixture
def signed_in(client, organizer):
    """A client holding a session for a real account.

    ``force_login`` rather than POSTing to ``/login/``, because that endpoint is
    throttled and this file is about comment limits;
    ``tests/test_setup_wizard.py`` is where login itself is exercised.
    """
    client.force_login(organizer)
    return client


def _post(client, path, body="a comment", **extra):
    return client.post(path, {"body": body, **extra})


class TestTheBudget:
    def test_five_comments_are_allowed(self, client, thread):
        """One short of the limit, not one over. **A limit that refuses the
        fifth is a limit that lost somebody's comment**, which is the failure mode
        a number chosen too low produces."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            assert _post(client, thread, f"comment {i}").status_code == 200, (
                f"comment {i + 1} of {ratelimit.COMMENTS_PER_HOUR} was refused"
            )

    def test_the_sixth_is_refused(self, client, thread):
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"comment {i}")
        sixth = _post(client, thread, "one too many")
        assert sixth.status_code == 403

    def test_the_refusal_is_the_portals_own_shape(self, client, thread):
        """A bare 403, an **empty body**, and the guard named -- because this is a
        refusal of a well-formed claim, and a rendered page would invite a retry,
        which is the one thing a rate limiter must discourage."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"comment {i}")
        refused = _post(client, thread, "one too many")

        assert refused.status_code == 403
        assert refused.content == b""
        assert refused["X-Refused-By"] == "comments.rate_limited"

    def test_the_refused_comment_is_not_stored(self, client, thread):
        """**The refusal has to have an effect.** A rate limiter that returns 403
        and writes the row anyway is a logging system."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"comment {i}")
        before = Comment.objects.count()
        _post(client, thread, "one too many")
        assert Comment.objects.count() == before


class TestItIsNotTheLengthCap:
    def test_an_over_long_comment_is_still_a_400(self, client, thread):
        """**F-40: the two failures must not look alike.** One is the poster's own
        mistake and fixing the text fixes it; the other is a refusal they cannot
        fix by editing. A client that cannot tell them apart cannot retry
        correctly."""
        from reviewer.comments.views import MAX_BODY_CHARS

        response = _post(client, thread, "x" * (MAX_BODY_CHARS + 1))
        assert response.status_code == 400
        assert response.headers.get("X-Refused-By") != "comments.rate_limited", (
            "a length cap is the poster's own malformed request and is answered "
            "with a rendered 400; a rate limit is a refusal and names its guard. "
            "F-40: the two must not look alike."
        )

    def test_an_over_long_comment_does_not_spend_the_budget(self, client, thread):
        """Otherwise an editor pasting a long draft could lock themselves out of
        commenting at all -- self-inflicted, and unexplainable."""
        from reviewer.comments.views import MAX_BODY_CHARS

        for _ in range(ratelimit.COMMENTS_PER_HOUR * 2):
            _post(client, thread, "x" * (MAX_BODY_CHARS + 1))
        assert _post(client, thread, "a short one").status_code == 200

    def test_an_empty_comment_does_not_spend_the_budget(self, client, thread):
        for _ in range(ratelimit.COMMENTS_PER_HOUR * 2):
            _post(client, thread, "   ")
        assert _post(client, thread, "a real one").status_code == 200


class TestItIsPerIdentity:
    def test_two_visitors_do_not_share_a_budget(self, client, thread):
        """The whole point of keying on identity: one person's flood must not lock
        everybody else out of commenting."""
        from django.test import Client

        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"mine {i}")

        other = Client()
        assert other.get(thread).status_code == 200
        assert _post(other, thread, "theirs").status_code == 200

    def test_the_budget_is_per_event_not_per_project(self, client, thread, other_thread):
        """**Per event, and that is a decision rather than an oversight.**

        The thing being protected is the **moderation queue**, and an organizer
        reads *one* queue for the whole event, not one per project. Ten comments
        spread over two projects are still ten items in that single queue, so a
        per-project budget would let somebody fill it twice over.

        The first draft of this test asserted the opposite -- that a per-event cap
        was wrong -- and the code was right. A test asserting the weaker property
        is how a stricter control gets "fixed" into a weaker one.
        """
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"a {i}")
        assert _post(client, other_thread, "on another project").status_code == 403

    def test_and_the_guard_says_which_one_it_was(self, client, thread, other_thread):
        """So the refusal is diagnosable rather than mysterious."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"a {i}")
        refused = _post(client, other_thread, "on another project")
        assert refused.headers["X-Refused-By"] == "comments.rate_limited"


class TestTheWindowSlides:
    def test_the_budget_returns_after_an_hour(self, client, thread):
        """Not asserted by moving the clock into the future for everything -- only
        the *comments* age, so a comment posted "now" is still countable."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"comment {i}")
        assert _post(client, thread, "one too many").status_code == 403

        stale = timezone.now() - dt.timedelta(hours=2)
        Comment.objects.update(created_at=stale)

        assert _post(client, thread, "later").status_code == 200

    def test_the_window_is_exactly_an_hour_not_a_day(self):
        """A daily cap would be a publish limit, not a rate limit."""
        assert ratelimit.WINDOW == dt.timedelta(hours=1)


class TestAnAccountIsTheStrongerKey:
    """**The reason `invite` exists**, asserted here rather than asserted in
    prose: a signed-in poster is keyed by the account, so the limit follows them
    across browsers and sessions."""

    def test_a_signed_in_poster_spends_a_shared_budget(self, signed_in, thread):
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(signed_in, thread, f"comment {i}")
        assert _post(signed_in, thread, "one too many").status_code == 403

    def test_a_second_browser_does_not_reset_an_accounts_budget(self, signed_in, thread, organizer):
        """**The counterpart to the anonymous bypass.** A new browser is a new
        session, and for an *account* that buys nothing -- which is the whole
        difference between the two keys."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(signed_in, thread, f"comment {i}")

        from django.test import Client

        fresh = Client()
        fresh.force_login(organizer)
        assert _post(fresh, thread, "new browser, same person").status_code == 403

    def test_clearing_cookies_resets_an_anonymous_budget(self, client, thread):
        """**The documented bypass, asserted so it stays true.**

        This is the control's real limit and it is stated in the module docstring,
        in the README and here. A new client is a new session and therefore a new
        budget. Shipping a limiter whose weakness is only in a comment is how
        people come to trust it more than it deserves.
        """
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"comment {i}")
        assert _post(client, thread, "one too many").status_code == 403

        from django.test import Client

        assert _post(Client(), thread, "fresh browser").status_code == 200

    def test_the_session_key_itself_is_never_stored(self, client, thread):
        """**A session key is a bearer credential.** A row that survives moderation
        review is a row somebody will read, so what is stored is a hash."""
        _post(client, thread, "hello")
        comment = Comment.objects.latest("created_at")
        assert comment.author_session_hash
        assert len(comment.author_session_hash) == 64, "expected a SHA-256 hex digest"

        key = client.session.session_key
        assert key not in comment.author_session_hash
        # And the stored value is not the key under any trivial transform.
        assert key[:8] not in comment.author_session_hash

    def test_a_signed_in_comment_is_keyed_by_account_not_session(self, signed_in, thread):
        """One key per identity, never two. A row carrying both would mean two
        answers to "who counted this"."""
        _post(signed_in, thread, "signed in")

        comment = Comment.objects.filter(author__isnull=False).latest("created_at")
        assert comment.author is not None
        assert comment.author_session_hash == "", (
            "a signed-in comment must not also carry a session hash: two keys means "
            "two ways to count, and they will disagree"
        )


class TestCountingWhatExists:
    def test_it_is_a_count_not_a_counter(self, client, thread):
        """Deleting a comment gives the budget back, because the limit asks what
        the rows say. A separate counter table would have to be kept in step with
        deletions, and this is why it was avoided."""
        for i in range(ratelimit.COMMENTS_PER_HOUR):
            _post(client, thread, f"comment {i}")
        assert _post(client, thread, "one too many").status_code == 403

        Comment.objects.filter(author_session_hash__gt="").delete()
        assert _post(client, thread, "after moderation").status_code == 200

    def test_an_uncountable_poster_gets_the_benefit_of_the_doubt(self):
        """The fallback filter matches nothing rather than everything -- an empty
        filter would count the whole table and lock out every visitor at once."""
        assert ratelimit.identity_filter(object(), _anonymous()) == {
            "author_session_hash": "\x00uncountable"
        }

    def test_a_first_time_visitor_can_still_comment(self, client, thread):
        """The limit degrades to *cannot count this one*, never to *refuse this
        one*. A brand-new session has no key until saved, and forcing a save would
        write a row for every visitor who merely loads a page."""
        assert ratelimit.session_hash(_FakeRequest()) is None
        assert _post(client, thread, "first ever comment").status_code == 200


class TestTheConstantsAreLegible:
    def test_the_limit_is_five(self):
        """**Pinned, because 'five' is a decision and a decision that rots is a
        decision nobody made.** An organizer moderating by hand wants a queue a
        person can work through; fifty protects the database and destroys the
        queue."""
        assert ratelimit.COMMENTS_PER_HOUR == 5

    def test_the_message_states_the_number_and_the_way_out(self):
        text = ratelimit.message()
        assert str(ratelimit.COMMENTS_PER_HOUR) in text
        assert "sign in" in text.lower()


def _anonymous():
    from reviewer.isolation import Actor

    return Actor.anonymous(None)


class _FakeRequest:
    """A request with a session that has never been saved."""

    class session:  # noqa: N801
        session_key = None
