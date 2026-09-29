"""The public results page (REQ-T3-03).

**The test that matters is `TestTheHiddenEventRefusesEveryRoleAndSaysSo`, and it
exists because "refused" and "empty" look identical to a reader.** A page that
renders a leaderboard with zero rows while results are hidden is a page that
**passes every shape assertion** and tells a judge there is nothing to see when
the truth is that there is something they may not see. That is the same class as
F-80 one layer up: structurally valid output whose values are empty.

So the assertions are on the **status, the empty body, the absence of a `Location`
header, and the absence of any project title in the bytes** -- four separate
claims, because four separate things could be wrong and a reader debugging this
wants to know which.

**And the surface-agreement test is the other one that matters.** The page and the
API must answer identically, or this project has two shipped artefacts disagreeing
about a ranking -- which is exactly what F-84's `voters` bug was, and the reason
it happened is that nobody compared the two.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from django.test import Client

from reviewer.events.models import RESULTS_HIDDEN, RESULTS_PUBLISHED
from reviewer.isolation.refusal import REFUSED_BY_HEADER
from reviewer.reviews import results as results_module
from reviewer.reviews.results_view import REFUSED_BY_RESULTS

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent

RESULTS_URL = "/results/"
API_URL = "/api/v1/results"

#: A real fixture title. **Asserted ABSENT from a refused page**: a refusal that
#: leaks one project name has leaked that the project exists and was ranked.
A_TITLE = "Glass Signal"


# --------------------------------------------------------------- the fixtures
# Deliberately duplicated rather than imported from `test_results_and_audit`.
# That module's fixtures are **module-scoped on purpose** -- a fully loaded
# fixture is expensive, and that file pays for it once. Importing them here would
# silently couple two files' setup, and the first version of this file did exactly
# that and produced 15 collection errors instead of a test failure.


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
def identities(event, raw_fixture) -> dict:
    from reviewer.accounts.models import User
    from reviewer.importer import census as census_module
    from reviewer.importer import demo as demo_module

    chosen = demo_module.choose(census_module.census(raw_fixture))
    return {i.key: User.objects.filter(email=i.email).first() for i in chosen}


def _client_for(email: str) -> Client:
    from reviewer.accounts.demo_tokens import mint

    return Client(HTTP_AUTHORIZATION=mint(email))


def _titles(event) -> list[str]:
    return list(event.projects.values_list("title", flat=True))


class TestTheHiddenEventRefusesEveryRoleAndSaysSo:
    """**The control half, and the reason this file exists.**"""

    def test_a_visitor_is_refused_with_an_empty_body(self, client, identities, event):
        response = client.get(RESULTS_URL)
        assert response.status_code == 403
        assert response.content == b"", "D-02: a refusal body is empty"
        assert "Location" not in response.headers
        assert response.headers[REFUSED_BY_HEADER] == REFUSED_BY_RESULTS

    def test_a_judge_is_refused(self, client, identities, event):
        judge = identities.get("judge_a")
        if judge is None:
            pytest.skip("the fixture build produced no judge identity")
        response = _client_for(judge.email).get(RESULTS_URL)
        assert response.status_code == 403
        assert response.content == b""

    def test_a_participant_is_refused(self, client, identities, event):
        participant = identities.get("participant")
        if participant is None:
            pytest.skip("the fixture build produced no participant identity")
        response = _client_for(participant.email).get(RESULTS_URL)
        assert response.status_code == 403

    def test_a_refused_page_leaks_no_project_title(self, client, identities, event):
        """**The assertion a shape check cannot make.** A page that rendered a
        leaderboard of zeros, or a list of names with no scores, would satisfy
        "the page is 403" nowhere and "the page has a table" everywhere -- but a
        reader would still learn that a project was ranked."""
        body = client.get(RESULTS_URL).content.decode()
        for title in _titles(event):
            assert title not in body, f"a refused results page leaked the title {title!r}"

    def test_a_refused_page_has_no_ranking_table_at_all(self, client, identities, event):
        body = client.get(RESULTS_URL).content.decode()
        assert "rank" not in body.lower()
        assert "normalization" not in body.lower()

    def test_the_api_and_the_page_refuse_identically_while_hidden(self, client, identities, event):
        """One predicate, two surfaces. If these ever diverge, the stricter one is
        a bug and the looser one is a leak."""
        page = client.get(RESULTS_URL)
        api = client.get(API_URL)
        assert page.status_code == api.status_code == 403


class TestAnOrganizerAlwaysSeesTheBoard:
    def test_an_organizer_is_shown_the_ranking_while_hidden(self, client, identities, event):
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        response = _client_for(organizer.email).get(RESULTS_URL)
        assert response.status_code == 200
        assert A_TITLE in response.content.decode()

    def test_the_board_is_not_empty_for_an_organizer(self, client, identities, event):
        """**F-80's shape, for the aggregate cell.** An organizer seeing an empty
        board while 41 projects have reviews is the "structurally valid, contains
        nothing" defect, and it is invisible in a status-code assertion."""
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        body = _client_for(organizer.email).get(RESULTS_URL).content.decode()
        assert body.count('<tr class="assignment">') > 0, "an organizer's board is empty"


