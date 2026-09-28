"""The schema's contract with the plan, and with the round-trip property.

**This file is on the isolation lint's allowlist, and it is the only test file
that is.** The reason is not convenience. The scope receipt claims "3 of 126",
and 126 has to be computed *independently* of the filter that produced the 3 --
if the denominator came from the same queryset, the receipt would be quoting
its own filter back at the reader as independent evidence. So the event-wide
totals live here, where the unscoped read is explicit, and the scoping tests in
``test_isolation.py`` compare against them.

**Every number this file asserts about the plan is read out of
``blueprint/build-plan.md`` and compared to the live app registry.** F-28 was a
hand-typed model count that was wrong, in a layer whose entire purpose is to
stop transcription; a test that hardcodes 24 instead of reading the plan and
comparing would be the same mistake one layer down. The plan is the claim; this
file is the check on it.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import connection, models

from reviewer.accounts.models import User

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent
BUILD_PLAN = REPO / "blueprint" / "build-plan.md"

#: Apps that are ours rather than Django's or a third party's. `contrib.*` and
#: `rest_framework` / `drf_spectacular` are not part of the domain and counting
#: them would make the number a Django-version artefact.
PROJECT_APP_PREFIX = "reviewer."


def project_app_configs():
    return sorted(
        (c for c in apps.get_app_configs() if c.name.startswith(PROJECT_APP_PREFIX)),
        key=lambda c: c.label,
    )


def project_models():
    out = []
    for config in project_app_configs():
        out.extend(config.get_models())
    return out


class TestPlanCounts:
    """The plan's numbers, checked against the app registry rather than believed."""

    @staticmethod
    def _plan_claims() -> dict[str, int]:
        text = BUILD_PLAN.read_text(encoding="utf-8")
        # The FEAT-02 checklist line. Narrow on purpose: a wide match would pick
        # up any other "N models" in the file and quietly compare the wrong one.
        match = re.search(r"(\d+)\s+models,\s*(\d+)\s+apps", text)
        assert match, (
            "blueprint/build-plan.md no longer states FEAT-02's model and app "
            "counts in the form this test reads. Update the test, not the test's "
            "assumption -- a reworded plan that cannot be checked is a plan that "
            "drifts."
        )
        return {"models": int(match.group(1)), "apps": int(match.group(2))}

    def test_model_count_matches_the_build_plan(self):
        claimed = self._plan_claims()["models"]
        actual = len(project_models())
        assert actual == claimed, (
            f"the build plan says {claimed} models, the app registry has {actual}. "
            "One of them is a transcription. The registry is the truth; correct the plan."
        )

    def test_app_count_matches_the_build_plan(self):
        claimed = self._plan_claims()["apps"]
        actual = len(project_app_configs())
        assert actual == claimed, (
            f"the build plan says {claimed} apps, Django has {actual} registered."
        )

    def test_data_model_document_matches_the_build_plan(self):
        """DATA-MODEL.md is a shipped document; the same number appears in both."""
        text = (REPO / "DATA-MODEL.md").read_text(encoding="utf-8")
        match = re.search(r"\*\*(\d+)\s+tables?\s+across\s+(\d+)\s+apps", text)
        assert match, "DATA-MODEL.md no longer states its table/app count in a checkable form."
        models_claimed, apps_claimed = int(match.group(1)), int(match.group(2))
        assert models_claimed == len(project_models()), (
            f"DATA-MODEL.md says {models_claimed} tables; the schema has "
            f"{len(project_models())}. A required deliverable carrying a wrong number "
            "is worse than one carrying none."
        )
        assert apps_claimed == len(project_app_configs())

    def test_no_app_holds_more_than_three_models(self):
        """coding-standards §3: many models in one app is a smell."""
        for config in project_app_configs():
            count = len(list(config.get_models()))
            assert count <= 3, f"{config.label} holds {count} models"


