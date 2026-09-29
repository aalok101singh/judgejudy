"""``/vote/`` -- the randomised ballot as a PRODUCT surface (REQ-T3-04).

**The test that matters most is `TestTheOrderActuallyVariesAcrossVoters`, and
the reason it exists is F-80.** The harness's own history is that 48 tests passed
against a quality ladder that made the field uncontested: a test that checks the
attack fires does not check the instrument can see anything else. The same shape
would ship here as a test that checks "the same voter gets the same order twice"
-- which a **constant** order satisfies perfectly, since a constant order is
trivially stable.

So the suite is built around the two halves, and neither is optional:

* the order is **stable per voter** -- the D-12 anti-refresh guarantee;
* the order **differs across voters** -- and this is the half that a degenerate
  implementation fails, because ``sorted()`` is stable and random is not.

A second control that is easy to skip and is not skipped: **the slot-1 project
is not the same project for every voter.** Uniformity of the *whole* order is not
the claim, and neither is a "random" order that happens to pin the same project
first. `presentation_order`'s own docstring says balanced is the null because it
cannot favour anybody, and a product that always shows project #1 first is the
attack arm wearing a different name.

**Every value assertion here is a VALUE, not a shape.** "The order is a
permutation of the projects" is a shape and a constant order satisfies it. "The
first three entries of voter 7's order are not the first three of voter 8's" is
a value, and it is the one that catches the defect.
"""

from __future__ import annotations

import pytest
from tests.factories import bind, make_event, make_project, make_team, make_track, make_user

from reviewer.ballots import order as order_service
from reviewer.ballots.models import Ballot
from reviewer.ballots.views import REFUSED_BY_NO_IDENTITY, REFUSED_BY_VOTING_CLOSED
from reviewer.events.models import VOTING_AUTHENTICATED, VOTING_OPEN_LINK
from reviewer.projects.models import Project


@pytest.fixture
def world(db):
    """One event, one track, one team, and ``n`` projects with distinct keys."""
    event = make_event(voting_mode=VOTING_OPEN_LINK)
    track = make_track(event, "Main")
    team = make_team(event, "Team")
    projects = [make_project(f"prj_{i:02d}", event, team, track) for i in range(1, 13)]
    return event, projects


def _get(client, url="/vote/", ip="10.0.0.1", agent="pytest"):
    """GET the ballot as a specific browser. REMOTE_ADDR is the identity."""
    return client.get(url, REMOTE_ADDR=ip, HTTP_USER_AGENT=agent)


class TestVotingWindowRefuses:
    """A closed event refuses. The shipped fixture is born closed, so this is
    the state a judge actually meets first, and a page that rendered anyway
    would be a ballot nobody could legitimately cast."""

    def test_closed_event_refuses_with_the_guard_named(self, client, db):
        make_event(voting_mode="closed")
        response = _get(client)
        assert response.status_code == 403
        assert response["X-Refused-By"] == REFUSED_BY_VOTING_CLOSED

    def test_the_refusal_is_not_a_redirect(self, client, db):
        """D-02, on the new surface. `run.py` follows redirects, so a 302 comes
        back as a 200 and fails a check while looking right in a browser."""
        make_event(voting_mode="closed")
        response = _get(client)
        assert response.status_code == 403
        assert "Location" not in response

    def test_a_refused_ballot_writes_no_row(self, client, db):
        """The control for the control. A guard that refuses *and* persists is a
        guard that has already done the thing it says it will not do."""
        make_event(voting_mode="closed")
        _get(client)
        assert Ballot.objects.count() == 0


class TestIdentityIsRequired:
    """`None` means refuse, never anonymous. An undeduplicated ballot is the
    free-for-all open-link mode is documented as being."""

    def test_no_remote_addr_is_a_refusal_not_an_empty_ballot(self, client, world):
        response = client.get("/vote/", REMOTE_ADDR="", HTTP_USER_AGENT="pytest")
        assert response.status_code == 403
        assert response["X-Refused-By"] == REFUSED_BY_NO_IDENTITY

    def test_and_still_writes_no_row(self, client, world):
        client.get("/vote/", REMOTE_ADDR="", HTTP_USER_AGENT="pytest")
        assert Ballot.objects.count() == 0

    def test_authenticated_mode_refuses_an_anonymous_visitor(self, client, world):
        """The mode is the event's choice, so switching to `authenticated`
        changes who may vote without changing the surface."""
        event, _ = world
        event.voting_mode = VOTING_AUTHENTICATED
        event.save()
        response = _get(client)
        assert response.status_code == 403
        assert response["X-Refused-By"] == REFUSED_BY_NO_IDENTITY

    def test_a_signed_in_user_gets_a_ballot_in_authenticated_mode(self, client, world):
        event, _ = world
        event.voting_mode = VOTING_AUTHENTICATED
        event.save()
        user = make_user("voter@example.org")
        bind(user, event, "participant")
        client.force_login(user)
        response = _get(client)
        assert response.status_code == 200
        assert Ballot.objects.filter(event=event, voter_key__isnull=False).count() == 1


