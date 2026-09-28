"""Ballots and votes -- the public tier's only two tables.

**A ballot is a randomised order, and both halves of that matter.** ``order`` is
the per-voter permutation of project ids and ``seed`` is what produced it. Stable
per voter, random across voters. That is the entire point: it kills position bias
*within* a ballot while preventing a determined voter from re-rolling the order by
refreshing the page. Storing the seed means the same ballot can be reconstructed
for the audit trail rather than merely asserted to have existed.

**Why ``voter_key`` and not a user, and why ``ip_hash`` rather than an address.**
``voter_key`` is the deduplication identity, resolved differently per voting
mode (``bible/05`` §7)::

    open_link      hash of IP + UA + a signed cookie
    email_gated    normalised email, after verification
    authenticated  user id

We need to detect duplicate voting without becoming a database of everyone's
home address. The IP and user agent are therefore **hashed before they are
stored** -- the salt is per event, so the value is not reversible across events,
and the salt is rotatable, which is the entire reason the raw value is not kept.

**Why ``weight`` is a column when the brief asks for one vote per person.**
Because the anti-abuse answer we ship is a published influence report, not a
fancyer ballot (D-13), and quadratic voting is a cheap door to leave open. Storing
``weight`` rather than counting rows is what makes it possible without a schema
change later -- and this project is meant to be forked for a decade.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel


class Ballot(SourceKeyMixin, TimeStampedModel, models.Model):
    """One voter's randomised presentation order. Immutable once cast."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ballots")
    #: The deduplication identity, hashed. See the module docstring.
    voter_key = models.CharField(max_length=128)
    #: Kept so the order can be re-derived for the audit trail instead of
    #: merely claimed. A random order that cannot be reproduced is an order
    #: nobody can check.
    seed = models.CharField(max_length=128)
    #: The permutation of project ids, as a JSON list of strings. Portable
    #: across both engines; we read and write it whole and never index into it,
    #: which is the portability rule (bible/05 §2).
    order = models.JSONField(default=list)
    cast_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ballots_ballot"
        ordering = ["event_id", "cast_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "voter_key"], name="ballots_ballot_voter_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["event", "voter_key"], name="ballots_ballot_ev_voter_idx"),
        ]

    def __str__(self) -> str:
        return f"ballot {self.event_id}/{self.voter_key[:8]}"


class Vote(SourceKeyMixin, TimeStampedModel, models.Model):
    """One project, one voter, one weight."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="votes")
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="votes")
    voter_key = models.CharField(max_length=128)
    weight = models.PositiveIntegerField(
        default=1,
        help_text=("Defaults to one. Stored rather than counted so quadratic voting is possible."),
    )
    # Hashed, salted per event, rotatable. Never the raw address.
    ip_hash = models.CharField(max_length=128, blank=True)
    user_agent_hash = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "ballots_vote"
        ordering = ["event_id", "project_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "project", "voter_key"], name="ballots_vote_dedup_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(weight__gte=1),
                name="ballots_vote_weight_positive",
                violation_error_message="A vote's weight is at least one.",
            ),
        ]
        indexes = [
            models.Index(fields=["event", "project", "voter_key"], name="ballots_vote_tally_idx"),
            # per-voter limits (D-12: amplification inside an identity budget)
            models.Index(fields=["event", "voter_key"], name="ballots_vote_voter_idx"),
        ]

    def __str__(self) -> str:
        return f"vote {self.event_id}/{self.project_id} w{self.weight}"
