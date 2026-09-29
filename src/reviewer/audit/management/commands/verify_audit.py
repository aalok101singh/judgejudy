"""``manage.py verify_audit`` -- re-walk the hash chain and exit non-zero on a break.

**This is the command the FEAT-02 docstring said was waiting for a writer.**
`AuditEntry.chain_head()`'s own docstring reads *"a read helper, not a verifier.
The verifier is FEAT-05: it re-walks the chain and recomputes the hashes, and
until the writer exists there is nothing to re-walk."* Both halves of that
sentence were wrong by the time it was written and both are fixed now: the
writer is `reviewer.audit.chain`, and this is the verifier.

**Why it has to be a command and not a function the tests call.** A chain that
only ever gets checked by the suite is a chain whose verification is a claim
rather than an artefact. A reviewer with the repository and a container can run
this and get an answer; that is the difference between "we check our audit
trail" and "we will check our audit trail".

**It exits non-zero on a break, unlike `run.py`.** A gate that always exits 0 is
not a gate (F-32), and this is exactly the kind of check that must be able to
fail loudly in CI.

**It is deliberately NOT inside `just check`**, for the same reason
`prove-offline` and `mutation-test` are not: it is a verification of the *data*,
it needs the seeded database, and `just check` must stay the one command a
reviewer runs. It is added to the break protocol in the FEAT-06 archive.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviewer.audit import chain as chain_module
from reviewer.audit.models import AuditEntry


class Command(BaseCommand):
    """Print the chain, its head, and whether it verifies. Non-zero on a break."""

    help = "Re-walk the audit hash chain for an event and fail if it does not verify."

    def add_arguments(self, parser):
        parser.add_argument(
            "--event",
            default="evt_01",
            help="Event id to verify. Defaults to the fixture's, evt_01.",
        )
        parser.add_argument(
            "--show",
            type=int,
            default=12,
            help="How many trailing entries to print. 0 for the summary only.",
        )

    def handle(self, *args, **options):
        from reviewer.events.models import Event

        try:
            event = Event.objects.get(pk=options["event"])
        except Event.DoesNotExist as exc:
            raise CommandError(f"no event {options['event']!r} in this database") from exc

        entries = list(AuditEntry.objects.filter(event=event).order_by("seq"))
        head = AuditEntry.chain_head(event)
        problems = chain_module.verify_chain(event)

        self.stdout.write("=" * 66)
        self.stdout.write(f" audit chain -- event {event.pk} -- {event.name}")
        self.stdout.write("=" * 66)
        self.stdout.write(f"  entries       {len(entries)}")
        self.stdout.write(f"  chain head    {head or '(empty chain)'}")
        if entries:
            self.stdout.write(f"  sequence      {entries[0].seq}..{entries[-1].seq}")
        else:
            self.stdout.write("  sequence      -")
        omitted = sum(entry.omitted_since_prev for entry in entries)
        if omitted:
            self.stdout.write(
                f"  DISCLOSED     {omitted} sampled-out action(s) recorded inside the chain"
            )
        self.stdout.write("")

        show = max(int(options["show"]), 0)
        for entry in entries[-show:] if show else []:
            actor = entry.actor.email if entry.actor_id else "(anonymous)"
            self.stdout.write(
                f"  #{entry.seq:<4} {entry.action:<18} {actor:<34} {entry.entry_hash[:12]}"
            )
        if show and len(entries) > show:
            self.stdout.write(f"  ... {len(entries) - show} earlier entries not shown")
        if show:
            self.stdout.write("")

        if problems:
            self.stdout.write("  CHAIN BROKEN. Each line is a different problem:")
            for problem in problems:
                self.stdout.write(f"    - {problem}")
            raise CommandError(f"{len(problems)} chain problem(s)")

        self.stdout.write(
            f"  CHAIN VERIFIED -- {len(entries)} entries re-walked, every entry hash"
            " recomputed from its own contents."
        )
