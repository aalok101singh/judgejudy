"""``manage.py build_openapi`` -- write the API document, or refuse to.

The `just schema` recipe used to run `manage.py spectacular`, which introspects DRF
views. **This API is plain Django views on purpose**, so the introspector found
nothing and emitted ``paths: {}`` -- a valid, committed, entirely empty OpenAPI
document. That is F-61's shape with a `paths:` key: it looks like a deliverable,
it is served, and it describes nothing.

So the document is assembled from ``reviewer.api.documents.PATHS`` and this command
refuses to write it if the table and ``urls.py`` disagree. **A partial document is
worse than none**, because a client built from it will 404 against an endpoint it
was never told existed.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Write openapi.yaml from the declarations, refusing if they have drifted."

    def add_arguments(self, parser):
        parser.add_argument("--file", default="openapi.yaml", help="Where to write it.")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Do not write; fail if the committed document is out of date.",
        )

    def handle(self, *args, **options):
        import django

        django.setup()
        from reviewer.api import schema

        try:
            text = schema.document()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        destination = Path(settings.REPO_ROOT) / options["file"]
        if options["check"]:
            current = destination.read_text(encoding="utf-8") if destination.exists() else ""
            if current != text:
                raise CommandError(
                    f"{destination.name} is out of date. Run `just schema` and commit "
                    "the result -- a stale API document is the one a client author "
                    "trusts and should not."
                )
            self.stdout.write(f"{destination.name} is current.")
            return

        destination.write_text(text, encoding="utf-8", newline="\n")
        parsed = schema.api_paths()
        self.stdout.write(
            f"wrote {destination.name}: {len(parsed['paths'])} paths, openapi {parsed['openapi']}"
        )
        for path in sorted(parsed["paths"]):
            self.stdout.write(f"  {path}")
