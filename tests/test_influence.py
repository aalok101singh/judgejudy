"""The influence report (D-13): the anti-abuse answer, and its two failure modes.

**The acceptance line for FEAT-06 is "the influence report renders for a
synthetic attack", and this file is that clause.** It builds a real brigade in the
database -- a bloc of identical ballots backing one project -- and asserts the
report *finds it and puts it first*, which is the whole claim. A test that built
a brigade and then asserted the report was "correct" without checking that the
brigade was visible would satisfy the shape and none of the meaning (F-61).

**The two failure modes this file exists to prevent, and both have a precedent in
the ledger:**

* **F-61 / F-69 / F-71, the fifth time.** The shipped fixture has **zero votes**.
  An implementation that iterated the projects and printed a row for each would
  emit forty-one lines of ``gini 0.00`` and a reader would conclude the event was
  checked and found clean. It was not checked; nothing was cast. So the empty
  case is asserted to be a *sentence*, and there is a test that fails if any
  table of zeros appears.
* **A report that accuses.** A Gini is a measurement, and a report that presents
  it without saying what it cannot conclude is a machine for accusing an
  enthusiastic table of friends. `TestTheReportDoesNotAccuse` asserts the caveat
  travels with every rendering, because a person skimming a table does not read
  docstrings.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest
from django.core.management import call_command
from django.test import Client

from reviewer.ballots import influence as influence_module
from reviewer.ballots.models import Ballot, Vote
from reviewer.isolation.refusal import REFUSED_BY_HEADER

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------- the fixture


@pytest.fixture(scope="module")
def raw_fixture() -> dict:
    return json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture
def loaded(raw_fixture):
    from reviewer.importer import loader as loader_module

    loader_module.load(raw_fixture)


@pytest.fixture
def event(loaded):
    from reviewer.events.models import Event

    return Event.objects.get(pk="evt_01")


@pytest.fixture
def projects(event):
    from reviewer.projects.models import Project

    return list(Project.objects.filter(event=event).order_by("source_key"))


# ------------------------------------------------------------- building an attack


def cast(event, project, voters, *, weight: int = 1, first: bool = True):
    """Cast one ballot per voter in ``voters``, all naming ``project`` first.

    **Identical ballots on purpose.** Every voter in a bloc gets the *same*
    order and the *same* weights, which is what the clustering detector keys on
    and what a real brigade would produce. If the detector only fired on
    near-identical vectors, this fixture would be too easy.
    """
    for index, voter in enumerate(voters):
        Ballot.objects.create(
            event=event,
            voter_key=voter,
            seed=f"seed-{voter}",
            order=[project.source_key, f"filler-{index}-{voter}"],
        )
        Vote.objects.create(event=event, project=project, voter_key=voter, weight=weight)


def cast_behind(event, project, voters):
    """Identical ballots in which ``project`` is **not** the first preference.

    **This is the fixture the ranking test needs, and building it is the point.**
    The first version of the acceptance test put the brigaded project first on
    every bloc ballot -- which is the realistic story, and which quietly made the
    test unfalsifiable: the target also led on first-preference share, so deleting
    the cluster key from the sort still ranked it first and the acceptance clause
    passed on a report that would not actually surface a brigade. The mutation
    harness caught it (58/59, "the ranking stops ordering by brigade size").

    Here the brigade's support is *identical* but *late* on the ballot, and the
    organic projects carry the first preferences. The only reason the target can
    reach the top of this report is the cluster detector, so a test that passes
    now genuinely tests the ranking rather than the tie-break.
    """
    for voter in voters:
        Ballot.objects.create(
            event=event,
            voter_key=voter,
            seed=f"seed-{voter}",
            order=[f"pad-{voter}", project.source_key],
        )
        Vote.objects.create(event=event, project=project, voter_key=voter, weight=1)


def organic(event, project, voters, *, distractors=()):
    """Scattered, individually distinct, and **first** preference.

    The other half of `cast_behind`'s fixture: these carry the first preferences,
    so the report's tie-break on first-preference share actively pushes the
    brigade *down* the ranking.

    **The ``distractors`` are load-bearing and the first version omitted them.**
    An identity is clustered by its *whole* vote vector, so nine voters who each
    backed exactly one project at weight 1 have byte-identical vectors -- and the
    "organic control" was itself a brigade of nine. It was found by running the
    report in the real container, where every row came back `clustered 9` and the
    control distinguished nothing. A green test suite did not catch it, because
    the assertions never said the organic rows *should not* be clustered.

    Each organic voter therefore backs ``project`` at a distinct weight **and** a
    distinct set of ``distractors``, so their vectors genuinely differ. A real
    ballot ranks projects, so this is the realistic shape and the trivial one was
    not.
    """
    for index, voter in enumerate(voters):
        order = [project.source_key, f"pad-{index}-{voter}"]
        Ballot.objects.create(
            event=event,
            voter_key=voter,
            seed=f"seed-{voter}",
            order=order,
        )
        Vote.objects.create(event=event, project=project, voter_key=voter, weight=index + 1)
        for position, other in enumerate(distractors):
            Vote.objects.create(event=event, project=other, voter_key=voter, weight=position + 1)


# ------------------------------------------------------------------------- gini


class TestGini:
    """The estimator itself, including the two edges it is honest about."""

    def test_perfectly_equal_values_are_zero(self):
        assert influence_module.gini([2, 2, 2, 2]) == 0.0

    def test_one_identity_carrying_everything_is_near_one(self):
        """The upper edge. 3 of 4 identities hold nothing gives 0.75."""
        assert influence_module.gini([12, 0, 0, 0]) == pytest.approx(0.75)

    def test_a_single_value_is_a_structural_zero_and_the_docstring_says_why(self):
        """**F-10's shape.** One identity cannot be differentially concentrated.

        A single enthusiastic voter is not a brigade, and reporting 1.0 would
        make them the most suspicious thing in the event.
        """
        assert influence_module.gini([5]) == 0.0

    def test_an_empty_population_is_none_and_not_zero(self):
        """**F-13's rule.** `None` is not `0`, and the difference is the point.

        A caller testing ``if gini`` cannot tell "no data" from "perfectly even",
        so an event with no votes would render the most innocent project in it.
        """
        assert influence_module.gini([]) is None

    def test_gini_is_symmetric_under_permutation(self):
        """It is a statistic of the multiset, so order cannot change it."""
        values = [1, 4, 9, 16, 25]
        assert influence_module.gini(values) == influence_module.gini(list(reversed(values)))


# ------------------------------------------------------- the acceptance line


class TestTheReportRendersForASyntheticAttack:
    """FEAT-06's acceptance clause. A real brigade, made real, then found."""

    def test_a_brigade_is_reported_and_ranked_first(self, event, projects):
        """**The clause itself, and the fixture is built to make it falsifiable.**

        The bloc's ballots are identical and the bloc's project is **not** their
        first preference, while the organic projects carry every first
        preference. So the report's last tie-break actively pushes the brigade
        *down*, and the only thing that can put it first is the cluster detector.

        The obvious first version of this test cast realistic ballots -- the
        brigade ranking its target first -- and it passed against a report with
        the cluster key deleted from the sort, because the target also led on
        first-preference share. That is F-41 in a new file: an assertion that
        cannot distinguish the two defects it is supposed to name. `just
        mutation-test` found it, and this is the repair.
        """
        target, *rest = projects
        cast_behind(event, target, [f"bloc-{i:02d}" for i in range(12)])
        for index, other in enumerate(rest[:5]):
            organic(
                event,
                other,
                [f"organic-{index}-{i}" for i in range(9)],
                distractors=rest[5:7],
            )

        report = influence_module.report(event)
        assert report is not None, "the report is None despite votes having been cast"
        assert report["ranking"], "the report rendered an empty ranking"

        top = report["ranking"][0]
        assert top["project"] == target.source_key, (
            "the brigaded project is not ranked first; the report does not surface an "
            "attack, which is the entire claim. The fixture puts every first "
            "preference on the organic projects, so only the cluster detector can "
            "produce this ranking: " + json.dumps(report["ranking"], indent=2)
        )
        assert top["clustered_identities"] == 12, (
            "the brigade is first for a reason other than being a brigade"
        )

    def test_the_organic_voters_are_not_also_flagged_as_a_brigade(self, event, projects):
        """**The assertion whose absence let a broken fixture pass.**

        The first version of this file gave every "organic" voter a single vote on
        a single project, which made their vote vectors byte-identical -- so the
        control was a brigade of nine and it flagged `9` on every row. The suite
        stayed green, because nothing ever asserted the organic rows *should not*
        be clustered. Running the report in the real container is what showed it.

        **A green test suite did not catch a fixture that could not distinguish
        its own subject from its control**, and the honest statement is that this
        is the same lesson as F-41 reached from the other direction: a test that
        cannot fail is not a test, and a *fixture* that cannot separate the case
        under test from its control is the same defect wearing different clothes.
        """
        target, *rest = projects
        cast_behind(event, target, [f"bloc-{i:02d}" for i in range(12)])
        for index, other in enumerate(rest[:5]):
            organic(
                event,
                other,
                [f"organic-{index}-{i}" for i in range(9)],
                distractors=rest[5:7],
            )

        report = influence_module.report(event)
        organic_rows = [r for r in report["ranking"] if r["project"] != target.source_key]
        assert organic_rows, "the fixture produced no control rows to check"
        for row in organic_rows:
            assert row["clustered_identities"] == 0, (
                f"{row['project']} was flagged as a brigade of "
                f"{row['clustered_identities']} but its voters cast distinct "
                "ballots -- the control is broken, not the detector"
            )

    def test_the_brigade_is_flagged_by_the_cluster_detector(self, event, projects):
        """The numbers that *name* the attack, asserted against its own row.

        **An identical brigade has Gini 0, and that is a fact worth pinning.**
        Twelve equal ballots are perfectly *evenly distributed* among themselves,
        so the Gini is the wrong instrument for this shape and the exact-match
        cluster detector is the right one. Asserting the Gini is 0 here is what
        stops a later reader "fixing" the report by ranking on Gini alone and
        losing every brigade in the process.
        """
        target, *rest = projects
        cast(event, target, [f"bloc-{i:02d}" for i in range(12)])
        for index, other in enumerate(rest[:5]):
            organic(
                event,
                other,
                [f"organic-{index}-{i}" for i in range(9)],
                distractors=rest[5:7],
            )

        report = influence_module.report(event)
        row = next(r for r in report["ranking"] if r["project"] == target.source_key)
        assert row["identities"] == 12
        assert row["clustered_identities"] == 12, "the brigade was not flagged"
        assert row["vote_mass_gini"] == pytest.approx(0.0), (
            "identical ballots carry equal mass, so the bloc's own Gini is 0 -- the "
            "concentration shows up in the *cluster* detector, not the Gini. If this "
            "fails the fixture changed, not the code."
        )
        assert row["first_preference_share"] > 0.0, "the brigade cast no first preferences"

    def test_a_lopsided_project_outranks_an_evenly_backed_one(self, event, projects):
        """**The other direction, and the reason Gini is here at all.**

        A brigade that piles *unequal* weight onto one project -- one identity
        with a big vote, the rest small -- is invisible to the cluster detector
        and obvious to the Gini. Both shapes of attack are covered, and the test
        that would fail if the Gini were computed over the wrong population is
        this one.
        """
        target, *rest = projects
        for index, voter in enumerate(f"heavy-{i:02d}" for i in range(4)):
            Vote.objects.create(
                event=target.event, project=target, voter_key=voter, weight=20 if index == 0 else 1
            )
        for index, other in enumerate(rest[:4]):
            for voter in (f"flat-{index}-{i}" for i in range(8)):
                Vote.objects.create(event=event, project=other, voter_key=voter, weight=1)

        report = influence_module.report(event)
        heavy = next(r for r in report["ranking"] if r["project"] == target.source_key)
        flat = next(r for r in report["ranking"] if r["project"] == rest[0].source_key)
        assert heavy["vote_mass_gini"] > flat["vote_mass_gini"], (
            f"a lopsided project ({heavy['vote_mass_gini']}) must read as more "
            f"concentrated than an evenly-backed one ({flat['vote_mass_gini']})"
        )


