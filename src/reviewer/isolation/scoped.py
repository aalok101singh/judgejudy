"""``ScopedQuerySet`` -- the mixin that carries a scope on the queryset itself.

This is the mechanical half of D-01. The decision (``bible/05`` §6) is that
scoping happens in the data-access layer, so a view cannot leak a peer's review
by forgetting a filter. This module is where that decision stops being a
convention and becomes a property of the object.

**Why the scope has to survive ``filter()``.** A ``QuerySet`` is immutable in
its *results* and mutable in its *configuration*, and Django's
``filter()``/``exclude()``/``order_by()`` all return a fresh clone. If the
receipt were set on the object ``for_actor()`` returns and nowhere else, then
``for_actor(actor).exclude(status=DECLINED)`` -- one keystroke in a list view --
would silently drop the receipt, and the page would render with no explanation
and no test would fail. The failure is invisible in the worst way: it removes
the evidence, not the protection. So ``_clone`` propagates it, which is the one
place a subclass of Django's ``QuerySet`` has to be deliberately different from
the base.

**Why ``scope_receipt()`` takes a ``total`` rather than computing one.** The
receipt's whole value is "3 of 126". That is only evidence if 126 was defined
independently of the filter that produced 3 -- otherwise a filter that dropped
95% of the rows for a reason unrelated to authorization would render a
confidently wrong denominator. ``for_actor`` therefore computes the total from
the *event*, not from the queryset it was handed, and passes it in.

**Why there is no way to set the scope from outside.** ``attach_scope`` is
prefixed with a single underscore and is only called from
``reviewer.reviews.queryset.ReviewQuerySet.for_actor``. A caller that could
attach its own scope could attach a permissive one, which is the same class of
mistake as writing the filter by hand -- so the method that grants scopes and
the methods that use them live in the same module, and the lint rule
(``tools/check_isolation.py``) watches that boundary.
"""

from __future__ import annotations

from reviewer.isolation.scope import Scope, ScopeReason


class ScopedQuerySetMixin:
    """Adds ``.scope`` and ``.scope_receipt()`` to a ``QuerySet``."""

    # A class-level default rather than an ``__init__`` override: Django builds
    # clones through ``self.__class__(model=..., query=..., using=..., hints=...)``
    # and never calls our ``__init__`` with those keyword names, so an instance
    # attribute set in ``__init__`` would not survive construction.
    _scope: Scope | None = None

    def _clone(self):
        """Propagate the scope across every derived queryset.

        Overriding ``_clone`` rather than ``_chain`` is deliberate: ``_chain``
        is only the no-argument path, while ``filter()`` and friends go through
        ``_filter_or_exclude`` -> ``_chain``. Overriding the lower-level method
        covers both, and anything Django adds later that clones will inherit it.
        """
        clone = super()._clone()
        clone._scope = self._scope
        return clone

    def _attach_scope(self, scope: Scope):
        """Bind a scope to this queryset. Not for callers -- see the module docs."""
        self._scope = scope
        return self

    @property
    def scope(self) -> Scope | None:
        """The rule that was applied, or ``None`` if this queryset was never scoped."""
        return self._scope

    @property
    def is_scoped(self) -> bool:
        return self._scope is not None

    def scope_total_count(self) -> int:
        """The population this scope was applied to, defined independently of it.

        Concrete querysets override this. It is a method rather than an
        attribute because the population is a *query*, and hard-coding it would
        put a number in a class body that the next reader cannot check.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement scope_total_count() to be able to explain itself"
        )

    def scope_receipt(self, total: int | None = None) -> ScopeReason:
        """The receipt for this queryset, with row counts filled in.

        Costs two ``COUNT`` queries, which is why it is a method and not
        something ``for_actor`` does on the way past. A list view that renders
        the block pays for it; a list view that does not, does not.
        """
        if self._scope is None:
            raise ValueError(
                "scope_receipt() called on an unscoped queryset. A receipt with no "
                "rule is worse than no receipt: it looks like an explanation."
            )
        visible = self.count()
        if total is None:
            total = self.scope_total_count()
        return self._scope.with_counts(visible=visible, total=total)
