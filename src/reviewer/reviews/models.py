"""Assignment, Review, Score -- and the one redundancy in the schema that is correct.

**``Review.judge`` and ``Review.project`` are denormalised from ``Assignment``
on purpose, and this is the only place in the schema where redundancy is
right.** The reason is authorization:

* The isolation query is "every review by judge J" and "every review on a
  project in track T". Both are single-table filtered reads. With the
  denormalised columns and a composite index they are index scans; without them
  every isolation check is a join across ``Assignment``, and the filter that must
  never be forgotten lives one hop further from the row it constrains.
* A ``Review`` row is a fact about a review. It should be self-describing. A
  reader should not have to traverse to ``Assignment`` to learn who reviewed
  what.

**The cost is two sources of truth, and the mitigation is a constraint plus a
test** (``bible/05`` §11). ``Assignment`` rows and the reviews that reference
them are written by one function in one place; the unique constraints below
stop a second review appearing for the same pair.

**Why ``Score.weight_applied`` is snapshotted rather than joined.** If an
organizer edits weights mid-judging, existing reviews must not silently change
meaning. ``Event.rubric_weights_locked_at`` prevents it on the normal path; the
snapshot makes it impossible on the abnormal one. Defence in depth on the one
number the entire result depends on.

**Why ``status = declined`` exists.** It is what makes a conflict of interest
real: a judge declares one, the project is reassigned, and the decline is
visible to the organizer instead of silently disappearing. Removing the row
would make the audit trail lie about coverage.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel
from reviewer.reviews.queryset import ReviewQuerySet

REVIEW_ASSIGNED = "assigned"
REVIEW_IN_PROGRESS = "in_progress"
REVIEW_SUBMITTED = "submitted"
REVIEW_DECLINED = "declined"
REVIEW_STATUS_CHOICES = [
    (REVIEW_ASSIGNED, "Assigned"),
    (REVIEW_IN_PROGRESS, "In progress"),
    (REVIEW_SUBMITTED, "Submitted"),
    (REVIEW_DECLINED, "Declined"),
]

ASSIGNMENT_MANUAL = "manual"
ASSIGNMENT_BATCH = "batch"
ASSIGNMENT_ALGORITHMIC = "algorithmic"
#: The spec says "by batch or algorithmically" and both must be visible to an
#: organizer, so the distinction is a stored value rather than an inference from
#: which code path happened to run.
ASSIGNMENT_METHOD_CHOICES = [
    (ASSIGNMENT_MANUAL, "Manual"),
    (ASSIGNMENT_BATCH, "Batch"),
    (ASSIGNMENT_ALGORITHMIC, "Algorithmic"),
]


class Assignment(SourceKeyMixin, TimeStampedModel, models.Model):
    """Who is judging what, and how that came to be.

    The 126 score rows in the fixture are *evidence* of assignment, so the
    loader synthesises these deterministically and idempotently from them
    (FEAT-03) -- which is what lets the progress dashboard and the isolation
    model run on real structure rather than on a join invented at read time.
    """

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="assignments")
    judge = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="assignments")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="assignments"
    )
    batch = models.CharField(max_length=64, blank=True)
    method = models.CharField(
        max_length=12, choices=ASSIGNMENT_METHOD_CHOICES, default=ASSIGNMENT_BATCH
    )
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        related_name="assignments_made",
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=REVIEW_STATUS_CHOICES, default=REVIEW_ASSIGNED)

    class Meta:
        db_table = "reviews_assignment"
        ordering = ["event_id", "project_id", "judge_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["judge", "project"], name="reviews_assignment_uniq_pair"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["assigned", "in_progress", "submitted", "declined"]),
                name="reviews_assignment_status_known",
                violation_error_message="Unknown assignment status.",
            ),
        ]
        indexes = [
            # "progress dashboard" -- every call asks "how far is this judge?".
            models.Index(fields=["event", "judge", "status"], name="reviews_asg_event_judge_idx"),
            # "project coverage".
            models.Index(fields=["event", "project"], name="reviews_asg_event_proj_idx"),
        ]

    def __str__(self) -> str:
        return f"judge {self.judge_id} -> {self.project_id}"


class Review(SourceKeyMixin, TimeStampedModel, models.Model):
    """One judge's review of one project. The table the whole isolation claim is about."""

    assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE, related_name="review")
    # Denormalised on purpose. See the module docstring.
    judge = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="reviews")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="reviews"
    )
    # Also denormalised, for the same reason and for the gallery/export index.
    # The event is one hop away through both, and every query has to be scopable
    # to an event and a role.
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="reviews")

    # The version this review was scored under. A judge on v1 and a judge on v2
    # are not comparable, and a normalization argument that mixes them is not an
    # argument (bible/05 §5).
    rubric_version = models.ForeignKey(
        "rubrics.Rubric", on_delete=models.PROTECT, related_name="reviews"
    )

    status = models.CharField(max_length=12, choices=REVIEW_STATUS_CHOICES, default=REVIEW_ASSIGNED)
    # Nullable because 51 of the 126 fixture comments are empty. An empty
    # comment is data, not a missing one.
    overall_comment = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Feeds the "judge rushing" signal in the abuse analysis.
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    # Organizer-declared conflict of interest, hard-blocked at assignment and
    # re-checked at submission (bible/05 §4).
    is_conflicted = models.BooleanField(default=False)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        db_table = "reviews_review"
        ordering = ["project_id", "judge_id"]
        constraints = [
            # `unique(assignment)` is the OneToOne above. This is the second
            # guarantee the denormalisation costs: one review per judge per
            # project, stated at the database rather than in a function.
            models.UniqueConstraint(fields=["judge", "project"], name="reviews_review_uniq_pair"),
            models.CheckConstraint(
                condition=models.Q(status__in=["assigned", "in_progress", "submitted", "declined"]),
                name="reviews_review_status_known",
                violation_error_message="Unknown review status.",
            ),
            models.CheckConstraint(
                condition=models.Q(status="submitted", submitted_at__isnull=False)
                | models.Q(status__in=["assigned", "in_progress", "declined"]),
                name="reviews_review_submitted_has_timestamp",
                violation_error_message="A submitted review must carry its submission timestamp.",
            ),
        ]
        indexes = [
            # T2-4, and the isolation read. `for_actor` filters on
            # (event, judge) and optionally joins project.track; this is the
            # prefix that makes it an index scan.
            models.Index(fields=["event", "judge", "status"], name="reviews_rev_event_judge_idx"),
            # project score rollup.
            models.Index(fields=["project", "status"], name="reviews_rev_project_idx"),
            # audit and export.
            models.Index(fields=["event", "submitted_at"], name="reviews_rev_event_sub_idx"),
        ]

    def __str__(self) -> str:
        return f"review {self.judge_id}/{self.project_id}"

    @property
    def is_scored(self) -> bool:
        """Whether this review carries any score at all (a declined one does not)."""
        return self.status == REVIEW_SUBMITTED


