"""Event, track, prize -- the tenant boundary and the policy that hangs off it.

``Event`` is the tenant. Every table that matters carries ``event`` directly or
one hop away, because **every query has to be scopable to an event and a role**
and that is only cheap if the index prefix is right (``bible/05`` §1).

**Why ``Event.id`` and ``Project.id`` are ``CharField`` primary keys that keep
the fixture's identifiers verbatim.** ``evt_01`` stays ``evt_01`` and ``prj_07``
stays ``prj_07``. That is not nostalgia for the fixture: it is what makes a
``curl`` transcript in the README and a row in the database checkable against
each other with nothing but a string comparison, and it is what lets the
supersede chain for ``prj_41 -> prj_07`` be stated as a fact about the schema
rather than as a lookup table. Every *other* table takes a surrogate integer
key and carries its external identifier in ``source_key`` (D-11), which is the
rule that makes the bulk round-trip byte-identical.

**Three timestamps rather than a status enum.** The organizers' acceptance check
depends on ``submissions_close`` being *a date the code reads*, not a state we
set (``bible/05`` §2). Keeping a real timestamp means the deadline is enforced by
comparison, which is the only enforcement that cannot be bypassed by forgetting to
flip a flag.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

RESULTS_HIDDEN = "hidden"
RESULTS_PUBLISHED = "published"
RESULTS_STATE_CHOICES = [
    (RESULTS_HIDDEN, "Hidden"),
    (RESULTS_PUBLISHED, "Published"),
]

VOTING_CLOSED = "closed"
VOTING_OPEN_LINK = "open_link"
VOTING_EMAIL_GATED = "email_gated"
VOTING_AUTHENTICATED = "authenticated"
VOTING_MODE_CHOICES = [
    (VOTING_CLOSED, "Closed"),
    (VOTING_OPEN_LINK, "Open link"),
    (VOTING_EMAIL_GATED, "Email gated"),
    (VOTING_AUTHENTICATED, "Authenticated"),
]


class Event(SourceKeyMixin, TimeStampedModel, models.Model):
    """One hackathon. The tenant boundary for every other table."""

    # Fixture ID preserved verbatim, e.g. "evt_01". See the module docstring.
    id = models.CharField(max_length=32, primary_key=True)
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    starts_at = models.DateTimeField()
    submissions_open = models.DateTimeField(null=True, blank=True)
    # THE deadline the guard reads (bible/05 §4). In the shipped fixture this is
    # a PAST date, so the portal is born closed and every mutating view must
    # refuse. Never move it -- see bible/04 §3.
    submissions_close = models.DateTimeField()
    judging_closes_at = models.DateTimeField(null=True, blank=True)

    results_state = models.CharField(
        max_length=16, choices=RESULTS_STATE_CHOICES, default=RESULTS_HIDDEN
    )
    voting_mode = models.CharField(
        max_length=20, choices=VOTING_MODE_CHOICES, default=VOTING_CLOSED
    )
    voting_opens_at = models.DateTimeField(null=True, blank=True)
    voting_closes_at = models.DateTimeField(null=True, blank=True)

    # A DEFAULT, not a policy. The operative target is per-track; see Track.
    reviews_per_project = models.PositiveIntegerField(default=3)

    # The assignment planner's two organizer-facing settings, both nullable so
    # that "unset" is a real state and not a magic number pretending to be a
    # decision.
    #
    # ``assignment_seed`` makes the seeded tiebreak reproducible. It is stored
    # rather than passed in because the acceptance line for FEAT-04 is that the
    # same seed reproduces the same assignment byte-for-byte, and a seed that
    # lived in a request would be a seed nobody could reproduce. `bible/06`
    # §2.2 requires it be shown in the organizer UI.
    assignment_seed = models.PositiveIntegerField(default=0)
    # The per-judge cap on the assignment search. NULL means "no organizer cap",
    # which is the right default: the search then finds the tightest bound that
    # delivers full coverage, which is a fact about the panel rather than a
    # number somebody typed. Setting it to 5 is what makes `trk_01` and
    # `trk_08` provably impossible (`bible/06` §2.1a) and is the infeasible
    # instance the acceptance line names.
    judge_capacity = models.PositiveIntegerField(null=True, blank=True)

    # Weights cannot change once judging starts. A schema-level statement of
    # that policy rather than a UI convention (bible/05 §2).
    rubric_weights_locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "events_event"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reviews_per_project__gte=1),
                name="events_event_target_positive",
                violation_error_message="A review target of zero can never be satisfied.",
            ),
            models.CheckConstraint(
                condition=models.Q(judge_capacity__isnull=True) | models.Q(judge_capacity__gte=1),
                name="events_event_capacity_positive",
                violation_error_message=(
                    "A per-judge capacity of zero can never assign anything. NULL means "
                    "'no organizer cap' and is the only other allowed value."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.name})"


class Track(SourceKeyMixin, TimeStampedModel, models.Model):
    """A competition track within an event.

    **``target_reviews_per_project`` is nullable and inherits from the event, and
    the fixture is why** (``bible/05`` §2, ``bible/06`` §2.1a). ``trk_01`` and
    ``trk_08`` each have six projects and three judges, so a target of 3 needs 18
    assignments from 3 judges -- exactly the maximum possible, with **zero
    structural slack**. One withdrawal makes it arithmetically impossible, and a
    single event-wide integer cannot express "3 everywhere except these two
    tracks, which cannot do 3 at all."

    Null means "inherit", which keeps the common case of a uniform event to a
    single field and makes the exception explicit rather than duplicative.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tracks")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64)
    description = models.TextField(blank=True)
    target_reviews_per_project = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "events_track"
        ordering = ["event_id", "name"]
        constraints = [
            models.UniqueConstraint(fields=["event", "name"], name="events_track_event_name_uniq"),
            models.UniqueConstraint(fields=["event", "slug"], name="events_track_event_slug_uniq"),
        ]
        indexes = [
            models.Index(fields=["event", "id"], name="events_track_event_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_id}/{self.name}"

    def effective_target(self) -> int:
        """The operative review target: this track's, or the event's if unset.

        A method rather than a property because it reads ``self.event``, and a
        property would make that an implicit query on a field access -- which is
        exactly the kind of surprise that turns a progress denominator into a
        slow page at hour 40.
        """
        if self.target_reviews_per_project is not None:
            return self.target_reviews_per_project
        return self.event.reviews_per_project


class Prize(SourceKeyMixin, TimeStampedModel, models.Model):
    """A prize on the results page.

    **Amounts are minor units as an integer. Never a float.** Binary floats make
    "the prizes add up to $10,000" fail for reasons no reader can reconstruct
    from the code, and this is the one number an organizer will audit.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="prizes")
    name = models.CharField(max_length=200)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="USD")
    rank = models.PositiveIntegerField(null=True, blank=True)
    category = models.CharField(max_length=100, blank=True)
    track = models.ForeignKey(
        Track, on_delete=models.SET_NULL, related_name="prizes", null=True, blank=True
    )

    class Meta:
        db_table = "events_prize"
        ordering = ["event_id", "-amount_cents"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_cents__gte=0),
                name="events_prize_amount_non_negative",
                violation_error_message="A negative prize is a data error, not a debt.",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="events_prize_currency_iso3",
                violation_error_message=(
                    "Currency is a 3-letter code; the panel is in five countries."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.amount_cents / 100:.2f} {self.currency})"
