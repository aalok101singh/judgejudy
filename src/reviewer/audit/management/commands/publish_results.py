"""``manage.py publish_results`` -- freeze the ranking and the chain head.

Writes a ``ResultPublication`` and replicates ``results_hash`` plus
``audit_chain_head`` into every signed judge record (D-09).

Two things it prints that a naive version would not:

* **the digest is re-derivable**, so the command says so rather than implying the
  hash is a secret or a signature;
* **how many signed records agree and how many disagree.** A non-zero
  ``disagrees`` means a judge signed, then the result changed underneath them --
  which is precisely the equivocation this replication exists to expose, and the
  one thing an organizer cannot see from inside their own database.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviewer.audit import publication


class Command(BaseCommand):
    help = "Publish the ranking, freeze its hash, and stamp every signed record."

    def add_arguments(self, parser):
        parser.add_argument("--event", default="", help="Which event to publish.")
        parser.add_argument(
            "--show-only",
            action="store_true",
            help="Print what would be published without writing a row.",
        )

    def handle(self, *args, **options):
        from reviewer.events.models import Event

        event = (
            Event.objects.get(pk=options["event"]) if options["event"] else Event.objects.first()
        )
        if event is None:
            raise CommandError("no event exists; load the fixtures first")

        organizer = _organizer(event)
        if organizer is None:
            raise CommandError(f"no organizer binding exists for {event.pk}")

        rows = publication.ranking_for(event, organizer)
        digest = publication.input_digest(event)

        if options["show_only"]:
            self.stdout.write(
                f"WOULD PUBLISH {len(rows)} rows for {event.pk}\n"
                f"  input_digest   {digest}\n"
                f"  results_hash   {publication.results_hash(rows, digest)}\n"
                f"  chain_head     {publication.chain_head(event)}"
            )
            return

        record = publication.publish(event, organizer)
        report = publication.replication_report(event, record)

        self.stdout.write(
            f"PUBLISHED {event.pk}: {len(record.ranking)} rows\n"
            f"  input_digest   {record.input_digest}\n"
            f"  results_hash   {record.results_hash}\n"
            f"  chain_head     {record.audit_chain_head}\n"
            f"  signed records {report['agrees']} agree, {report['disagrees']} disagree, "
            f"{report['no_results_hash']} carry no hash\n"
            f"  publication    {record.pk}"
        )
        self.stdout.write(
            "\nBoth hashes are re-derivable from the raw scores by anyone holding the "
            "export.\nA mismatch means the ranking was edited after publication."
        )
        if report["disagrees"]:
            self.stdout.write(
                f"\n  WARNING: {report['disagrees']} signed record(s) disagree with this "
                "publication. A judge signed, and the result changed afterwards."
            )


def _organizer(event):
    """The first organizer for this event, as an ``Actor``.

    Publication is an organizer action and the command has no credentials of its
    own -- it runs inside the container with the database's credentials. **That is
    a deliberate limit, stated rather than hidden:** this command can publish
    *because it is the operator*, and the actor it builds is the organizer's.
    Anything that published on an unauthenticated actor's word would be a worse
    bug than this one.
    """
    from reviewer.accounts.models import RoleBinding
    from reviewer.isolation import Actor

    binding = (
        RoleBinding.objects.filter(event=event, role="organizer").select_related("user").first()
    )
    if binding is None:
        return None
    return Actor.for_user(event, binding.user)
