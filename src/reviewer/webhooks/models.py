"""Webhook endpoints and deliveries -- the models, and nothing else.

**This is a cut, decided at H+0 (D-14, F-20), and both tables ship anyway.**
The plan for the build: webhook *delivery* is roughly two hours, scores zero
points on all four criteria, and the SSRF mitigation it needs (scheme
allowlist, DNS resolution checked against private ranges before delivery,
redirect limit) is a real bug class written from scratch under time pressure.

So what ships is the schema, a view returning **501 Not Implemented**, and
`export run` / `import run` audit entries -- so whoever extends this has
somewhere to put the code and the tables are already in the migrations. What
does **not** ship is anything that silently fails to deliver. A webhook endpoint
that accepts a URL and quietly drops the event is the exact behaviour this
project criticises everyone else for, and the honest alternative is a 501 plus
one sentence in the README saying that delivery, retries and HMAC signature
verification are not implemented.

At-least-once with a visible log would have been the honest delivery semantic
anyway: we cannot guarantee delivery without infrastructure we are not allowed to
depend on, so the failure would have had to be visible rather than pretended
away. That reasoning survives the cut and is in the README.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

DELIVERY_PENDING = "pending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"
DELIVERY_STATUS_CHOICES = [
    (DELIVERY_PENDING, "Pending"),
    (DELIVERY_SENT, "Sent"),
    (DELIVERY_FAILED, "Failed"),
]


class WebhookEndpoint(SourceKeyMixin, TimeStampedModel, models.Model):
    """A registered callback URL. No delivery machinery is wired to it."""

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="webhook_endpoints"
    )
    url = models.URLField(max_length=500)
    #: An HMAC secret would be stored here if delivery shipped. It is deliberately
    #: NOT a CharField today: a column named `secret` that is never written is a
    #: column someone will later write an unhashed value into.
    secret_ref = models.CharField(
        max_length=128,
        blank=True,
        help_text="Reference to a signing secret. Delivery is not implemented; see D-14.",
    )
    #: The event types this endpoint subscribes to.
    events = models.JSONField(default=list)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "webhooks_endpoint"
        ordering = ["event_id", "id"]
        constraints = [
            # The scheme allowlist. It is here, in the schema, rather than in the
            # cut code, so that whoever implements delivery cannot start from
            # "whatever URL validates" (bible/07 P-8).
            models.CheckConstraint(
                condition=models.Q(url__startswith="https://"),
                name="webhooks_endpoint_https_only",
                violation_error_message=(
                    "A webhook URL must be https; http is plaintext to a third party."
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["event", "active"], name="webhooks_ep_event_active_idx"),
        ]

    def __str__(self) -> str:
        return f"webhook {self.pk} -> {self.url}"


class WebhookDelivery(SourceKeyMixin, TimeStampedModel, models.Model):
    """One attempted delivery. Always empty in the shipped build."""

    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=10, choices=DELIVERY_STATUS_CHOICES, default=DELIVERY_PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    response_code = models.IntegerField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webhooks_delivery"
        ordering = ["endpoint_id", "created_at"]
        indexes = [
            models.Index(fields=["endpoint", "status"], name="webhooks_dl_endpoint_idx"),
        ]

    def __str__(self) -> str:
        return f"delivery {self.pk} {self.status}"