class TestSourceKey:
    """D-11: every importable table carries the external natural key."""

    def test_every_model_has_source_key(self):
        missing = [m.__name__ for m in project_models() if not _has_field(m, "source_key")]
        assert not missing, (
            f"models without source_key: {missing}. The round-trip property is "
            "'byte-identical INCLUDING every source_key', and a table without one "
            "makes the property untestable -- a dropped column just makes the "
            "second export shorter."
        )

    def test_source_key_is_nullable_and_unique(self):
        for model in project_models():
            field = model._meta.get_field("source_key")
            assert field.null, (
                f"{model.__name__}.source_key must be nullable for portal-created rows"
            )
            assert field.unique, (
                f"{model.__name__}.source_key must be unique: two rows claiming the "
                "same external identity is a data error the loader must detect."
            )

    def test_source_key_is_unique_in_the_database(self):
        """Asserted against the live schema, not against the model attribute.

        ``unique=True`` on a field and a UNIQUE index in the migration are the
        same intent, but only the second is what the round-trip depends on, and
        only the second survives someone hand-editing a Meta block.
        """
        with connection.cursor() as cursor:
            for model in project_models():
                table = model._meta.db_table
                indexes = connection.introspection.get_constraints(cursor, table)
                unique_columns = {
                    tuple(sorted(col for col in info["columns"]))
                    for info in indexes.values()
                    if info["unique"] and "source_key" in info["columns"]
                }
                assert ("source_key",) in unique_columns, (
                    f"{table} has no UNIQUE index on source_key alone. D-11's "
                    "uniqueness is not enforced."
                )


class TestHotPathIndexes:
    """The three hot paths FEAT-02 names, plus the authorization lookup."""

    @staticmethod
    def _indexed(model, fields: tuple[str, ...]) -> bool:
        wanted = tuple(fields)
        for index in model._meta.indexes:
            # `index.fields` is a list of NAMES, not field objects -- a field
            # object is what `model._meta.get_field` gives you. Reading the
            # attribute and calling `.name` on it is the kind of assumption
            # that costs an hour, and it is the installed Django that settles
            # it, not memory.
            if tuple(index.fields) == wanted:
                return True
        return False

    def test_judge_on_track(self):
        from reviewer.reviews.models import Review

        # `for_actor` filters (event, judge) and joins project.track. Without
        # the composite index the isolation read is a scan, and the first thing
        # that gets cut under time pressure is the index nobody measured.
        assert self._indexed(Review, ("event", "judge", "status"))

    def test_judge_on_project(self):
        from reviewer.reviews.models import Review

        assert self._indexed(Review, ("project", "status"))

    def test_event_gallery(self):
        from reviewer.projects.models import Project

        assert self._indexed(Project, ("event", "track", "status"))

    def test_role_binding_lookup(self):
        """`bible/05` §10: the two indexes that matter most are this one and Review's.

        "every authorization decision" is not a rhetorical phrase: `Actor.for_user`
        is on the request path of every scoped view.
        """
        from reviewer.accounts.models import RoleBinding

        assert self._indexed(RoleBinding, ("event", "user"))
        assert self._indexed(RoleBinding, ("event", "role", "track_id"))


class TestAuditChain:
    """D-08: the chain, and the column that makes sampling coherent with it."""

    def test_chain_columns_exist(self):
        from reviewer.audit.models import AuditEntry

        for name in ("seq", "prev_hash", "entry_hash", "omitted_since_prev"):
            assert _has_field(AuditEntry, name), f"AuditEntry is missing {name}"

    def test_seq_is_unique_per_event(self):
        from reviewer.audit.models import AuditEntry

        names = {c.name for c in AuditEntry._meta.constraints}
        assert any("seq" in n for n in names), (
            "seq must be unique per event. A duplicate seq breaks the chain's claim "
            "that a gap is a disclosed omission rather than an ambiguity."
        )

    def test_scope_reason_is_stored(self):
        """`bible/05` §9: the trail records what each actor was able to see."""
        from reviewer.audit.models import AuditEntry

        assert _has_field(AuditEntry, "scope_reason")

    def test_the_trail_is_append_only(self):
        from reviewer.audit.models import AuditEntry

        event = _one_event()
        with pytest.raises(TypeError):
            AuditEntry.objects.all().update(action="tampered")
        with pytest.raises(TypeError):
            AuditEntry.objects.all().delete()
        assert AuditEntry.objects.filter(event=event).count() == 0


