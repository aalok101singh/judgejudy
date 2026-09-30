"""Assemble the OpenAPI 3.1 document, and refuse to ship one that lies.

**The document is built from ``documents.PATHS``, not from introspection, and
the reason is in that module: the API is plain Django views on purpose, because DRF
would override the ``request.user`` our credential middleware assigns and turn three
T2 checks into false passes.**

That leaves one thing this module must be trusted to do, and it is not "produce
YAML". It is **refuse to produce a document that does not match the application**,
because the failure mode of a generated API doc is not a crash -- it is a spec that
looks fine, is served at a URL, and omits an endpoint. That is F-61's shape with a
`paths:` key.

So :func:`undocumented_routes` compares the declared paths against the routes
``urls.py`` actually registers, and :func:`build_schema` **raises** rather than
emitting a partial document. A missing entry is a build failure, not a gap.

Why hand-assembled YAML rather than a library's emitter
-------------------------------------------------------
``json`` and a small YAML writer are enough for one document shape, and the
alternative -- coercing the declarations into something only a library will accept
-- reintroduces the mismatch we are avoiding. The cost is that this file knows
about OpenAPI 3.1's shape; the benefit is that **the only way an endpoint goes
missing is an explicit table row**, which a reviewer can read in one screen.

The 403 is described as an empty body
------------------------------------
Every operation here can return a 403 with **no body and no Location header**.
The document says so in prose, and -- more usefully -- a 403 response is emitted
with an empty ``content`` rather than an error object, so a client generator
produces a branch that does not try to parse a body that is not there.
"""

from __future__ import annotations

import re

from reviewer.api import documents

OPENAPI_VERSION = "3.1.0"

#: Refusals are the product. An empty content map says "no body" to a generator,
#: which is the thing a client author needs and cannot infer from prose.
_EMPTY = {}


def declared_paths() -> set[str]:
    return set(documents.PATHS)


def _registered_paths() -> set[str]:
    """The ``/api/v1/`` routes ``urls.py`` actually serves.

    **Read from the URLconf, never transcribed.** A hand-written list of the
    endpoints is a list that goes stale the day somebody adds a route, and it goes
    stale silently, which is the only way a list ever goes stale.
    """
    from django.urls import get_resolver

    found: set[str] = set()
    for pattern in get_resolver().url_patterns:
        route = _route_of(pattern)
        if route and route.startswith("/api/"):
            found.add(route)
    return found


def _route_of(pattern) -> str:
    """A concrete path string, or ``""`` for a pattern with converters or a prefix."""
    text = str(pattern.pattern)
    if "<" in text or text in {"", "/"}:
        return ""
    if text.startswith("^"):
        return ""
    return "/" + text.lstrip("/")


def undocumented_routes() -> set[str]:
    """Routes that exist but have no declaration. Empty set means the doc is honest."""
    return _registered_paths() - declared_paths()


def stale_declarations() -> set[str]:
    """Declarations for routes that do not exist. A renamed route, left behind."""
    return declared_paths() - _registered_paths()


def _operation(spec: dict) -> dict:
    """One operation, built from a declaration.

    **The response objects are plain dicts written in ``documents.py``, not
    drf-spectacular's ``OpenApiResponse``.** That was the first design and it does
    not work: those are not mappings, so assembling a document from them means
    either duck-typing a third party's internals or dropping the dependency that
    produced them. Since this module hand-assembles the document anyway, the
    declarations are plain dicts too, and nothing outside this file depends on
    drf-spectacular's object model.
    """
    operation = {
        "summary": spec.get("summary", ""),
        "description": spec.get("description", ""),
        "responses": {
            str(code): {"description": entry.get("description", ""), "content": entry["content"]}
            for code, entry in (spec.get("responses") or {}).items()
        },
    }
    if spec.get("tags"):
        operation["tags"] = list(spec["tags"])
    if spec.get("examples"):
        operation["examples"] = {
            str(i): {"summary": e.get("summary", ""), "value": e.get("value")}
            for i, e in enumerate(spec["examples"], start=1)
        }
    return operation


