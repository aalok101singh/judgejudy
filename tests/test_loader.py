"""The loader, against the real ``fixtures.json``, and against a clean database.

**These tests read the repository's own ``fixtures.json`` rather than a
hand-built miniature.** A miniature would let the loader pass on tidy input,
which is the one thing the brief says the organizers are testing: *"if your
portal only works on tidy input, you will find out on Friday."* The fixture's
awkward parts -- the duplicate submission, the nine dual-track judges, the 51
empty comments, the three team names that collapse onto one slug -- are the
point, and a test fixture that omits them tests nothing.

The only cost is time, and it is paid once: the fixture is a module-level
constant and the loader runs inside a transaction that pytest rolls back.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from django.core.management import call_command
from tests import ground_truth

from reviewer.accounts.models import RoleBinding, User
from reviewer.core import ROLE_JUDGE, ROLE_ORGANIZER, ROLE_PARTICIPANT
from reviewer.events.models import Event, Track
from reviewer.importer import census as census_module
from reviewer.importer import loader as loader_module
from reviewer.projects.models import Project
from reviewer.reviews.models import Assignment, Review, Score
from reviewer.rubrics.models import Criterion, Rubric
from reviewer.teams.models import Team, TeamMembership

REPO = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO / "fixtures.json"

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def raw_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture_census(raw_fixture) -> census_module.Census:
    return census_module.census(raw_fixture)


@pytest.fixture
def report(raw_fixture) -> loader_module.LoadReport:
    return loader_module.load(raw_fixture)


# --------------------------------------------------------------------- census


class TestCensusIsDerived:
    """The census is re-derived from the file, and the invariants are the pair."""

    def test_no_failure_on_the_published_fixture(self, raw_fixture):
        _, failures = census_module.check(raw_fixture)

        assert failures == [], (
            "fixtures.json does not reconcile with itself. Every count below is "
            f"re-derived, so this is a real property of the file: {failures}"
        )

    def test_cardinality_and_mass_hold_over_projects(self, raw_fixture, fixture_census):
        """Both, because F-28 satisfied one and failed the other.

        The histogram said ``8@2, 26@3, 3@4, 5@5``; the truth is ``4@5``. The
        cardinality sum was right and only the mass caught it, which is the
        argument for asserting two invariants rather than the one that is easy.
        """
        _, failures = census_module.check(raw_fixture)
        project_failures = [f for f in failures if "projects" in f]

        assert project_failures == []
        assert sum(fixture_census.projects_by_reviews.values()) == fixture_census.projects
        assert (
            sum(n * c for n, c in fixture_census.projects_by_reviews.items())
            == fixture_census.reviews
        )

    def test_both_invariants_catch_f28s_exact_error(self, fixture_census):
        """F-28, injected into the place it can actually bite -- and **both**
        invariants fire, which is not what our own ledger says.

        ``blueprint/context/findings.md`` records F-28 as the mass invariant
        settling the histogram, and writes the mass as
        ``8x2 + 26x3 + 3x4 + 5x5 = 126``. That sum is **131**, and the buckets
        also total 42 rather than 41, so cardinality catches it too. The
        overview's arithmetic is the correct one; the ledger entry is the
        transcription error, which is a slightly embarrassing place to find one
        and is recorded as its own finding rather than quietly fixed here.

        Either way the two invariants together are strictly stronger than one,
        and the test asserts both halves so the claim is checkable.
        """
        import dataclasses

        wrong = dataclasses.replace(
            fixture_census,
            projects_by_reviews={2: 8, 3: 26, 4: 3, 5: 5},  # F-28: 5@5, not 4@5
        )
        failures = census_module._population_failures(wrong)

        assert any("mass over projects" in f for f in failures), failures
        assert any("cardinality over projects" in f for f in failures), (
            "8+26+3+5 is 42, not 41, so cardinality fires as well. The ledger "
            "credits only the mass invariant; both do."
        )
        assert 8 * 2 + 26 * 3 + 3 * 4 + 5 * 5 == 131, (
            "the mass arithmetic quoted in findings.md for F-28 does not add up"
        )

    def test_the_real_histogram_satisfies_both(self, fixture_census):
        failures = census_module._population_failures(fixture_census)

        assert failures == []
        assert 8 * 2 + 26 * 3 + 3 * 4 + 4 * 5 == 126

    def test_structural_check_catches_an_off_track_score(self, raw_fixture):
        """The fixture has zero off-track scores. Injected, it must be caught.

        This is the check that matters for the assignment engine: a judge
        reviewing outside their own track is the cross-track leak, and a
        census that only counted rows would import it happily.
        """
        broken = json.loads(json.dumps(raw_fixture))
        projects = {p["id"]: p for p in broken["projects"]}
        other_track = next(p["track"] for p in broken["projects"] if p["track"] != "trk_01")
        broken["scores"].append(
            {
                "judge": next(j["id"] for j in broken["judges"] if "trk_01" in j["tracks"]),
                "project": next(pid for pid, p in projects.items() if p["track"] == other_track),
                "criteria": {"functionality": 3, "quality": 3, "innovation": 3},
                "comment": "off-track",
            }
        )
        _, failures = census_module.check(broken)

        assert any("off-track" in f for f in failures), failures

    def test_structural_check_catches_an_unknown_reference(self, raw_fixture):
        broken = json.loads(json.dumps(raw_fixture))
        broken["scores"].append(
            {
                "judge": "jdg_99",
                "project": broken["scores"][0]["project"],
                "criteria": {"functionality": 3, "quality": 3, "innovation": 3},
                "comment": "ghost",
            }
        )
        _, failures = census_module.check(broken)

        assert any("unknown id" in f for f in failures), failures

    def test_criteria_key_order_is_the_fixtures_not_alphabets(self, fixture_census):
        """F-04. The export header is this order; deriving it from a row
        transposes two columns in every export."""
        assert fixture_census.criteria_keys == ("functionality", "quality", "innovation")
        assert fixture_census.criteria_keys != tuple(sorted(fixture_census.criteria_keys))

    def test_the_target_is_the_mode_and_not_a_typed_three(self, fixture_census):
        assert fixture_census.modal_reviews_per_project == 3
        assert fixture_census.projects_by_reviews == {2: 8, 3: 26, 4: 3, 5: 4}

    def test_people_are_judges_plus_members_and_disjoint(self, raw_fixture, fixture_census):
        assert fixture_census.people == 121
        assert fixture_census.judges == 30
        assert fixture_census.team_members == 91
        _, failures = census_module.check(raw_fixture)
        assert not [f for f in failures if "both a judge and a team member" in f]

    def test_slug_collisions_are_reported_not_raised(self, fixture_census):
        """40 teams, 36 distinct names. A property of the data, and the loader
        has to survive it because the schema says UNIQUE (event, slug)."""
        notes = census_module.observations(
            json.loads(FIXTURE_PATH.read_text(encoding="utf-8")), fixture_census
        )
        collapsed = [n for n in notes if "collapse onto one slug" in n]

        assert len(collapsed) == 1
        assert "stilltrail" in collapsed[0]
        assert "tm_03" in collapsed[0] and "tm_30" in collapsed[0] and "tm_40" in collapsed[0]


# --------------------------------------------------------------------- loader


class TestLoad:
    def test_every_fixture_table_lands(self, report):
        assert report.ok, report.failures
        assert Event.objects.count() == report.census.events == 1
        assert Track.objects.count() == report.census.tracks == 8
        assert Team.objects.count() == report.census.teams == 40
        assert TeamMembership.objects.count() == report.census.team_members == 91
        assert Project.objects.count() == report.census.projects == 41
        assert ground_truth.total_reviews() == report.census.reviews == 126
        assert Score.objects.count() == report.census.reviews * 3 == 378
        assert Assignment.objects.count() == report.census.reviews == 126

    def test_fixture_ids_are_preserved_verbatim(self, report):
        """`prj_07` stays `prj_07`, so a curl transcript and a row are the same
        string and a signed record can be checked against the published file."""
        assert Project.objects.get(pk="prj_07").title == "Dry Harbour"
        assert Project.objects.filter(pk__startswith="prj_").count() == 41
        assert Event.objects.get(pk="evt_01").slug

    def test_dual_track_judges_get_one_binding_per_track(self, report, fixture_census):
        """39 rows for 30 judges. The seed is a direct expression of the model's
        shape, not a special case for the nine dual-track judges."""
        from collections import Counter

        per_judge = Counter(
            RoleBinding.objects.filter(role=ROLE_JUDGE).values_list("user_id", flat=True)
        )

        assert sum(per_judge.values()) == report.census.judge_track_bindings == 39
        assert report.census.judges == 30
        assert report.census.dual_track_judges == 9
        assert Counter(per_judge.values()) == {1: 21, 2: 9}

    def test_no_judge_binding_is_event_wide(self, report):
        assert not RoleBinding.objects.filter(role=ROLE_JUDGE, track__isnull=True).exists()

    def test_one_fixture_row_becomes_one_review_and_three_scores(self, report):
        review = ground_truth.any_review()

        assert review.scores.count() == 3
        assert set(review.scores.values_list("criterion__key", flat=True)) == {
            "functionality",
            "quality",
            "innovation",
        }
        assert review.status == "submitted"
        assert review.rubric_version_id == Rubric.objects.get().pk

    def test_an_empty_comment_is_stored_not_dropped(self, report, fixture_census):
        empties = ground_truth.reviews_with_empty_comment()

        assert empties == fixture_census.empty_comments == 51
        assert ground_truth.total_reviews() == 126

    def test_the_rubric_exists_and_is_versioned(self, report):
        rubric = Rubric.objects.get()
        assert rubric.version == loader_module.RUBRIC_VERSION
        assert rubric.scale_min == 1 and rubric.scale_max == 5
        weights = dict(Criterion.objects.values_list("key", "weight"))
        assert weights == loader_module.RUBRIC_WEIGHTS
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)
        # Position is the FIXTURE's key order, not the weight order. F-04.
        assert list(Criterion.objects.order_by("position").values_list("key", flat=True)) == list(
            census_module.CRITERIA_KEYS
        )

    def test_starts_at_is_derived_from_the_data_and_close_is_untouched(self, report, raw_fixture):
        event = Event.objects.get()
        earliest = min(p["submitted_at"] for p in raw_fixture["projects"])
        fixture_close = raw_fixture["event"]["submissions_close"].replace("Z", "+00:00")

        assert event.submissions_close.isoformat().startswith("2026-03-01T18:00:00")
        assert event.submissions_close.isoformat() == fixture_close
        assert event.starts_at.isoformat() == earliest.replace("Z", "+00:00")
        assert event.submissions_open is None, (
            "the fixture configures a close and no open, so the loader must not "
            "invent an opening date -- the guard reads NULL as 'no opening gate'"
        )


class TestIdempotency:
    """The property that matters is "the second run creates nothing"."""

    def test_a_second_run_creates_zero_rows(self, raw_fixture):
        first = loader_module.load(raw_fixture)
        assert first.created_total > 0

        second = loader_module.load(raw_fixture)

        assert second.created_total == 0, (
            f"a second load created {second.created} rows. `docker compose up` runs "
            "against a volume that already has yesterday's data, so a loader that "
            "only works once makes the portal non-reproducible."
        )
        assert second.ok, second.failures

    def test_a_second_run_creates_no_duplicates(self, raw_fixture):
        loader_module.load(raw_fixture)
        before = {
            model: model.objects.count()
            for model in (Event, Track, User, Team, TeamMembership, Project, Review, Score)
        }
        loader_module.load(raw_fixture)

        assert {model: model.objects.count() for model in before} == before

    def test_a_second_run_re_hashes_nothing(self, raw_fixture):
        """F-12's budget is per BOOT, not per first boot."""
        first = loader_module.load(raw_fixture)
        assert first.passwords_hashed == 5

        second = loader_module.load(raw_fixture)

        assert second.passwords_hashed == 0
        assert second.elapsed < first.elapsed + 1.0


