"""OpenAPI 3.1 declarations for the JSON API, which is **plain Django views**.

**Why these are declarations and not serializers.** ``reviewer/reviews/api.py``
explains at length why the API is not a DRF viewset: DRF populates
``request.user`` from its own authentication classes and would ignore the
``request.user`` our credential middleware assigns, so every header-only request
would arrive anonymous -- and three of the four T2 checks want a 403. That is a
**false pass, not a red check**, which is the worst available outcome for an
isolation feature.

So the views stay plain, and each is annotated with ``@extend_schema(**documents.X)``
in ``reviews/api.py``. The prose lives here; the decorator sits on the function
drf-spectacular reads. ``tests/test_openapi.py`` asserts that **every**
``/api/v1/`` route in ``urls.py`` appears in the generated document, so a route
added without a description fails a test rather than shipping undocumented.

The refusal is in the document, because it is the point
------------------------------------------------------
**Every one of these endpoints can return a 403 with an empty body**, and that is
the load-bearing behaviour of the whole project: *isolation is a 403 with an empty
body. Never a 302.* ``run.py`` follows redirects, so a portal that "protects" a
score by bouncing to a login page returns 200 to the checker and looks correct in a
browser.

A reader integrating against this API needs to know a 403 will not parse, so each
operation declares its refusals with an **empty** content entry rather than an
error object. A document that quietly implied a JSON error body would be worse
than no document.

Responses are described precisely where the shape is a contract, and loosely where
it is a presentation decision. The leaderboard's ``normalization`` field is precise
and always present, because a ranking that does not say how it was computed is a
ranking a reader has to guess about.
"""

from __future__ import annotations

#: Appended to every 403 description. Written once because it is the same sentence
#: everywhere, and a refusal that is described three different ways in three
#: places is a refusal a client will get wrong.
_REFUSAL_NOTE = (
    "Refused. The response body is EMPTY and there is no Location header -- a "
    "redirect would return 200 to a client that follows one, which is why this "
    "is a 403 and not a 302."
)


def _refusal(description: str) -> dict:
    """A 403 whose body is empty.

    **``content: {}`` is the whole point.** An OpenAPI response with an empty
    ``content`` map tells a client generator that there is nothing to parse, which
    is true and which a hand-written description would not convey. A 403 here has
    no body and no ``Location`` header.
    """
    return {"description": f"{description} {_REFUSAL_NOTE}", "content": {}}


def _ok(description: str, schema: dict, media: str = "application/json") -> dict:
    """A 200, with the media type stated -- this API also serves ``text/csv``."""
    return {"description": description, "content": {media: {"schema": schema}}}


JUDGE_SCORES = dict(
    methods=["GET"],
    summary="A judge's own scores, and only their own",
    description=(
        "Returns the requesting judge's submitted scores. Any other judge, a "
        "participant and a visitor are refused. The scoping is a query-level "
        "guarantee (`for_actor`), not a filter applied after the rows are read, so "
        "there is no code path in which a peer's score reaches this response."
    ),
    responses={
        200: _ok(
            "The judge's own scores.",
            schema={
                "type": "object",
                "properties": {
                    "actor": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "nullable": True},
                            "roles": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "scores": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["actor", "scores"],
            },
        ),
        403: _refusal("This actor may not read scores."),
    },
    examples=[
        {
            "summary": "A refusal that carries a reason. Only some do.",
            "value": {"error": "refused", "refused_by": "role"},
        },
        {
            "summary": "Asking about a peer -- the case this endpoint exists for.",
            "value": {"error": "refused", "refused_by": "peer"},
        },
    ],
    tags=["T2", "isolation"],
)

CSV_EXPORT = dict(
    methods=["GET"],
    summary="Every review as CSV",
    description=(
        "The complete review export, carrying the natural key of every row so that "
        "an export can be imported again and round-trips byte-for-byte. Organizer "
        "only. Every exported cell is checked against the database by a test, "
        "because a structurally perfect export whose first column is empty once "
        "shipped here (F-69)."
    ),
    responses={
        200: _ok("text/csv.", {"type": "string"}, media="text/csv"),
        403: _refusal("This actor may not export reviews."),
    },
    tags=["T2", "export"],
)