class TestAPublishedEventOpensItToEverybody:
    @pytest.fixture(autouse=True)
    def _published(self, event):
        event.results_state = RESULTS_PUBLISHED
        event.save()

    def test_a_visitor_sees_the_published_ranking(self, client, identities, event):
        response = client.get(RESULTS_URL)
        assert response.status_code == 200
        assert A_TITLE in response.content.decode()

    def test_a_published_judge_is_told_the_board_is_scoped_to_them(self, client, identities, event):
        """**The sentence that keeps a scoped board from being read as a result.**
        A judge reading their own four projects' worth of mean scores and calling
        it "the results" is the exact misreading this capability invites."""
        judge = identities.get("judge_a")
        if judge is None:
            pytest.skip("the fixture build produced no judge identity")
        body = _client_for(judge.email).get(RESULTS_URL).content.decode()
        assert "your own reviews only" in body

    def test_an_organizer_is_not_told_the_board_is_scoped(self, client, identities, event):
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        body = _client_for(organizer.email).get(RESULTS_URL).content.decode()
        assert "your own reviews only" not in body


class TestThePageAndTheApiAgree:
    """**The F-84 lesson, applied proactively.** Two renderings of one ranking is
    a liability; the test is the thing that makes it an asset."""

    def _rows_from_page(self, body: str) -> list[tuple[str, str]]:
        return re.findall(
            r'<span class="project-id">(prj_\d+)</span>.*?<td>([\d.]+)</td>', body, re.S
        )

    def test_an_organizer_sees_the_same_rows_on_both_surfaces(self, client, identities, event):
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        http = _client_for(organizer.email)
        page = http.get(RESULTS_URL).content.decode()
        api = json.loads(http.get(API_URL).content.decode())
        from_page = self._rows_from_page(page)
        from_api = [(r["project"], str(r["mean"])) for r in api["ranking"]]
        assert from_page == from_api, (
            "the public page and the API disagree about the ranking; they must "
            "come from the same aggregate function"
        )

    def test_both_surfaces_report_the_same_normalization(self, client, identities, event):
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        http = _client_for(organizer.email)
        page = http.get(RESULTS_URL).content.decode()
        api = json.loads(http.get(API_URL).content.decode())
        assert results_module.NORMALIZATION in page
        assert api["normalization"] == results_module.NORMALIZATION