class TestPortability:
    """`bible/05` rule 2: Postgres-portable or not at all.

    Asserted on the *field classes* rather than on a list of banned strings,
    because the failure mode is a new field type nobody thought to ban, and
    `issubclass` catches it the day it is added.
    """

    #: Field types with no portable equivalent, or whose behaviour differs.
    #: Matched on the field class's MODULE rather than imported by name, because
    #: importing django.contrib.postgres pulls in psycopg, which is deliberately
    #: not in requirements.txt -- the Postgres path is a documented switch, not
    #: a dependency. A module-path test also catches a new non-portable field
    #: type nobody thought to ban, which is the failure that matters.
    FORBIDDEN_MODULE_PREFIXES = ("django.contrib.postgres", "django.contrib.gis", "sqlite3")

    def test_no_sqlite_or_postgres_only_field_types(self):
        offenders = []
        for model in project_models():
            for field in model._meta.get_fields():
                if not isinstance(field, models.Field):
                    continue
                cls = type(field)
                module = cls.__module__
                if module.startswith(self.FORBIDDEN_MODULE_PREFIXES):
                    offenders.append(f"{model.__name__}.{field.name} ({module}.{cls.__name__})")
        assert not offenders, (
            f"fields that are not portable to both engines: {offenders}. We develop "
            "on SQLite because the brief requires it, and the schema has to survive a port."
        )

    def test_json_fields_are_not_indexed(self):
        """We store and read JSONField whole. Indexing into it is the portability trap."""
        for model in project_models():
            for index in model._meta.indexes:
                for name in index.fields:
                    # A descending index names its field "-published_at".
                    clean = name.lstrip("-")
                    assert not isinstance(model._meta.get_field(clean), models.JSONField), (
                        f"{model.__name__} indexes JSONField {clean}"
                    )

    def test_every_model_names_its_table(self):
        """An explicit db_table on every model, so a future rename cannot be silent."""
        for model in project_models():
            assert model._meta.db_table, f"{model.__name__} has no explicit db_table"


class TestMigrationsInStep:
    """The schema and the migration cannot drift."""

    def test_makemigrations_would_produce_nothing(self):
        from django.core.management import call_command
        from django.core.management.base import SystemCheckError

        try:
            call_command("makemigrations", "--check", "--dry-run", verbosity=0)
        except SystemCheckError as exc:  # pragma: no cover - only on drift
            pytest.fail(f"models and migrations have drifted: {exc}")


class TestCustomUser:
    """`User` has no `PermissionsMixin`, and the consequences are stated in the ledger."""

    def test_no_permission_framework_fields(self):
        for name in ("groups", "user_permissions"):
            assert not _has_field(User, name), (
                f"User has {name}. Django's permission framework is global and "
                "cannot express per-track authority; ours lives in RoleBinding."
            )

    def test_has_perm_is_always_false(self):
        user = User(email="probe@example.invalid", display_name="probe")
        assert user.has_perm("anything") is False
        assert user.has_perms(["a", "b"]) is False
        assert user.has_module_perms("reviews") is False

    def test_username_field_is_the_email(self):
        assert User.USERNAME_FIELD == "email"

    def test_it_is_the_configured_user_model(self):
        from django.conf import settings

        assert settings.AUTH_USER_MODEL == "accounts.User"


def _has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


def _one_event():
    """A bare event, for the tests that only need a foreign key target."""
    from tests.factories import make_event

    return make_event(event_id="evt_probe", slug="evt-probe")