# ------------------------------------------------------------- the empty case


class TestTheReportRefusesToBeATableOfZeros:
    """F-61, the fifth time, in the place a clean build would show it."""

    def test_no_votes_yields_none_and_not_an_empty_report(self, event):
        """**The assertion that must not be `== {}`.** An empty report is a value
        a caller could render as a table; ``None`` cannot be."""
        assert influence_module.report(event) is None, (
            "the report returned a structure for an event with no votes. That is the "
            "F-61 shape: valid output containing nothing."
        )

    def test_the_command_says_there_is_nothing_rather_than_printing_a_table(self, event):
        out = io.StringIO()
        call_command("influence_report", event=event.pk, stdout=out)
        text = out.getvalue()
        assert "NO VOTES HAVE BEEN CAST" in text
        assert "NOT a" in text and "finding" in text, (
            "the command must say this is not a clean bill of health; a bare "
            "'no votes' reads as reassurance"
        )
        assert "gini" not in text, "the command printed a table on an event with no votes"

    def test_the_api_says_no_votes_and_says_why(self, event):
        from reviewer.accounts.demo_tokens import mint
        from reviewer.accounts.models import User
        from reviewer.importer import census as census_module
        from reviewer.importer import demo as demo_module

        organizer = demo_module.choose(
            census_module.census(json.loads((REPO / "fixtures.json").read_text(encoding="utf-8")))
        )
        email = next(i.email for i in organizer if "organizer" in i.key)
        assert User.objects.filter(email=email).exists()

        client = Client(HTTP_AUTHORIZATION=mint(email))
        response = client.get("/api/v1/influence")
        assert response.status_code == 200
        body = json.loads(response.content.decode())
        assert body["status"] == "no_votes"
        assert "not a finding" in body["reason"]
        assert body["ranking"] == []


