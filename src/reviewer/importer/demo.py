"""The five identities the acceptance checker needs, and the rule that picks them.

**Three are promoted out of the fixture's 121 people; two are ours.** That split
is the decision, and it is worth being explicit about because the obvious
alternative -- mint six synthetic accounts -- quietly changes a number the panel
can check without running anything (121 fixture people becomes 127).

What is promoted, and why each one has to be a real fixture person:

``judge_a`` / ``judge_b``
    Two judges with reviews, on **different tracks**, each bound to exactly one.
    The different-track part is the whole point: with both on one track, the
    cross-track cell of the isolation matrix would be untested in the demo even
    though the code path exists. "Exactly one track each" is there so the
    isolation proof's judge row is populated by an actor whose *strongest* role
    is judge -- F-45's refusal, which is correct and which a dual-track judge
    would trip only by accident.

``participant``
    A member of the lowest-id team who is not a judge. ``.dogfood.toml`` sends
    the participant header to the judge-scores route and expects a refusal, so a
    participant who was also an organizer or a judge would make the check pass
    for a reason that is not the isolation model. The fixture's judges and
    members are disjoint, which is what makes "a member" sufficient.

What is ours, and why it cannot be promoted:

``organizer`` / ``admin``
    **Nobody in ``fixtures.json`` is an organizer**, so there is nothing to
    promote. And promoting a team member would be the wrong design: an organizer
    who competes in the event can export every score in it, which is a
    conflict-of-interest rule stated as a data-model accident. So these two are
    portal-created rows with ``source_key = NULL``, and the census reports them
    separately from the 121 so the two populations never get added together.

**Why the three are picked by a rule and not typed.** ``bible/04`` §5.2 names
``jdg_08`` and ``jdg_07`` in an example -- and names ``jdg_07`` as bound to
``trk_03``, which the fixture says is ``trk_06``. A planning document carrying a
transcribed track id is F-28's shape, so the loader reads the ids it needs out
of the file. The rule is "lowest id with at least two reviews and exactly one
track", applied twice with a disjointness condition, and it is a pure function
of the fixture -- so the same fixture always yields the same demo identities, and
a different fixture yields *some* defensible pair rather than a broken one.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The two addresses this portal owns. `@example.org` is the same reserved
#: documentation domain the fixture uses, so nothing here can be mistaken for a
#: real person -- and `example.org` is reserved by RFC 2606 precisely so that a
#: sample value can never belong to anyone.
ORGANIZER_EMAIL = "organizer@example.org"
ADMIN_EMAIL = "admin@example.org"

#: The minimum reviews a promoted judge must have. Two, not one: ``jdg_01`` and
#: ``jdg_23`` have exactly one review each, and a demo identity whose own-scores
#: page shows a single row makes "the judge sees their own scores" look like an
#: empty result rather than a working one.
MIN_JUDGE_REVIEWS = 2


@dataclass(frozen=True)
class DemoIdentity:
    """One identity the checker authenticates as, and the reason it is that one."""

    key: str
    email: str
    role: str
    reason: str
    from_fixture: bool
    is_staff: bool = False
    password: str = ""


def choose(fixture_census) -> list[DemoIdentity]:
    """The five identities, derived from a :class:`reviewer.importer.census.Census`.

    Pure. Takes the census rather than the raw fixture so the caller has already
    paid for the parse and so this function cannot quietly disagree with the
    numbers the census command prints.
    """
    by_judge = fixture_census.review_counts_by_judge
    tracks_of = _track_index(fixture_census)

    singles = sorted(
        judge_id
        for judge_id, tracks in tracks_of.items()
        if len(tracks) == 1 and by_judge.get(judge_id, 0) >= MIN_JUDGE_REVIEWS
    )
    if len(singles) < 2:
        raise ValueError(
            f"the fixture has {len(singles)} judge(s) with at least "
            f"{MIN_JUDGE_REVIEWS} reviews on exactly one track. The demo needs two on "
            "DIFFERENT tracks so the cross-track isolation cell is live in the demo. "
            "Inventing them would be inventing a person, which this project does not do."
        )

    judge_a = singles[0]
    judge_b = next(
        (j for j in singles[1:] if not set(tracks_of[j]) & set(tracks_of[judge_a])),
        None,
    )
    if judge_b is None:
        raise ValueError(
            "every judge with enough reviews shares a track with the first one, so "
            "judge_a and judge_b could not be on different tracks."
        )

    participants = fixture_census.first_team_members
    if not participants:
        raise ValueError("the fixture has no team members, so there is no participant to promote.")
    participant = participants[0]

    return [
        DemoIdentity(
            key="organizer",
            email=ORGANIZER_EMAIL,
            role="organizer",
            reason="ours, not the fixture's: nobody in fixtures.json is an organizer, and "
            "promoting a team member would make an organizer a competitor in the event "
            "they administer. Not is_staff, because the isolation proof's organizer row "
            "refuses to be populated by an actor whose strongest role is admin (F-45).",
            from_fixture=False,
            password="judgejudy-organizer",
        ),
        DemoIdentity(
            key="judge_a",
            email=_email_of(judge_a, fixture_census),
            role="judge",
            reason=f"lowest-id judge with >= {MIN_JUDGE_REVIEWS} reviews on exactly one "
            f"track ({judge_a}, {by_judge.get(judge_a, 0)} reviews, "
            f"{tracks_of[judge_a][0]}). Real reviews, so the own-scores check returns "
            "data rather than an empty list.",
            from_fixture=True,
            password="judgejudy-judge",
        ),
        DemoIdentity(
            key="judge_b",
            email=_email_of(judge_b, fixture_census),
            role="judge",
            reason=f"lowest-id judge after judge_a on a DIFFERENT track ({judge_b}, "
            f"{tracks_of[judge_b][0]} against {tracks_of[judge_a][0]}), so one live seed "
            "exercises peer isolation, track isolation and the cross-track cell together.",
            from_fixture=True,
            password="judgejudy-judge",
        ),
        DemoIdentity(
            key="participant",
            email=participant,
            role="participant",
            reason="first member of the lowest-id team, and not a judge. A participant who "
            "was also an organizer or a judge would make the participant-blocked check "
            "pass for a reason that is not the isolation model.",
            from_fixture=True,
            password="judgejudy-participant",
        ),
        DemoIdentity(
            key="admin",
            email=ADMIN_EMAIL,
            role="admin",
            reason="ours, not the fixture's. Admin is resolved from is_staff rather than "
            "from a RoleBinding, so the admin surfaces need a staff user; see "
            "reviewer.isolation.actor.Actor.",
            from_fixture=False,
            is_staff=True,
            password="judgejudy-admin",
        ),
    ]


def _track_index(fixture_census) -> dict[str, list[str]]:
    return fixture_census.judge_tracks


def _email_of(judge_id: str, fixture_census) -> str:
    return fixture_census.judge_emails[judge_id]
