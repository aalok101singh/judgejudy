"""The loader, the census, and the identities the acceptance checker uses.

A package rather than an app, and the reason is the same one that made
``reviewer/isolation`` a package: it defines no model, so adding it to
``INSTALLED_APPS`` would add a ``models`` module that does not exist and a
migration that creates nothing. It is also not a domain, so naming it after one
of the twelve would be a lie about where it belongs.
"""

from __future__ import annotations

__all__ = ["census", "demo", "loader"]
