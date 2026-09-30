"""The embeddable widget: self-contained, escaped, and refusing until published.

**The acceptance criterion is "the widget renders offline", and the whole file is
arranged around making that mean something.** Not "loads while the server is up" --
the portal is a server, so that would be trivially true and worth nothing. It means
the document reaches the browser having requested *nothing*: no CDN, no font host,
no stylesheet link, no script src, no favicon, no external image.

So the central test asserts the **absence** of each of those, because a document
that renders offline until somebody adds a webfont is a document that renders
online. And the escaping tests put a hostile project title into the database rather
than trusting the reviewer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from reviewer.widget import build

pytestmark = pytest.mark.django_db


@pytest.fixture
def raw_fixture():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture):
    from reviewer.events.models import Event
    from reviewer.importer import loader as loader_module

    loader_module.load(raw_fixture)
    return Event.objects.get(pk="evt_01")


def _publish(event) -> None:
    event.results_state = "published"
    event.save(update_fields=["results_state"])


@pytest.fixture
def published(loaded):
    _publish(loaded)
    return loaded


def _get(client, path):
    response = client.get(path)
    return response, response.content.decode("utf-8")


class TestItRendersOffline:
    """The acceptance line. Absence, not presence."""

    def test_the_document_references_nothing_off_the_machine(self, client, published):
        _publish(published)
        response, html = _get(client, "/widget/results/")

        assert response.status_code == 200
        assert "<script" not in html.lower(), "a script tag is a dependency waiting to happen"
        assert "<link" not in html.lower(), "a stylesheet link is a network request"
        assert "<img" not in html.lower(), "an image is a network request"
        assert "@import" not in html.lower()
        assert "http://" not in html
        assert "https://" not in html
        assert "//cdn" not in html

    def test_no_external_reference_survives_in_the_css_either(self, client, published):
        """The stylesheet is inlined, so a ``url()`` inside it would be the one
        external reference a tag-scanning test would miss."""
        _publish(published)
        _, html = _get(client, "/widget/results/")
        for block in re.findall(r"<style>(.*?)</style>", html, re.S):
            assert "url(" not in block, f"the inlined CSS fetches something: {block[:80]}"

    def test_the_ranking_actually_appears_in_the_bytes(self, client, published):
        """**The other half, and the one a "no external references" test misses.**

        A document with no network dependencies that renders an empty table is
        offline and useless. So the rows have to be in the HTML, not fetched after
        load.
        """
        _publish(published)
        _response, html = _get(client, "/widget/results/")

        from reviewer.projects.models import Project

        titles = list(Project.objects.order_by("source_key").values_list("title", flat=True))
        present = [t for t in titles if t in html]
        assert len(present) >= 30, (
            f"only {len(present)} of {len(titles)} projects are in the document"
        )
        assert "<tbody>" in html and html.count("<tr>") > 30

    def test_it_needs_no_javascript_to_be_read(self, client, published):
        _publish(published)
        _, html = _get(client, "/widget/results/")
        assert "onerror" not in html.lower()
        assert "<noscript>" not in html.lower(), "a table does not need a noscript branch"


class TestItIsSelfContained:
    def test_it_has_no_site_chrome_to_paste_around(self, client, published):
        """It goes in somebody else's iframe, so a site header would be a bug."""
        _publish(published)
        _, html = _get(client, "/widget/results/")
        for chrome in ("<nav", "Judge Judy</a>", "footer class=", "Sign in"):
            assert chrome not in html, f"the widget carries site chrome: {chrome}"

    def test_it_is_a_complete_document(self, client, published):
        _publish(published)
        _, html = _get(client, "/widget/results/")
        assert html.startswith("<!DOCTYPE html>")
        assert '<meta charset="utf-8">' in html
        assert "</html>" in html

    def test_the_json_half_agrees_with_the_html_half(self, client, published):
        """Two renderings of one ranking is a liability -- F-84 and F-89 were both
        exactly that, two shipped artefacts answering one question differently. The
        widget's HTML and JSON are the third, so they are compared."""
        _publish(published)
        _, html = _get(client, "/widget/results/")
        response, _ = _get(client, "/widget/results.json")
        payload = json.loads(response.content)

        assert payload["rows"]
        for row in payload["rows"]:
            assert row["title"] in html
        assert str(len(payload["rows"])) in html


class TestItSaysHowTheRankingWasComputed:
    """On the document, because a widget is read by people who never see the portal."""

    def test_the_label_is_on_the_page_and_in_the_data(self, client, published):
        _publish(published)
        from reviewer.reviews import results as results_module

        _, html = _get(client, "/widget/results/")
        response, _ = _get(client, "/widget/results.json")

        assert results_module.NORMALIZATION in html
        assert json.loads(response.content)["normalization"] == results_module.NORMALIZATION

    def test_the_footer_names_the_method_itself(self, client, published):
        """**Assert the FOOTER, not the string.**

        The first version of this test asserted ``NORMALIZATION in html`` and the
        mutation deleting the footer's copy reported NOT DETECTED -- because the
        same string also appears in the ``<p class="meta">`` line and on every
        row, so the assertion could not tell a labelled footer from an unlabelled
        one. *Three copies of a fact and one assertion about its presence* is the
        shape of F-84 exactly. So this one is scoped to the element.
        """
        _publish(published)
        from reviewer.reviews import results as results_module

        _, html = _get(client, "/widget/results/")
        footer = re.search(r"<footer>(.*?)</footer>", html, re.S)
        assert footer, "the document has no footer at all"
        assert results_module.NORMALIZATION in footer.group(1)
        assert "Ranking:" in footer.group(1)

    def test_every_row_carries_it_too(self, client, published):
        _publish(published)
        response, _ = _get(client, "/widget/results.json")
        rows = json.loads(response.content)["rows"]
        assert rows
        for row in rows:
            assert row["normalization"], "a row that does not say how it was computed"

    def test_it_carries_no_scores(self, client, published):
        """**A widget embedded in a sponsor's page is the least controlled surface in
        the system**, so what it carries is what we would publish anyway: standings,
        not per-judge numbers."""
        _response, raw = _get(client, "/widget/results.json")
        payload = json.loads(raw)
        for row in payload["rows"]:
            assert set(row) == {
                "rank",
                "project",
                "title",
                "track",
                "mean",
                "reviews_counted",
                "normalization",
            }


