#!/usr/bin/env python3
"""Probe the running portal from inside the container. Stdlib only.

Run inside a `--network none` container by tools/prove_offline.py, which
mounts this file. It is deliberately a separate file rather than an inline
`sh -c "..."` string: three layers of quoting — PowerShell, then docker, then
`sh` — is where a reviewer loses half an hour, and a proof that is awkward to
re-run is a proof that does not get re-run.

The probes assert on CONTENT, not just status. A healthcheck alone would pass
for a process serving an empty page, or a proxy error page, or a redirect to
nowhere; requiring our own title in the body is what makes the result mean
something.

`/admin/` expects 200 or 302 and nothing else. A 302 to the login page is the
correct answer for an anonymous request, and a 403 would be wrong — an
unauthenticated visitor is not a forbidden role, and conflating the two is
precisely the mistake the isolation design is trying to avoid elsewhere.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"


def probe(path: str) -> tuple[int, str]:
    """Return (status, body). Never raises: a refusal is a measurement too.

    The scheme is asserted rather than assumed, which is what S310 is actually
    worried about. It is checked here rather than silenced in the config so the
    reason is attached to the code that could go wrong.
    """
    url = BASE + path
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing to fetch a non-HTTP URL: {url!r}")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    failures = 0

    status, body = probe("/healthz")
    ok = status == 200
    print(f"   {'GET /healthz':<28} {'PASS' if ok else 'FAIL'} (HTTP {status})")
    if not ok:
        failures += 1
        print(f"      body: {body[:160]!r}")

    status, body = probe("/")
    ok = status == 200 and "Judge Judy" in body
    print(f"   {'GET /':<28} {'PASS' if ok else 'FAIL'} (HTTP {status})")
    if not ok:
        failures += 1
        print(f"      body: {body[:160]!r}")

    status, _ = probe("/admin/")
    ok = status in (200, 302)
    print(f"   {'GET /admin/ reachable':<28} {'PASS' if ok else 'FAIL'} (HTTP {status})")
    if not ok:
        failures += 1

    # The deep probe touches the database. It must pass in an empty namespace
    # too: a portal that needs a network to reach its own database has not been
    # tested.
    status, body = probe("/healthz?deep=1")
    ok = status == 200 and '"database": "ok"' in body.replace(" ", " ")
    print(f"   {'GET /healthz?deep=1':<28} {'PASS' if ok else 'FAIL'} (HTTP {status})")
    if not ok:
        failures += 1
        print(f"      body: {body[:200]!r}")

    print()
    print(f"   NO-NETWORK BOOT: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
