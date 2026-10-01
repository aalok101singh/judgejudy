"""``provisioning.py`` -- turn an empty database into a runnable hackathon.

**This is the module that makes the portal plug-and-play.** Everything else in
the codebase assumes an event exists; before this, the only way to get one was
to run the organizers' fixture loader, which means the only hackathon you could
run was the one they shipped. That is a demo, not a product.

So: one call provisions an event from a handful of answers. Organizer, event,
tracks, rubric, prizes. Nothing here reads the fixture, and nothing here knows
the word ``evt_01``.

**Why it is a module and not a view.** A view is only reachable over HTTP,
which needs a session, which needs an organizer, which is what this creates --
a chicken-and-egg that would force the first-run flow to be unauthenticated by
necessity rather than by decision. Keeping provisioning as a plain function means
the wizard, a management command and the tests all call the *same* code, and the
one piece that must be correct before anybody can trust the portal is testable
without a browser.

**The one invariant worth stating loudly: provisioning is refused once an event
exists.** Not "warned", not "merged" -- refused. An event is the unit of
deployment, so a second one is a configuration error rather than a feature, and
silently creating it would leave an organizer staring at a portal whose routes
resolve an arbitrary event.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

#: The rubric every hackathon gets unless it says otherwise. Three criteria,
#: weights summing to 1. **These are defaults, not doctrine** -- an organizer
#: edits them, and ``rubric_weights_locked_at`` stops them changing under judges
#: who have already scored.
#:
#: **``Decimal``, not ``str``.** ``Criterion.objects.create()`` returns the
#: instance holding the value you passed, not a refetched one, so a string
#: literal here would round-trip correctly into the database while leaving every
#: caller holding a ``str`` where the schema says ``Decimal`` -- and the first
#: thing anyone does with a weight is add it to another one.
DEFAULT_CRITERIA = (
    ("functionality", "Functionality", "Does it do what it claims?", Decimal("0.40")),
    ("quality", "Quality", "Is it well made and maintainable?", Decimal("0.30")),
    ("innovation", "Innovation", "Is it a new idea or a new application?", Decimal("0.30")),
)

#: Refuse a password shorter than this. Argon2 makes a short password expensive
#: to guess but not impossible, and this is the only credential most organizers
#: will ever set here.
MIN_PASSWORD_LENGTH = 12


class ProvisioningError(Exception):
    """Refused, with a reason an organizer can act on.

    Raised rather than returned because every caller either aborts a transaction
    or prints the message; a boolean would push that choice onto each of them and
    one of them would forget to check.
    """


@dataclass(frozen=True)
class TrackSpec:
    name: str
    target_reviews_per_project: int | None = None


@dataclass(frozen=True)
class ProvisionRequest:
    """Everything provisioning needs. No defaults that could surprise anyone."""

    organizer_email: str
    organizer_name: str
    password: str
    event_name: str
    starts_at: object
    submissions_close: object
    judging_closes_at: object
    submissions_open: object | None = None
    tracks: tuple[TrackSpec, ...] = ()
    rubric_name: str = "Standard rubric"
    scale_min: int = 1
    scale_max: int = 5
    reviews_per_project: int = 3
    voting_mode: str = "closed"
    description: str = ""


@dataclass
class ProvisionResult:
    event: object
    organizer: object
    tracks: list = field(default_factory=list)
    rubric: object = None
    criteria: list = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"event      {self.event.slug} ({self.event.name})\n"
            f"organizer  {self.organizer.email}\n"
            f"tracks     {len(self.tracks)}\n"
            f"rubric     {self.rubric.name} with {len(self.criteria)} criteria\n"
            f"window     submissions close {self.event.submissions_close:%Y-%m-%d %H:%M %Z}"
        )


def slugify(name: str) -> str:
    """A URL-safe slug, with a fallback so a name of only punctuation still works.

    ``slugify("Hackathon 2026!")`` would be ``"hackathon-2026"``; a name made
    entirely of symbols gives ``""``, and an event whose slug is the empty string
    is unusable, so a random suffix is the honest repair.
    """
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48]
    return base or f"event-{secrets.token_hex(3)}"


def _normalise_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ProvisioningError(f"{raw!r} is not an email address.")
    return email


def _check_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ProvisioningError(
            f"The organizer password must be at least {MIN_PASSWORD_LENGTH} characters. "
            "This is the one credential you will set by hand."
        )


def already_provisioned() -> bool:
    """True once an event exists. The wizard's entire authorisation."""
    from reviewer.events.models import Event

    return Event.objects.exists()


