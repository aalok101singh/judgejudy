"""The leaderboard, the audit chain, and the three matrix cells that used to be `?`.

**Three traps, each with a test named for it.**

1. **A refusal is not a zero.** The isolation matrix has to be able to say
   "refused" as distinct from "permitted, and there is nothing". A judge reading
   the aggregate column as ``0/41`` would conclude there are no projects, when in
   fact there are 41 and this actor may not see the ranking of them. This is the
   same distinction the API makes and the ``UNPROVEN`` docstring in
   ``isolation_proof.py`` names as the option to avoid.

2. **A chain that nothing appends to is a valid chain of nothing.** At FEAT-06 the
   audit table existed with ``seq``/``prev_hash``/``entry_hash`` and
   ``count() == 0`` on a fully seeded event -- and the isolation proof could
   already verify that it was append-only without ever checking that it existed.
   So there is a test that the chain is **non-empty after a real action**, and one
   that a tampered row is **caught**, because "verifies" over zero entries is
   trivially true and would be a second structurally-valid-nothing.

3. **An unnormalized ranking must say it is unnormalized.** The leaderboard is a
   raw weighted mean; judge-severity correction is FEAT-08. A ranking that does
   not label itself invites a reader to assume it is corrected, and that is the
   assumption the whole detectability analysis exists to prevent.
"""

from __future__ import annotations

import itertools
import json
import pathlib

import pytest
from django.db import connection
from django.test import Client
from django.urls import reverse

from reviewer.audit import chain as chain_module
from reviewer.audit.models import AuditEntry
from reviewer.isolation.refusal import REFUSED_BY_HEADER

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent


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
def identities(event, raw_fixture) -> dict:
    from reviewer.accounts.models import User
    from reviewer.importer import census as census_module
    from reviewer.importer import demo as demo_module

    chosen = demo_module.choose(census_module.census(raw_fixture))
    return {identity.key: User.objects.filter(email=identity.email).first() for identity in chosen}


def _client_for(email: str) -> Client:
    from reviewer.accounts.demo_tokens import mint

    return Client(HTTP_AUTHORIZATION=mint(email))


def _body(response) -> dict:
    return json.loads(response.content.decode())


def _assert_refused(response, guard: str) -> None:
    assert response.status_code == 403
    assert response.content == b"", "D-02: a refusal body is empty"
    assert "Location" not in response.headers
    assert response.headers.get(REFUSED_BY_HEADER) == guard


def _tamper(event, **columns) -> None:
    """Edit an audit row the way somebody with database access would.

    **Bypassing the ORM guard is the point, and the guard is real:**
    ``AuditQuerySet.update`` and ``.delete`` both raise ``TypeError``, which
    `manage.py isolation_proof` already asserts. So the interesting question is
    not whether the application can corrupt the trail -- it cannot -- but whether
    the **chain** notices corruption that arrived by another route. Raw SQL is
    that route, and it is the only way to test the second half of the claim.
    """
    assignments = ", ".join(f"{column} = %s" for column in columns)
    values = [*columns.values(), str(event.pk)]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE audit_auditentry SET {assignments} WHERE event_id = %s",  # noqa: S608
            values,
        )


def _raw_delete(event, seq: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM audit_auditentry WHERE event_id = %s AND seq = %s", [str(event.pk), seq]
        )


# ------------------------------------------------------------------ the aggregate


