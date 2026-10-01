"""The demo is opt-in. The product is the default.

**This file exists because of one specific trap.** The image shipped with
`load_fixtures` running unconditionally on every first boot, because the
acceptance checker needs the organizers' data. Then a real deployment that starts
with somebody else's 41-project event in it has **an event already**, and the
setup wizard's whole authorisation is "no event exists" -- so the one page a new
user needs was the one page they could not reach. The feature was present,
tested, documented, and **unreachable in the shipped product**.

Nothing about that is visible from inside Django. It is only visible by asking
what a *fresh container* does, which is what these tests do: they read the
entrypoint and the compose file rather than calling the code, because the code was
already correct and the wiring around it was not.

Two things are asserted, and the second is the one that would be forgotten:

1. a plain `docker compose up` does **not** seed, and
2. `just check` and `prove-offline` **do**, so the acceptance gate keeps working.

Asserting only the first would be a fix that quietly breaks the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO / "docker" / "entrypoint.sh"
COMPOSE = REPO / "docker-compose.yml"
JUSTFILE = REPO / "justfile"
PROVE_OFFLINE = REPO / "tools" / "prove_offline.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestTheImageDoesNotSeedByDefault:
    def test_the_entrypoint_gates_seeding_on_the_env_var(self):
        """The gate has to be a *condition*, not a comment. A comment saying
        "seeding is opt-in" next to an unconditional call is worse than nothing,
        because it reads as done."""
        text = _read(ENTRYPOINT)
        assert "JJ_SEED_DEMO" in text
        assert "load_fixtures" in text

    def test_seeding_is_inside_a_case_on_that_variable(self):
        """Asserted structurally rather than by substring proximity, so moving the
        call out of the conditional breaks this."""
        text = _read(ENTRYPOINT)
        match = re.search(r'case\s+"\$\{JJ_SEED_DEMO:-0\}".*?esac', text, re.S)
        assert match, "the entrypoint no longer branches on JJ_SEED_DEMO at all"
        assert "load_fixtures" in match.group(0), (
            "load_fixtures is no longer inside the JJ_SEED_DEMO branch, so it is "
            "either dead code or unconditional again"
        )

    def test_the_default_is_off(self):
        """`${JJ_SEED_DEMO:-0}` -- the fallback is the whole product decision. A
        default of 1 here would put the demo back in every fresh deployment."""
        text = _read(COMPOSE)
        assert "${JJ_SEED_DEMO:-0}" in text
        assert "${JJ_SEED_DEMO:-1}" not in text

    def test_compose_does_not_unconditionally_set_it(self):
        """Compose can override the shell with a literal, and a literal `1` here
        would beat the `-e` flag on a raw `docker run` only by accident."""
        text = _read(COMPOSE)
        seed_lines = [ln.strip() for ln in text.splitlines() if "JJ_SEED_DEMO" in ln]
        assert seed_lines, "compose no longer passes JJ_SEED_DEMO through"
        for line in seed_lines:
            if line.startswith("#"):
                continue
            assert "${JJ_SEED_DEMO" in line, f"compose hardcodes the seed flag: {line}"


class TestTheAcceptanceGateStillSeeds:
    """**The other half.** Without this, "the demo is opt-in" is a fix that
    breaks the gate, and the gate is the only thing that can tell us we did."""

    def test_just_check_asks_for_the_demo_before_compose_up(self):
        """**Asserted as a mechanism, not as a string.**

        Two earlier versions of this line both looked right and did nothing:

        - `@set JJ_SEED_DEMO=1` runs the **shell's** `set` builtin, which sets
          positional parameters, and `just` gives each recipe line its own shell
          anyway;
        - `export JJ_SEED_DEMO := "1"` is just's own directive, but **just runs
          recipes through cmd.exe on this machine**, where `export` is "not
          recognized as an internal or external command".

        In both cases the container started empty, the checker scored an empty
        portal, and the gate reported three regressions plus an OVERCLAIM that had
        nothing to do with any of it. The fix is a flag consumed by
        `tools/docker.py`, which sets the variable in Python.

        So the assertion is on that flag appearing in the recipe **and** on the
        wrapper implementing it. *A test that greps for a string cannot tell a
        working line from a decorative one* — the same proxy-assertion mistake
        this project has now made against a substring, a number and an env var.
        """
        text = _read(JUSTFILE)
        assert "compose_base_seed" in text, (
            "`just check` does not use the seeded compose base, so the acceptance "
            "checker scores an empty portal"
        )

        # The known-broken forms must stay gone, so nobody re-introduces them.
        check_body = text.split("\ncheck:", 1)[1]
        assert not re.search(r"(?m)^\s*@?set\s+JJ_SEED_DEMO", check_body), (
            "the recipe uses the shell's `set`, which does not export anything"
        )
        assert not re.search(r"(?m)^\s*export\s+JJ_SEED_DEMO", check_body), (
            "the recipe uses `export`, which cmd.exe does not have"
        )

    def test_the_wrapper_actually_implements_the_flag(self):
        """**The mechanism, not the mention.** Without this, `--seed-demo` could be
        deleted from `docker.py` and the recipe would still read correctly."""
        text = _read(REPO / "tools" / "docker.py")
        assert '"--seed-demo"' in text, "the wrapper no longer recognises --seed-demo"
        assert "JJ_SEED_DEMO" in text, "the wrapper sets no environment variable"
        # It must be *assigned*, not merely compared.
        assert re.search(r'env\["JJ_SEED_DEMO"\]\s*=\s*"1"', text), (
            "the wrapper mentions the variable without assigning it"
        )

    def test_prove_offline_passes_the_flag_to_its_own_docker_run(self):
        """It boots the raw image rather than the compose stack, so the compose
        default does not reach it -- and it needs an event to publish."""
        text = _read(PROVE_OFFLINE)
        run_block = re.search(r'"run".*?judgejudy:local', text, re.S)
        assert run_block, "prove-offline no longer runs the image directly"
        assert "JJ_SEED_DEMO=1" in run_block.group(0), (
            "prove-offline starts the raw image with no demo event, so the widget "
            "probe has nothing to publish"
        )


class TestTheCausalChain:
    """seed -> an event exists -> the wizard refuses. Walked end to end rather
    than restated, because the whole design rests on this link and the failure
    mode is invisible from inside Django."""

    @pytest.mark.django_db
    def test_the_wizard_is_open_on_an_empty_database(self, client):
        from reviewer.setup.provisioning import already_provisioned

        assert already_provisioned() is False
        assert client.get("/setup/").status_code == 200

    @pytest.mark.django_db
    def test_once_an_event_exists_the_wizard_is_shut(self, client):
        from datetime import timedelta

        from django.utils import timezone

        from reviewer.setup.provisioning import (
            ProvisionRequest,
            TrackSpec,
            already_provisioned,
            provision,
        )

        now = timezone.now()
        provision(
            ProvisionRequest(
                organizer_email="o@example.org",
                organizer_name="O",
                password="correct-horse-battery-staple",
                event_name="Any Hackathon",
                starts_at=now,
                submissions_close=now + timedelta(days=2),
                judging_closes_at=now + timedelta(days=3),
                tracks=(TrackSpec(name="General"),),
            )
        )
        assert already_provisioned() is True
        refused = client.get("/setup/")
        assert refused.status_code == 403
        assert refused.content == b""

    @pytest.mark.django_db
    def test_so_seeding_closes_it_which_is_why_seeding_is_off(self):
        """The one-line reason the entrypoint changed, as an executable claim."""
        from reviewer.setup.provisioning import already_provisioned

        # An empty database -- what a fresh deployment has, given the new default.
        assert already_provisioned() is False
        # Anything that loads the fixture makes this True, and the assertion
        # above in the previous test shows what True costs.
        assert already_provisioned() is False