@transaction.atomic
def provision(request: ProvisionRequest) -> ProvisionResult:
    """Create the organizer, the event, its tracks and its rubric. All or nothing.

    **Atomic on purpose.** A half-provisioned database is the worst state this
    module could leave behind: an event with no rubric refuses every review form,
    and an organizer with a password but no event cannot log in to fix it. The
    transaction means the only reachable states are "nothing" and "runnable".
    """
    from reviewer.accounts.models import RoleBinding, User
    from reviewer.events.models import Event, Track
    from reviewer.rubrics.models import Criterion, Rubric

    if Event.objects.exists():
        raise ProvisioningError(
            "This deployment already has an event. One deployment runs one "
            "hackathon -- delete the data volume to start over."
        )

    email = _normalise_email(request.organizer_email)
    _check_password(request.password)

    if User.objects.filter(email=email).exists():
        raise ProvisioningError(f"{email} already has an account here.")

    if request.submissions_close <= request.starts_at:
        raise ProvisioningError("Submissions must close after the event starts.")
    if request.judging_closes_at < request.submissions_close:
        raise ProvisioningError("Judging cannot close before submissions close.")

    slug = slugify(request.event_name)
    if Event.objects.filter(slug=slug).exists():
        slug = f"{slug}-{secrets.token_hex(2)}"

    organizer = User.objects.create_user(
        email=email,
        password=request.password,
        display_name=request.organizer_name.strip() or email,
    )
    # `is_staff` is what `Actor` unions with an organizer binding into `admin`.
    # It grants no Django permission -- `User.has_perm` returns False
    # unconditionally -- so this is a routing hint, not a privilege escalation.
    organizer.is_staff = True
    organizer.save(update_fields=["is_staff"])

    event = Event.objects.create(
        id=f"evt_{secrets.token_hex(6)}",
        slug=slug,
        name=request.event_name.strip(),
        description=request.description,
        starts_at=request.starts_at,
        submissions_open=request.submissions_open or request.starts_at,
        submissions_close=request.submissions_close,
        judging_closes_at=request.judging_closes_at,
        results_state="hidden",
        voting_mode=request.voting_mode,
        reviews_per_project=request.reviews_per_project,
    )

    RoleBinding.objects.create(event=event, user=organizer, role="organizer")

    tracks = [
        Track.objects.create(
            event=event,
            name=spec.name,
            slug=slugify(spec.name),
            target_reviews_per_project=spec.target_reviews_per_project,
        )
        for spec in request.tracks
    ]

    rubric = Rubric.objects.create(
        event=event,
        name=request.rubric_name,
        version=1,
        scale_min=request.scale_min,
        scale_max=request.scale_max,
    )
    criteria = [
        Criterion.objects.create(
            rubric=rubric,
            key=key,
            label=label,
            description=description,
            weight=weight,
            position=index,
        )
        for index, (key, label, description, weight) in enumerate(DEFAULT_CRITERIA)
    ]

    # **Asserted, not assumed.** A rubric whose weights do not sum to 1 is
    # normalised at read time, so it still *works* -- it just ranks on a scale the
    # rubric never described, and nothing downstream compares weights to catch it.
    # Editing the tuple above is the likely way to break this, and the check that
    # the arithmetic holds belongs next to the constants rather than only in a test.
    total_weight = sum((c.weight for c in criteria), Decimal("0"))
    if total_weight != Decimal("1"):
        raise ProvisioningError(
            f"The default rubric's weights sum to {total_weight}, not 1. This is a bug "
            "in Judge Judy, not in your event -- please report it."
        )

    return ProvisionResult(
        event=event,
        organizer=organizer,
        tracks=tracks,
        rubric=rubric,
        criteria=criteria,
    )


def default_window(now=None):
    """A two-day hackathon with judging the day after. Returned, not assumed.

    An organizer's first decision is their dates, and guessing them silently is
    how a portal ends up refusing submissions to an event that "started" in 1990.
    """
    now = now or timezone.now()
    return {
        "starts_at": now,
        "submissions_open": now,
        "submissions_close": now + timedelta(days=2),
        "judging_closes_at": now + timedelta(days=3),
    }