RESULTS = dict(
    methods=["GET"],
    summary="The published ranking",
    description=(
        "The leaderboard, when this actor is allowed one. **Refused for everyone but "
        "an organizer until results are published** -- the same rule the public "
        "page enforces. Every row carries `normalization`, which is "
        "`unnormalized-raw-weighted-mean`: the shipped ranking is a raw weighted "
        "mean. The normalization engine was built and measured, and it is not "
        "applied because the measurement found no judge-severity effect to correct."
    ),
    responses={
        200: _ok(
            "The ranking.",
            schema={
                "type": "object",
                "properties": {
                    "actor": {"type": "object"},
                    "results_state": {"type": "string", "enum": ["hidden", "published"]},
                    "normalization": {
                        "type": "string",
                        "enum": ["unnormalized-raw-weighted-mean"],
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "rank": {"type": "integer"},
                                "project": {"type": "string"},
                                "title": {"type": "string"},
                                "mean": {"type": "number", "nullable": True},
                                "reviews_counted": {"type": "integer"},
                                "normalization": {"type": "string"},
                            },
                        },
                    },
                },
            },
        ),
        403: _refusal("Results are hidden, or this actor may not read a ranking."),
    },
    tags=["T3", "aggregate"],
)

AUDIT = dict(
    methods=["GET"],
    summary="The audit chain, and whether it verifies",
    description=(
        "Every audit entry for the event, the chain head, and the verdict of "
        "re-walking the hashes. `verified: false` means the chain does not hash "
        "consistently -- the signal an organizer needs, and the reason the chain is "
        "readable by a human and not only by the verifier."
    ),
    responses={
        200: _ok(
            "The chain.",
            schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "chain_head": {"type": "string"},
                    "verified": {"type": "boolean"},
                    "entries": {"type": "array", "items": {"type": "object"}},
                    "problems": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
        403: _refusal("This actor may not read the audit chain."),
    },
    tags=["T2", "audit"],
)

INFLUENCE = dict(
    methods=["GET"],
    summary="Vote concentration",
    description=(
        "Per project: distinct identities, first-preference share, vote-mass Gini, "
        "and identical-ballot cluster sizes. **Deliberately not gated on "
        "`results_state`** -- an organizer has to see concentration before deciding "
        "to publish, or the report becomes a post-mortem. No threshold is applied: "
        "Gini and cluster size are reported and ranked, and the report never says "
        "'brigaded'."
    ),
    responses={
        200: _ok(
            "The report, or `status: no_votes` when no ballot exists.",
            schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "projects": {"type": "array", "items": {"type": "object"}},
                },
            },
        ),
        403: _refusal("This actor may not read the influence report."),
    },
    tags=["T3", "abuse"],
)


#: Every ``/api/v1/`` route, mapped to its declarations. **The single source of
#: truth for the API document.**
#:
#: **Why this is a table and not drf-spectacular introspection.** The generator
#: enumerates DRF views, and these are plain Django functions on purpose: DRF
#: populates ``request.user`` from its own authentication classes and would ignore
#: the user our credential middleware assigns, so every header-only request would
#: arrive anonymous and three of the four T2 checks would get a false pass instead
#: of a 403. Wrapping them in ``@api_view`` to satisfy the introspector would put
#: that risk back.
#:
#: So the declarations live here, ``reviewer.api.schema`` assembles the document
#: from them, and ``tests/test_openapi.py`` asserts that **every** ``/api/v1/``
#: route in ``urls.py`` has an entry. **``urls.py`` is the truth about what exists;
#: this table is the truth about what is documented; the test is what keeps them
#: from drifting.** A route added without documentation fails a test rather than
#: shipping as an empty ``paths: {}`` -- which is exactly what the introspector
#: produced.
PATHS = {
    "/api/v1/judge/scores": JUDGE_SCORES,
    "/api/v1/export.csv": CSV_EXPORT,
    "/api/v1/results": RESULTS,
    "/api/v1/audit": AUDIT,
    "/api/v1/influence": INFLUENCE,
}

__all__ = ["AUDIT", "CSV_EXPORT", "INFLUENCE", "JUDGE_SCORES", "PATHS", "RESULTS"]
