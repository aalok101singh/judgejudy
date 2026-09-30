"""The OpenAPI document must describe the API that is actually running.

**The failure mode this file exists for is not a crash.** It is a committed
`openapi.yaml` that parses, is served, and omits an endpoint -- which is what the
introspector produced when the API was plain Django views: `paths: {}`, a valid
document describing nothing. So every test here compares the document against
`urls.py`, and the generator refuses rather than emitting a partial one.

Three directions, because each fails differently:

* a route exists and is **undocumented** -- a client will 404 on it;
* a route is documented and **no longer exists** -- the document describes an
  endpoint nobody can call, which is worse than silence;
* a documented response **lies** about its body.
"""

from __future__ import annotations

import pytest

from reviewer.api import schema

pytestmark = pytest.mark.django_db


class TestTheDocumentMatchesTheApplication:
    def test_every_api_route_is_documented(self):
        """``urls.py`` is the truth about what exists; this is the truth about what
        is documented; the gap between them is the bug."""
        assert schema.undocumented_routes() == set(), (
            "these routes are served but absent from documents.PATHS"
        )

    def test_no_declaration_outlives_its_route(self):
        """A renamed route leaves its declaration behind, and the document then
        advertises an endpoint that 404s."""
        assert schema.stale_declarations() == set()

    def test_the_route_list_is_read_from_the_urlconf_not_transcribed(self):
        """A hand-written list of endpoints goes stale silently, which is the only
        way a list ever goes stale. So this asserts the reader finds the routes at
        all -- if the URLconf walk stopped working, everything above would pass by
        finding nothing to complain about."""
        registered = schema._registered_paths()
        assert len(registered) >= 5, f"only found {registered}; the URLconf walk is broken"

    def test_the_generator_refuses_rather_than_emitting_a_partial_document(self, monkeypatch):
        """**The property that makes the other three worth having.** A generator
        that quietly omits is the bug; a generator that stops is the fix."""
        import reviewer.api.documents as documents

        monkeypatch.setitem(documents.PATHS, "/api/v1/results", documents.RESULTS)
        monkeypatch.setattr(
            schema, "declared_paths", lambda: set(documents.PATHS) - {"/api/v1/results"}
        )
        with pytest.raises(RuntimeError) as excinfo:
            schema.build_schema()
        assert "/api/v1/results" in str(excinfo.value)

    def test_the_generator_refuses_a_declaration_for_a_route_that_is_gone(self, monkeypatch):
        """**The mutation harness reported this NOT DETECTED, and it was right.**

        There was a test for `stale_declarations()` -- the *helper* -- and none for
        the refusal it exists to produce, which lives two lines away inside
        `build_schema`. So the helper was pinned and the behaviour was not.

        Identical in shape to the one-payload guard in `tests/test_signing.py`: a
        predicate that is tested and an action it drives that is not. **A predicate
        is worth testing for what it causes.**
        """
        import reviewer.api.documents as documents

        monkeypatch.setattr(
            schema,
            "declared_paths",
            lambda: set(documents.PATHS) | {"/api/v1/removed-by-a-rename"},
        )
        with pytest.raises(RuntimeError) as excinfo:
            schema.build_schema()
        assert "/api/v1/removed-by-a-rename" in str(excinfo.value)
        assert "no longer exist" in str(excinfo.value)


class TestTheDocumentIsWellFormed:
    def test_it_parses_as_the_openapi_version_we_claim(self):
        parsed = schema.api_paths()
        assert parsed["openapi"] == "3.1.0"
        assert parsed["info"]["title"]
        assert parsed["info"]["version"]

    def test_every_operation_declares_both_a_success_and_a_refusal(self):
        """**An endpoint that can refuse must say so.** The 403 is the product; a
        document that only describes the happy path describes a portal that leaks.
        """
        parsed = schema.api_paths()
        for path, operations in parsed["paths"].items():
            for method, operation in operations.items():
                codes = set(operation["responses"])
                assert "200" in codes, f"{method} {path} has no documented success"
                assert "403" in codes, f"{method} {path} does not document its refusal"

    def test_a_refusal_is_declared_with_an_empty_body(self):
        """Not described as an error *object*. A client generator that sees a schema
        will emit a branch that parses a body which is not there."""
        parsed = schema.api_paths()
        for path, operations in parsed["paths"].items():
            for method, operation in operations.items():
                refusal = operation["responses"]["403"]
                assert refusal["content"] == {}, (
                    f"{method} {path} describes a refusal body that does not exist"
                )

    def test_the_refusal_text_says_why_it_is_not_a_redirect(self):
        """The single most important sentence in this API, in every refusal."""
        parsed = schema.api_paths()
        for operations in parsed["paths"].values():
            for operation in operations.values():
                text = operation["responses"]["403"]["description"]
                assert "302" in text, "the refusal must explain why it is not a redirect"

    def test_every_operation_says_how_the_ranking_was_computed(self):
        """`normalization` is in the results schema and in the prose, because a
        ranking that does not say how it was computed is one a reader guesses at."""
        parsed = schema.api_paths()
        results = parsed["paths"]["/api/v1/results"]["get"]
        schema_json = results["responses"]["200"]["content"]["application/json"]["schema"]
        assert "normalization" in schema_json["properties"]
        assert "unnormalized-raw-weighted-mean" in results["description"]


class TestTheDocumentIsRegenerable:
    def test_generating_twice_produces_identical_bytes(self):
        """**A generated file whose diff is never empty is a file nobody reads**,
        and the committed copy is only trustworthy if regeneration is a no-op."""
        assert schema.document() == schema.document()

    def test_the_committed_copy_matches_what_the_generator_produces(self):
        from pathlib import Path

        committed = Path(schema.__file__).resolve().parents[3] / "openapi.yaml"
        assert committed.exists(), "openapi.yaml is not committed"
        assert committed.read_text(encoding="utf-8") == schema.document(), (
            "openapi.yaml is out of date. Run `just schema` and commit the result."
        )

    def test_the_command_check_mode_agrees(self):
        from django.core.management import call_command

        call_command("build_openapi", "--check")

    def test_the_command_lists_exactly_the_documented_paths(self, capsys):
        from django.core.management import call_command

        call_command("build_openapi")
        out = capsys.readouterr().out
        assert "5 paths" in out
        for path in schema.declared_paths():
            assert path in out


class TestTheIsolationStorySurvivesTheIntrospection:
    def test_the_views_are_still_plain_django_views(self):
        """**The reason this document is hand-assembled, asserted so it stays true.**

        drf-spectacular's generator enumerates DRF views. Wrapping these in
        `@api_view` to satisfy it would put DRF's authentication back in front of
        a middleware-assigned `request.user` -- and then three of the four T2 checks
        would get a **false pass instead of a 403**, which is the worst available
        outcome for an isolation feature.
        """
        from rest_framework.views import APIView

        from reviewer.reviews import api as api_views

        for name in ("judge_scores", "csv_export", "results", "audit", "influence"):
            view = getattr(api_views, name)
            assert not isinstance(view, type) or not issubclass(view, APIView), (
                f"{name} became a DRF view; DRF populates request.user from its own "
                "authentication classes and would defeat the credential middleware"
            )
            assert hasattr(view, "__wrapped__") or view.__name__ == name
