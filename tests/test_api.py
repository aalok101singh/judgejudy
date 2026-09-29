"""The T2 surface: the scoped score endpoint and the CSV export.

**The three traps this module exists to close, and each one has a test whose
name is the trap.**

1. **A CSRF rejection and a scope rejection are both 403.** So a strict test
   client with no token is refused *before the view runs*, and an isolation
   assertion can pass without the scope ever being consulted -- a green test
   proving nothing. Every refusal test here therefore asserts **which** guard
   refused, by reading ``X-Refused-By``, and there is a test whose whole job is
   to prove the guard is reachable at all. That is F-40 applied to our own
   suite rather than to the acceptance gate.

2. **A feature that returns structurally valid output containing nothing is
   indistinguishable from a feature that works.** An empty collection is a valid
   value, so ``assert found == []`` passes forever. So the refusals here are
   asserted as **an empty BODY with a 403 and a named guard**, never as an empty
   list -- and there is a separate test for the judge with zero reviews, whose
   correct answer is a **200 with an empty list**, precisely so that the two cases
   cannot be confused with each other.

3. **An unresolvable subject must not fall through.** ``?judge=nobody`` silently
   returning your own scores is a wrong answer produced by a missing lookup, and
   a reader has no way to tell it from a right one (F-42).

**Why the export header is asserted against `fixtures.json` and not against a
constant.** F-04: the header is the fixture's KEY order,
``functionality, quality, innovation``, which is neither alphabetical nor the
order any row's values appear in. Getting it backwards transposes two columns in
every row of every export, and **nothing else catches it** -- a CSV with the
right number of columns in the wrong order is a perfectly well-formed CSV. The
comparison is therefore against a value derived from the fixture file.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib

import pytest
from django.test import Client
from django.urls import reverse

from reviewer.isolation.refusal import REFUSED_BY_HEADER
from reviewer.reviews import api as api_module
from reviewer.reviews.models import Review

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


@pytest.fixture
def identities(event) -> dict:
    """The five demo identities as users. Derived, never typed -- see the note
    in ``tests/test_judge_console.py``; typing them here would be a second source
    of truth that rots the moment the chooser picks a different judge."""
    from reviewer.accounts.models import User
    from reviewer.importer import census as census_module
    from reviewer.importer import demo as demo_module

    chosen = demo_module.choose(census_module.census(raw_fixture_for_tests()))
    return {identity.key: User.objects.filter(email=identity.email).first() for identity in chosen}


def raw_fixture_for_tests() -> dict:
    return json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))


def _client_for(email: str, *, strict_csrf: bool = False) -> Client:
    """A client whose ``request.user`` is this identity, via the real door.

    **Not** ``force_login``: the demo-token backend is what actually
    authenticates the organizers' checker, and a test that used a different door
    would not be testing the door in production.

    ``strict_csrf=True`` builds the client Django's own way of observing CSRF
    behaviour at all. Left false, a 403 in any test below could be a CSRF
    rejection wearing the same status code as a scope rejection.
    """
    from reviewer.accounts.demo_tokens import mint

    return Client(HTTP_AUTHORIZATION=mint(email), enforce_csrf_checks=strict_csrf)


def _body(response) -> dict:
    return json.loads(response.content.decode())


def _assert_real_refusal(response, expected_guard: str) -> None:
    """A 403, an EMPTY body, no ``Location``, and the guard that produced it.

    Four assertions, and they are four because a refusal can pass three of them
    and fail the fourth. The one that matters most is the guard: a 403 with an
    empty body and no ``Location`` that was produced by **CSRF** is
    indistinguishable from one produced by the isolation layer, and only the
    header tells them apart.
    """
    assert response.status_code == 403, (
        f"expected a literal 403, got {response.status_code} ({response.content[:120]!r})"
    )
    assert response.content == b"", (
        f"refusal body was {response.content[:200]!r} -- it must be empty, or a "
        "reader (and run.py) cannot tell a refusal from an answer"
    )
    assert "Location" not in response.headers, (
        f"refusal carried a Location header: {response.headers.get('Location')!r}. "
        "run.py FOLLOWS redirects, so a 302 comes back to the checker as a 200."
    )
    assert response.headers.get(REFUSED_BY_HEADER) == expected_guard, (
        f"refused by {response.headers.get(REFUSED_BY_HEADER)!r}, expected "
        f"{expected_guard!r}. A refusal from CSRF or from a missing credential "
        "is the same status code, and this header is the only thing that tells "
        "the isolation layer was actually reached."
    )


# --------------------------------------------------------------- the routes exist


class TestTheRoutesResolve:
    def test_the_url_is_the_one_dot_dogfood_toml_names(self):
        """`.dogfood.toml` is the file the panel's checker reads.

        The first version of this test asserted the route *exists*. It does not
        matter: a route can exist at a path the checker never calls, and the
        check still fails. So this compares the reversed URL to the file.
        """
        config = (REPO / ".dogfood.toml").read_text(encoding="utf-8")
        assert f'judge_scores = "{reverse("judge_scores")}"' in config
        assert f'csv_export   = "{reverse("csv_export")}"' in config

    def test_both_routes_reach_the_view_and_not_a_404(self, identities, event):
        """A 404 would be a 4xx, and the checker's peer and participant probes
        accept 4xx -- so isolation enforced by absence is not isolation."""
        judge = identities["judge_a"]
        assert _client_for(judge.email).get(reverse("judge_scores")).status_code == 200
        assert (
            _client_for(identities["organizer"].email).get(reverse("csv_export")).status_code == 200
        )


# ----------------------------------------------------------------- the CSRF trap


class TestCsrfCannotMasqueradeAsIsolation:
    """**Trap 1. A CSRF rejection and a scope rejection are both 403.**

    If the refusals below were happening in front of the view rather than in it,
    every isolation test in this file would still be green. So the guards are
    made *reachable*, and then shown to be the ones that fire.
    """

    def test_a_get_with_only_a_credential_header_is_not_a_csrf_rejection(self, identities, event):
        """**Executed, not recalled.** F-11 was a documented DRF default that
        was backwards; this is the same class of claim about the same machinery.

        Django's ``CsrfViewMiddleware`` is unconditional in this project -- there
        is no ``csrf_exempt`` on either route -- so the honest thing is to watch
        a header-only GET come back 200 and know why.
        """
        response = _client_for(identities["judge_a"].email, strict_csrf=True).get(
            reverse("judge_scores")
        )
        assert response.status_code == 200, (
            "a GET carrying only the credential header was refused. If this ever "
            "becomes a 403 the two refusals stop being distinguishable and every "
            "isolation test in this file is testing CSRF."
        )
        assert _body(response)["scope"]["decision"] == "allow-own"

    def test_a_strict_client_is_still_refused_by_scope_not_by_csrf(self, identities, event):
        """The participant refusal, on a client that DOES enforce CSRF.

        So the 403 below cannot be a CSRF rejection: the guard name in the
        header says which layer produced it.
        """
        response = _client_for(identities["participant"].email, strict_csrf=True).get(
            reverse("judge_scores")
        )
        _assert_real_refusal(response, api_module.REFUSED_BY_ROLE)


# -------------------------------------------------------------- the three checks


class TestTheJudgeSeesOwnScores:
    """T2-4. ``judge sees own scores``: 200 for judge_a."""

    def test_the_owner_gets_200_and_only_their_own(self, identities, event):
        judge = identities["judge_a"]
        payload = _body(_client_for(judge.email).get(reverse("judge_scores")))

        assert payload["count"] > 0, "judge_a was promoted because it has reviews"
        assert payload["scope"]["decision"] == "allow-own"
        assert {row["judge"] for row in payload["reviews"]} == {judge.source_key}

    def test_the_receipt_says_how_much_of_the_event_this_is(self, identities, event):
        """``bible/05`` §6a: "3 of 126", so a reader can check isolation without
        running our suite. The total is the event-wide count, not a filtered one.

        **The expected total is taken from ``scope_total_count()`` and not from a
        hand-written ``Review.objects.filter(event=event)``** -- the first version
        of this test did the latter and JJ01, the isolation lint rule, failed the
        build on it. That is D-01 working: the rule reaches the tests too, and it
        is right to, because a helper that reads around the scope can hand a test
        the wrong row.
        """
        from reviewer.isolation import Actor

        judge = identities["judge_a"]
        payload = _body(_client_for(judge.email).get(reverse("judge_scores")))

        event_total = Review.objects.for_actor(Actor.for_user(event, judge)).scope_total_count()

        assert payload["scope"]["visible"] == payload["count"]
        assert payload["scope"]["total"] == event_total
        assert payload["scope"]["visible"] < payload["scope"]["total"], (
            "if a judge sees the whole event the receipt is lying about them"
        )

    def test_asking_about_yourself_by_the_demo_key_is_the_same_answer(self, identities, event):
        """``.dogfood.toml`` names ``?judge=judge_a``. That spelling must resolve."""
        bare = _body(_client_for(identities["judge_a"].email).get(reverse("judge_scores")))
        named = _body(
            _client_for(identities["judge_a"].email).get(
                reverse("judge_scores"), {"judge": "judge_a"}
            )
        )
        assert named["count"] == bare["count"]
        assert named["scope"]["decision"] == "allow-own"
        assert named["subject"]["source_key"] == identities["judge_a"].source_key

    def test_the_natural_key_and_the_email_also_resolve(self, identities, event):
        """D-11's ``source_key`` is the stable identifier, so ``?judge=jdg_01``
        has to work -- and so does the address an organizer would paste."""
        judge = identities["judge_a"]
        client = _client_for(judge.email)
        for spelling in (judge.source_key, judge.email, str(judge.pk)):
            response = client.get(reverse("judge_scores"), {"judge": spelling})
            assert response.status_code == 200, spelling
            assert _body(response)["count"] > 0, spelling


class TestTheJudgeCannotSeePeerScores:
    """T2-5. **The one that matters most.** judge_b is refused judge_a's URL."""

    def test_a_peer_is_refused_not_filtered(self, identities, event):
        response = _client_for(identities["judge_b"].email).get(
            reverse("judge_scores"), {"judge": "judge_a"}
        )
        _assert_real_refusal(response, api_module.REFUSED_BY_SUBJECT)

    def test_the_refusal_carries_no_rows_at_all(self, identities, event):
        """**Trap 2, stated as its own test.**

        ``assert found == []`` passes forever against a feature that returns
        nothing. So this asserts the *body is empty and the status is 403* -- the
        two properties an empty-list assertion cannot distinguish from a working
        filter. A judge_b who received ``{"reviews": []}`` has been told the
        truth in the most useless way available, and the brief names that shape
        by name.
        """
        response = _client_for(identities["judge_b"].email).get(
            reverse("judge_scores"), {"judge": "judge_a"}
        )
        assert response.status_code == 403
        assert response.content == b""
        assert b"reviews" not in response.content
        assert b"jdg_" not in response.content, "a refusal leaked an identifier"

    def test_a_peer_refusal_works_for_every_spellings_of_the_subject(self, identities, event):
        """Refusing only the ``judge_a`` spelling would be refusing the demo."""
        judge = identities["judge_a"]
        client = _client_for(identities["judge_b"].email)
        for spelling in ("judge_a", judge.source_key, judge.email):
            _assert_real_refusal(
                client.get(reverse("judge_scores"), {"judge": spelling}),
                api_module.REFUSED_BY_SUBJECT,
            )

    def test_a_judge_with_no_reviews_is_not_refused(self, identities, event):
        """**The other half of trap 2, and the reason it is easy to get wrong.**

        A judge who has genuinely not scored anything has reached a decision of
        ``allow-own`` with nothing behind it. That is a **200 with an empty
        list**, not a 403. If the branch were written on emptiness rather than on
        the decision -- which is the natural way to write it and the wrong one --
        this judge would be refused, and the refusal would be indistinguishable
        from a real one.

        So this test pins the case where the two answers must differ, which is
        the only way a test can tell "refused" from "nothing here".
        """
        from reviewer.accounts.models import RoleBinding, User
        from reviewer.core import ROLE_JUDGE

        quiet = User.objects.create_user("quiet-judge@example.org", password="x")
        RoleBinding.objects.create(user=quiet, event=event, role=ROLE_JUDGE)

        response = _client_for(quiet.email).get(reverse("judge_scores"))
        payload = _body(response)

        assert response.status_code == 200, "an empty scope is not a refusal"
        assert payload["count"] == 0
        assert payload["reviews"] == []
        assert payload["scope"]["decision"] == "allow-own"
        assert payload["scope"]["visible"] == 0
        assert payload["scope"]["total"] > 0, "the denominator is event-wide"

    def test_an_unknown_subject_is_a_400_and_never_a_fall_through(self, identities, event):
        """**Trap 3.** Silently ignoring an unresolvable ``judge=`` and returning
        your own scores is a wrong answer produced by a missing lookup, and the
        caller cannot tell it from a right one (F-42)."""
        response = _client_for(identities["judge_a"].email).get(
            reverse("judge_scores"), {"judge": "nobody-at-all"}
        )
        assert response.status_code == 400
        assert _body(response)["refused_by"] == api_module.BAD_SUBJECT
        assert "reviews" not in _body(response), "a 400 must not carry a review set"

    def test_a_participant_is_refused_the_bare_route(self, identities, event):
        """T2-6. ``participant blocked``."""
        _assert_real_refusal(
            _client_for(identities["participant"].email).get(reverse("judge_scores")),
            api_module.REFUSED_BY_ROLE,
        )

    def test_a_visitor_is_refused_too(self, event):
        _assert_real_refusal(Client().get(reverse("judge_scores")), api_module.REFUSED_BY_ROLE)


