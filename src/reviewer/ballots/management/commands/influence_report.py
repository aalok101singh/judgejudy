"""``manage.py influence_report`` -- render the anti-abuse report, or say there is none.

**This is the rendering half of FEAT-06's acceptance line** ("the influence report
renders for a synthetic attack"), and the reason it is a *command* rather than a
function the tests call is the same reason `verify_audit` is: a report that only
ever gets rendered by the suite is a report whose existence is a claim rather
than an artefact. A reviewer with the repository and a container runs this and
gets an answer in front of them.

**The command prints the method and its caveat every single time.** The table
without the caveat is a table of accusations, and the caveat is the difference
between a measurement and a verdict. It is printed as part of the output rather
than left in the docstring because a person skimming a table does not read
docstrings.

**The empty case prints a sentence, and that is the F-61 defence in the place it
matters most.** The shipped fixture has zero votes. An implementation that
iterated the projects and printed a row each would emit forty-one lines of
``gini 0.00, lift 0.00`` and a reader would conclude the event had been checked
and found clean. It has not been checked; nothing has been cast. So the command
prints *no votes have been cast* and returns, and `tests/test_influence.py`
asserts that no table of zeros can appear.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviewer.ballots import influence as influence_module


class Command(BaseCommand):
    """Print the per-project influence report. Says so plainly when there is none."""

    help = "Render the vote-concentration influence report for an event (D-13)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--event",
            default="evt_01",
            help="Event id to report on. Defaults to the fixture's, evt_01.",
        )

    def handle(self, *args, **options):
        from reviewer.events.models import Event

        try:
            event = Event.objects.get(pk=options["event"])
        except Event.DoesNotExist as exc:
            raise CommandError(f"no event {options['event']!r} in this database") from exc

        report = influence_module.report(event)

        self.stdout.write("=" * 78)
        self.stdout.write(f" influence report -- event {event.pk} -- {event.name}")
        self.stdout.write("=" * 78)
        self.stdout.write(f"  method   {influence_module.REPORT_METHOD}")
        self.stdout.write("")

        if report is None:
            # F-61's shape, refused. A table of zeroes here would read as
            # "checked, and nothing to report" when the truth is "nothing to
            # check", and those are the sentences a reader acts on.
            self.stdout.write("  NO VOTES HAVE BEEN CAST.")
            self.stdout.write("")
            self.stdout.write("  There is no concentration to report, and this is NOT a")
            self.stdout.write("  finding of 'no brigade'. Cast ballots, then re-run.")
            return

        self.stdout.write(
            f"  {report['identities']} distinct identities, {report['votes']} votes,"
            f" {report['projects']} project(s) voted for"
        )
        self.stdout.write("")

        header = f"  {'project':<12} {'ids':>4} {'1st%':>7} {'gini':>6} {'clustered':>10}"
        self.stdout.write(header)
        self.stdout.write("  " + "-" * (len(header) - 2))

        for row in report["ranking"]:
            self.stdout.write(
                f"  {row['project']:<12}"
                f" {row['identities']:>4}"
                f" {row['first_preference_share'] * 100:>6.1f}%"
                f" {row['vote_mass_gini'] if row['vote_mass_gini'] is not None else '-':>6}"
                f" {row['clustered_identities']:>10}"
            )

        self.stdout.write("")
        self.stdout.write("  Most suspicious first: an exact-match brigade, then a")
        self.stdout.write("  lopsided weight distribution, then first-preference share.")
        self.stdout.write("  'clustered' counts identities voting a byte-identical ballot.")
        self.stdout.write("")
        for line in _wrap(influence_module.INTERPRETATION, 74):
            self.stdout.write(f"  {line}")


def _wrap(text: str, width: int) -> list[str]:
    """Naive greedy wrap. Only ever applied to one constant, so it stays naive."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
