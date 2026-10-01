"""Public comments.

One table, and almost all of the file is about one decision: **bodies are
rendered escaped, always, with no raw HTML, and there is no code path in this
project that turns a comment body into markup.** ``bible/07`` §4 is the threat
model for it, and the mitigation is a template that never calls ``|safe`` and a
serializer whose ``CharField`` is the only writer.

``status`` exists because moderation has to be visible. A comment that is
pending or hidden keeps its row, so the organizer can see that it existed and
why it is not shown -- a filtered comment is indistinguishable from one that was
never posted, and that ambiguity is how a moderation queue becomes untrustworthy.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

COMMENT_VISIBLE = "visible"
COMMENT_PENDING = "pending"
COMMENT_HIDDEN = "hidden"
COMMENT_STATUS_CHOICES = [
    (COMMENT_VISIBLE, "Visible"),
    (COMMENT_PENDING, "Pending"),
    (COMMENT_HIDDEN, "Hidden"),
]


class Comment(SourceKeyMixin, TimeStampedModel, models.Model):
    """A public comment on a project, optionally threaded."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="comments")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="comments"
    )
    #: Nullable: a public comment can be anonymous, and requiring an author row
    #: would mean every anonymous comment creates a User.
    author = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, related_name="comments", null=True, blank=True
    )
    author_label = models.CharField(max_length=120, blank=True)
    #: **The anonymous poster's identity, for rate limiting only.**
    #:
    #: A comment may be posted without an account, so "who is this" has no answer
    #: from `author`. This is a SHA-256 of the posting session key: stable enough
    #: to count someone's comments within a window, useless for signing in.
    #:
    #: **Empty whenever `author` is set**, because an account is the better key
    #: and having both would mean two answers to "who".
    #:
    #: `blank=True, default=""` and deliberately **not** `null=True`: null *and*
    #: blank would be two ways for this column to say "no anonymous key", and a
    #: filter on one would silently miss the other. This project's recurring
    #: finding (F-13) is that two representations of "absent" are what let a
    #: control quietly count nothing. One absent value, one thing to count.
    #:
    #: The rate limit counts rows rather than keeping a counter, so there is no
    #: second store to disagree with this one -- see the migration's docstring.
    author_session_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "SHA-256 of the posting session key, for rate-limiting anonymous "
            "comments. Empty when the comment is attributed to an account. Never "
            "the session key itself."
        ),
    )
    body = models.TextField()
    status = models.CharField(
        max_length=10, choices=COMMENT_STATUS_CHOICES, default=COMMENT_PENDING
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, related_name="replies", null=True, blank=True
    )
    moderated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        related_name="comments_moderated",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "comments_comment"
        ordering = ["project_id", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["visible", "pending", "hidden"]),
                name="comments_comment_status_known",
                violation_error_message="Unknown comment status.",
            ),
            models.CheckConstraint(
                condition=~models.Q(parent_id=models.F("pk")),
                name="comments_comment_no_self_parent",
                violation_error_message="A comment cannot be its own parent.",
            ),
            models.CheckConstraint(
                condition=~models.Q(body=""),
                name="comments_comment_body_not_empty",
                violation_error_message="An empty comment is not a comment.",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"], name="comments_cm_project_idx"),
            models.Index(fields=["event", "status"], name="comments_cm_event_idx"),
        ]

    def __str__(self) -> str:
        return f"comment {self.pk} on {self.project_id}"