class Score(SourceKeyMixin, TimeStampedModel, models.Model):
    """One criterion's value in one review.

    ``value`` is nullable because an in-progress review has criteria filled in
    one at a time, and a NOT NULL here would mean a half-finished review cannot
    be saved -- which is the single most common thing a judge actually does.
    """

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="scores")
    criterion = models.ForeignKey(
        "rubrics.Criterion", on_delete=models.PROTECT, related_name="scores"
    )
    value = models.SmallIntegerField(null=True, blank=True)
    # Snapshotted at submission time. See the module docstring.
    weight_applied = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("1.0000"))

    class Meta:
        db_table = "reviews_score"
        ordering = ["review_id", "criterion_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["review", "criterion"], name="reviews_score_review_crit_uniq"
            ),
            # The rubric's own scale is 1..5 by default and is organizer-
            # configurable, so the absolute bound asserted here is the widest one
            # a SmallInteger can be given a meaning on. The rubric-specific
            # bound is checked at the service layer, which is also where the
            # error message can name the criterion and the allowed range.
            models.CheckConstraint(
                condition=models.Q(value__isnull=True) | models.Q(value__gte=1, value__lte=10),
                name="reviews_score_value_in_range",
                violation_error_message=(
                    "A score outside 1..10 cannot be interpreted on any rubric."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(weight_applied__gt=0),
                name="reviews_score_weight_positive",
                violation_error_message="A snapshotted weight must be greater than zero.",
            ),
        ]
        indexes = [
            # "normalization passes" (bible/05 §10): the estimator groups scores
            # by criterion and reads the distribution of values.
            models.Index(fields=["criterion_id", "value"], name="reviews_score_crit_value_idx"),
        ]

    def __str__(self) -> str:
        return f"score r{self.review_id}/c{self.criterion_id}={self.value}"
