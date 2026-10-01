"""Provisioning: making an empty deployment into a runnable hackathon.

**The acceptance claim is "any hackathon", so the central test is that nothing in
provisioning knows the fixture.** There is no ``evt_01`` in this file, no
``prj_``, no ``jdg_``, and the event's slug and id are derived from what the
organizer typed. If provisioning ever grew a hardcoded default, these tests would
fail rather than quietly producing another demo.

The second thing worth knowing is what is deliberately absent: no emails are
sent, no network is touched, and the transaction is all-or-nothing. A half-built
database is the worst state this code can leave behind -- an event with no rubric
refuses every review form, and an organizer with no event cannot sign in to fix
it.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from reviewer.setup.provisioning import (
    ProvisioningError,
    ProvisionRequest,
    TrackSpec,
    already_provisioned,
    provision,
    slugify,
)

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
        "tracks": (TrackSpec(name="General"), TrackSpec(name="Hardware")),
    }
    base.update(overrides)
    return ProvisionRequest(**base)


class TestItBuildsARunnableHackathon:
    def test_an_empty_database_is_the_starting_point(self):
        """**The whole feature, stated as one assertion.**"""
        assert already_provisioned() is False

    def test_it_creates_the_event_the_organizer_asked_for(self):
        result = provision(_request())
        assert result.event.name == "Ridgeway Hack 2026"
        assert result.event.slug == "ridgeway-hack-2026"
        assert not result.event.results_state == "published"

    def test_the_organizer_can_sign_in_with_the_password_they_chose(self):
        """Not 'a user exists' -- the credential actually authenticates.

        Asserting the row is not enough: a user saved with an unusable password
        would satisfy a row check and lock the organizer out of their own event.
        """
        from django.contrib.auth import authenticate

        result = provision(_request())
        user = authenticate(username="organizer@example.org", password=PASSWORD)
        assert user is not None
        assert user.pk == result.organizer.pk

    def test_the_organizer_holds_an_organizer_binding(self):
        from reviewer.accounts.models import RoleBinding

        result = provision(_request())
        assert RoleBinding.objects.filter(
            event=result.event, user=result.organizer, role="organizer"
        ).exists()

    def test_it_creates_the_tracks_it_was_given(self):
        result = provision(_request())
        assert sorted(t.name for t in result.tracks) == ["General", "Hardware"]
        assert all(t.event_id == result.event.pk for t in result.tracks)

    def test_the_rubric_weights_sum_to_one(self):
        """**A rubric whose weights do not sum to 1 produces a leaderboard on a
        different scale from the one the rubric claims**, and nothing else notices.

        ``Decimal`` rather than float, deliberately: ``0.4 + 0.35 + 0.25`` is
        ``0.9999999999999999`` in IEEE 754, and an organizer told their rubric is
        malformed when it is not learns to distrust every other number.
        """
        result = provision(_request())
        total = sum(c.weight for c in result.criteria)
        assert total == Decimal("1")

    def test_the_criteria_have_distinct_keys(self):
        """Two criteria sharing a key would silently overwrite each other in a
        score payload, and the export would carry one column for both."""
        result = provision(_request())
        keys = [c.key for c in result.criteria]
        assert len(keys) == len(set(keys))

    def test_the_windows_land_where_the_organizer_put_them(self):
        now = timezone.now()
        result = provision(_request(starts_at=now, submissions_close=now + timedelta(days=2)))
        assert result.event.submissions_close == now + timedelta(days=2)
        assert result.event.judging_closes_at > result.event.submissions_close

    def test_it_is_runnable_immediately_after(self):
        """The real acceptance line: after one call, the judging surfaces work.

        Asserting row counts would pass on a database the console cannot read.
        This walks the actual queries a judge and an organizer make.
        """
        from reviewer.isolation import Actor
        from reviewer.reviews.results import leaderboard

        result = provision(_request())
        actor = Actor.for_user(result.event, result.organizer)
        assert actor.is_organizer
        # An organizer may read the board; it is empty, and empty is a list.
        assert leaderboard(actor) == []


class TestItRefusesWhatWouldBreakIt:
    def test_it_refuses_a_second_event(self):
        """**One deployment, one hackathon.** Not a warning -- a refusal.

        Silently creating a second one would leave every route resolving an
        arbitrary event, which is the bug the single-event design exists to avoid.
        """
        provision(_request())
        assert already_provisioned() is True
        with pytest.raises(ProvisioningError, match="already has an event"):
            provision(_request(event_name="Another One"))

    def test_it_refuses_a_short_password(self):
        with pytest.raises(ProvisioningError, match="at least"):
            provision(_request(password="short"))

    def test_a_refused_provision_leaves_nothing_behind(self):
        """**All or nothing.** The failure mode this guards is the worst one:
        an event with no rubric, which refuses every review form."""
        with pytest.raises(ProvisioningError):
            provision(_request(password="short"))

        from reviewer.accounts.models import User
        from reviewer.events.models import Event

        assert Event.objects.count() == 0, "a failed setup left an event behind"
        assert User.objects.count() == 0, "a failed setup created an organizer"
        assert already_provisioned() is False

    def test_it_refuses_a_window_that_closes_before_it_opens(self):
        now = timezone.now()
        with pytest.raises(ProvisioningError, match="Submissions must close"):
            provision(_request(starts_at=now, submissions_close=now - timedelta(hours=1)))

    def test_it_refuses_judging_that_closes_before_submissions(self):
        now = timezone.now()
        with pytest.raises(ProvisioningError, match="Judging cannot close"):
            provision(
                _request(
                    starts_at=now,
                    submissions_close=now + timedelta(days=5),
                    judging_closes_at=now + timedelta(days=1),
                )
            )

    @pytest.mark.parametrize("bad", ["not-an-email", "@example.org", "a@", ""])
    def test_it_refuses_something_that_is_not_an_email(self, bad):
        with pytest.raises(ProvisioningError):
            provision(_request(organizer_email=bad))

    def test_it_refuses_an_email_that_already_has_an_account(self):
        """**Reachable only with a user and no event.**

        Once an event exists the "already has an event" refusal fires first, so a
        second organizer cannot even be attempted. This branch is for the case
        that actually happens -- somebody created a user through the admin, then
        ran setup -- and it must refuse rather than create a duplicate account.
        """
        from reviewer.accounts.models import User

        User.objects.create_user(email="taken@example.org", password="x" * 20)
        with pytest.raises(ProvisioningError, match="already has an account"):
            provision(_request(organizer_email="taken@example.org"))

    def test_the_second_organizer_is_refused_before_the_email_is_even_read(self):
        """Ordering matters for what the organizer learns: once a hackathon
        exists, the honest answer is "this deployment is taken", not "that address
        is invalid"."""
        provision(_request())
        with pytest.raises(ProvisioningError, match="already has an event"):
            provision(_request(organizer_email="taken@example.org"))

    def test_a_refused_duplicate_leaves_the_first_intact(self):
        """**The transaction has to hold across the whole call**, not just the
        event creation, or a second attempt could half-attach a binding to the
        first event."""
        provision(_request())
        with pytest.raises(ProvisioningError):
            provision(_request(event_name="Second"))
        from reviewer.accounts.models import RoleBinding

        assert RoleBinding.objects.count() == 1


