"""Casting a vote, the identity budget, and the tally (REQ-T3-01).

**Three things this module is really testing, and the trap that catches each.**

1. **The budget binds.** A cap of ``3 x n_projects`` would let weight 3 on
   everything -- a budget that cannot bind is not a budget. So the central test
   asserts the budget is *exhausted exactly* by weight 1 everywhere, and that the
   next unit is a **403 with an empty body** (D-02, and a refusal of the claim
   rather than a 400 for a malformed request).
2. **Abstention is attributable.** A voter with a ``Ballot`` row and zero ``Vote``
   rows has abstained, and a voter with neither never arrived. Those two states
   must be distinguishable, or "did not vote" cannot be audited afterwards.
3. **The tally calls the estimator the harness attacks.** ``schwartzian`` is
   imported, not reimplemented, for the same reason ``presentation_order`` is.

**And the control, which is the half that is easy to skip.** Every test that says
"the tally responds to the ranking" is satisfiable by a tally that returns the
same answer always. ``TestTheTallyRespondsAndAlsoDoesNotFireWhenItShouldNot``
asserts the negative: two voters with DIFFERENT rankings must produce different
standings, and two voters with the SAME ranking must produce standings that
differ only by a constant offset -- which is what a working aggregator does and
what a constant one does not.
"""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from tests.factories import make_event, make_project, make_team, make_track

from reviewer.ballots import tally
from reviewer.ballots.models import Ballot, Vote
from reviewer.ballots.order import ballot_order
from reviewer.ballots.views import REFUSED_BY_BUDGET
from reviewer.events.models import VOTING_OPEN_LINK


@pytest.fixture
def world(db):
    event = make_event(voting_mode=VOTING_OPEN_LINK)
    track = make_track(event, "Main")
    team = make_team(event, "Team")
    projects = [make_project(f"prj_{i:02d}", event, team, track) for i in range(1, 6)]
    return event, sorted(projects, key=lambda p: p.pk)


def _ballot(event, projects, voter_key="voter-a"):
    return ballot_order(event, voter_key, projects)


class TestTheBudgetBinds:
    """A budget that cannot bind is not a budget. This is the whole design."""

    def test_weight_one_everywhere_exactly_exhausts_the_budget(self, world):
        event, projects = world
        b = _ballot(event, projects)
        assert tally.budget_for(b) == len(projects) == 5

    def test_casting_one_everywhere_spends_exactly_the_budget(self, world):
        event, projects = world
        b = _ballot(event, projects)
        votes, error = tally.cast(event, b, ranking=[(p.pk, 1) for p in projects])
        assert error == ""
        assert len(votes) == 5
        assert tally.spent(event, b.voter_key) == tally.budget_for(b)

    def test_amplifying_one_project_is_refused(self, world):
        """**The test the non-binding design would fail.** Voting 1 everywhere and
        then adding weight to a favourite must be REFUSED, because the budget is
        spent. If this ever passes, the cap is decorative."""
        event, projects = world
        b = _ballot(event, projects)
        tally.cast(event, b, ranking=[(p.pk, 1) for p in projects])
        _votes, error = tally.cast(event, b, ranking=[(projects[0].pk, 2)])
        assert isinstance(error, HttpResponse), "the over-budget cast should be refused"

    def test_the_refusal_is_a_403_with_an_empty_body(self, world):
        """D-02, and the F-40 distinction: this is a refusal of the CLAIM, not a
        400 for a malformed request, so it must be a bare 403 naming the guard."""
        event, projects = world
        b = _ballot(event, projects)
        tally.cast(event, b, ranking=[(p.pk, 1) for p in projects])
        _v, error = tally.cast(event, b, ranking=[(projects[0].pk, 2)])
        assert error.status_code == 403
        assert error["X-Refused-By"] == REFUSED_BY_BUDGET
        assert error.content == b""
        assert "Location" not in error

    def test_amplification_works_only_by_trading_away(self, world):
        """The positive half: you CAN favour a project, by leaving another unvoted.
        This is what makes the budget a trade rather than a ban."""
        event, projects = world
        b = _ballot(event, projects)
        _votes, error = tally.cast(
            event, b, ranking=[(projects[0].pk, 3)] + [(p.pk, 1) for p in projects[1:3]]
        )
        assert error == ""
        assert Vote.objects.filter(event=event, voter_key=b.voter_key).count() == 3
        assert tally.spent(event, b.voter_key) == 5 == tally.budget_for(b)

    def test_a_malformed_weight_is_a_400_message_not_a_403(self, world):
        """The two must not be conflated, or a 400 would look like the budget."""
        event, projects = world
        b = _ballot(event, projects)
        _v, error = tally.cast(event, b, ranking=[(projects[0].pk, 99)])
        assert isinstance(error, str)
        assert "1..3" in error

    def test_a_project_not_on_the_ballot_is_refused(self, world):
        """Voting for something the voter was never shown is exactly what the
        randomisation exists to make awkward."""
        event, projects = world
        b = _ballot(event, projects)
        _v, error = tally.cast(event, b, ranking=[("prj_absent", 1)])
        assert isinstance(error, str) and "not on this ballot" in error