def build_schema() -> dict:
    """The OpenAPI 3.1 document, or raise if it would not match the application.

    **Raises rather than emits a partial document.** A generated spec that quietly
    omits an endpoint is worse than no spec: it is served, it looks authoritative,
    and a client built from it will 404 against a route it was never told existed.
    """
    global _current

    missing = undocumented_routes()
    if missing:
        raise RuntimeError(
            "these routes are served but not documented in reviewer.api.documents."
            f"PATHS: {sorted(missing)}. Add a declaration, or the OpenAPI document "
            "will describe an API that is not the one running."
        )
    stale = stale_declarations()
    if stale:
        raise RuntimeError(
            f"documents.PATHS describes routes that no longer exist: {sorted(stale)}. "
            "A declaration for a renamed route is worse than none, because it "
            "documents an endpoint nobody can call."
        )

    paths = {}
    for path, spec in sorted(documents.PATHS.items()):
        _current = path
        operations = {}
        for method in spec.get("methods", ["GET"]):
            operations[method.lower()] = _operation(spec)
        paths[path] = operations

    from django.conf import settings

    spectacular = getattr(settings, "SPECTACULAR_SETTINGS", {})
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": spectacular.get("TITLE", "Judge Judy API"),
            "version": spectacular.get("VERSION", "1.0.0"),
            "description": spectacular.get("DESCRIPTION", ""),
        },
        "paths": paths,
        "components": {},
    }


_SCALAR = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|\"[^\"]*\"):")


def _render(value, indent: int) -> str:
    """One value as YAML: a nested block, a block sequence, or a scalar.

    ``indent`` is the level of the **key** this value belongs to, so nested blocks
    render at ``indent + 1``. Getting that off by one is not a cosmetic bug -- the
    document still parses, and a client generator then reads the structure one
    level too shallow. It was found because the command printed a path list
    containing its own keys.

    **Empty containers are the case this got wrong first.** A falsy `{}` fell
    through to the scalar path and was emitted as the quoted *string* `"{}"`, so
    every `content: {}` -- that is, every refusal, which is the load-bearing part
    of the document -- parsed back as a string rather than an empty map. The
    document was still valid YAML and still looked right, which is the same
    failure mode as the `paths: {}` this file exists to prevent.
    """
    if isinstance(value, dict):
        return " {}" if not value else "\n" + _render_map(value, indent + 1).rstrip("\n")
    if isinstance(value, list):
        return " []" if not value else "\n" + _render_sequence(value, indent + 1).rstrip("\n")
    return f" {_scalar(value)}"


def _render_sequence(value: list, indent: int) -> str:
    pad = "  " * indent
    return "\n".join(f"{pad}- {_strip_leading(_render(item, indent))}" for item in value)


def _strip_leading(rendered: str) -> str:
    """Nested blocks are emitted one level in; a sequence item must not be."""
    return rendered[1:] if rendered.startswith(" ") else rendered


def _key(key) -> str:
    return key if _SCALAR.match(f"{key}:") else f'"{key}"'


def _scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if "\n" in text:
        return "|-\n" + "\n".join("    " + line for line in text.splitlines())
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def document() -> str:
    """The whole document as YAML text.

    Top-level keys are emitted in a **fixed order** rather than the dict's, because
    a committed generated file whose diff is always empty is a file nobody reads,
    and key order is the most common source of a spurious diff.
    """
    schema = build_schema()
    out = [f"openapi: {schema['openapi']}\n"]
    out.append("info:\n" + _render_map(schema["info"], 1))
    out.append("paths:\n" + (_render_map(schema["paths"], 1) if schema["paths"] else " {}\n"))
    out.append("components: {}\n")
    return "".join(out)


def _render_map(value: dict, indent: int) -> str:
    """A mapping at the given indent, with every value rendered one level in."""
    pad = "  " * indent
    lines = []
    for key, item in value.items():
        lines.append(f"{pad}{_key(key)}:{_render(item, indent)}")
    return "\n".join(lines) + "\n"


def api_paths() -> dict:
    """The parsed YAML, for a test that wants to assert on structure."""
    import yaml

    return yaml.safe_load(document())
