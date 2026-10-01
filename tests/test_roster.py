"""``invite`` and ``set_password`` -- turning a spreadsheet into a roster.

**The two properties that matter are idempotency and honest reporting**, because
the most likely thing an organizer will do is run ``invite`` twice.

Running it twice must not duplicate thirty people, must not reset anyone's
password, and must not silently drop a line -- a skipped judge is a judge with no
console and an organizer who never learns why. Both are asserted here rather than
assumed, and the rejected-line behaviour is asserted *separately* from the
success behaviour so "it created five people" can never be satisfied by a file
that silently created the wrong five.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from reviewer.setup.provisioning import ProvisionRequest, TrackSpec, provision
from reviewer.setup.roster import RosterError, apply_roster, load_emails

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"


def _piped(monkeypatch, text: str) -> None:
    """Point ``sys.stdin`` at ``text``.

    The command reads the global behind an explicit ``--stdin`` flag, which is
    what makes ``echo pw | manage.py set_password ...`` work. Django's own
    ``call_command(stdin=...)`` plumbing was tried first and does not reliably
    reach the command in this version, so the test drives the same seam a shell
    does rather than pretending to an API that is not there.
    """
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(text))


@pytest.fixture
def event():
    now = timezone.now()
    return provision(
        ProvisionRequest(
            organizer_email="organizer@example.org",
            organizer_name="Ada",
            password=PASSWORD,
            event_name="Ridgeway Hack 2026",
            starts_at=now,
            submissions_close=now + timedelta(days=2),
            judging_closes_at=now + timedelta(days=3),
            tracks=(TrackSpec(name="General"), TrackSpec(name="Hardware")),
        )
    ).event


class TestLoading:
    def test_it_reads_one_address_per_line(self, tmp_path):
        path = tmp_path / "judges.txt"
        path.write_text("ada@example.org\ngrace@example.org\n", encoding="utf-8")
        assert load_emails(path) == ["ada@example.org", "grace@example.org"]

    def test_it_drops_blanks_and_comments(self, tmp_path):
        path = tmp_path / "judges.txt"
        path.write_text("# the judges\nada@example.org\n\n  \n", encoding="utf-8")
        assert load_emails(path) == ["ada@example.org"]

    def test_it_lowercases(self, tmp_path):
        """Addresses are matched with ``=`` on a unique column, so a mixed-case
        paste creating a second account for the same person is a real bug."""
        path = tmp_path / "judges.txt"
        path.write_text("Ada@Example.ORG\n", encoding="utf-8")
        assert load_emails(path) == ["ada@example.org"]

    def test_a_missing_file_is_refused_by_name(self, tmp_path):
        with pytest.raises(RosterError, match="does not exist"):
            load_emails(tmp_path / "nope.txt")


class TestApplyingARoster:
    def test_it_creates_the_accounts(self, event):
        result = apply_roster(["ada@example.org", "grace@example.org"], role="judge")
        assert result.created_users == 2

        from reviewer.accounts.models import User

        assert User.objects.filter(email__in=["ada@example.org", "grace@example.org"]).count() == 2

    def test_it_binds_them_as_judges(self, event):
        apply_roster(["ada@example.org"], role="judge")

        from reviewer.accounts.models import RoleBinding

        assert RoleBinding.objects.filter(event=event, role="judge").count() == 1

    def test_a_new_account_has_no_usable_password(self, event):
        """**The honest state, and the reason ``set_password`` exists.** There is
        no mail service, so nothing could have delivered a credential."""
        from django.contrib.auth import authenticate

        apply_roster(["ada@example.org"], role="judge")
        assert authenticate(username="ada@example.org", password="") is None
        assert authenticate(username="ada@example.org", password="anything") is None

    def test_participants_are_bound_as_participants(self, event):
        apply_roster(["ada@example.org"], role="participant")

        from reviewer.accounts.models import RoleBinding

        # Filtered by user: provisioning already made the organizer a binding, and
        # an unfiltered `.get()` would fail on the fixture rather than the thing
        # under test.
        binding = RoleBinding.objects.get(user__email="ada@example.org")
        assert binding.role == "participant"

    def test_a_track_scopes_the_judge_binding(self, event):
        """**Scoping a judge is a leak control**, not a tidiness feature: an
        event-wide judge can see every project's standings."""
        apply_roster(["ada@example.org"], role="judge", track="Hardware")

        from reviewer.accounts.models import RoleBinding

        binding = RoleBinding.objects.get(user__email="ada@example.org")
        assert binding.track.name == "Hardware"

    def test_an_unknown_track_is_refused_and_names_the_real_ones(self, event):
        with pytest.raises(RosterError, match="Available: General, Hardware"):
            apply_roster(["ada@example.org"], role="judge", track="Nonexistent")

    def test_it_refuses_an_unknown_role(self, event):
        with pytest.raises(RosterError, match="not a role"):
            apply_roster(["ada@example.org"], role="wizard")