class TestTheOrderIsStablePerVoter:
    """The anti-refresh guarantee. This is the half that a constant order also
    satisfies, which is why it is worthless on its own."""

    def test_two_requests_from_one_voter_get_the_same_order(self, client, world):
        _get(client, ip="10.0.0.7")
        first = Ballot.objects.get()
        _get(client, ip="10.0.0.7")
        assert Ballot.objects.count() == 1, "a refresh minted a second ballot"
        assert Ballot.objects.get().order == first.order

    def test_the_second_request_does_not_mint_a_new_row(self, client, world):
        for _ in range(5):
            _get(client, ip="10.0.0.7")
        assert Ballot.objects.count() == 1

    def test_changing_the_user_agent_changes_the_identity(self, client, world):
        """The identity is IP + UA, so a different browser is a different voter.
        Asserted because the alternative -- keying on IP alone -- would silently
        merge a household, and the tests below would still pass."""
        _get(client, ip="10.0.0.7", agent="firefox")
        _get(client, ip="10.0.0.7", agent="chrome")
        assert Ballot.objects.count() == 2


class TestTheOrderActuallyVariesAcrossVoters:
    """**The F-80 half. A test that only checks stability passes against
    `sorted()`.** These assert values, and they are the ones that would go red if
    the permutation were replaced with anything constant."""

    def test_two_voters_on_the_same_host_get_different_orders(self, client, world):
        _get(client, ip="10.0.0.1", agent="firefox")
        _get(client, ip="10.0.0.1", agent="chrome")
        a, b = Ballot.objects.order_by("voter_key").values_list("order", flat=True)
        assert a != b, "two voters saw the same order; the permutation is constant"

    def test_five_voters_produce_at_least_four_distinct_orders(self, client, world):
        """A value threshold rather than "all different", because a permutation
        of 12 taken 5 times colliding once is arithmetic, not a defect. Asserting
        a *count* rather than pairwise inequality is what makes this a real
        discrimination check and not a flaky one."""
        for i in range(5):
            _get(client, ip=f"10.0.0.{i}", agent="pytest")
        orders = list(Ballot.objects.values_list("order", flat=True))
        distinct = len(set(map(tuple, orders)))
        assert distinct >= 4, f"only {distinct} distinct orders of 5 voters"

    def test_slot_one_is_not_the_same_project_for_every_voter(self, client, world):
        """The control that a 'randomised' order that always pins project #1
        first would fail. `balanced` is the harness's null precisely because it
        cannot favour anybody; a product order that always leads with the same
        project is the attack arm under another name."""
        for i in range(6):
            _get(client, ip=f"10.0.1.{i}", agent="pytest")
        firsts = {next(iter(o)) for o in Ballot.objects.values_list("order", flat=True)}
        assert len(firsts) >= 3, f"slot 1 was the same project for all voters: {firsts}"

    def test_the_order_is_a_permutation_of_the_projects(self, client, world):
        """A shape check, kept deliberately alongside the value checks. On its
        own it is satisfied by a constant order, which is why it is not alone."""
        _, projects = world
        _get(client, ip="10.0.0.2")
        assert sorted(Ballot.objects.get().order) == sorted(p.pk for p in projects)


