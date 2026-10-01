"""``/organizer/settings/`` -- the lifecycle, in a browser.

Two properties are worth more than the rest, and both are about what this page
must **not** be able to do:

1. **A non-organizer gets the portal's own bare 403**, not a page that renders an
   empty form. A settings page a judge can open is a settings page a judge can
   submit, and the second one closes the voting window.
2. **No setting on this page can widen what any actor reads.** The form is
   asserted to contain the fields that gate the *event* and to contain **no**
   field that would reach isolation, the rubric's weights, or a project's track.
   That is the property, and asserting the *absence* is the only way to keep it
   true when somebody later adds a convenient-looking checkbox.

The publication path is asserted to go through `audit.publication.publish`
rather than writing `results_state`, because a result published by a browser and
not by the publication module has no hash and no audit entry — the F-92 shape
somewhere new.
"""

from __future__ import annotations

import re

import pytest
from django.urls import reverse
from django.utils import timezone

from reviewer.events.models import VOTING_CLOSED, VOTING_OPEN_LINK

pytestmark = pytest.mark.django_db

URL = "/organizer/settings/"


@pytest.fixture
def world(db):
    from tests.factories import bind, make_event, make_rubric, make_track, make_user

    event = make_event(
        name="Ridgeway Hack 2026",
        voting_mode=VOTING_CLOSED,
        submissions_open=timezone.now() - timedelta_days(1),
        submissions_close=timezone.now() + timedelta_days(1),
        judging_closes_at=timezone.now() + timedelta_days(2),
    )
    make_track(event, "General")
    # **A rubric, because publishing needs one.** Without it every publish test
    # was really testing the "nothing to publish" refusal, and the happy path
    # -- hash, digest, audit head -- was never executed at all.
    make_rubric(event)
    organizer = make_user("organizer@ridgeway.example")
    bind(organizer, event, "organizer")
    judge = make_user("judge@ridgeway.example")
    bind(judge, event, "judge")
    return event, organizer, judge


def timedelta_days(n):
    import datetime as dt

    return dt.timedelta(days=n)


@pytest.fixture
def as_organizer(client, world):
    client.force_login(world[1])
    return client


class TestTheGuard:
    def test_an_anonymous_visitor_is_refused(self, client, world):
        """A bare 403 with an **empty body** and the guard named. Not a page that
        renders an empty form, because a page is a form."""
        response = client.get(URL)
        assert response.status_code == 403
        assert response.content == b""
        assert response["X-Refused-By"] == "organizer_settings.role"

    def test_a_judge_is_refused(self, client, world):
        """**This is the case that matters.** A judge who can open settings can close
        the window and publish the board."""
        client.force_login(world[2])
        response = client.get(URL)
        assert response.status_code == 403
        assert response.content == b""

    def test_a_participant_is_refused(self, client, world):
        from tests.factories import bind, make_user

        event = world[0]
        bind(make_user("p@ridgeway.example"), event, "participant")
        assert client.get(URL).status_code == 403

    def test_a_refused_post_changes_nothing(self, client, world):
        """**A GET-only guard is not a guard.**"""
        event = world[0]
        before = event.submissions_close
        client.force_login(world[2])
        response = client.post(URL, {"name": "Hijacked", "submissions_close": "2030-01-01T00:00"})
        assert response.status_code == 403
        event.refresh_from_db()
        assert event.name == "Ridgeway Hack 2026"
        assert event.submissions_close == before

    def test_no_event_is_a_403_rather_than_a_404(self, client, db):
        """A 404 would be indistinguishable from a mistyped URL, and the acceptance
        gate's route probes cannot tell those apart (F-40)."""
        assert client.get(URL).status_code == 403

    def test_an_organizer_may_open_it(self, as_organizer):
        assert as_organizer.get(URL).status_code == 200


class TestNoSettingWidensAccess:
    """**The property, asserted as an absence.**"""

    def test_the_form_offers_no_isolation_field(self, as_organizer):
        body = as_organizer.get(URL).content.decode()
        fields = set(re.findall(r'(?s)<input[^>]*name="([^"]+)"', body))
        forbidden = {
            "results_state",  # must go through publish()
            "reviews_per_project",  # would change what a judge is asked to score
            "assignment_seed",  # would change the plan under judges' feet
            "judge_capacity",
        }
        assert not fields & forbidden, f"settings offers isolation fields: {fields & forbidden}"

    def test_the_form_offers_no_track_or_rubric_field(self, as_organizer):
        """Moving a project between tracks decides **which judges can see it**, and
        reweighting the rubric moves a board a judge already scored. Neither is a
        setting."""
        body = as_organizer.get(URL).content.decode()
        assert 'name="track"' not in body
        assert 'name="weight"' not in body
        assert 'name="criteria"' not in body

    def test_and_the_page_says_why_the_rubric_is_absent(self, as_organizer):
        """A missing control that is not explained reads as an oversight."""
        body = as_organizer.get(URL).content.decode().lower()
        assert "rubric" in body
        assert "not" in body and "editable" in body


