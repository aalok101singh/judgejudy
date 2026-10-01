"""``manage.py set_password`` -- the other half of ``invite``.

**Exists because there is no mail service.** The roster command creates accounts
with unusable passwords on purpose, so somebody has to be able to set one, and
that somebody is the organizer at the keyboard. Offering a "forgot password" link
that silently does nothing would be the more dishonest option.

Two properties worth stating:

- **The password is never echoed, never logged, and never accepted on the command
  line.** ``--stdin`` and a hidden prompt are both offered, and neither puts the
  value in the shell history or in this process's arguments.
- **It works for an organizer who has locked themselves out**, which is the
  moment they will need it. That is the whole point of shipping it.
"""

from __future__ import annotations

import getpass
import sys

from django.core.management.base import BaseCommand, CommandError

from reviewer.setup.provisioning import MIN_PASSWORD_LENGTH


class Command(BaseCommand):
    help = "Set or reset one account's password."

    def add_arguments(self, parser):
        parser.add_argument("email", help="the account's email address")
        parser.add_argument(
            "--stdin",
            action="store_true",
            help="read the password from stdin instead of prompting, for scripting",
        )

    def handle(self, *args, **options):
        from reviewer.accounts.models import User

        email = options["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"No account called {email!r} on this deployment.")

        # **`--stdin` reads `sys.stdin`, deliberately.** `getattr(self, "stdin", ...)`
        # was tried first, on the theory that `BaseCommand` carries the stream; in
        # this Django version the attribute is not reliably set, so the flag fell
        # through to the interactive prompt and the command could not be driven
        # from a pipe at all -- the one thing it exists for. Reading the global
        # with an explicit flag is the version that works at a terminal *and* under
        # `echo pw | manage.py set_password x@example.org --stdin`, and the tests
        # monkeypatch `sys.stdin` rather than pretending to an API that is not
        # there.
        if options["stdin"]:
            password = sys.stdin.readline().rstrip("\n")
            confirm = sys.stdin.readline().rstrip("\n")
        else:
            password = getpass.getpass("New password: ")
            confirm = getpass.getpass("Confirm: ")

        if password != confirm:
            raise CommandError("The two passwords did not match.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise CommandError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")

        user.set_password(password)
        user.save(update_fields=["password"])

        # A locked-out organizer must not stay locked out after a reset.
        if hasattr(user, "session_set"):
            user.session_set.all().delete()

        self.stdout.write(f"Password set for {email}.")
        self.stdout.write("They can now sign in at /login/.")