class TestTheLeaderboardIsRefusedWhileResultsAreHidden:
    """**Trap 1, and the cell the proof called "nobody tests and everybody forgets"**."""

    def test_the_fixture_is_born_with_results_hidden(self, event):
        """The rule has to rest on a real field, not on a comment.

        If a future loader stops setting ``results_state``, this test fails and
        the refusal below starts silently permitting a judge to read the
        standings during judging -- which is the exact leak the cell exists for.
        """
        assert event.results_state == "hidden"

    def test_a_judge_is_refused_the_leaderboard(self, identities, event):
        from reviewer.reviews import api as api_module

        _assert_refused(
            _client_for(identities["judge_a"].email).get(reverse("results")),
            api_module.REFUSED_BY_RESULTS,
        )

    def test_a_participant_and_a_visitor_are_refused_too(self, identities, event):
        _assert_refused(
            _client_for(identities["participant"].email).get(reverse("results")),
            "api.results.hidden",
        )
        _assert_refused(Client().get(reverse("results")), "api.results.hidden")

    def test_an_organizer_sees_the_whole_event(self, identities, event):
        response = _client_for(identities["organizer"].email).get(reverse("results"))
        assert response.status_code == 200
        payload = _body(response)
        assert payload["count"] == 41, "every project has at least one answered score"

    def test_the_ranking_is_labelled_unnormalized(self, identities, event):
        """**Trap 3.** A ranking that does not say it is corrected invites the
        reader to assume it is, and that assumption is the whole risk."""
        payload = _body(_client_for(identities["organizer"].email).get(reverse("results")))
        assert payload["normalization"] == "unnormalized-raw-weighted-mean"
        for row in payload["ranking"]:
            assert row["normalization"] == "unnormalized-raw-weighted-mean"

    def test_the_ranking_is_ordered_and_complete(self, identities, event):
        payload = _body(_client_for(identities["organizer"].email).get(reverse("results")))
        board = payload["ranking"]
        assert [r["rank"] for r in board] == list(range(1, len(board) + 1))
        means = [r["mean"] for r in board]
        assert means == sorted(means, reverse=True), "rank order must match the means"

    def test_a_published_event_opens_it_to_everybody(self, identities, event):
        """**The other direction, and the one that makes the refusal a policy
        rather than a permanent block.** A test that only checks "refused" would
        pass against a rule that refuses everyone always.

        The first version of this asserted ``count == 41`` for the judge too, and
        **it failed at 4** -- which is the scope working: publishing the results
        opens the endpoint, it does not widen the scope. So the assertion is
        `> 0` here and the *relationship* is asserted separately below, where a
        change to either number is caught with a message that says which one
        moved.
        """
        event.results_state = "published"
        event.save(update_fields=["results_state"])

        for key in ("judge_a", "participant"):
            response = _client_for(identities[key].email).get(reverse("results"))
            assert response.status_code == 200, key
            assert _body(response)["results_state"] == "published", key

    def test_a_judge_published_still_sees_a_ranking_over_a_scoped_set(self, identities, event):
        """A published ranking for a judge is over *their* reviews, not the event's.

        This is why the refusal matters while results are hidden: without it, the
        scoped set would already be a five-row leaderboard that still leaks the
        standing.
        """
        event.results_state = "published"
        event.save(update_fields=["results_state"])
        judge = identities["judge_a"]

        payload = _body(_client_for(judge.email).get(reverse("results")))
        organizer_view = _body(_client_for(identities["organizer"].email).get(reverse("results")))

        assert payload["count"] < organizer_view["count"], (
            "a judge must not see the whole event's ranking even once results are "
            "published -- the scope still applies"
        )
        assert payload["count"] > 0


# ------------------------------------------------------------------------ audit


