"""Isolation: the access-control primitive, and nothing else.

A reviewer should be able to read this one package and understand the security
model of the project. That is the stated reason it exists as its own module
rather than being scattered through ``views.py`` (``coding-standards.md`` §3), and
it is the reason nothing in here knows what a ``Project`` is.

Three pieces, in dependency order:

``scope``
    ``Scope`` and ``ScopeReason`` -- the rule that fired, and the rule plus the
    numbers a reader needs to check it. Pure data, no Django imports.

``scoped``
    ``ScopedQuerySetMixin`` -- the queryset carries the scope, and the scope
    survives ``filter()``.

``actor``
    ``Actor`` -- an immutable, already-resolved authority for one event.

``refusal``
    ``deny()`` -- the portal's single 403/empty-body/no-``Location`` primitive,
    shared by the judge console and the API surface.

The accessors that *apply* a scope live next to the models they scope, in
``reviewer.reviews.queryset``. Putting them here would need this package to
import the models, and putting the models here would make ``reviewer.isolation``
depend on the domain -- which is the direction every import cycle in a Django
project eventually takes.
"""

from reviewer.isolation.actor import Actor
from reviewer.isolation.refusal import REFUSED_BY_HEADER, deny
from reviewer.isolation.scope import (
    DECISION_ALLOW_ALL,
    DECISION_ALLOW_OWN,
    DECISION_DENY,
    Scope,
    ScopeReason,
)
from reviewer.isolation.scoped import ScopedQuerySetMixin

__all__ = [
    "DECISION_ALLOW_ALL",
    "DECISION_ALLOW_OWN",
    "DECISION_DENY",
    "REFUSED_BY_HEADER",
    "Actor",
    "Scope",
    "ScopeReason",
    "ScopedQuerySetMixin",
    "deny",
]