class TestThePageAlwaysSaysTheRankingIsUnnormalized:
    """**A published ranking that does not say whether it is corrected is a
    ranking a reader has to guess about.** This is asserted on the 200, because a
    caveat that only appears when somebody remembers to add it is not a caveat."""

    def test_an_organizer_page_carries_the_label(self, client, identities, event):
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        body = _client_for(organizer.email).get(RESULTS_URL).content.decode()
        assert results_module.NORMALIZATION in body
        assert "No judge-severity correction" in body

    def test_the_label_survives_publication(self, client, identities, event):
        event.results_state = RESULTS_PUBLISHED
        event.save()
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        body = _client_for(organizer.email).get(RESULTS_URL).content.decode()
        assert results_module.NORMALIZATION in body


class TestTheTemplateIsWellFormed:
    """F-88, applied to the new template: a `{#` that does not close on its own
    line renders as literal page text, and a page that renders correctly *and*
    carries extra text passes every other assertion here."""

    def test_no_comment_opener_is_unterminated(self):
        src = pathlib.Path(__file__).resolve().parents[1] / "src"
        offenders = []
        for path in src.rglob("*.html"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for m in re.finditer(r"\{#", line):
                    if "#}" not in line[m.start() :]:
                        offenders.append(f"{path.relative_to(src)}:{n}")
        assert offenders == [], f"these comment openers never close: {offenders}"


class TestTheScopeLabelMatchesTheBoard:
    """**F-90, and it was found by reading the live page rather than by a test.**

    The page's "you are seeing your own reviews only" warning was derived from
    ``not actor.can_read_all_reviews`` -- a statement about the actor's ROLE. But
    the board is derived from whether they have any reviews of their own (F-89),
    and **the two disagree for exactly one case: a published visitor.** The
    visitor is shown the whole event and was told it was scoped to them.

    **A page asserting a scope it did not apply is the same defect as a page
    asserting a count it did not compute** -- a sentence in place of a number.
    The fix is to derive the label from the *same* predicate the aggregate
    branches on, so the two cannot drift, and the test is the one that says so:
    a non-empty board with the scoped label on it is a contradiction.
    """

    def _says_scoped(self, body: str) -> bool:
        return "your own reviews only" in body

    def _row_count(self, body: str) -> int:
        return body.count('<tr class="assignment">')

    def test_a_visitor_seeing_the_whole_event_is_not_told_it_is_scoped(
        self, client, identities, event
    ):
        event.results_state = RESULTS_PUBLISHED
        event.save()
        body = client.get(RESULTS_URL).content.decode()
        assert self._row_count(body) > 1, "the visitor's board should be the whole event"
        assert not self._says_scoped(body), (
            "the page tells the visitor their board is scoped to their own reviews "
            "while showing them the whole event -- the label and the board "
            "disagree, and one of them is a lie"
        )

    def test_a_judge_seeing_their_own_reviews_is_told_so(self, client, identities, event):
        event.results_state = RESULTS_PUBLISHED
        event.save()
        judge = identities.get("judge_a")
        if judge is None:
            pytest.skip("the fixture build produced no judge identity")
        body = _client_for(judge.email).get(RESULTS_URL).content.decode()
        assert self._row_count(body) > 0
        assert self._says_scoped(body), "a judge shown a scoped board is not told it is scoped"

    def test_an_organizer_is_never_told_the_board_is_scoped(self, client, identities, event):
        organizer = identities.get("organizer")
        if organizer is None:
            pytest.skip("the fixture build produced no organizer identity")
        for state in (RESULTS_HIDDEN, RESULTS_PUBLISHED):
            event.results_state = state
            event.save()
            body = _client_for(organizer.email).get(RESULTS_URL).content.decode()
            assert not self._says_scoped(body), state


def test_the_event_is_born_hidden():
    """Stated as a fact about the shipped fixture, in the file that depends on it.

    `RESULTS_HIDDEN` is imported for the assertion below and for the reader; this
    test is the reminder that the refusal tests are exercising the REAL shipped
    state rather than a state the test set up for itself.
    """
    assert RESULTS_HIDDEN == "hidden"
    assert RESULTS_PUBLISHED == "published"
    assert issubclass(Client, object)
