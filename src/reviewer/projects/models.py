"""Projects -- the thing being judged, and the awkward one.

``prj_07`` and ``prj_41`` are the same team, the same track, the same title and
the same ``repo_url``, submitted 13h28m apart, with 5 and 4 reviews
respectively (``bible/04`` §3.3). Every deliberate choice in this file is a
consequence of those two rows existing in the published fixture.

**``supersedes`` is a self-reference and BOTH rows are kept.** Nothing is
destroyed and nothing is deduplicated on load. The superseded row keeps its
reviews for the audit trail; results aggregate by team with latest-wins; the
export writes both with the relation, so a round trip is lossless.

The alternative -- deduplicating during import -- was rejected because it makes
the loader lossy, and a lossy import path quietly discards an organizer's data.
That is the "platform you cannot leave" trap pointed the other way: a platform
you cannot trust to take your data in. Note where ``counted`` is *not*: it is
not a column here. It is written by the export (FEAT-07) so the aggregation
decision is auditable in the artefact rather than recomputed differently by
each consumer.

**No uniqueness constraint on ``title``.** Two fixture projects share the title
``Dry Harbour``, and more importantly titles collide in real events constantly.
A unique index on a user-supplied string is a support incident waiting to
happen. Uniqueness where it is wanted lives on ``slug`` scoped to the team.

**``team`` is a foreign key, and a project has exactly one.** ``tm_07`` has two
projects, not two teams, and the "who submitted this" question is answered by
the team.
"""

from __future__ import annotations

from django.db import models

from reviewer.core import SourceKeyMixin, TimeStampedModel

PROJECT_DRAFT = "draft"
PROJECT_SUBMITTED = "submitted"
PROJECT_WITHDRAWN = "withdrawn"
PROJECT_STATUS_CHOICES = [
    (PROJECT_DRAFT, "Draft"),
    (PROJECT_SUBMITTED, "Submitted"),
    (PROJECT_WITHDRAWN, "Withdrawn"),
]

#: The only combination the gallery will ever render. A draft is invisible, and
#: the invisibility lives in the queryset rather than in the template so that a
#: second rendering path cannot accidentally expose one.
GALLERY_FILTER = {"status": PROJECT_SUBMITTED, "submitted_at__isnull": False}


class Project(SourceKeyMixin, TimeStampedModel, models.Model):
    """One submitted thing. 41 of them in the published fixture."""

    # Fixture ID preserved verbatim, e.g. "prj_07". See the module docstring on
    # why two tables keep their external identifier as the primary key.
    id = models.CharField(max_length=32, primary_key=True)

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="projects")
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="projects")
    # Non-null, not "one hop through the event": the assignment model is
    # track-scoped, so a project with no track has no meaning here. An event
    # with no tracks is allowed and is simply un-tracked; we do not invent an
    # "other" row, because a synthetic track pollutes the gallery filters.
    track = models.ForeignKey("events.Track", on_delete=models.PROTECT, related_name="projects")

    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=300)  # deliberately NOT unique -- see docs
    summary = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    # Never fetched. A project that declares a URL does not cause an outbound
    # request at any point in the request path: the network is off by design and
    # a request-path fetch is how a self-hosted portal becomes a browser of
    # someone else's server.
    thumbnail_url = models.URLField(max_length=500, blank=True)
    video_url = models.URLField(max_length=500, blank=True)
    live_url = models.URLField(max_length=500, blank=True)
    repo_url = models.URLField(max_length=500, blank=True)

    # JSONField is portable across SQLite and Postgres with no operator
    # assumptions. We store and read them whole; we do not index into them, which
    # is the portability trap (bible/05 §2 rule 2).
    tags = models.JSONField(default=list, blank=True)
    custom_answers = models.JSONField(default=dict, blank=True)
    images = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=12, choices=PROJECT_STATUS_CHOICES, default=PROJECT_DRAFT)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="superseded_by",
        null=True,
        blank=True,
    )
    # Null on a draft. See the CHECK constraint below.
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "projects_project"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "slug"], name="projects_project_team_slug_uniq"
            ),
            # `choices` is not a database constraint, and a status outside the
            # three enumerated values is a bug that would otherwise surface as
            # a project that is in no state and therefore in no gallery and no
            # export. CheckConstraint over application validation (bible/05 §2).
            models.CheckConstraint(
                condition=models.Q(status__in=["draft", "submitted", "withdrawn"]),
                name="projects_project_status_known",
                violation_error_message="Unknown project status.",
            ),
            models.CheckConstraint(
                condition=~models.Q(supersedes_id=models.F("pk")),
                name="projects_project_no_self_supersede",
                violation_error_message="A project cannot supersede itself.",
            ),
            # A draft has never been submitted, so it has no submission
            # timestamp. The gallery keys off `submitted_at IS NOT NULL`, and a
            # draft carrying one would be rendered as a submission the organizer
            # never made.
            models.CheckConstraint(
                condition=models.Q(status="draft", submitted_at__isnull=True)
                | models.Q(status__in=["submitted", "withdrawn"]),
                name="projects_project_draft_has_no_submitted_at",
                violation_error_message="A draft cannot have a submission timestamp.",
            ),
        ]
        indexes = [
            # "the event gallery" -- the first hot path named in FEAT-02.
            models.Index(fields=["event", "track", "status"], name="projects_proj_gal_idx"),
            # team view and the supersede chain.
            models.Index(fields=["event", "team"], name="projects_proj_event_team_idx"),
            # `run.py` reads projects[:3] positionally, so the gallery's default
            # ordering has to be index-friendly rather than arbitrary.
            models.Index(fields=["event", "submitted_at"], name="projects_proj_submitted_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.id} {self.title}"

    @property
    def is_public(self) -> bool:
        """Whether the gallery may render this row. The one definition of it."""
        return self.status == PROJECT_SUBMITTED and self.submitted_at is not None