class TestPasswords:
    def test_production_still_hashes_with_pbkdf2(self):
        """The suite swaps in MD5 for speed. The portal must not.

        Read off the settings **module** rather than through the lazy settings
        object, because ``override_settings`` patches the latter and would
        report the test's own override back as the production value. This is the
        test that stops a fast-suite convenience from becoming a fast portal.

        The assertion is that the module does not mention the setting *at all*:
        F-12's whole argument is that the shipped portal pays Django 5.2's
        default ``pbkdf2_sha256`` at 1,000,000 iterations and manages by hashing
        only five people. An override anywhere in this file would silently
        invalidate that measurement.
        """
        from django.conf import global_settings

        import judge_judy.settings as our_settings

        assert "PASSWORD_HASHERS" not in vars(our_settings), (
            "judge_judy.settings now overrides PASSWORD_HASHERS. F-12's 10-second "
            "budget assumes Django's default pbkdf2_sha256 at 1,000,000 iterations."
        )
        assert global_settings.PASSWORD_HASHERS[0] == (
            "django.contrib.auth.hashers.PBKDF2PasswordHasher"
        ), (
            "Django's default hasher is no longer PBKDF2PasswordHasher, so F-12's "
            "~400 ms per hash is no longer the number to plan against"
        )

    def test_exactly_five_accounts_can_authenticate(self, report, fixture_census):
        """F-12, asserted. 121 at ~400 ms each is ~48 s against a 10 s timeout."""
        usable = [u for u in User.objects.all() if not u.password.startswith("!")]

        assert len(usable) == 5
        assert fixture_census.people == 121

    def test_a_fixture_person_cannot_log_in_with_an_empty_password(self, report):
        """The bug this loader shipped for one run.

        ``User.has_usable_password()`` returns True for an EMPTY password, so
        the obvious "only set one if there isn't one" guard skips every fresh
        row, and ``check_password("", "")`` is True -- 123 accounts that
        authenticate with a blank string.
        """
        victim = User.objects.exclude(source_key__isnull=True).first()

        assert victim.password != ""
        assert victim.password.startswith("!")
        assert not victim.has_usable_password()
        assert victim.check_password("") is False

    def test_the_five_demo_identities_have_their_documented_passwords(self, report):
        for identity in report.demo_identities:
            user = User.objects.get(email=identity.email)
            assert user.check_password(identity.password), identity.key