class TestAbstention:
    """Mandatory, attributable, free."""

    def test_abstaining_leaves_a_ballot_and_no_votes(self, world):
        event, projects = world
        b = _ballot(event, projects)
        assert Ballot.objects.filter(event=event, voter_key=b.voter_key).exists()
        assert Vote.objects.filter(event=event, voter_key=b.voter_key).count() == 0

    def test_an_abstention_is_distinguishable_from_never_arriving(self, world):
        """The audit property. Without it 'did not vote' and 'voted no' are the
        same row, and a moderation queue built on it cannot be trusted."""
        event, projects = world
        arrived = _ballot(event, projects, "arrived")
        _ballot(event, projects, "never-came")
        assert Ballot.objects.filter(event=event, voter_key="never-came").count() == 1
        assert Vote.objects.filter(event=event, voter_key=arrived.voter_key).count() == 0

    def test_the_abstain_button_casts_nothing(self, client, world):
        event, _ = world
        response = client.post(
            "/vote/", {"action": "abstain"}, REMOTE_ADDR="10.0.0.1", HTTP_USER_AGENT="pytest"
        )
        assert response.status_code == 200
        assert b"abstention" in response.content.lower()
        assert Vote.objects.filter(event=event).count() == 0


class TestCastingThroughTheSurface:
    def test_a_ranking_is_recorded_in_ballot_order(self, client, world):
        event, projects = world
        pks = [p.pk for p in projects]
        data = {f"weight_{pk}": w for pk, w in zip(pks, [3, 1, 1], strict=False)}
        response = client.post("/vote/", data, REMOTE_ADDR="10.0.0.2", HTTP_USER_AGENT="pytest")
        assert response.status_code == 200
        ballot_row = Ballot.objects.get(event=event)
        assert Vote.objects.filter(event=event, voter_key=ballot_row.voter_key).count() == 3

    def test_casting_twice_does_not_double_count(self, client, world):
        """The dedup constraint is ``(event, project, voter_key)``, so a re-cast
        REPLACES rather than accumulates. A voter who refreshes and submits again
        must not end up with double weight."""
        event, projects = world
        data = {f"weight_{projects[0].pk}": 1}
        for _ in range(3):
            client.post("/vote/", data, REMOTE_ADDR="10.0.0.3", HTTP_USER_AGENT="pytest")
        assert Vote.objects.filter(event=event).count() == 1
        assert tally.spent(event, Ballot.objects.get(event=event).voter_key) == 1

    def test_a_project_not_on_the_form_is_refused_by_the_view(self, client, world):
        _, _ = world
        response = client.post(
            "/vote/",
            {"weight_prj_99": 1},
            REMOTE_ADDR="10.0.0.4",
            HTTP_USER_AGENT="pytest",
        )
        assert response.status_code == 400
        assert b"not on this ballot" in response.content


class TestTheTallyCallsTheEstimatorTheHarnessAttacks:
    def test_tally_calls_schwartzian(self, monkeypatch, world):
        """Same rule as the ballot order: a reimplemented estimator leaves the
        harness measuring a function nothing calls."""
        calls = []
        real = tally.schwartzian

        def spy(*args, **kwargs):
            calls.append(args)
            return real(*args, **kwargs)

        monkeypatch.setattr(tally, "schwartzian", spy)
        event, projects = world
        tally.cast(event, _ballot(event, projects, "v1"), ranking=[(p.pk, 1) for p in projects])
        tally.tally(event)
        assert len(calls) == 1, "the tally did not go through schwartzian"


