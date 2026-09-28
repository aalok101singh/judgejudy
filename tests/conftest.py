"""Shared pytest fixtures.

**The one that matters is the password hasher swap**, and the reason it is here
rather than in the loader's own test module is that it has to apply to every
test: a fixture that only covers the file that needs it is a fixture the next
test quietly bypasses.

``pbkdf2_sha256`` at Django 5.2's default 1,000,000 iterations costs about
400 ms per hash. F-12 measured the consequence -- 121 people would cost ~48 s
against a 10-second acceptance timeout -- and the seed's answer is to hash
exactly five. But five real hashes per test, across the thirty-odd tests that
need a loaded database, put the loader's test module at **116 seconds**, which
is how a suite that runs at every break stops being run at every break.

So the suite swaps in ``MD5PasswordHasher``. **What that hides, stated plainly:
the COST, and only the cost.** Everything the seed actually asserts about
credentials is hasher-independent and still tested for real:

* ``set_unusable_password()`` writes ``"!" + 32 random characters`` regardless
  of hasher, so the empty-password bug that shipped for one run (F-49) is still
  exactly as catchable here as in production.
* ``check_password`` against a real stored hash still runs.

And the swap cannot hide a change to the production setting, because
``TestPasswords::test_production_still_hashes_with_pbkdf2`` reads the attribute
off the settings **module** -- which ``override_settings`` does not touch.
"""

from __future__ import annotations

import pytest
from django.conf import settings

#: Fast, deliberately weak, and never shipped. See the module docstring for
#: exactly what it hides and why that is only the cost.
TEST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _fast_password_hashing(settings) -> None:
    """MD5 in the suite, pbkdf2 in the portal, and a test that says so."""
    settings.PASSWORD_HASHERS = TEST_PASSWORD_HASHERS


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
