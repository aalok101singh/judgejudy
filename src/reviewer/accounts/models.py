"""Identity and roles.

**The one decision in this file is that ``User`` has no ``PermissionsMixin``,
and it is worth defending because it will look like an omission.**

Django's permission framework is *global*, not per-event. It attaches a
permission bitmask to a user, and nothing in it can express "a judge on
``trk_03`` and a judge on ``trk_07`` are the same person with different
authority." Modelling that in Django's framework means bolting a parallel system
alongside it, and a reviewer would be right to ask which one the application
reads. Ours reads exactly one: ``RoleBinding``.

So ``User`` is an ``AbstractBaseUser`` with a custom manager and no permission
mixin, and every authorization decision in the project is a ``RoleBinding``
lookup plus a queryset scope (``bible/05`` §3, §6).

**The consequence, stated rather than hidden:** ``django.contrib.admin`` renders,
and a staff user sees an empty app list, because ``has_perm`` below returns
False. That is the correct behaviour for this design -- the admin is not our
security surface and must not be mistaken for one -- and it is the honest cost
of having exactly one place where the rules live. ``is_staff`` is retained
because the admin's login gate needs it, and it is deliberately *separate* from
the product roles: an organizer is a ``RoleBinding``, not a ``is_staff``.

**Why the login identity is an email.** ``fixtures.json`` is email-keyed
throughout and hackathons are email-first, so ``USERNAME_FIELD = "email"`` and
there is no second identifier to keep in sync.
"""

from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from reviewer.core import STORED_ROLE_CHOICES, SourceKeyMixin, TimeStampedModel


class UserManager(BaseUserManager):
    """Creates users by email.

    ``AbstractBaseUser`` ships a manager that makes a username unique, so
    without this the first call to ``create_user`` either fails or silently
    accepts a second user with a colliding username -- and the failure would
    appear at seed time (FEAT-03) rather than here.
    """

    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Users are identified by email; an empty one is not a user.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_active", True)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_active", True)
        if extra["is_staff"] is not True:
            raise ValueError("A superuser must have is_staff=True.")
        return self._create(email, password, **extra)


class User(SourceKeyMixin, TimeStampedModel, AbstractBaseUser):
    """A person. Authority lives in ``RoleBinding``; credentials live here."""

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=200, blank=True)

    # Deliberately NOT Django's permission groups/user_permissions M2M. See the
    # module docstring.
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text="Django admin gate only. Product authority is a RoleBinding.",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["email"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(email=""),
                name="accounts_user_email_not_empty",
                violation_error_message="An empty email is not an identity.",
            )
        ]

    def __str__(self) -> str:
        return self.email

    # -- the shape django.contrib.admin expects -------------------------------
    #
    # The admin's index and every ModelAdmin permission check call these four.
    # They return False because the answer is genuinely "no": this user model has
    # no permission framework attached, and pretending otherwise by returning
    # True would give the admin an authority path that bypasses RoleBinding --
    # which is the exact failure D-01 exists to make impossible.

    def has_perm(self, perm, obj=None) -> bool:
        """Always False. See the module docstring -- this is not an oversight."""
        return False

    def has_perms(self, perm_list, obj=None) -> bool:
        return False

    def has_module_perms(self, app_label) -> bool:
        return False

    def get_all_permissions(self, obj=None) -> set:
        return set()

    def get_group_permissions(self, obj=None) -> set:
        return set()


class RoleBinding(SourceKeyMixin, TimeStampedModel, models.Model):
    """Authority, scoped to an event and optionally to a track.

    **``track`` being nullable is the whole design** (``bible/05`` §3). A judge
    binding carries the track; an organizer or admin binding carries
    ``track = NULL`` and is event-wide. A judge with two tracks has two rows,
    which is exactly the fixture's shape for its nine dual-track judges -- so the
    seed is a direct expression of the model rather than a special case in the
    loader.

    **``visitor`` is absent as a stored value.** A visitor is someone with no
    binding, and storing it would mean every anonymous request creates a row.
    ``reviewer.isolation.actor.Actor.is_visitor`` derives it.
    """

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="role_bindings"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_bindings")
    role = models.CharField(max_length=20, choices=STORED_ROLE_CHOICES)
    track = models.ForeignKey(
        "events.Track",
        on_delete=models.CASCADE,
        related_name="role_bindings",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "accounts_role_binding"
        ordering = ["event", "role", "track_id", "user_id"]
        constraints = [
            # F-12's cousin: only a judge binding is track-scoped. An organizer
            # row with a track is a misconfiguration that would read as
            # "organizer of one track" and quietly narrow their reach, so the
            # database refuses to store it rather than the resolver guessing.
            models.CheckConstraint(
                condition=models.Q(role="judge") | models.Q(track__isnull=True),
                name="accounts_rolebinding_track_only_on_judge",
                violation_error_message="Only a judge binding may be track-scoped.",
            ),
        ]
        indexes = [
            # "every authorization decision" (bible/05 §10). Indexed on
            # (event, user) rather than (event, user, role) because the
            # resolver asks "what may this user do here" and filters roles in
            # Python; a wider prefix serves more queries.
            models.Index(fields=["event", "user"], name="accounts_rb_event_user_idx"),
            models.Index(
                fields=["event", "role", "track_id"], name="accounts_rb_event_role_trk_idx"
            ),
        ]

    def __str__(self) -> str:
        where = self.track_id or "event"
        return f"{self.user_id} {self.role} @{where}"
