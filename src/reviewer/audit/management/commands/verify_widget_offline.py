"""``manage.py verify_widget_offline`` -- render the widget with no network at all.

**This is the acceptance line, and it is deliberately run inside the container
started with ``--network none``** (``just prove-offline``). The pytest suite proves
the document contains no external reference; this proves the *server* produces
that document with no way to reach anything else while it does.

**Why it lives in ``reviewer.audit`` and not in ``reviewer.widget``.** The command
has to be inside an app for Django to discover it, and ``reviewer.widget``
deliberately is **not an app** -- see ``DATA-MODEL.md``: registering an app with no
models would add a ``models`` module that does not exist and a migration that
creates nothing, which is the same reason ``reviewer/isolation/`` and
``reviewer/normalization/`` are packages. The widget obeys the publication gate
this app owns (``ResultPublication``), so the proof lives here rather than forcing
a fourteenth app into a document that says thirteen.

**Why it publishes the event rather than just probing a 403.** The shipped fixture
is born with ``results_state = hidden`` -- that is the REQ-T3-03 rule and the T1
check depends on it. A probe against a hidden event would fetch a 403 with an empty
body, which is a trivially-satisfiable pass: a widget that 403s everything renders
offline beautifully. So this command publishes, fetches, asserts the **rows are
there**, and then **restores the original state**.

The restore is not a courtesy. A verification step that leaves the demo published
would make the next T1 check fail for a reason that has nothing to do with the
code, which is exactly the class of damage this project keeps refusing to do.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError

BASE = "http://127.0.0.1:8080"

#: Each of these is an external reference the document must not contain. **The
#: assertion is on absence**, because "renders offline" is a property of what is
#: NOT there.
FORBIDDEN = ("<script", "<link", "<img", "@import", "http://", "https://")


def _fetch(path: str) -> tuple[int, str]:
    url = BASE + path
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing to fetch a non-HTTP URL: {url!r}")
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # pragma: no cover - the container is up or it is not
        return 0, f"{type(exc).__name__}: {exc}"


class Command(BaseCommand):
    help = "Prove the widget renders with no network: publish, fetch, assert, restore."

    def handle(self, *args, **options):
        from reviewer.events.models import Event

        event = Event.objects.order_by("pk").first()
        if event is None:
            raise CommandError("no event exists; load the fixtures first")

        original = event.results_state
        if original != "published":
            Event.objects.filter(pk=event.pk).update(results_state="published")
        try:
            failures = self._check()
        finally:
            Event.objects.filter(pk=event.pk).update(results_state=original)

        if failures:
            raise CommandError(
                f"the widget did not render offline: {failures}. Note that this ran "
                f"inside a container with --network none, so any external reference "
                f"would have failed here and nowhere else."
            )
        self.stdout.write("WIDGET OFFLINE: PASS (fetched, ranked, no external reference)")

    def _check(self) -> list[str]:
        failures: list[str] = []

        status, body = _fetch("/widget/results/")
        if status != 200:
            return [f"GET /widget/results/ returned HTTP {status}"]
        self.stdout.write(f"   {'GET /widget/results/':<28} PASS (HTTP 200, {len(body)} bytes)")

        for token in FORBIDDEN:
            if token in body.lower():
                failures.append(f"the document contains {token!r}, which is a network request")

        for block in re.findall(r"<style>(.*?)</style>", body, re.S):
            if "url(" in block:
                failures.append("the inlined CSS fetches something with url()")

        rows = body.count("<tr>")
        if rows < 2:
            failures.append(
                f"the document has {rows} table row(s); a widget that renders an "
                "empty ranking is offline and useless (F-61's shape)"
            )
        else:
            self.stdout.write(f"   {'ranking in the bytes':<28} PASS ({rows - 1} rows)")

        status, data = _fetch("/widget/results.json")
        if status != 200:
            failures.append(f"GET /widget/results.json returned HTTP {status}")
        elif "unnormalized-raw-weighted-mean" not in data:
            failures.append("the JSON does not say how the ranking was computed")
        else:
            self.stdout.write(f"   {'GET /widget/results.json':<28} PASS")

        for failure in failures:
            self.stderr.write(f"   FAIL: {failure}")
        return failures
