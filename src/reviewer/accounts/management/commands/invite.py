"""``manage.py invite`` -- build a roster from a file of email addresses.

**Every organizer needs this and there was no way to do it.** A portal whose only
source of users is the organizers' fixture file is a demo; a hackathon's roster is
a spreadsheet of names the organizer already has, so the tool reads that.

**What it does and does not do, deliberately.**

- **Creates accounts with an unusable password.** This deployment has no mail
  service on purpose (D-14: no third-party service, ever), so there is nothing
  to send a reset link with. An account that cannot be signed into is honest; one
  with a password the organizer guessed is not. ``set_password`` is the other
  half.
- **Idempotent.** Re-running after adding three more judges must not duplicate
  the first thirty, and must not reset anyone's binding. An organizer who runs
  this twice should see the same roster, not an error.
- **Reports, never guesses.** A line that is not an email address is reported and
  skipped rather than silently dropped or silently created -- an organizer who
  pastes a header row should be told, not left wondering why two judges have no
  console.
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand, CommandError

from reviewer.setup.roster import RosterError, apply_roster, load_emails

VALID_ROLES = ("participant", "judge", "organizer")


class Command(BaseCommand):
    help = "Create accounts and role bindings from a file of email addresses, one per line."

    def add_arguments(self, parser):
        parser.add_argument("path", help="a file of email addresses, one per line")
        parser.add_argument(
            "--role",
            default="judge",
            choices=VALID_ROLES,
            help="what these people are (default: judge)",
        )
        parser.add_argument(
            "--track",
            default=None,
            help="restrict judge bindings to this track name; omit for event-wide",
        )

    def handle(self, *args, **options):
        try:
            wanted = load_emails(options["path"])
        except RosterError as exc:
            raise CommandError(str(exc)) from exc
        if not wanted:
            raise CommandError(f"{options['path']} contained no email addresses.")

        try:
            result = apply_roster(wanted, role=options["role"], track=options["track"])
        except RosterError as exc:
            raise CommandError(str(exc)) from exc

        for line in result.rejected:
            self.stderr.write(f"  skipped: {line}")
        self.stdout.write(
            f"{result.created_users} account(s) created, "
            f"{result.existing_users} already existed, "
            f"{result.bindings_created} binding(s) added."
        )
        if result.rejected:
            self.stdout.write(
                f"{len(result.rejected)} line(s) skipped. Nothing was created for those."
            )
        self.stdout.write("")
        self.stdout.write(
            "Set a password for each person with:\n  python src/manage.py set_password <email>"
        )
        if options["role"] == "judge" and not options["track"]:
            self.stdout.write(
                "These judge bindings are EVENT-WIDE. Pass --track to scope them, "
                "which is what keeps judges off projects they have a stake in."
            )
        sys.stdout.flush()