# ------------------------------------------------------------------ the caveat


class TestTheReportDoesNotAccuse:
    """A Gini is a measurement. The report has to say what it cannot conclude."""

    def test_the_caveat_travels_with_the_payload(self, event, projects):
        target = projects[0]
        cast(event, target, [f"bloc-{i}" for i in range(6)])
        report = influence_module.report(event)
        assert "not proof" in report["interpretation"]
        assert "does not name a culprit" in report["interpretation"]

    def test_the_command_prints_the_caveat_and_not_only_the_table(self, event, projects):
        target = projects[0]
        cast(event, target, [f"bloc-{i}" for i in range(6)])
        out = io.StringIO()
        call_command("influence_report", event=event.pk, stdout=out)
        text = out.getvalue()
        assert "not proof" in text, "the rendered table shipped without its caveat"
        assert target.source_key in text, "the table did not name the project it flagged"

    def test_identical_ballots_need_not_be_malicious_and_the_report_says_so(self):
        """The exact-match cluster is a *signature*, not a conviction."""
        assert "enthusiastic" in influence_module.INTERPRETATION
        assert "brigade" in influence_module.INTERPRETATION


# ----------------------------------------------------------------- the detector


class TestTheClusterDetectorIsExact:
    def test_two_identities_with_the_same_ballot_are_a_cluster(self):
        vectors = {"a": {"p": 1}, "b": {"p": 1}}
        assert influence_module.identical_ballot_clusters(vectors) == {"p": 2}

    def test_one_weight_apart_is_not_the_same_ballot(self):
        """The limitation is a design choice, so it is pinned by a test."""
        vectors = {"a": {"p": 1}, "b": {"p": 2}}
        assert influence_module.identical_ballot_clusters(vectors) == {}

    def test_backing_the_same_project_differently_is_not_a_cluster(self):
        """Sharing a preference is not sharing a ballot."""
        vectors = {"a": {"p": 1, "q": 1}, "b": {"p": 1, "r": 1}}
        assert influence_module.identical_ballot_clusters(vectors) == {}

    def test_a_lone_identity_is_never_a_cluster(self):
        assert influence_module.identical_ballot_clusters({"a": {"p": 1}}) == {}