class TestItIsIdempotent:
    """**The most likely thing an organizer will do is run it twice.**"""

    def test_running_twice_creates_nothing_new(self, event):
        first = apply_roster(["ada@example.org", "grace@example.org"], role="judge")
        second = apply_roster(["ada@example.org", "grace@example.org"], role="judge")

        assert first.created_users == 2
        assert second.created_users == 0
        assert second.existing_users == 2
        assert second.bindings_created == 0

        from reviewer.accounts.models import User

        assert User.objects.filter(email="ada@example.org").count() == 1

    def test_running_twice_does_not_duplicate_the_binding(self, event):
        apply_roster(["ada@example.org"], role="judge")
        apply_roster(["ada@example.org"], role="judge")

        from reviewer.accounts.models import RoleBinding

        # One binding for this person, plus the organizer's from provisioning.
        assert RoleBinding.objects.filter(user__email="ada@example.org").count() == 1
        assert RoleBinding.objects.count() == 2

    def test_a_repeat_does_not_reset_a_password_they_already_set(self, event):
        """**The destructive version of this bug.** Re-running `invite` on a roster
        that has been live for a week must not lock every judge out."""
        from reviewer.accounts.models import User

        apply_roster(["ada@example.org"], role="judge")
        user = User.objects.get(email="ada@example.org")
        user.set_password("a-password-they-chose")
        user.save(update_fields=["password"])

        apply_roster(["ada@example.org"], role="judge")

        from django.contrib.auth import authenticate

        assert authenticate(username="ada@example.org", password="a-password-they-chose")

    def test_a_repeated_address_in_one_file_is_reported(self, event):
        """Two lines, one person: creating them twice gives them two workloads and
        a console showing one assignment."""
        result = apply_roster(["ada@example.org", "ada@example.org"], role="judge")
        assert result.created_users == 1
        assert any("repeated" in line for line in result.rejected)

    def test_a_person_can_hold_two_different_roles(self, event):
        """A judge who also submitted a project is a real case, and collapsing it
        would stop them commenting on their own entry."""
        apply_roster(["ada@example.org"], role="judge")
        apply_roster(["ada@example.org"], role="participant")

        from reviewer.accounts.models import RoleBinding

        assert RoleBinding.objects.filter(user__email="ada@example.org").count() == 2


class TestItReportsRatherThanGuesses:
    def test_a_bad_line_is_skipped_and_reported(self, event):
        """**A spreadsheet header is the single most likely bad line**, and an
        organizer who pasted one should be told rather than left wondering."""
        result = apply_roster(["email", "ada@example.org"], role="judge")
        assert result.created_users == 1
        assert "email" in result.rejected

    @pytest.mark.parametrize("bad", ["ada", "ada@", "@example.org", "a b@example.org"])
    def test_it_recognises_these_as_not_addresses(self, event, bad):
        result = apply_roster([bad, "grace@example.org"], role="judge")
        assert bad in result.rejected
        assert result.created_users == 1

    def test_an_entirely_bad_file_is_refused_not_half_applied(self, event):
        with pytest.raises(RosterError, match="None of those lines"):
            apply_roster(["nope", "also-nope"], role="judge")

        from reviewer.accounts.models import User

        assert not User.objects.filter(email__startswith="nope").exists()

    def test_an_empty_file_is_refused(self, event):
        with pytest.raises(RosterError, match="None of those lines"):
            apply_roster([], role="judge")