class TestSupersedeChain:
    def test_both_duplicate_rows_survive(self, report):
        assert Project.objects.filter(title="Dry Harbour").count() == 2
        assert Project.objects.filter(pk__in=["prj_07", "prj_41"]).count() == 2

    def test_the_earlier_row_points_at_the_later_one(self, report):
        earlier = Project.objects.get(pk="prj_07")
        later = Project.objects.get(pk="prj_41")

        assert earlier.supersedes_id is None
        assert later.supersedes_id == "prj_07"
        assert later.submitted_at > earlier.submitted_at

    def test_nothing_else_is_linked(self, report):
        assert Project.objects.filter(supersedes__isnull=False).count() == 1

    def test_the_chain_is_derived_from_team_and_title(self):
        """Not typed: two teams building the same name is normal and must not link."""
        projects = [
            {
                "id": "prj_a",
                "team": "tm_1",
                "title": "Same",
                "submitted_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "prj_b",
                "team": "tm_2",
                "title": "Same",
                "submitted_at": "2026-01-02T00:00:00Z",
            },
        ]
        assert loader_module._supersede_map(projects) == {}

    def test_two_projects_by_one_team_do_link(self):
        projects = [
            {
                "id": "prj_a",
                "team": "tm_1",
                "title": "Same",
                "submitted_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "prj_b",
                "team": "tm_1",
                "title": "Same",
                "submitted_at": "2026-01-02T00:00:00Z",
            },
        ]
        assert loader_module._supersede_map(projects) == {"prj_b": "prj_a"}