class TestTheWindows:
    def test_it_saves_a_new_window(self, as_organizer, world):
        from datetime import datetime

        as_organizer.post(
            URL,
            {
                "name": "Ridgeway Hack 2026",
                "starts_at": "2026-03-01T09:00",
                "submissions_close": "2026-03-03T17:00",
                "judging_closes_at": "2026-03-04T17:00",
                "voting_mode": VOTING_CLOSED,
            },
        )
        event = world[0]
        event.refresh_from_db()
        assert event.submissions_close == datetime(2026, 3, 3, 17, 0, tzinfo=event.starts_at.tzinfo)

    def test_an_unparseable_date_is_refused_by_name(self, as_organizer):
        response = as_organizer.post(
            URL,
            {"name": "Ridgeway", "submissions_close": "not-a-date", "voting_mode": VOTING_CLOSED},
        )
        assert response.status_code == 400
        assert b"not a date and time" in response.content

    def test_submissions_must_close_after_the_start(self, as_organizer):
        response = as_organizer.post(
            URL,
            {
                "name": "Ridgeway",
                "starts_at": "2026-03-05T09:00",
                "submissions_close": "2026-03-01T09:00",
                "voting_mode": VOTING_CLOSED,
            },
        )
        assert response.status_code == 400
        assert b"must close after the event starts" in response.content

    def test_judging_cannot_close_before_submissions(self, as_organizer):
        """**Judges score what arrived, not what has not.** A window that says
        otherwise invites scoring an incomplete event."""
        response = as_organizer.post(
            URL,
            {
                "name": "Ridgeway",
                "submissions_close": "2026-03-10T09:00",
                "judging_closes_at": "2026-03-01T09:00",
                "voting_mode": VOTING_CLOSED,
            },
        )
        assert response.status_code == 400
        assert b"cannot close before submissions close" in response.content

    def test_voting_must_close_after_it_opens(self, as_organizer):
        response = as_organizer.post(
            URL,
            {
                "name": "Ridgeway",
                "voting_opens_at": "2026-03-10T09:00",
                "voting_closes_at": "2026-03-01T09:00",
                "voting_mode": VOTING_OPEN_LINK,
            },
        )
        assert response.status_code == 400

    def test_a_refused_post_leaves_the_event_alone(self, as_organizer, world):
        event = world[0]
        before = (event.name, event.submissions_close)
        as_organizer.post(URL, {"name": "", "voting_mode": VOTING_CLOSED})
        event.refresh_from_db()
        assert (event.name, event.submissions_close) == before

    def test_a_blank_name_is_refused_because_it_is_on_every_page(self, as_organizer):
        response = as_organizer.post(URL, {"name": "  ", "voting_mode": VOTING_CLOSED})
        assert response.status_code == 400
        assert b"needs a name" in response.content

    def test_a_post_omitting_the_start_keeps_it_and_does_not_a_500(self, as_organizer, world):
        """**The defect this page actually shipped with.** `starts_at` is
        `NOT NULL`, and the save path wrote `None` for any date the form left out
        -- so the publish button, whose form deliberately carried fewer fields,
        nulled the column and returned a 500. The assertion is not the status
        code alone: the stored value is what the 500 was destroying."""
        event = world[0]
        before = event.starts_at
        response = as_organizer.post(
            URL, {"name": "Ridgeway Hack 2026", "voting_mode": VOTING_CLOSED}
        )
        assert response.status_code == 302
        event.refresh_from_db()
        assert event.starts_at == before

    def test_publishing_does_not_depend_on_the_settings_form_at_all(self, as_organizer, world):
        """Publish is reached with one field in the POST. If it ever needs the
        settings to arrive alongside it, this is the test that notices."""
        event = world[0]
        before = (event.name, event.starts_at, event.submissions_close)
        response = as_organizer.post(URL, {"action": "publish"})
        assert response.status_code == 302
        event.refresh_from_db()
        assert (event.name, event.starts_at, event.submissions_close) == before