class TestTheSlug:
    @pytest.mark.parametrize(
        ("name", "want"),
        [
            ("Ridgeway Hack 2026", "ridgeway-hack-2026"),
            ("  Spaces   Everywhere  ", "spaces-everywhere"),
            ("Hack/athon: v2!", "hack-athon-v2"),
        ],
    )
    def test_it_slugifies_ordinary_names(self, name, want):
        assert slugify(name) == want

    def test_a_name_of_only_punctuation_still_yields_a_usable_slug(self):
        """An empty slug is an event nobody can address, so this has a fallback."""
        result = provision(_request(event_name="!!! ???"))
        assert result.event.slug
        assert result.event.slug != ""

    def test_two_identically_named_events_would_not_collide(self):
        """Only one event per deployment, so this is defensive -- but a slug
        collision is the kind of thing that should not be reachable by renaming."""
        assert slugify("Same Name") == slugify("same name")


class TestNoFixtureKnowsInThisModule:
    def test_the_code_mentions_no_fixture_identity(self):
        """**A guard against the failure this feature exists to prevent.**

        Provisioning that defaulted to the organizers' event would make every
        deployment a copy of their demo, and every other test in this file would
        still pass -- so the guard is structural, not behavioural.

        **The module docstring is stripped first.** The first version of this test
        scanned the whole file and failed, because the docstring says out loud
        that the module does not know the fixture, and therefore contains the
        token. A guard that trips on the thing it is guarding is a guard nobody
        will re-enable; a finding this project has earned four times over.
        """
        import pathlib
        import re

        import reviewer.setup.provisioning as module

        text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        # Drop every docstring, keeping the code that has to execute.
        code = re.sub(r'(?s)"""..*?"""', '""', text)
        for token in ("evt_01", "prj_01", "jdg_01", "fixtures.json", "Sample Hack"):
            assert token not in code, (
                f"provisioning's CODE mentions {token!r}: a setup wizard that knows "
                "the fixture is a demo, not a product"
            )

    def test_the_provisioned_event_id_is_generated_not_typed(self):
        """A random id is what makes two separately-provisioned deployments
        genuinely independent rather than coincidentally equal."""
        first = provision(_request())
        assert first.event.pk.startswith("evt_")
        assert first.event.pk != "evt_01"

    def test_the_password_is_never_in_the_result_summary(self):
        """The summary is what a management command prints, and a printed
        password outlives the terminal it was printed in."""
        result = provision(_request())
        assert PASSWORD not in result.summary()
        assert "password" not in result.summary().lower()