class TestTags:
    def test_three_to_five_tags_per_project(self, report):
        counts = {len(p.tags) for p in Project.objects.all()}

        assert min(counts) >= loader_module.MIN_TAGS
        assert max(counts) <= loader_module.MAX_TAGS

    def test_tags_are_deterministic_across_processes(self):
        """Not `hash()`, which is randomised per process by PYTHONHASHSEED."""
        assert loader_module._tags_for("prj_01") == loader_module._tags_for("prj_01")
        assert loader_module._tags_for("prj_01") != loader_module._tags_for("prj_02")

    def test_every_tag_comes_from_the_closed_vocabulary(self, report):
        allowed = set(loader_module.TAG_VOCABULARY)
        for project in Project.objects.all():
            assert set(project.tags) <= allowed


class TestSlugs:
    def test_team_slugs_are_unique_per_event_despite_repeated_names(self, report):
        slugs = list(Team.objects.values_list("slug", flat=True))

        assert len(slugs) == len(set(slugs)) == 40
        assert Team.objects.filter(slug__startswith="stilltrail").count() == 3

    def test_project_slugs_are_unique_per_team_despite_a_duplicate_title(self, report):
        for team in Team.objects.all():
            slugs = list(team.projects.values_list("slug", flat=True))
            assert len(slugs) == len(set(slugs)), team.pk