class TestVoting:
    def test_an_organizer_can_open_voting_to_strangers(self, as_organizer, world):
        """**The mode that makes a public vote possible at all** -- provisioning
        creates every event with voting closed, so without this a fresh deployment
        can never take a public vote."""
        as_organizer.post(URL, {"name": "Ridgeway Hack 2026", "voting_mode": VOTING_OPEN_LINK})
        world[0].refresh_from_db()
        assert world[0].voting_mode == VOTING_OPEN_LINK

    def test_an_unknown_mode_is_refused_rather_than_stored(self, as_organizer, world):
        response = as_organizer.post(
            URL, {"name": "Ridgeway Hack 2026", "voting_mode": "whatever_i_like"}
        )
        assert response.status_code == 400
        world[0].refresh_from_db()
        assert world[0].voting_mode == VOTING_CLOSED

    def test_every_mode_in_the_schema_is_selectable(self, as_organizer):
        """**A mode that exists but is not offered is a mode nobody can turn on.**
        The list imports the constants rather than re-typing them, and this is the
        test that says so."""
        from reviewer.events.models import VOTING_MODE_CHOICES
        from reviewer.events.settings_view import VOTING_MODES

        offered = {value for value, _ in VOTING_MODES}
        assert offered == {value for value, _ in VOTING_MODE_CHOICES}


class TestTheAuditTrail:
    def test_a_change_is_recorded_with_its_old_and_new_value(self, as_organizer, world):
        from reviewer.audit.models import AuditEntry

        before = world[0].submissions_close
        as_organizer.post(
            URL,
            {
                "name": "Ridgeway Hack 2026",
                "starts_at": "2026-03-01T09:00",
                "submissions_close": "2026-03-09T17:00",
                "voting_mode": VOTING_CLOSED,
            },
        )
        entries = AuditEntry.objects.filter(action__contains="submissions_close")
        assert entries.exists(), "changing a deadline wrote no audit entry"
        assert str(before.year) in str(entries.first().before)
        assert "2026" in str(entries.first().after)

    def test_a_no_op_post_writes_nothing(self, as_organizer, world):
        """**An append-only chain full of no-op entries is a chain nobody reads** --
        the F-80 shape for a log. Saving the form unchanged must be silent."""
        from reviewer.audit.models import AuditEntry

        values = {
            "name": "Ridgeway Hack 2026",
            "starts_at": world[0].starts_at.strftime("%Y-%m-%dT%H:%M"),
            "submissions_close": world[0].submissions_close.strftime("%Y-%m-%dT%H:%M"),
            "judging_closes_at": world[0].judging_closes_at.strftime("%Y-%m-%dT%H:%M"),
            "voting_mode": world[0].voting_mode,
        }
        before = AuditEntry.objects.count()
        as_organizer.post(URL, values)
        assert AuditEntry.objects.count() == before


class TestPublishing:
    def test_publishing_writes_a_publication_with_a_hash(self, as_organizer):
        from reviewer.audit.models import ResultPublication

        as_organizer.post(URL, {"name": "Ridgeway Hack 2026", "action": "publish"})
        assert ResultPublication.objects.exists()

    def test_it_goes_through_the_publication_module(self, as_organizer, world, monkeypatch):
        """**A result published by writing ``results_state`` would have no hash and
        no audit entry** -- F-92 in a new place. So the call is pinned, and
        monkeypatching it to fail makes the failure mode visible: a settings page
        that published by other means would raise rather than quietly succeed.
        """
        import reviewer.audit.publication as publication

        called = []
        monkeypatch.setattr(
            publication, "publish", lambda event, actor, **kw: called.append(event) or object()
        )
        as_organizer.post(URL, {"name": "Ridgeway Hack 2026", "action": "publish"})
        assert called, "the settings page published without the publication module"

    def test_publishing_twice_adds_a_row_rather_than_editing(self, as_organizer):
        from reviewer.audit.models import ResultPublication

        as_organizer.post(URL, {"name": "Ridgeway", "action": "publish"})
        first = ResultPublication.objects.count()
        as_organizer.post(URL, {"name": "Ridgeway", "action": "publish"})
        assert ResultPublication.objects.count() == first + 1, (
            "the history of publications IS the tamper evidence; an overwrite destroys it"
        )


class TestPublishingWithNothingToPublish:
    def test_an_event_with_no_rubric_is_refused_in_words_not_a_500(self, client, world):
        """**`publish` signals "no rubric" with `ValueError`.** Letting it escape
        made the page's only button a 500, and the only person who can see it is
        the organizer. The status and the message are both asserted because a
        silent redirect would leave them wondering."""
        event = world[0]
        event.rubrics.all().delete()
        client.force_login(world[1])
        response = client.post(URL, {"action": "publish"}, follow=True)
        assert response.status_code == 200
        assert b"nothing to publish" in response.content
        from reviewer.audit.models import ResultPublication

        assert not ResultPublication.objects.exists()

    def test_the_button_is_hidden_when_there_is_nothing_to_publish(self, client, world):
        world[0].rubrics.all().delete()
        client.force_login(world[1])
        body = client.get(URL).content.decode()
        assert 'value="publish"' not in body
        assert "nothing to publish" in body


class TestTheRouteIsReachable:
    def test_it_reverses(self):
        assert reverse("organizer_settings") == URL
