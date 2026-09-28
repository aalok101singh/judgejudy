"""`manage.py isolation_proof` -- both modes, and the honesty of its output.

**The tests that matter here are the ones that could have passed while proving
nothing.** A green exit from this command on an empty database is a real risk:
the published matrix cannot be computed without rows, so the easy implementation
prints a table of zeroes and exits 0, and every assertion in this file passes.
The output is therefore asserted for the specific things that make it honest --
that it says which mode it ran in, and that it names what it has not proven.
"""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command
from tests import factories, ground_truth

from reviewer.core import ROLE_JUDGE, ROLE_ORGANIZER, ROLE_PARTICIPANT
from reviewer.isolation import Actor
from reviewer.reviews.models import Review

pytestmark = pytest.mark.django_db


def run(*args: str) -> str:
    from io import StringIO

    out = StringIO()
    call_command("isolation_proof", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def seeded():
    """An event with every role bound, so the matrix mode is reachable.

    Five roles means five rows, and three of them (participant, judge,
    organizer) need a real ``RoleBinding`` and admin needs ``is_staff`` -- the
    same asymmetry ``Actor`` has, because a proof that resolved admin
    differently from the actor would print a row no request could produce.
    """
    event = factories.make_event()
    track_a = factories.make_track(event, "Security")
    track_b = factories.make_track(event, "Infrastructure")
    team = factories.make_team(event, "Team")
    rubric = factories.make_rubric(event)

    alice = factories.make_user("alice@example.invalid")
    bob = factories.make_user("bob@example.invalid")
    staff = factories.make_user("staff@example.invalid", is_staff=True)
    organizer = factories.make_user("organizer@example.invalid")
    participant = factories.make_user("participant@example.invalid")

    # Alice is a judge AND a participant, which is the ordinary case at a
    # hackathon. The matrix therefore cannot use her for the participant row --
    # her strongest role is judge -- so `participant` exists separately. See
    # ROLE_STRENGTH in the command.
    factories.bind(alice, event, ROLE_JUDGE, track_a)
    factories.bind(alice, event, ROLE_PARTICIPANT)
    factories.bind(bob, event, ROLE_JUDGE, track_b)
    factories.bind(organizer, event, ROLE_ORGANIZER)
    factories.bind(participant, event, ROLE_PARTICIPANT)
    # `staff` deliberately has NO RoleBinding: `Actor` derives admin from
    # is_staff, so binding them as an organizer as well would make their
    # strongest role admin and leave the organizer row unrepresentable.

    p1 = factories.make_project("prj_01", event, team, track_a)
    p2 = factories.make_project("prj_02", event, team, track_b)
    factories.make_review(p1, alice, rubric)
    factories.make_review(p2, bob, rubric)
    return {
        "event": event,
        "alice": alice,
        "bob": bob,
        "staff": staff,
        "organizer": organizer,
        "participant": participant,
    }


class TestEmptyDatabaseMode:
    """The FEAT-02 acceptance line: exit 0 on the empty DB."""

    def test_it_exits_zero(self, seeded):
        """With data. The empty case is TestEmptyDatabaseReallyEmpty below."""
        output = run()
        assert "mode: MATRIX" in output

    def test_on_a_truly_empty_database_it_exits_zero(self):
        assert ground_truth.total_reviews() == 0
        output = run()
        assert "mode: WIRING ONLY" in output

    def test_it_says_the_matrix_is_not_proven(self):
        """The whole point. A matrix of zeroes here would be a false pass (F-40)."""
        output = run()
        assert "NOT proven by this run" in output
        assert "NOT that isolation is verified" in output

    def test_it_prints_no_matrix_rows(self):
        """A table on an empty database is a table of guesses."""
        output = run()
        assert "mode: MATRIX" not in output
        assert "cross-track" not in output

    def test_it_names_what_is_still_unproven_every_run(self):
        output = run()
        for line in (
            "403 / empty body / no Location",
            "published FIG. 02 matrix",
            "unscoped Review",
        ):
            assert line in output, f"the output does not disclose: {line}"

    def test_require_data_turns_an_empty_database_into_a_failure(self):
        """At a verification break the loader has run; an empty DB is a defect."""
        with pytest.raises(CommandError, match="no reviews"):
            run("--require-data")

    def test_require_data_passes_once_there_are_reviews(self, seeded):
        run("--require-data")


class TestWiringChecks:
    def test_every_wiring_check_passes(self):
        output = run()
        assert "FAIL" not in output, output
        assert output.count("  ok   ") >= 12, (
            "the wiring mode lost checks. Twelve was the FEAT-02 count; a silent "
            f"drop is how a proof stops proving anything.\n{output}"
        )

    def test_the_three_hot_roles_are_named(self):
        output = run()
        assert "visitor=deny" in output
        assert "participant=deny" in output
        assert "judge=allow-own" in output
        assert "organizer=allow-all" in output
        assert "admin=allow-all" in output

    def test_it_proves_the_judge_scope_in_the_sql(self):
        output = run()
        assert "a judge's scope constrains exactly event, judge and track" in output
        assert "['event', 'judge', 'track']" in output

    def test_it_proves_a_refusal_is_an_empty_result_set(self):
        output = run()
        assert "visitor scope is provably empty (EmptyResultSet)" in output
        assert "participant scope is provably empty (EmptyResultSet)" in output

    def test_it_proves_the_scope_survives_a_clone(self):
        output = run()
        assert "the scope survives .filter() and .order_by()" in output

    def test_it_proves_the_audit_trail_is_append_only(self):
        output = run()
        assert "the audit trail is append-only" in output

    def test_it_says_where_the_lint_rule_lives(self):
        """A reader who wants the syntactic half needs to be told where it is."""
        assert "just lint" in run()


class TestMatrixMode:
    def test_the_header_is_the_published_capability_set(self, seeded):
        output = run()
        for column in ("own", "peer", "cross-track", "aggregate", "export", "audit"):
            assert column in output

    def test_a_judge_sees_only_their_own_reviews(self, seeded):
        output = run()
        judge_row = _row(output, "judge")
        assert judge_row.split()[1] == "1/2", (
            f"the judge row should be 1 of 2 reviews for their own work: {judge_row}"
        )

    def test_a_judge_sees_nothing_of_a_peer(self, seeded):
        """The peer column is the cell the whole feature exists for."""
        output = run()
        assert _cell(output, "judge", "peer") == "0/2", output

    def test_a_judge_sees_nothing_across_tracks(self, seeded):
        output = run()
        assert _cell(output, "judge", "cross-track") == "0/2", output

    def test_an_organizer_sees_the_whole_event(self, seeded):
        output = run()
        assert _cell(output, "organizer", "own") == "2/2", output

    def test_an_organizer_may_ask_about_a_peer(self, seeded):
        output = run()
        assert _cell(output, "organizer", "peer") == "2/2", output

    def test_a_visitor_sees_nothing_anywhere(self, seeded):
        output = run()
        for column in ("own", "peer", "cross-track"):
            assert _cell(output, "visitor", column) == "0/2", output

    def test_a_participant_sees_nothing_anywhere(self, seeded):
        output = run()
        for column in ("own", "peer", "cross-track"):
            assert _cell(output, "participant", column) == "0/2", output

    def test_admin_sees_the_whole_event(self, seeded):
        output = run()
        assert _cell(output, "admin", "own") == "2/2", output

    def test_the_unbuilt_capabilities_print_a_question_mark(self, seeded):
        """`?`, not `0/2`. A zero would read as "verified, and the answer is none"."""
        output = run()
        judge_row = _row(output, "judge")
        assert judge_row.count("?") == 3, judge_row
        assert judge_row.split()[4:] == ["?", "?", "?"], judge_row

    def test_every_cell_states_its_provenance(self, seeded):
        output = run()
        for column in ("own", "peer", "cross-track", "aggregate", "export", "audit"):
            assert column in output.split("own          ")[-1]

    def test_it_still_discloses_the_denial_properties(self, seeded):
        """Even in matrix mode. D-02 is not covered by a row count."""
        output = run()
        assert "403 / empty body / no Location" in output

    def test_an_unknown_event_is_an_error_not_an_empty_table(self, seeded):
        with pytest.raises(CommandError, match="no event"):
            run("--event", "evt_99")

    def test_a_missing_binding_is_an_error_not_a_visitor_row(self, seeded):
        """Nobody bound as participant is a census error, not a refusal."""
        from reviewer.accounts.models import RoleBinding

        RoleBinding.objects.filter(role=ROLE_PARTICIPANT).delete()
        with pytest.raises(CommandError, match="strongest role"):
            run()

    def test_a_judge_who_is_also_an_organizer_cannot_populate_the_judge_row(self, seeded):
        """The F-40 shape, caught in our own proof.

        If every judge also organizes, borrowing one for the judge row would
        print "2 of 2 reviews visible to a judge" -- a number that contradicts
        the design, in the row a judge is most likely to read. The command must
        refuse rather than publish it.
        """
        from reviewer.accounts.models import RoleBinding

        RoleBinding.objects.filter(role=ROLE_ORGANIZER).update(user=seeded["bob"])
        RoleBinding.objects.create(event=seeded["event"], user=seeded["alice"], role=ROLE_ORGANIZER)
        with pytest.raises(CommandError, match="strongest role"):
            run()

    def test_no_staff_user_is_an_error(self, seeded):
        from reviewer.accounts.models import User

        User.objects.filter(is_staff=True).update(is_staff=False)
        with pytest.raises(CommandError, match="is_staff"):
            run()


class TestTheProofAgreesWithTheAccessor:
    """The command must not have its own idea of what a scope returns."""

    def test_the_organizer_row_matches_a_direct_count(self, seeded):
        event = seeded["event"]
        actor = Actor.for_user(event, seeded["organizer"])
        direct = Review.objects.for_actor(actor).count()
        total = ground_truth.reviews_in_event(event)
        assert _cell(run(), "organizer", "own") == f"{direct}/{total}"

    def test_the_judge_row_matches_a_direct_count(self, seeded):
        event = seeded["event"]
        actor = Actor.for_user(event, seeded["alice"])
        direct = Review.objects.for_actor(actor).count()
        total = ground_truth.reviews_in_event(event)
        assert _cell(run(), "judge", "own") == f"{direct}/{total}"


def _row(output: str, label: str) -> str:
    """The matrix line for one actor, by its label rather than by position."""
    for line in output.splitlines():
        if line.startswith("  ") and line.split()[:1] == [label]:
            return line
    raise AssertionError(f"no matrix row for {label!r} in:\n{output}")


def _cell(output: str, label: str, column: str) -> str:
    """One cell, located by the header rather than by index.

    The first draft of this helper returned `row.split()[1]`, which is a
    hardcoded column position. The moment a column is added to the table the
    helper keeps passing while reading the wrong cell, which is worse than not
    having the helper.
    """
    header_index = None
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "actor" in line and "cross-track" in line:
            header_index = i
            break
    assert header_index is not None, f"no matrix header in:\n{output}"
    columns = lines[header_index].split()[1:]
    wanted = columns.index(column) + 1
    return _row(output, label).split()[wanted]
