"""``manage.py sign_records`` -- sign every judge's participation.

The writer F-97 says was missing. Before this existed, ``JudgeCredential`` and
``SignedRecord`` shipped with complete schemas and **no code path that created
either**, so D-09's replication had nothing to replicate into.

What it prints, and why each line is there:

* **how many judges were signed and how many were skipped**, because a skipped
  judge is a judge whose participation is uncovered and a count of only the
  signed ones hides that;
* **the key fingerprints**, so a human can say "key ``a3f1...``" in an audit
  conversation instead of reading 32 bytes aloud;
* **the verification result**, run immediately after signing. A signer that
  reports success without verifying its own output is the F-61 shape with a
  signature on it.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviewer.credentials import keys, signing


class Command(BaseCommand):
    help = "Sign every judge's participation record with their Ed25519 key."

    def add_arguments(self, parser):
        parser.add_argument("--event", default="", help="Which event to sign.")
        parser.add_argument(
            "--reissue-keys",
            action="store_true",
            help="Replace existing keys. ORPHANS EVERY PREVIOUS SIGNATURE.",
        )
        parser.add_argument(
            "--verify-only",
            action="store_true",
            help="Do not sign; verify what is already stored.",
        )

    def handle(self, *args, **options):
        from reviewer.events.models import Event

        event = (
            Event.objects.get(pk=options["event"]) if options["event"] else Event.objects.first()
        )
        if event is None:
            raise CommandError("no event exists; load the fixtures first")

        self.stdout.write(f"keys on their own volume: {keys.keys_dir()}")

        if options["verify_only"]:
            report = signing.verify_event(event)
            self._print(report)
            return

        if options["reissue_keys"]:
            self.stderr.write(
                "REISSUING KEYS: every signature made with the old key becomes "
                "unverifiable, and nothing in the schema records that this happened."
            )

        records = signing.sign_all(event, overwrite=options["reissue_keys"])
        judges = self._judge_count(event)
        self.stdout.write(
            f"SIGNED {len(records)} of {judges} judges\n"
            f"  keys         {keys.keys_dir()} (mode 0600, never in the database)"
        )
        for record in records[:5]:
            fingerprint = keys.public_key_fingerprint(bytes.fromhex(record.credential.public_key))
            self.stdout.write(f"  {record.judge.email:<40} key {fingerprint}…")
        if len(records) > 5:
            self.stdout.write(f"  … and {len(records) - 5} more")

        skipped = judges - len(records)
        if skipped:
            self.stdout.write(
                f"\n  {skipped} judge(s) signed NO RECORD because they submitted "
                "nothing.\n  An empty-subject statement is valid in-toto and proves "
                "nothing, so no record is written."
            )

        self._print(signing.verify_event(event))

    def _judge_count(self, event) -> int:
        from reviewer.accounts.models import RoleBinding

        return RoleBinding.objects.filter(event=event, role="judge").count()

    def _print(self, report: dict) -> None:
        self.stdout.write(f"\nVERIFY: {report['ok']} of {report['total']} records valid")
        for detail in report["details"]:
            if not detail["ok"]:
                self.stdout.write(f"  record {detail['record']}: {detail['why']}")
        if report["bad"]:
            raise CommandError(f"{report['bad']} signed record(s) did not verify")