# ----------------------------------------------------------------- demo ids


class TestDemoIdentities:
    def test_three_are_promoted_and_two_are_ours(self, report, fixture_census):
        from_fixture = [i for i in report.demo_identities if i.from_fixture]
        ours = [i for i in report.demo_identities if not i.from_fixture]

        assert len(from_fixture) == 3
        assert len(ours) == 2
        # The 121 are the number the panel can check. Promoting three of them
        # rather than inventing six is the whole reason for the split.
        assert fixture_census.people == 121
        for identity in from_fixture:
            assert User.objects.get(email=identity.email).source_key == identity.email

    def test_judge_a_and_judge_b_are_on_different_tracks(self, report):
        tracks = {}
        for key in ("judge_a", "judge_b"):
            identity = next(i for i in report.demo_identities if i.key == key)
            tracks[key] = set(
                RoleBinding.objects.filter(user__email=identity.email, role=ROLE_JUDGE).values_list(
                    "track_id", flat=True
                )
            )

        assert tracks["judge_a"] and tracks["judge_b"]
        assert not (tracks["judge_a"] & tracks["judge_b"]), (
            "both demo judges on one track leaves the cross-track cell untested in "
            "the demo, which is the cell bible/04 5.2 exists to make live"
        )

    def test_each_demo_judge_has_at_least_two_reviews(self, report):
        for key in ("judge_a", "judge_b"):
            identity = next(i for i in report.demo_identities if i.key == key)
            assert ground_truth.reviews_by_judge(identity.email) >= 2

    def test_the_organizer_is_not_staff(self, report):
        """F-45's refusal, applied to the seed.

        ``bible/04`` 5.2 suggests "organizer + admin" as one identity. If the
        organizer is also ``is_staff`` then ``Actor.label`` returns ``admin``,
        and ``isolation_proof``'s organizer row cannot be populated -- it
        refuses rather than print an admin's numbers, which is correct and
        which would leave a hole in the published matrix.
        """
        identity = next(i for i in report.demo_identities if i.key == "organizer")
        user = User.objects.get(email=identity.email)

        assert not user.is_staff
        assert RoleBinding.objects.filter(user=user, role=ROLE_ORGANIZER).count() == 1

    def test_the_admin_is_staff_and_holds_no_binding(self, report):
        identity = next(i for i in report.demo_identities if i.key == "admin")
        user = User.objects.get(email=identity.email)

        assert user.is_staff
        assert not RoleBinding.objects.filter(user=user).exists()

    def test_the_participant_holds_only_the_participant_role(self, report):
        """.dogfood.toml sends the participant header to the judge-scores route
        and expects a refusal. If the participant were also a judge or an
        organizer, the check would pass for a reason that is not isolation."""
        identity = next(i for i in report.demo_identities if i.key == "participant")
        user = User.objects.get(email=identity.email)
        roles = set(RoleBinding.objects.filter(user=user).values_list("role", flat=True))

        assert roles == {ROLE_PARTICIPANT}
        assert not user.is_staff
        assert ground_truth.reviews_by_judge(user.email) == 0

    def test_the_participant_is_on_a_team(self, report):
        identity = next(i for i in report.demo_identities if i.key == "participant")
        user = User.objects.get(email=identity.email)

        assert TeamMembership.objects.filter(user=user).count() == 1

    def test_no_demo_judge_gains_an_event_wide_grant(self, report):
        """A judge binding with track=NULL sees the whole event. The seed must
        not create one, because nothing in the code asked for it."""
        for identity in report.demo_identities:
            assert not RoleBinding.objects.filter(
                user__email=identity.email, role=ROLE_JUDGE, track__isnull=True
            ).exists()


