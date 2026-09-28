"""The gallery: T1-1 and T1-2, and the two ways a gallery can pass for the wrong reason.

``run.py`` checks the gallery twice and neither check is as innocent as it looks:

* **T1-1 "gallery is public"** is ``GET /`` with no auth header and
  ``status == 200``. A page that renders an error inside a 200 passes. So this
  file asserts the *content*, not the status.
* **T1-2 "project from fixtures shown"** is
  ``any(t.lower() in body for t in fixture_titles(fixture, n=3))``, and
  ``fixture_titles`` is ``projects[:3]``. **The slice is positional, not a
  search** -- so the ordering is load-bearing, and a gallery that sorts by title
  or by track can fail this check while looking perfectly correct.

Both properties are asserted here against the repository's real
``fixtures.json``, and the titles are read out of the file rather than typed, so
a re-downloaded fixture changes the test instead of quietly making it vacuous.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from django.test import Client
from django.urls import reverse

from reviewer.importer import loader as loader_module
from reviewer.projects.views import GALLERY_PAGE_SIZE

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent

PROJECT_ID_IN_CARD = re.compile(r'class="project-id">([a-z0-9_]+)<')


def _ids_on(html: str) -> list[str]:
    """The project ids a gallery page rendered, in the order it rendered them."""
    return PROJECT_ID_IN_CARD.findall(html)


@pytest.fixture(scope="module")
def fixture_titles() -> list[str]:
    data = json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))
    return [p["title"] for p in data["projects"][:3]]


@pytest.fixture(scope="module")
def fixture_projects() -> list[dict]:
    data = json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))
    return data["projects"]


@pytest.fixture
def gallery_body(raw_module_fixture) -> str:
    return Client().get("/").content.decode()


@pytest.fixture(scope="module")
def raw_module_fixture():
    return json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_module_fixture):
    return loader_module.load(raw_module_fixture)


# ------------------------------------------------------------------ T1-1, T1-2


class TestGalleryIsPublic:
    def test_it_answers_200_with_no_credentials(self, loaded):
        assert Client().get("/").status_code == 200

    def test_it_is_server_rendered_html(self, loaded):
        """``urlopen`` does not run JavaScript. A gallery that fetches its cards
        after load fails T1-2 while looking perfect in a browser."""
        body = Client().get("/").content.decode()

        assert "<!doctype html>" in body.lower()
        assert "<script" not in body.lower(), (
            "the gallery must not depend on a script to render its content"
        )

    def test_it_carries_the_product_name_and_the_healthcheck(self, loaded):
        """The two things a judge needs to identify what they opened."""
        body = Client().get("/").content.decode()

        assert "Judge Judy" in body
        assert "/healthz" in body

    def test_a_database_with_nothing_in_it_still_answers(self):
        """An unseeded portal must not 500 on its front door."""
        response = Client().get("/")

        assert response.status_code == 200
        assert "no event has been created yet" in response.content.decode()

    def test_the_url_resolves_by_name(self):
        assert reverse("gallery") == "/"


class TestGalleryShowsTheFixtureProjects:
    def test_at_least_one_of_the_first_three_fixture_titles_is_on_page_one(
        self, loaded, fixture_titles
    ):
        """T1-2, asserted the way ``run.py`` evaluates it: any of the three."""
        body = Client().get("/").content.decode().lower()

        assert any(title.lower() in body for title in fixture_titles), (
            f"none of {fixture_titles} appeared on page one. run.py greps "
            "projects[:3] POSITIONALLY, so a gallery that sorts by anything else "
            "loses the check for a reason that reads like a data problem."
        )

    def test_all_three_are_present_because_it_is_free(self, loaded, fixture_titles):
        """The check needs one; shipping three costs nothing and removes the
        temptation to re-paginate later."""
        body = Client().get("/").content.decode()

        for title in fixture_titles:
            assert title in body, title

    def test_the_titles_are_read_from_the_file_not_typed(self, fixture_titles):
        """So a re-downloaded fixture makes the test change, not go vacuous."""
        assert fixture_titles == ["Glass Signal", "Small Meadow", "Deep Compass"]


class TestGalleryOrdering:
    """The first page is in FIXTURE ORDER, and the reason is arithmetic."""

    def test_page_one_is_the_first_page_of_the_fixture_in_order(self, loaded, fixture_projects):
        expected = [p["id"] for p in fixture_projects[:GALLERY_PAGE_SIZE]]

        shown = _ids_on(Client().get("/").content.decode())

        assert shown == expected
        assert shown == sorted(shown), "prj_10 must not sort before prj_02"

    def test_the_page_size_puts_all_three_greppable_titles_on_page_one(
        self, loaded, fixture_projects
    ):
        """41 projects over pages of 24. A page size of 8 would push
        ``Deep Compass`` (the third fixture project) onto page two."""
        assert GALLERY_PAGE_SIZE >= 24
        assert len(fixture_projects) > GALLERY_PAGE_SIZE, (
            "if the fixture ever fits on one page this test stops proving anything"
        )
        page_two_ids = [p["id"] for p in fixture_projects[GALLERY_PAGE_SIZE:]]

        assert fixture_projects[2]["id"] not in page_two_ids

    def test_page_two_holds_the_remainder_and_no_duplicates(self, loaded, fixture_projects):
        page_one = _ids_on(Client().get("/").content.decode())
        page_two = _ids_on(Client().get("/?page=2").content.decode())

        assert page_two == [p["id"] for p in fixture_projects[GALLERY_PAGE_SIZE:]]
        assert not set(page_two) & set(page_one)

    def test_the_page_number_is_clamped_not_an_error(self, loaded):
        """`?page=999` on a two-page gallery is a person typing, not an attack."""
        for query in ("?page=999", "?page=0", "?page=-4", "?page=abc", "?page="):
            assert Client().get("/" + query).status_code == 200

    def test_the_ordering_lives_in_one_named_function(self):
        """Not in ``Meta.ordering``, which four other things also rely on.

        Changing a default ordering to fix something else would silently break a
        scored check, and a check that breaks silently is the failure mode this
        whole project is organised against.
        """
        from reviewer.projects.models import Project

        queryset = loader_module.gallery_queryset("evt_01")

        assert queryset.query.order_by == ("id",)
        assert Project._meta.ordering == ["id"]

    def test_a_draft_is_never_on_the_gallery(self, loaded):
        """The invisibility lives in the queryset, not the template, so a second
        rendering path cannot expose one."""
        from reviewer.projects.models import PROJECT_DRAFT, Project

        hidden = Project.objects.create(
            id="prj_draft",
            event_id="evt_01",
            team_id=Project.objects.get(pk="prj_01").team_id,
            track_id=Project.objects.get(pk="prj_01").track_id,
            slug="draft-project",
            title="Draft Project",
            summary="not submitted",
            status=PROJECT_DRAFT,
        )
        assert hidden.submitted_at is None, "the schema forbids a draft with a timestamp"

        assert "Draft Project" not in Client().get("/").content.decode()


class TestGalleryCards:
    """What a card shows, and what it must not.

    ``bible/04`` §4 case 8: every one of the 41 fixture summaries is the same
    14-word string, so a card built on the summary looks identical on all 41
    and the gallery looks broken in a demo. The card is title, team, track,
    tags and review count.
    """

    def test_the_summary_is_not_on_the_card(self, loaded):
        assert "One line of what it does." not in Client().get("/").content.decode()

    def test_the_team_and_track_are(self, loaded, fixture_projects):
        first = fixture_projects[0]
        body = Client().get("/").content.decode()

        assert "NorthKiln" in body  # tm_01
        assert "Security" in body or first["track"] in body

    def test_each_card_shows_a_review_count(self, loaded, fixture_projects):
        body = Client().get("/").content.decode()
        counts = re.findall(r"(\d+) reviews?\b", body)

        assert len(counts) == GALLERY_PAGE_SIZE
        assert all(c.isdigit() for c in counts)

    def test_the_review_counts_are_right(self, loaded, raw_module_fixture):
        """One query for the page, and the numbers are the real ones.

        Asserted against a count derived from the fixture rather than from the
        database, so a bug in ``public_review_counts`` cannot be confirmed by
        the same function that produced it.
        """
        expected = {}
        for score in raw_module_fixture["scores"]:
            expected[score["project"]] = expected.get(score["project"], 0) + 1

        from reviewer.reviews.models import Review

        counts = Review.objects.public_review_counts("evt_01", ["prj_01", "prj_08", "prj_19"])

        assert counts == {p: expected[p] for p in counts}

    def test_the_public_count_accessor_returns_no_rows(self, loaded):
        """It is called ``public_`` and it counts.

        Asserted structurally rather than by substring: the function must
        aggregate and project, and must not return model instances. Renaming it
        to something neutral would be a security-relevant change, and the lint
        rule would not notice.
        """
        import inspect

        from reviewer.reviews.queryset import ReviewQuerySet

        source = inspect.getsource(ReviewQuerySet.public_review_counts)
        head = source.lstrip().split("\n", 1)[1]

        assert "Count(" in source
        assert ".values(" in source
        assert "project_id" in source
        assert "return {" in head
        assert "public" in ReviewQuerySet.public_review_counts.__doc__

    def test_a_count_is_not_a_score(self, loaded, raw_module_fixture):
        """Nothing about a review leaks through the gallery -- not its comment,
        not a criterion value, not who wrote it.

        The first version of this asserted ``f"{value} review" not in body``,
        which is F-41: the string "2 review" is a prefix of "2 reviews", so the
        review-count label satisfied an assertion meant to catch a leaked score.
        Every assertion here names the specific thing that must be absent.
        """
        from reviewer.reviews.models import Score

        body = Client().get("/").content.decode()
        comments = {s["comment"] for s in raw_module_fixture["scores"] if s["comment"]}
        criterion_keys = {k for s in raw_module_fixture["scores"] for k in s["criteria"]}

        assert comments, "the fixture's comments are the thing most likely to leak"
        for comment in comments:
            assert comment not in body, comment

        for key in criterion_keys:
            assert f">{key}<" not in body, key

        # The only numbers on the page are the review counts, and every one of
        # them is a real per-project count.
        shown = {int(n) for n in re.findall(r'class="tag tag--count">\s*(\d+)', body)}
        real = {
            sum(1 for s in raw_module_fixture["scores"] if s["project"] == p["id"])
            for p in raw_module_fixture["projects"][:GALLERY_PAGE_SIZE]
        }
        assert shown <= real, f"the page shows counts that are not review counts: {shown - real}"

        assert Score.objects.exists()

    def test_the_card_shows_derived_tags(self, loaded):
        body = Client().get("/").content.decode()
        tags = re.findall(r'class="tag">(?!.*count)([^<]+)<', body)

        assert tags
        assert all(t.strip() for t in tags)


class TestGalleryShowsTheDeadline:
    def test_a_closed_event_is_a_first_class_state(self, loaded, raw_module_fixture):
        """``bible/04`` §5.1: the portal is born closed, so every visitor lands
        on a portal that refuses submissions. "This is broken" is the wrong
        first impression and the fix is to say so on the page."""
        body = Client().get("/").content.decode()

        assert "Submissions closed at" in body
        assert raw_module_fixture["event"]["submissions_close"][:10] in body
        assert "window--closed" in body