class TestOnADeploymentWithNoEvent:
    def test_it_refuses_and_says_what_to_do_first(self):
        """**The error has to be actionable.** "No event" with no next step is the
        kind of message that ends a first run."""
        with pytest.raises(RosterError, match="no event yet"):
            apply_roster(["ada@example.org"], role="judge")


class TestTheCommands:
    def _roster_file(self, tmp_path, body="ada@example.org\ngrace@example.org\n"):
        path = tmp_path / "judges.txt"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_invite_prints_what_it_did(self, event, tmp_path, capsys):
        call_command("invite", self._roster_file(tmp_path), role="judge")
        out = capsys.readouterr().out
        assert "2 account(s) created" in out
        assert "set_password" in out, "the organizer is not told the next step"

    def test_invite_warns_when_judges_are_event_wide(self, event, tmp_path, capsys):
        """An event-wide judge binding is the *default*, and it is the one that
        leaks. Saying so is cheaper than an organizer discovering it later."""
        call_command("invite", self._roster_file(tmp_path), role="judge")
        assert "EVENT-WIDE" in capsys.readouterr().out

    def test_invite_does_not_warn_when_a_track_was_given(self, event, tmp_path, capsys):
        call_command("invite", self._roster_file(tmp_path), role="judge", track="Hardware")
        assert "EVENT-WIDE" not in capsys.readouterr().out

    def test_invite_reports_skipped_lines_on_stderr(self, event, tmp_path, capsys):
        call_command("invite", self._roster_file(tmp_path, "email\nada@example.org\n"))
        err = capsys.readouterr().err
        assert "skipped" in err

    def test_set_password_works_and_lets_them_in(self, event, monkeypatch):
        """The pair of commands, end to end: ``invite`` makes an account nobody
        can sign into, ``set_password`` makes it usable. Neither is much use alone.
        """

        apply_roster(["ada@example.org"], role="judge")

        from django.contrib.auth import authenticate

        assert authenticate(username="ada@example.org", password="anything") is None

        _piped(monkeypatch, "a-long-enough-one\na-long-enough-one\n")
        call_command("set_password", "ada@example.org", "--stdin")

        assert authenticate(username="ada@example.org", password="a-long-enough-one")

    def test_set_password_refuses_an_unknown_account(self, event):
        with pytest.raises(CommandError, match="No account called"):
            call_command("set_password", "nobody@example.org", "--stdin")

    def test_set_password_refuses_a_mismatch(self, event, monkeypatch):
        apply_roster(["ada@example.org"], role="judge")
        _piped(monkeypatch, "first-password-x\nsecond-password-y\n")
        with pytest.raises(CommandError, match="did not match"):
            call_command("set_password", "ada@example.org", "--stdin")

    def test_set_password_refuses_a_short_one(self, event, monkeypatch):
        apply_roster(["ada@example.org"], role="judge")
        _piped(monkeypatch, "short\nshort\n")
        with pytest.raises(CommandError, match="at least"):
            call_command("set_password", "ada@example.org", "--stdin")

    def test_the_new_password_is_never_echoed(self, event, capsys, monkeypatch):
        """A command that prints the password puts it in a terminal scrollback and
        possibly a session log."""
        apply_roster(["ada@example.org"], role="judge")
        secret = "a-very-distinctive-password"
        _piped(monkeypatch, f"{secret}\n{secret}\n")
        call_command("set_password", "ada@example.org", "--stdin")
        assert secret not in capsys.readouterr().out
