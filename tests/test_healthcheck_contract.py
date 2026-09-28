"""The healthcheck TIMING contract, asserted as numbers.

These assert on two documented constants: the image's `HEALTHCHECK
--start-period` and compose's `healthcheck.start_period`.

It is tempting to argue they need no test, because a start period that is too
short produces no failing test — it produces a *slow* container that reports
itself unhealthy on a busy machine and healthy on an idle one. That is exactly
the class of defect this project exists to catch: **a wrong number that looks
correct everywhere you happen to look.** The measured cold start is 6.2 s, the
budget is 60 s, and the start period exists to cover a reviewer's first
`slow` boot on a machine we have never seen. The number is the thing being
protected, so the number gets a test.

If a future change makes these fail, the question to ask is "is the real cold
start still comfortably under this?" — not "can I relax the assertion".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


class TestHealthcheckContract:
    """Two timing constants that must never be quietly relaxed."""

    def test_dockerfile_start_period_covers_the_measured_cold_start(self) -> None:
        """The image's start period must be at least 45 s.

        Measured cold start is 6.2 s to a serving page with a warm build cache.
        45 s leaves room for a reviewer's first boot, which includes Docker
        unpacking layers on a machine that has never run this image. The
        original value of 10 s was itself a defect discovered during FEAT-01: it
        was below the real cold start, so the container reported itself
        unhealthy during normal operation.
        """
        dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")

        match = re.search(r"HEALTHCHECK[^#\n]*--start-period=(\d+)s", dockerfile)
        assert match, (
            "The Dockerfile HEALTHCHECK has no --start-period. Without one, "
            "Docker applies its own default and the portal is judged healthy "
            "or unhealthy against a number nobody chose."
        )

        assert int(match.group(1)) >= 45, (
            f"Dockerfile start-period is {match.group(1)}s, below the 45s the "
            f"measured cold start requires. A start period shorter than the "
            f"real boot makes a working portal report itself unhealthy."
        )

    def test_compose_start_period_matches_the_dockerfile(self) -> None:
        """compose and the Dockerfile must not disagree about readiness.

        Two definitions of "healthy" in two files is two places to forget to
        update, and the one that is wrong is the one the reviewer hits — because
        `docker compose up --wait` polls the compose healthcheck, not the
        image's.
        """
        compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")

        match = re.search(r"start_period:\s*(\d+)s", compose)
        assert match, (
            "docker-compose.yml has no healthcheck.start_period, so `up --wait` "
            "uses Docker's default rather than a number we chose."
        )

        assert int(match.group(1)) >= 45, (
            f"compose start_period is {match.group(1)}s. `docker compose up "
            f"--wait` polls THIS, so it is the value that decides when a "
            f"reviewer's `up` returns."
        )

    def test_the_healthcheck_is_one_script(self) -> None:
        """Dockerfile, compose and the offline proof all call one file.

        Three definitions of "healthy" is three places to forget. The Dockerfile
        and compose must both name `docker/healthcheck.py`, and must not inline
        a curl that could drift from it.
        """
        dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
        compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")

        assert "/app/healthcheck.py" in dockerfile, (
            "The Dockerfile HEALTHCHECK should call the shared script, not an inline command."
        )
        assert "healthcheck.py" in compose, (
            "compose should call the same script the Dockerfile does."
        )
        # An inline curl is the specific thing that drifts.
        assert "curl" not in compose, (
            "docker-compose.yml contains an inline curl. The healthcheck must "
            "be the one script in docker/healthcheck.py, or the two will "
            "disagree about what 'healthy' means."
        )

    def test_the_probe_never_reports_healthy_on_a_body_it_did_not_verify(
        self,
    ) -> None:
        """`tools/coldstart.py` must assert on content, not only on status.

        A 200 from a proxy, a placeholder, or a previous container that never
        died all satisfy a bare status check. This is the difference between
        measuring the portal and measuring that a socket answered.
        """
        import sys

        tools = str(REPO / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        coldstart = pytest.importorskip("coldstart")

        ok, message = coldstart.verdict(200, "<html>a proxy error</html>", 1.0)
        assert not ok
        assert "not ours" in message
