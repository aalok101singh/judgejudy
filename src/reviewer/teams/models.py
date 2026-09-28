"""Teams, memberships and invites.

**The one decision here is the constraint that is deliberately *absent*.**

There is no uniqueness constraint on "a user in one team per event". The fixture
happily satisfies it -- every person is in exactly one team -- so adding the
constraint would pass every test we have and be wrong. But real events have
people who float between teams, they collaborate across them, and a organizer
importing an archive from a previous event will hit it immediately. A bulk
import that trips a database constraint on real input is a bad import path, and
this project is scored on being a platform somebody can get their data *out* of
(``bible/05`` §8, "a platform you cannot leave is a trap").

The trade is stated rather than hidden: data integrity at the database, traded
for a loader that never fails on real input. The organizer-facing surface warns
in the UI; the schema does not lie about it. Every *other* constraint on this
page is real.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

TEAM_ROLE_OWNER = "owner"
TEAM_ROLE_MEMBER = "member"
TEAM_ROLE_CHOICES = [
    (TEAM_ROLE_OWNER, "Owner"),
    (TEAM_ROLE_MEMBER, "Member"),
]


class Team(SourceKeyMixin, TimeStampedModel, models.Model):
    """A set of people who submit together.

    **A project belongs to a team, not to a submitter.** ``prj_07`` and
    ``prj_41`` are the same team submitting the same title twice
    (``bible/04`` §3.3), and per-submission attribution is precisely the thing
    that fixture exists to test.
    """

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64)
    invite_code = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "teams_team"
        ordering = ["event_id", "name"]
        constraints = [
            models.UniqueConstraint(fields=["event", "name"], name="teams_team_event_name_uniq"),
            models.UniqueConstraint(fields=["event", "slug"], name="teams_team_event_slug_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.event_id}/{self.name}"


class TeamMembership(SourceKeyMixin, TimeStampedModel, models.Model):
    """Who is on a team, and in what capacity.

    Unique on ``(team, user)`` -- a person has exactly one capacity per team.
    The *absence* of the cross-team constraint is the module docstring.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="team_memberships"
    )
    role_in_team = models.CharField(
        max_length=10, choices=TEAM_ROLE_CHOICES, default=TEAM_ROLE_MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "teams_teammembership"
        ordering = ["team_id", "user_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "user"], name="teams_membership_team_user_uniq"
            ),
        ]
        indexes = [
            # "is this user on any team in this event?" is the conflict-of-interest
            # check (bible/05 §4: a judge who is a team member is a HARD BLOCK).
            # It runs once per assignment candidate, so it is a hot path.
            models.Index(fields=["user", "team"], name="teams_membership_user_team_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.role_in_team}@{self.team_id}"


class TeamInvite(SourceKeyMixin, TimeStampedModel, models.Model):
    """A redeemable invitation. Redeeming is idempotent on ``(team, user)``."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="invites")
    code = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, related_name="team_invites_created", null=True
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "teams_teaminvite"
        ordering = ["team_id", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(uses__gte=0),
                name="teams_invite_uses_non_negative",
                violation_error_message="An invite cannot be used a negative number of times.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} -> team {self.team_id}"