class TestTheDegenerateMetricStaysCut:
    """**F-76, pinned.** The `lift` column was built, measured and removed.

    It is tempting to add a "lift" back -- first-preference share over voter
    share reads like the obvious detector, and `bible/06` §6.2's worked example is
    phrased in those terms. It was shipped in the first draft and the synthetic
    attack scored it at **exactly 1.0**, because every voter casts one first
    preference, so a project's backers are its first-preferencers in the normal
    case and the ratio is identically 1. **A column that looks like a detector and
    is not one is worse than no column**, because a reader reasons about a "lift
    of 1.0" as if it meant something.

    This test is the only thing stopping a later session from re-deriving it,
    which is the whole reason a cut belongs in a test and not only in a docstring.
    """

    def test_no_row_carries_a_lift_field(self, event, projects):
        target, *rest = projects
        cast(event, target, [f"bloc-{i}" for i in range(12)])
        for index, other in enumerate(rest[:3]):
            organic(
                event,
                other,
                [f"organic-{index}-{i}" for i in range(9)],
                distractors=rest[3:5],
            )
        report = influence_module.report(event)
        for row in report["ranking"]:
            assert "lift" not in row, f"the degenerate lift metric is back: {row}"
            assert "voter_share" not in row, f"voter_share only existed to feed lift: {row}"

    def test_the_method_string_does_not_advertise_lift(self):
        assert "lift" not in influence_module.REPORT_METHOD