class TestTheAuditChain:
    """**Trap 2: a chain nothing appends to verifies trivially and means nothing.**"""

    def test_a_fully_seeded_event_has_an_empty_chain(self, loaded, event):
        """**The defect, stated as its own test so it cannot regress silently.**

        This is the F-61 shape for the fourth time. Nothing had ever written an
        ``AuditEntry``, so the isolation matrix's audit column had a
        structurally valid answer of zero and `verify_chain` returned no problems
        over an empty sequence -- which is what "verifies" means when there is
        nothing to verify.
        """
        assert AuditEntry.objects.count() == 0, (
            "if this now fails, the seed writes audit entries, which is better. "
            "It failed at FEAT-06 and that is the finding."
        )

    def test_a_real_action_appends_exactly_one_entry(self, identities, event):
        response = _client_for(identities["organizer"].email).get(reverse("csv_export"))
        assert response.status_code == 200

        entries = AuditEntry.objects.filter(event=event)
        assert entries.count() == 1
        entry = entries.get()
        assert entry.action == chain_module.ACTION_EXPORT_RUN
        assert entry.actor == identities["organizer"]
        assert entry.seq == 1
        assert entry.prev_hash == "", "the first link chains to nothing"

    def test_a_denial_is_logged_too(self, identities, event):
        """The model's own docstring: "why denials are logged" -- a run of refused
        peer-score requests is exactly the signal an organizer wants, and it is
        free here."""
        _client_for(identities["judge_b"].email).get(reverse("judge_scores"), {"judge": "judge_a"})
        entry = AuditEntry.objects.get(action=chain_module.ACTION_DENIED)
        assert entry.after["guard"] == "api.judge_scores.peer_scope"

    def test_the_chain_is_sequential_and_links(self, identities, event):
        for _ in range(3):
            _client_for(identities["organizer"].email).get(reverse("csv_export"))
        entries = list(AuditEntry.objects.order_by("seq"))
        assert [e.seq for e in entries] == [1, 2, 3]
        assert entries[0].prev_hash == ""
        for previous, current in itertools.pairwise(entries):
            assert current.prev_hash == previous.entry_hash

    def test_a_fresh_chain_verifies(self, identities, event):
        for _ in range(2):
            _client_for(identities["organizer"].email).get(reverse("csv_export"))
        assert chain_module.verify_chain(event) == []

    def test_an_empty_chain_verifies_and_that_is_not_evidence(self, loaded, event):
        """**Stated explicitly, because "no problems" over zero entries is the
        most misleading PASS available.** The test above the class is the one that
        catches it."""
        assert chain_module.verify_chain(event) == []
        assert AuditEntry.objects.count() == 0

    def test_an_edited_row_is_caught(self, identities, event):
        """**In-place tampering, which is the case a chain exists for and the one a
        signed list would miss.** The hash covers the payload, so changing `after`
        is detected even though `entry_hash` is untouched."""
        _client_for(identities["organizer"].email).get(reverse("csv_export"))
        _tamper(event, after=json.dumps({"rows": 99999}))

        problems = chain_module.verify_chain(event)
        assert problems, "an edited row must be reported"
        assert any("does not hash to its recorded digest" in p for p in problems)

    def test_a_deleted_row_is_caught_as_a_sequence_gap(self, identities, event):
        """**One failure mode, one test, one message.**

        The first version of this asserted ``"is missing" in p or "prev_hash" in
        p`` over a chain of three with the middle row deleted -- and **removing
        either check from `verify_chain` left it green**, because an `or` is
        satisfied by whichever check survived. That is F-41's defect in a new
        file: an assertion that cannot distinguish the two defects it names, so it
        passes against half the implementation. Deleting a row raises *both* a gap
        and a broken link, and the two are now asserted separately, each against
        its own message.
        """
        for _ in range(3):
            _client_for(identities["organizer"].email).get(reverse("csv_export"))
        _raw_delete(event, 2)

        problems = chain_module.verify_chain(event)
        assert any("is missing" in p for p in problems), (
            f"deleting seq 2 of 3 is a sequence gap and must say so: {problems}"
        )

    def test_a_deleted_row_is_also_caught_as_a_broken_link(self, identities, event):
        """The second of the two, asserted on its own so neither can be dropped.

        The same deletion also leaves entry 3 pointing at a ``prev_hash`` that no
        longer follows from anything. Detecting only the gap would catch a
        *truncation*; detecting only the link would catch an *insertion*. They are
        different attacks and this is the test that says so.
        """
        for _ in range(3):
            _client_for(identities["organizer"].email).get(reverse("csv_export"))
        _raw_delete(event, 2)

        problems = chain_module.verify_chain(event)
        assert any("prev_hash does not match" in p for p in problems), (
            f"a deletion must also break the link, or an insertion is undetected: {problems}"
        )

    def test_an_inserted_row_is_caught_by_the_link_check_alone(self, identities, event):
        """**The insertion case, which the gap check cannot see at all.**

        An entry inserted with the *right* ``seq`` renumbers nothing and leaves no
        gap -- only the link is wrong. This is the reason `prev_hash` exists and
        it is the one tamper a sequence check alone would miss entirely.
        """
        for _ in range(2):
            _client_for(identities["organizer"].email).get(reverse("csv_export"))
        last = AuditEntry.objects.order_by("-seq").first()

        forged = AuditEntry(
            event=event,
            actor=None,
            action="results publish",
            seq=last.seq,
            prev_hash=last.prev_hash,
            after={},
        )
        forged.entry_hash = chain_module.compute_hash(forged)
        # Bypass `save()`'s uniqueness only to plant the row; the chain is what
        # has to notice it.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE audit_auditentry SET seq = seq + 1 WHERE event_id = %s AND seq = %s",
                [str(event.pk), str(last.seq)],
            )
            cursor.execute(
                "INSERT INTO audit_auditentry "
                "(event_id, actor_id, action, object_type, object_id, before, after, "
                "ip_hash, seq, prev_hash, entry_hash, omitted_since_prev, scope_reason, "
                "source_key, created_at, updated_at) "
                "VALUES (%s, NULL, %s, '', '', '{}', '{}', '', %s, %s, %s, 0, '{}', "
                "NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                [
                    str(event.pk),
                    "results publish",
                    str(last.seq),
                    last.prev_hash,
                    forged.entry_hash,
                ],
            )

        problems = chain_module.verify_chain(event)
        assert any("prev_hash does not match" in p for p in problems), (
            f"an inserted row must be caught by the link check: {problems}"
        )

    def test_the_verifier_command_fails_on_a_broken_chain(self, identities, event, capsys):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        _client_for(identities["organizer"].email).get(reverse("csv_export"))
        _tamper(event, after=json.dumps({"rows": 1}))

        with pytest.raises(CommandError):
            call_command("verify_audit", event=event.pk, show=0)


