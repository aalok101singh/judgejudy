"""``roster.py`` -- read a list of people and give them a role.

Separate from the management command so the logic is testable without argv, and
so the same code can serve a future web import. Every function here is
**idempotent**: an organizer who runs it twice gets the same roster, because the
most likely thing to happen is that they run it twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

#: Deliberately permissive on the shape and strict on the obvious mistakes. A
#: regex cannot validate an address; it can catch a spreadsheet header and a
#: truncated paste, which are the two ways this file actually goes wrong.
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")

VALID_ROLES = ("participant", "judge", "organizer")


class RosterError(Exception):
    """Refused, with something an organizer can act on."""


@dataclass
class RosterResult:
    created_users: int = 0
    existing_users: int = 0
    bindings_created: int = 0
    rejected: list[str] = field(default_factory=list)


def load_emails(path: str | Path) -> list[str]:
    """Read addresses from a file, dropping blanks and whole-line comments.

    Returns the addresses and **nothing about what was wrong** -- the caller
    reports rejections from :func:`apply_roster`, which is the single place that
    decides what a valid address is. Two parsers would drift.

    **A comment is the whole line, not a prefix.** The first version used
    ``lstrip("#")``, which turned ``"# the judges"`` into ``"the judges"`` and
    then reported it as a malformed address -- a comment header becoming a
    confusing error about somebody who does not exist.
    """
    target = Path(path)
    if not target.exists():
        raise RosterError(f"{path} does not exist.")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.lower())
    return out


def _split_rejected(candidates: list[str]) -> tuple[list[str], list[str]]:
    """Separate real addresses from lines that are not. Order is preserved."""
    good, bad = [], []
    for candidate in candidates:
        (good if EMAIL_RE.match(candidate) else bad).append(candidate)
    return good, bad


@transaction.atomic
def apply_roster(candidates: list[str], *, role: str, track: str | None = None) -> RosterResult:
    """Create users and role bindings for ``candidates``. Safe to run twice."""
    from reviewer.accounts.models import RoleBinding, User
    from reviewer.events.models import Event, Track

    if role not in VALID_ROLES:
        raise RosterError(f"{role!r} is not a role. Use one of: {', '.join(VALID_ROLES)}.")

    event = Event.objects.order_by("pk").first()
    if event is None:
        raise RosterError(
            "This deployment has no event yet. Run /setup/ first, or "
            "`python src/manage.py shell -c 'from reviewer.setup.provisioning import *'`."
        )

    track_row = None
    if track:
        track_row = Track.objects.filter(event=event, name__iexact=track).first()
        if track_row is None:
            available = ", ".join(sorted(t.name for t in event.tracks.all())) or "none"
            raise RosterError(
                f"No track called {track!r} in {event.name!r}. Available: {available}."
            )

    good, rejected = _split_rejected(candidates)
    result = RosterResult(rejected=rejected)
    if not good:
        raise RosterError(
            "None of those lines looked like an email address. "
            "Expected one address per line, for example:\n"
            "  ada@example.org"
        )

    # Duplicates within the file itself would otherwise create the person twice
    # and bind them twice, which reads as two judges with two workloads.
    seen: set[str] = set()
    for email in good:
        if email in seen:
            result.rejected.append(f"{email} (repeated in the file)")
            continue
        seen.add(email)

        user, created = User.objects.get_or_create(
            email=email, defaults={"display_name": email.split("@")[0]}
        )
        if created:
            # **No password.** There is no mail service, so there is nothing to
            # send a link with; an unusable password is the honest state, and
            # `set_password` is how a person gets in.
            user.set_unusable_password()
            user.save(update_fields=["password"])
            result.created_users += 1
        else:
            result.existing_users += 1

        _, made = RoleBinding.objects.get_or_create(
            event=event,
            user=user,
            role=role,
            track=track_row,
            defaults={},
        )
        if made:
            result.bindings_created += 1

    return result