# --------------------------------------------------------------------- isolation


class TestTheReportIsOrganizerOnly:
    def test_a_judge_is_refused_and_the_refusal_names_its_guard(self, event):
        from reviewer.accounts.demo_tokens import mint

        judge = "amara.okafor@example.org"
        response = Client(HTTP_AUTHORIZATION=mint(judge)).get("/api/v1/influence")
        assert response.status_code == 403
        assert response.content == b"", "D-02: a refusal body is empty"
        assert "Location" not in response.headers
        assert response.headers.get(REFUSED_BY_HEADER) == "api.influence.role"

    def test_the_report_is_readable_while_the_event_is_still_hidden(self, event):
        """**The asymmetry, and it is the design.**

        `results_visible_to` lets an *organizer* read the leaderboard at any time
        (`can_read_all_reviews`), so the meaningful contrast is not
        organizer-vs-organizer. It is **the guard**: the leaderboard's refusal is
        `api.results.hidden`, which is a *state* guard, and this report's refusal
        is `api.influence.role`, which is a *role* guard. The report must not
        consult `results_state` at all, because an organizer has to see how
        concentrated the support is **before** deciding to publish. Gating it
        behind publication would turn a preventive report into a post-mortem.
        """
        from django.urls import reverse

        from reviewer.accounts.demo_tokens import mint
        from reviewer.importer import census as census_module
        from reviewer.importer import demo as demo_module

        assert event.results_state == "hidden", (
            "this test's premise is that results are hidden on the shipped fixture"
        )
        identities = demo_module.choose(
            census_module.census(json.loads((REPO / "fixtures.json").read_text(encoding="utf-8")))
        )
        email = next(i.email for i in identities if "organizer" in i.key)
        client = Client(HTTP_AUTHORIZATION=mint(email))

        report = client.get(reverse("influence"))
        assert report.status_code == 200, (
            "the influence report must be readable while results are hidden; gating it "
            "behind publication turns a preventive report into a post-mortem"
        )
        assert json.loads(report.content.decode())["status"] == "no_votes"

    def test_the_report_never_refuses_on_the_state_guard(self, event):
        """The refusal is about the ROLE and nothing else.

        If a judge is refused here, the header must name the role guard -- never
        `api.results.hidden`, which would mean this endpoint had started sharing
        the leaderboard's state gate and lost the ability to work before
        publication.
        """
        from django.urls import reverse

        from reviewer.accounts.demo_tokens import mint

        response = Client(HTTP_AUTHORIZATION=mint("amara.okafor@example.org")).get(
            reverse("influence")
        )
        assert response.status_code == 403
        assert response.headers[REFUSED_BY_HEADER] == "api.influence.role"
