"""Shared pytest fixtures.

Kept deliberately small. At the skeleton milestone the database is Django's own
contrib tables and nothing else, so the only fixture that earns its place is the
one that makes those tables exist per-test.

The isolation matrix and the fixture census land in FEAT-02 and FEAT-03; the
stubs below are here so `just check` is green from the first commit rather than
failing on a missing `conftest.py` that no test needs yet.
"""

from __future__ import annotations

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _isolated_settings() -> None:
    """Keep a test from writing to the developer's real instance volume.

    Points the database at a temporary file for the duration of the session and
    restores the real path afterwards. Without this, a test that touches the
    database writes to `data/instance/db.sqlite3` — the same file a local
    `manage.py runserver` uses — and a "harmless" test run silently corrupts a
    running portal.
    """
    original = settings.DATABASES["default"]["NAME"]
    yield
    settings.DATABASES["default"]["NAME"] = original
