"""Rubrics and criteria -- versioned, because two judges on two rubrics are not comparable.

**Why a rubric is versioned at all.** Most teams will not think of this, and it
costs one foreign key. A judge who scored against version 1 and a judge who
scored against version 2 produced numbers that are not on the same scale, and a
normalization argument that silently mixes them is not an argument. So
``Rubric`` carries a ``version``, is unique on ``(event, name, version)``, and
every ``Review`` records the version it was scored under.

**Why ``weight`` is a ``Decimal`` and not a ``float``.** Rubric weights are
money-adjacent arithmetic, and binary floats make "the weights sum to 1.0" fail
for reasons no reader can reconstruct from the code -- 0.4 + 0.35 + 0.25 is
0.9999999999999999 in IEEE 754. An organizer who is told their rubric is
malformed when it is not learns to distrust every other number the portal shows
them.

**Why weights are not stored pre-summed.** They are normalised at read time, so
an organizer editing 40/35/25 to 4/3.5/2.5 does not have to think about scale.

**The known weakness, recorded rather than discovered later** (``bible/05`` §12
item 4): the *version* is versioned but the weights live on ``Criterion`` rows,
so a weight edited after the fact contradicts the version it belongs to. An
immutable ``RubricVersion`` aggregate with copied criteria would be right. The
lock is ``Event.rubric_weights_locked_at`` and the defence in depth is
``Score.weight_applied`` being snapshotted, so the practical exposure is an
organizer with admin access deliberately rewriting history -- which the audit
chain records.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel


class Rubric(SourceKeyMixin, TimeStampedModel, models.Model):
    """One version of one scoring rubric, for one event."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="rubrics")
    name = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    scale_min = models.SmallIntegerField(default=1)
    scale_max = models.SmallIntegerField(default=5)

    class Meta:
        db_table = "rubrics_rubric"
        ordering = ["event_id", "name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "name", "version"], name="rubrics_rubric_event_name_ver_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(scale_min__lt=models.F("scale_max")),
                name="rubrics_rubric_scale_ordered",
                violation_error_message=(
                    "scale_min must be below scale_max; a one-point scale is a config error."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class Criterion(SourceKeyMixin, TimeStampedModel, models.Model):
    """One axis of a rubric, with the weight it carried at scoring time.

    ``created_at`` / ``updated_at`` come from ``TimeStampedModel`` even though
    ``created_at`` is a little redundant against ``Rubric.created_at``: criteria
    are edited independently of the rubric they hang off, and the audit trail
    (FEAT-07) wants to say when a weight changed.
    """

    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name="criteria")
    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    weight = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal("1.0000"),
        help_text="Relative weight. Normalised at read time; never stored pre-summed.",
    )
    position = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)

    class Meta:
        db_table = "rubrics_criterion"
        ordering = ["rubric_id", "position", "key"]
        constraints = [
            models.UniqueConstraint(fields=["rubric", "key"], name="rubrics_criterion_key_uniq"),
            # Positive, and non-zero: a zero weight silently drops a criterion
            # from every total, which is a different thing from not asking it.
            models.CheckConstraint(
                condition=models.Q(weight__gt=0),
                name="rubrics_criterion_weight_positive",
                violation_error_message="A criterion weight must be greater than zero.",
            ),
        ]
        indexes = [
            # Reading one rubric in display order is what the judge console and
            # the export both do, and `ordering` alone does not give an index.
            models.Index(fields=["rubric_id", "position"], name="rubrics_criterion_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.rubric_id}/{self.key}"
