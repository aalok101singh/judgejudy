"""Shared model bases, and the two rules every model in the schema obeys.

This is a module rather than a Django app on purpose: it defines no model of its
own, so it is not one of the twelve apps, and it can be imported by any of them
without creating an import cycle.

Two bases live here, and both exist because retrofitting them later is expensive:

``SourceKeyMixin``
    Adds the external natural key to a table (D-11, ``bible/05`` §8a). The
    bulk round-trip property is "export -> import -> export is byte-identical
    *including every source_key*". Without the column, "modulo generated IDs"
    is an escape hatch that quietly removes the property: a dropped column just
    makes the second export shorter and nothing asserts the length. One nullable
    column now, three hours per table if it is added after the importer exists.

``TimeStampedModel``
    ``created_at`` / ``updated_at`` on every table. These are generated values,
    not imported ones, so they are excluded from the round-trip's byte-identity
    allowlist rather than nulled.
"""

from __future__ import annotations

from django.db import models

# The five roles. `visitor` is deliberately NOT stored on a RoleBinding row: a
# visitor is the absence of a binding, and making it a row would mean every
# anonymous request creates a User. The role set still has five members, because
# the tier requires five, and `reviewer.isolation.actor.Actor` returns
# `visitor` explicitly rather than making every call site handle None.
ROLE_VISITOR = "visitor"
ROLE_PARTICIPANT = "participant"
ROLE_JUDGE = "judge"
ROLE_ORGANIZER = "organizer"
ROLE_ADMIN = "admin"

ROLE_CHOICES = [
    (ROLE_VISITOR, "Visitor"),
    (ROLE_PARTICIPANT, "Participant"),
    (ROLE_JUDGE, "Judge"),
    (ROLE_ORGANIZER, "Organizer"),
    (ROLE_ADMIN, "Admin"),
]

# The four roles that actually appear on a RoleBinding row. `visitor` is
# excluded by construction, which is what makes "is this person a visitor?" a
# question about absence rather than about a stored value.
STORED_ROLE_CHOICES = [
    (ROLE_PARTICIPANT, "Participant"),
    (ROLE_JUDGE, "Judge"),
    (ROLE_ORGANIZER, "Organizer"),
    (ROLE_ADMIN, "Admin"),
]


class SourceKeyMixin(models.Model):
    """The external natural key this row was imported under.

    Nullable and unique. Nullable because a row the portal created itself has
    no external key, and unique because two rows claiming the same external
    identity is a data error the loader must be able to detect rather than
    absorb. Both SQLite and Postgres allow any number of NULLs in a unique
    index, so "absent" does not collide with "absent" and this costs nothing on
    a self-hosted instance.

    The length is 255 because the shortest useful natural key is an email
    address and the longest Django's own ``EmailField`` admits is 254. Sizing
    this to the fixture's ``evt_01`` would be a number transcribed from a test
    file into a schema, which is the habit this column exists to prevent.
    """

    source_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        help_text="Natural key from the source system. Null for rows this portal created.",
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """``created_at`` / ``updated_at``, maintained by the database layer."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