class TestTheAuditAccessor:
    def test_a_judge_is_refused_the_audit_view(self, identities, event):
        _assert_refused(
            _client_for(identities["judge_a"].email).get(reverse("audit")), "api.audit.role"
        )

    def test_a_participant_is_refused_too(self, identities, event):
        _assert_refused(
            _client_for(identities["participant"].email).get(reverse("audit")), "api.audit.role"
        )

    def test_an_organizer_sees_the_chain_and_whether_it_verifies(self, identities, event):
        _client_for(identities["organizer"].email).get(reverse("csv_export"))
        response = _client_for(identities["organizer"].email).get(reverse("audit"))
        payload = _body(response)

        assert response.status_code == 200
        assert payload["count"] == 1
        assert payload["verified"] is True
        assert payload["problems"] == []
        assert payload["entries"][0]["action"] == chain_module.ACTION_EXPORT_RUN

    def test_a_broken_chain_is_reported_in_the_same_response(self, identities, event):
        """**A reader who must run a second tool to learn whether the trail they
        were shown is intact will not run it.**"""
        _client_for(identities["organizer"].email).get(reverse("csv_export"))
        _tamper(event, after=json.dumps({"rows": 7}))

        payload = _body(_client_for(identities["organizer"].email).get(reverse("audit")))
        assert payload["verified"] is False
        assert payload["problems"], "verified=False with no explanation is a worse answer"


class TestTheMatrixCellsAreNoLongerQuestionMarks:
    """The proof's own output, asserted rather than eyeballed."""

    def test_no_cell_prints_a_question_mark(self, loaded, event, capsys):
        from django.core.management import call_command

        call_command("isolation_proof", event=event.pk)
        out = capsys.readouterr().out
        table = [
            line
            for line in out.splitlines()
            if line.strip().startswith(("visitor", "participant", "judge", "organizer", "admin"))
        ]
        assert table, "the matrix printed no rows at all"
        assert "?" not in "".join(table), "a capability column is still unproven:\n" + "\n".join(
            table
        )

    def test_a_refused_cell_is_the_word_refused_and_not_a_zero(self, loaded, event, capsys):
        """**Trap 1 at the level it will actually be read.**"""
        from django.core.management import call_command

        call_command("isolation_proof", event=event.pk)
        out = capsys.readouterr().out
        judge_row = next(line for line in out.splitlines() if line.strip().startswith("judge"))
        assert "refused" in judge_row, (
            f"the judge row must show a refusal, not a count:\n{judge_row}"
        )
        assert "0/41" not in judge_row, (
            f"0/41 would read as 'no projects' rather than 'you may not':\n{judge_row}"
        )

    def test_the_capability_sources_name_functions_not_features(self, event):
        from reviewer.reviews.management.commands import isolation_proof as ip

        for name, source in ip.CAPABILITY_SOURCES.items():
            assert "FEAT-" not in source, (
                f"the {name} column's provenance still names a feature rather than "
                f"the function that produces the number: {source!r}"
            )

    def test_the_still_not_proven_list_does_not_claim_the_columns_are_missing(
        self, loaded, event, capsys
    ):
        """A "still not proven" list that is not maintained is worse than none."""
        from django.core.management import call_command

        call_command("isolation_proof", event=event.pk)
        out = capsys.readouterr().out
        assert "they print `?`" not in out, (
            "the STILL NOT PROVEN list still says the columns are unbuilt"
        )