# -------------------------------------------------------------------- the export


class TestTheCsvExport:
    """T2-7. ``csv export works``: 200 for an organizer."""

    def test_the_organizer_gets_a_csv(self, identities, event):
        response = _client_for(identities["organizer"].email).get(reverse("csv_export"))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        assert len(rows) == 127, "a header plus one row per review"
        assert rows[1][0], (
            "F-69: the review column was 126 empty cells until the test that "
            "checks every exported value against the database caught it"
        )

    def test_no_column_in_the_export_is_empty_throughout(self, identities, event):
        """**F-69, stated as its own test so it cannot be re-broken quietly.**

        A CSV is structurally valid with an empty column, which is precisely why
        a 126-row export whose first column held nothing looked like a working
        export. This asserts the shape a reader would assume: every cell in
        every data row is populated.
        """
        response = _client_for(identities["organizer"].email).get(reverse("csv_export"))
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        for row in rows[1:]:
            blanks = [index for index, cell in enumerate(row) if cell == ""]
            assert not blanks, (
                f"row {row[0]!r} has empty cells at {blanks}. A structurally valid "
                "export containing nothing is indistinguishable from one that works."
            )

    def test_the_header_is_the_fixtures_key_order(self, identities, event, raw_fixture):
        """**F-04, and the assertion is against the file rather than a constant.**

        The fixture's criteria keys, read out of ``fixtures.json`` in the order
        the file itself uses them. Deriving the order from a *row's values* is
        the error, and it transposes two columns in every export while leaving a
        perfectly well-formed CSV behind it.
        """
        from_rows = tuple(raw_fixture["scores"][0]["criteria"].keys())
        assert from_rows == ("functionality", "quality", "innovation")

        response = _client_for(identities["organizer"].email).get(reverse("csv_export"))
        header = next(csv.reader(io.StringIO(response.content.decode())))
        assert header[-3:] == list(from_rows), (
            f"export header ends {header[-3:]}, the fixture's key order is "
            f"{list(from_rows)}. This is F-04: two columns transpose in every row."
        )

    def test_a_values_position_matches_its_own_column_everywhere(self, identities, event):
        """**The other half of F-04: the values, not just the header.**

        A header in the right order with the values paired positionally is the
        same defect with the evidence removed. Every row is checked against the
        database, per criterion key, so a transposition cannot hide behind a
        correct-looking header.
        """
        from reviewer.accounts.models import User
        from reviewer.reviews.models import Score

        response = _client_for(identities["organizer"].email).get(reverse("csv_export"))
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        header = rows[0]
        criteria = header[-3:]

        # Keyed on the same label the view uses, which falls back to the
        # (judge, project) natural key because the loader leaves the column
        # empty -- F-69. Keyed on the blank source_key the lookup would find
        # nothing and this test would fail for the wrong reason.
        expected = {}
        for score in Score.objects.select_related("criterion", "review").all():
            expected.setdefault(
                score.review.source_key
                or f"{score.review.judge.source_key}:{score.review.project.source_key}",
                {},
            )[score.criterion.key] = score.value

        checked = 0
        for row in rows[1:]:
            record = expected.get(row[0])
            assert record is not None, f"unknown review {row[0]!r} in the export"
            for index, key in enumerate(criteria):
                cell = row[len(row) - len(criteria) + index]
                want = record.get(key)
                assert cell == ("" if want is None else str(want)), (
                    f"review {row[0]!r}, column {key!r}: exported {cell!r}, database says {want!r}"
                )
            checked += 1
        assert checked == 126, f"checked {checked} rows, expected 126"

        assert User.objects.filter(email=identities["organizer"].email).exists()

    def test_a_judge_is_refused_the_export(self, identities, event):
        _assert_real_refusal(
            _client_for(identities["judge_a"].email).get(reverse("csv_export")),
            api_module.REFUSED_BY_EXPORT,
        )

    def test_a_participant_is_refused_the_export(self, identities, event):
        _assert_real_refusal(
            _client_for(identities["participant"].email).get(reverse("csv_export")),
            api_module.REFUSED_BY_EXPORT,
        )

    def test_the_export_is_reached_through_the_scoped_accessor(self, identities, event):
        """D-01. The export must not be a second, unscoped path to every score.

        Asserted on the source rather than on behaviour, because the behaviour
        is identical for the organizer either way -- which is exactly why an
        unscoped export would ship unnoticed. ``tools/check_isolation.py`` (JJ01)
        is the gate that catches it in every file including this one.
        """
        source = (REPO / "src" / "reviewer" / "reviews" / "api.py").read_text(encoding="utf-8")
        assert "Review.objects.for_actor(actor)" in source
        assert "Review.objects.all()" not in source