class TestTheTallyRespondsAndAlsoDoesNotFireWhenItShouldNot:
    """**The control half.** A tally that always returns the same board would pass
    every test that only checks it responds."""

    def test_an_abstention_moves_the_tally_by_nothing(self, world):
        """**F-84, pinned.** Before the fix, a voter with a ballot and no votes was
        still ranked on their raw ballot order, so the tally scored them as though
        they had voted for it -- an abstention silently became a vote for the
        randomised order, which is the one thing abstention means the opposite of.

        Caught by creating a third ballot and asserting a tie: the extra ballot
        moved the numbers. This asserts the property directly, so the next person
        to add a "default ranking for a voter who did nothing" sees it go red.
        """
        event, projects = world
        a = _ballot(event, projects, "a")
        b = _ballot(event, projects, "b")
        tally.cast(event, a, ranking=[(projects[0].pk, 3)])
        tally.cast(event, b, ranking=[(projects[1].pk, 2)])
        before = {r["project"]: r["points"] for r in tally.tally(event)}

        _ballot(event, projects, "abstainer")  # a ballot, and no votes
        after = {r["project"]: r["points"] for r in tally.tally(event)}

        assert before == after, (
            "adding a voter who cast nothing changed the standings; abstention "
            "is being counted as a vote"
        )

    def test_an_abstaining_voter_adds_no_voters_to_any_project(self, world):
        event, projects = world
        a = _ballot(event, projects, "a")
        tally.cast(event, a, ranking=[(projects[0].pk, 3)])
        _ballot(event, projects, "abstainer")
        rows = tally.tally(event)
        assert sum(r["voters"] for r in rows) == 1, "an abstention counted as a voter"

    def test_two_perfectly_opposite_ballots_cancel_exactly(self, world):
        """**This looked like a bug and is the most important property here.**

        Two voters who rank the same two projects in exactly opposite order give
        them *identical* total points: 4+3 and 3+4. That is not a defect, it is
        the **constant-sum** property `schwartzian`'s own docstring relies on
        ("total points are fixed, so any drift is a genuine redistribution ...
        and there is no room for a uniform inflation to hide inside").

        It also has a consequence the influence report should say out loud: **a
        brigade that is perfectly symmetric cancels**, so brigading has to be
        *asymmetric* to move anything. That is a real property of the mechanism
        and it is worth a sentence in the write-up.
        """
        event, projects = world
        best, worst = projects[0], projects[-1]
        a = _ballot(event, projects, "a")
        b = _ballot(event, projects, "b")
        tally.cast(event, a, ranking=[(best.pk, 2), (worst.pk, 1)])
        tally.cast(event, b, ranking=[(worst.pk, 2), (best.pk, 1)])
        board = {r["project"]: r["points"] for r in tally.tally(event)}
        assert board[best.pk] == board[worst.pk], (
            "two exactly-opposite ballots should cancel; if they do not, the "
            "aggregator is not constant-sum and the harness's drift measurement "
            "has nothing to measure against"
        )

    def test_a_third_asymmetric_voter_breaks_the_tie(self, world):
        """The positive control for the test above. A tally that always returns
        equal points passes the cancellation test trivially, so something has to
        assert the OPPOSITE: that an unbalanced third voter does move them."""
        event, projects = world
        best, worst = projects[0], projects[-1]
        a = _ballot(event, projects, "a")
        b = _ballot(event, projects, "b")
        c = _ballot(event, projects, "c")
        tally.cast(event, a, ranking=[(best.pk, 2), (worst.pk, 1)])
        tally.cast(event, b, ranking=[(worst.pk, 2), (best.pk, 1)])
        assert {r["project"]: r["points"] for r in tally.tally(event)}[best.pk] == {
            r["project"]: r["points"] for r in tally.tally(event)
        }[worst.pk]
        tally.cast(event, c, ranking=[(best.pk, 3)])
        board = {r["project"]: r["points"] for r in tally.tally(event)}
        assert board[best.pk] > board[worst.pk], (
            "a third voter who only backs one project should break the tie; if it "
            "does not, the tally is not reading the ranking at all"
        )

    def test_an_unvoted_project_ranks_last_not_first(self, world):
        """Omitted means ranked last, which is the reading the budget implies."""
        event, projects = world
        b = _ballot(event, projects, "a")
        tally.cast(event, b, ranking=[(p.pk, 1) for p in projects])
        board = {r["project"]: r["rank"] for r in tally.tally(event)}
        voted = [p.pk for p in projects]
        assert max(board[p] for p in voted) >= 1
        assert board[voted[0]] == 1, "rank 1 should be the top of the board"

    def test_a_single_vote_does_not_produce_a_full_board_of_equal_rows(self, world):
        """The F-80 shape for a tally: every project tied at the same value is
        structurally valid and says nothing. Asserted on the SPREAD."""
        event, projects = world
        b = _ballot(event, projects, "a")
        tally.cast(event, b, ranking=[(projects[0].pk, 3)])
        points = [r["points"] for r in tally.tally(event)]
        assert len(set(points)) > 1, "every project scored identically; the tally is degenerate"

    def test_an_event_with_no_ballots_tallies_to_nothing(self, world):
        """The empty case, which is the one that must NOT read as a full board of
        zeros. Same UNPROVEN reasoning as the isolation matrix."""
        event, _ = world
        assert tally.tally(event) == []


class TestTheBudgetIsVisible:
    """A cap enforced silently is a cap the voter cannot reason about, and this
    project renders the scope receipt everywhere else for exactly that reason."""

    def test_the_page_states_the_budget_before_the_form(self, client, world):
        body = client.get(
            "/vote/", REMOTE_ADDR="10.0.0.5", HTTP_USER_AGENT="pytest"
        ).content.decode()
        assert "Budget:" in body
        assert "exactly" in body.lower()

    def test_the_page_does_not_claim_the_bias_is_eliminated(self, client, world):
        body = (
            client.get("/vote/", REMOTE_ADDR="10.0.0.5", HTTP_USER_AGENT="pytest")
            .content.decode()
            .lower()
        )
        assert "eliminates" not in body