class TestItRefusesUntilPublished:
    def test_a_hidden_event_serves_a_bare_403(self, client, loaded):
        """Same refusal as everywhere else: status, empty body, no Location."""
        response = client.get("/widget/results/")
        assert response.status_code == 403
        assert response.content == b""
        assert "Location" not in response.headers

    def test_the_json_half_refuses_too(self, client, loaded):
        response = client.get("/widget/results.json")
        assert response.status_code == 403
        assert response.content == b""

    def test_publishing_opens_it_without_any_other_change(self, client, loaded):
        assert client.get("/widget/results/").status_code == 403
        _publish(loaded)
        assert client.get("/widget/results/").status_code == 200

    def test_it_is_public_because_an_embedder_holds_no_credential(self, client, published):
        """No login, no header, no session: an organizer pasting this into a sponsor
        page is not going to authenticate anyone."""
        _publish(published)
        response = client.get("/widget/results/")
        assert response.status_code == 200


class TestItEscapes:
    """A hostile title in the database, not an assumption about the reviewer."""

    @pytest.fixture
    def hostile(self, published):
        from reviewer.projects.models import Project

        project = Project.objects.order_by("source_key").first()
        project.title = '<img src=x onerror="alert(1)">Ampersand & "quote"'
        # **The track is hostile too, on purpose.** Every cell except the title
        # goes through `_cell`, so a payload in the title alone would never reach
        # the shared escaping path -- which is exactly how the first draft shipped
        # a second, untested copy of the escaping rule and the mutation harness
        # reported the `_cell` escape as NOT DETECTED.
        #
        # The track needs its OWN save: assigning to `project.track.slug` mutates
        # the related instance in memory, and `project.save()` persists the
        # Project, not the Track. The first version of this fixture did exactly
        # that and the payload silently never reached the page.
        track = project.track
        track.slug = 'dev" onmouseover="alert(2)'
        track.save()
        project.save()
        _publish(published)
        return project

    def test_the_title_is_escaped_not_rendered(self, client, hostile):
        """**Assert on the escaping, not on a substring's absence.**

        The first version of this test asserted ``"onerror=" not in html`` and it
        **failed against correctly escaped output**, where ``onerror=`` is inert
        text inside a ``<td>``. That is F-86's lesson and I walked into it anyway:
        *a test that asserts a substring is absent is asserting a proxy, and what
        a browser acts on is an element.* The sibling test below asserts the
        element; this one asserts the escaping.
        """
        _, html = _get(client, "/widget/results/")
        assert "&lt;img" in html, "the payload should appear escaped, not raw"
        assert "onerror=&quot;alert(1)&quot;" in html, "the quotes were not escaped either"
        assert "<img" not in html.lower(), "the payload became a live element"
        # The first draft also asserted no `="` survived in the body, which failed
        # on `<p class="meta">` and the `<meta>` tag -- our own markup, escaped
        # correctly. An assertion that trips on the template is an assertion about
        # the template, not about the payload.

    def test_the_shared_cell_path_escapes_too(self, client, hostile):
        """The other cell values go through ``_cell`` rather than the title's
        f-string, so the shared path needs its own hostile input. Without this the
        ``_cell`` escape could be deleted outright and the suite would stay green.
        """
        _, html = _get(client, "/widget/results/")
        assert "onmouseover=&quot;alert(2)" in html, "the track cell stopped escaping"
        assert "onmouseover=" not in html.replace("onmouseover=&quot;", "")

    def test_the_document_has_no_injected_element(self, client, hostile):
        _, html = _get(client, "/widget/results/")
        body = html.split("<body>", 1)[1]
        assert body.count("<tr>") == html.count("<tr>")
        assert "<img" not in html.lower()
        # The track payload would otherwise add a second attribute to the <td>.
        assert html.count("onmouseover") == html.count("onmouseover=&quot;")

    def test_the_json_half_is_json_even_then(self, client, hostile):
        response, _ = _get(client, "/widget/results.json")
        payload = json.loads(response.content)  # would raise if the value broke it
        assert any("onerror" in row["title"] for row in payload["rows"])


class TestTheBuilderInIsolation:
    def test_a_row_with_no_mean_renders_a_dash_not_a_crash(self):
        payload = {
            "event": "evt_01",
            "event_name": "Edge",
            "results_state": "published",
            "normalization": "unnormalized-raw-weighted-mean",
            "rows": [
                {
                    "rank": 1,
                    "project": "prj_01",
                    "title": "No scores yet",
                    "track": "t",
                    "mean": None,
                    "reviews_counted": 0,
                    "normalization": "unnormalized-raw-weighted-mean",
                }
            ],
        }
        html = build.build_document(payload)
        assert ">" in html
        assert "-" in html

    def test_the_document_is_byte_stable_for_one_payload(self, published):
        """The JSON carries a generation timestamp and the HTML does not, so this
        asserts the HTML half specifically -- a widget an organizer re-saves should
        not churn."""
        from reviewer.isolation import Actor

        payload = build.widget_payload(published, Actor.anonymous(published))
        assert build.build_document(payload) == build.build_document(payload)