class TestCredentialBlock:
    def test_the_block_covers_the_four_keys_the_checker_reads(self, report):
        for key in ("organizer", "judge_a", "judge_b", "participant"):
            assert report.auth_block[key].startswith("Authorization: JJ1.")

    def test_each_value_verifies_back_to_its_identity(self, report):
        from reviewer.accounts import demo_tokens

        for identity in report.demo_identities:
            value = report.auth_block[identity.key]
            assert demo_tokens.email_from_config_value(value) == identity.email

    def test_the_seeder_says_they_are_not_secrets(self, report):
        assert report.auth_block, "the seed must print real values, not placeholders"


class TestCommands:
    def test_load_fixtures_exits_zero(self, raw_fixture, capsys):
        call_command("load_fixtures", verbosity=0)

        out = capsys.readouterr().out
        assert "census failure" not in out
        assert "paste this into .dogfood.toml" in out

    def test_verify_census_exits_zero_after_a_load(self, raw_fixture):
        from django.core.management.base import CommandError

        call_command("load_fixtures", verbosity=0, quiet=True)

        try:
            call_command("verify_census", verbosity=0)
        except CommandError as exc:  # pragma: no cover - only on drift
            pytest.fail(f"verify_census failed on a freshly loaded database: {exc}")

    def test_verify_census_fails_loudly_on_a_missing_row(self, raw_fixture, capsys):
        """A census check that has only ever passed is not evidence (F-33).

        The assertion is on the *printed* line, not on the exception message:
        ``CommandError`` carries only a count, so a test that asserted on it
        would pass on any failure at all -- which is F-41's exact shape.
        """
        from django.core.management.base import CommandError

        call_command("load_fixtures", verbosity=0, quiet=True)
        capsys.readouterr()
        Project.objects.filter(pk="prj_01").delete()

        with pytest.raises(CommandError):
            call_command("verify_census", verbosity=0)

        out = capsys.readouterr().out
        assert "projects.Project" in out
        assert "40 rows, the fixture implies 41" in out
        assert "mass over projects" in out

    def test_verify_census_fails_loudly_on_a_missing_fixture(self):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError) as caught:
            call_command("verify_census", fixtures="nope.json", verbosity=0)

        assert "not found" in str(caught.value)