class TestTheOrderIsNotSortedOrder:
    """**The cheapest possible catch, and the one most likely to be all that
    is needed.** If the permutation is ever replaced by the base order, this goes
    red immediately without needing any of the statistical reasoning above."""

    def test_the_order_is_not_the_base_order(self, client, world):
        _, projects = world
        _get(client, ip="10.0.0.3")
        base = [p.pk for p in sorted(projects, key=lambda p: p.pk)]
        assert Ballot.objects.get().order != base, "the ballot is in base order"

    def test_a_self_submitted_project_with_no_source_key_still_appears(self, client, world):
        """**F-83, pinned.** `source_key` is NULL for every project the portal
        created itself, so keying the ballot on it put a `None` in the
        permutation: structurally valid, renders, ranks nothing. This is F-80's
        shape one level down, and the fix -- key on the primary key -- is only
        worth anything if a project with a NULL `source_key` is actually in the
        fixture this test uses.
        """
        event, _ = world
        track = make_track(event, "Late")
        team = make_team(event, "Late Team")
        make_project("prj_late", event, team, track)
        assert Project.objects.get(pk="prj_late").source_key is None
        _get(client, ip="10.0.0.6")
        order = Ballot.objects.get().order
        assert None not in order, "a NULL source_key leaked into the permutation"
        assert "prj_late" in order


class TestItCallsTheFunctionTheHarnessAttacks:
    """**The claim and the implementation must be the same code, or the harness
    is measuring a function nothing calls.** A second copy of the seed formula
    would be invisible: the harness keeps reporting zero-mean against a
    permutation the product stopped using."""

    def test_the_surface_calls_presentation_order(self, monkeypatch, db):
        """Traced rather than assumed. If someone re-implements the shuffle
        inline, this is the test that notices."""
        from reviewer.ballots import order as module

        calls = []
        real = module.presentation_order

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return real(*args, **kwargs)

        monkeypatch.setattr(module, "presentation_order", spy)
        event = make_event(voting_mode=VOTING_OPEN_LINK)
        track = make_track(event, "Main")
        team = make_team(event, "Team")
        projects = [make_project(f"prj_{i:02d}", event, team, track) for i in range(1, 6)]
        order_service.ballot_order(event, "deadbeef", projects)
        assert len(calls) == 1, "the ballot did not go through presentation_order"

    def test_the_shipped_design_is_randomised_not_fixed(self):
        """`fixed` is the harness's ATTACK arm. A product wired to it would make
        every 'does it detect the attack' test pass and ship the attack."""
        assert order_service.DESIGN == "randomised"

    def test_the_same_identity_yields_the_same_order_through_the_service(self, world):
        """The service is pure in the identity, which is the property the stored
        row exists to enforce against a lost cookie."""
        event, projects = world
        base = sorted(projects, key=lambda p: p.pk)
        a = order_service.ballot_order(event, "voter-a", base)
        b = order_service.ballot_order(event, "voter-a", base)
        assert a.order == b.order
        assert a.seed == b.seed


class TestThePageSaysWhatTheRandomisationDoes:
    """D-12's caveat belongs in the MARKUP. `tests/test_bias_attack.py` already
    forbids the word 'eliminates' in the harness output; this is the same
    sentence forbidden in the second place it could be written."""

    def test_the_page_states_zero_mean(self, client, world):
        response = _get(client)
        body = response.content.decode()
        assert "zero-MEAN" in body or "zero-mean" in body.lower()

    def test_the_page_does_not_claim_the_bias_is_eliminated(self, client, world):
        body = _get(client).content.decode().lower()
        assert "eliminates" not in body
        assert "removes position bias" not in body

    def test_the_seed_is_rendered_so_the_order_is_checkable(self, client, world):
        """An order nobody can reproduce is an order nobody can audit."""
        _get(client, ip="10.0.0.4")
        body = _get(client, ip="10.0.0.4").content.decode()
        assert Ballot.objects.get().seed in body


class TestIsolationOfTheStoredOrder:
    """The ballot is per-voter state, so the questions a reviewer asks are
    'can I read yours' and 'can I re-roll mine'."""

    def test_one_voter_cannot_read_another_voters_ballot_by_id(self, client, world):
        """There is no per-ballot route at all, which is the strongest possible
        answer. Asserted as a URL check so adding one later is a deliberate act
        rather than an accident."""
        _get(client, ip="10.0.0.5")
        assert client.get("/vote/1/").status_code == 404

    def test_the_ballot_key_is_hashed_not_a_raw_ip(self, client, world):
        """The models docstring says IP and UA are hashed before storage. An
        assertion on the VALUE, not just the presence of a column."""
        _get(client, ip="203.0.113.99", agent="pytest")
        ballot = Ballot.objects.get()
        assert "203.0.113.99" not in ballot.voter_key
        assert len(ballot.voter_key) == 64, "expected a sha256 hex digest"
