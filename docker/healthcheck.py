#!/usr/bin/env python3
"""Container healthcheck.

Kept as a script rather than a shell one-liner for one reason: the Dockerfile
HEALTHCHECK, the compose healthcheck and a human running `docker exec` all call
this same file, so there is exactly one definition of "healthy" and a change to
it cannot land in one of the three places.

It deliberately uses only the standard library and only HTTP against
localhost. It does not import Django, does not read the database and does not
touch the volume — a healthcheck that needs a working database cannot report
healthy during the migration that creates one, which is exactly when the
container most needs to be told apart from a broken one.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

PORT = os.environ.get("PORT", "8080")
URL = f"http://127.0.0.1:{PORT}/healthz"

# Short on purpose. Docker's own --timeout is 4s; a check that takes longer
# than that reports a timeout rather than our error message, which throws away
# the diagnostic.
DEADLINE_SECONDS = 3


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=DEADLINE_SECONDS) as response:
            if response.status != 200:
                print(f"unhealthy: {URL} returned {response.status}")
                return 1
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        print(f"unhealthy: {URL} returned {exc.code}")
        return 1
    except Exception as exc:  # noqa: BLE001 - the point is to report anything
        print(f"unhealthy: {URL} unreachable: {type(exc).__name__}: {exc}")
        return 1

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(f"unhealthy: {URL} did not return JSON: {body[:120]!r}")
        return 1

    if payload.get("status") != "ok":
        print(f"unhealthy: {payload}")
        return 1

    print(f"healthy: {payload}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
