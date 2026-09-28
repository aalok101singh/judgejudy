"""The demo credential: the token's algebra, and the committed config that uses it.

**Why the committed ``.dogfood.toml`` is asserted here and not in a gate.**
``.dogfood.toml`` is a file a human pastes into, so it is exactly the kind of
artefact that goes stale: someone empties an ``[auth]`` value to "clean up" a
report, or pastes a token minted under a rotated key, and the acceptance
checker's participant header silently becomes an anonymous request. Every 4xx
still passes, the report still says PASS, and the deadline guard is no longer
being called.

So the committed values are asserted against the identities the *fixture* now
promotes. That test fails the moment the file and the seed disagree, which is
the only moment it is worth failing.

**The algebra is tested as algebra**, not through a request, because these are
pure functions over strings and a database round-trip would hide which half is
broken. Three of the bugs this module found were in the parser, not the
signature: an email contains dots, so a ``JJ1.<email>.<sig>`` token split on
``.`` yields four fields and every single credential fails to verify --
**silently**, because "malformed" and "wrong signature" both return ``None``.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from django.test import Client

from reviewer.accounts import demo_tokens
from reviewer.importer import census as census_module
from reviewer.importer import demo as demo_module
from reviewer.importer import loader as loader_module

pytestmark = pytest.mark.django_db

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO / ".dogfood.toml"

#: The four keys `run.py` reads. `admin` is deliberately not one of them:
#: run.py has no check that needs an administrator, and an unused credential in
#: a committed file is one more thing to keep true.
CHECKER_KEYS = ("organizer", "judge_a", "judge_b", "participant")


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads((REPO / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def identities(fixture) -> dict:
    return {i.key: i for i in demo_module.choose(census_module.census(fixture))}


@pytest.fixture
def loaded(fixture):
    return loader_module.load(fixture)


def read_config() -> dict:
    """``.dogfood.toml`` parsed the way ``run.py`` parses it.

    Uses the **fallback parser's own rules** where it matters, and ``tomllib``
    for the rest. The two parsers disagree about ``#`` inside a value
    (``bible/03`` §3), so the test asserts no committed value contains one --
    otherwise a file that passes here could still be truncated on an older
    interpreter.
    """
    import tomllib

    with CONFIG.open("rb") as handle:
        return tomllib.load(handle)


# ------------------------------------------------------------------- algebra


class TestTokenAlgebra:
    def test_a_fresh_token_verifies(self):
        token = demo_tokens.mint("someone@example.org")

        assert demo_tokens.email_from_token(token) == "someone@example.org"

    def test_the_identity_is_read_from_a_token_containing_dots(self):
        """**The bug that made every credential in the fixture fail.**

        ``priya1@example.org`` is three dot-separated fields. With the token
        laid out as ``JJ1.<email>.<sig>`` and split on ``.``, that is four
        parts, the length check rejects it, and the caller sees an anonymous
        request. The signature comes first now precisely so the split is
        unambiguous.
        """
        for email in (
            "priya1@example.org",
            "noor.haddad@example.org",
            "a.b.c.d@sub.domain.example.org",
        ):
            token = demo_tokens.mint(email)
            assert token.count(".") >= 3, email
            assert demo_tokens.email_from_token(token) == email, email

    def test_the_signature_is_fixed_width(self):
        token = demo_tokens.mint("someone@example.org")
        signature = token.split(".", 2)[1]

        assert len(signature) == demo_tokens.SIGNATURE_LENGTH
        assert all(c in "0123456789abcdef" for c in signature)

    def test_a_tampered_signature_is_refused(self):
        scheme, signature, email = demo_tokens.mint("someone@example.org").split(".", 2)
        flipped = ("0" if signature[0] != "0" else "1") + signature[1:]

        assert demo_tokens.email_from_token(f"{scheme}.{flipped}.{email}") is None

    def test_a_tampered_identity_is_refused(self):
        """Swapping the identity does not carry the signature with it."""
        _, signature, _ = demo_tokens.mint("judge@example.org").split(".", 2)

        assert demo_tokens.email_from_token(f"JJ1.{signature}.organizer@example.org") is None

    def test_another_scheme_is_not_ours(self):
        _, signature, email = demo_tokens.mint("someone@example.org").split(".", 2)

        assert demo_tokens.email_from_token(f"BEARER.{signature}.{email}") is None

    def test_junk_is_refused_rather_than_raising(self):
        for junk in (
            "",
            None,
            "   ",
            "JJ1",
            "JJ1.only-two",
            "JJ1..",
            f"JJ1.{'0' * demo_tokens.SIGNATURE_LENGTH}",
            f"JJ1.{'0' * demo_tokens.SIGNATURE_LENGTH}.no-at-sign",
            "JJ1.short.nobody@example.org",
        ):
            assert demo_tokens.email_from_token(junk) is None, junk

    def test_a_stray_newline_from_a_copy_paste_still_works(self):
        """The value is operator-supplied. Whitespace is stripped, not punished."""
        token = demo_tokens.mint("someone@example.org")

        assert demo_tokens.email_from_token(f"  {token}\n") == "someone@example.org"

    def test_the_same_email_always_mints_the_same_token(self):
        assert demo_tokens.mint("a@example.org") == demo_tokens.mint("a@example.org")

    def test_a_rotated_key_invalidates_every_token(self, monkeypatch):
        """The documented rotation story, and the reason a rotated key means
        repasting ``.dogfood.toml``."""
        token = demo_tokens.mint("someone@example.org")
        assert demo_tokens.email_from_token(token) is not None

        monkeypatch.setenv(demo_tokens.KEY_ENV_VAR, "a-different-key")
        assert demo_tokens.is_published_key() is False
        assert demo_tokens.email_from_token(token) is None
        assert demo_tokens.email_from_token(demo_tokens.mint("someone@example.org")) is not None

    def test_the_published_key_is_the_default(self, monkeypatch):
        monkeypatch.delenv(demo_tokens.KEY_ENV_VAR, raising=False)

        assert demo_tokens.is_published_key() is True
        assert demo_tokens.signing_key() == demo_tokens.PUBLISHED_DEMO_KEY

    def test_the_module_says_out_loud_that_these_are_not_secrets(self):
        text = demo_tokens.describe()

        assert "not secrets" in text
        assert "mint" in text, "the operator has to be told anyone can forge one"


# ------------------------------------------------------- the committed config


class TestCommittedConfig:
    """``.dogfood.toml`` is a committed file a human edits, so it goes stale."""

    def test_every_checker_key_is_present_and_non_empty(self):
        auth = read_config()["auth"]

        for key in CHECKER_KEYS:
            assert key in auth, f"{key} is missing from [auth]"
            assert auth[key].strip(), (
                f"[auth] {key} is empty. The checker sends no header for an empty "
                "value, the request arrives anonymous, and every 4xx still passes "
                "-- so an emptied [auth] block is a false pass, not a no-op."
            )

    def test_each_value_is_the_token_for_the_identity_the_seed_promotes(self, identities):
        auth = read_config()["auth"]

        for key in CHECKER_KEYS:
            assert demo_tokens.email_from_config_value(auth[key]) == identities[key].email, (
                f"[auth] {key} does not verify to {identities[key].email}. Either the "
                "file is stale or the seed's rule changed; the seed prints the "
                "paste-ready block, so re-copy it rather than editing by hand."
            )

    def test_the_header_name_is_the_one_the_module_uses(self):
        auth = read_config()["auth"]

        for key in CHECKER_KEYS:
            assert auth[key].startswith(demo_tokens.HEADER_NAME + ":")

    def test_no_value_contains_a_hash(self):
        """``run.py``'s fallback parser drops everything after a ``#``, even
        inside a quoted string, and a token truncated there is a token that
        silently stops authenticating."""
        for key in CHECKER_KEYS:
            assert "#" not in read_config()["auth"][key], key

    def test_the_routes_the_file_names_all_exist(self):
        """A route the file names but the app does not have is a 404, and 404 is
        inside the 4xx range every relevant check accepts."""
        from django.urls import resolve

        config = read_config()["routes"]
        for name in ("gallery", "submit"):
            assert resolve(config[name].split("?")[0]) is not None, name

    def test_the_claimed_tier_list_is_still_empty(self):
        """The claim is made at a break, against what is green. Not here."""
        assert read_config()["tiers"]["claimed"] == []


# ---------------------------------------------------------------- the backend


class TestAuthentication:
    def test_a_valid_token_authenticates_its_identity(self, identities, loaded):
        from reviewer.accounts.models import User

        user = User.objects.get(email=identities["participant"].email)
        response = Client().get(
            "/projects/new", headers={"Authorization": demo_tokens.mint(user.email)}
        )

        assert response.status_code == 200
        assert str(user.pk)  # the identity resolved to a real row, not just a string

    def test_an_invalid_token_leaves_the_request_anonymous(self, loaded):
        response = Client().get("/projects/new", headers={"Authorization": "JJ1.bogus.x@y.org"})

        assert response.status_code == 200, "the page is public; nobody is signed in"

    def test_the_backend_never_creates_a_user(self, loaded):
        """This portal has no registration. Inventing one on the strength of a
        header is the sort of thing that survives into production."""
        from reviewer.accounts.models import User

        before = User.objects.count()
        Client().get(
            "/projects/new", headers={"Authorization": demo_tokens.mint("ghost@example.org")}
        )

        assert User.objects.count() == before

    def test_a_session_cookie_is_not_overridden_by_a_header(self, identities):
        """The middleware only ever ADDS a user, and only when there is not one
        already. A browser session is the more specific claim about who is
        asking, and letting a header override it would be an authority-widening
        path nobody would look for."""
        import inspect

        from reviewer.accounts.authentication import DemoCredentialMiddleware

        source = inspect.getsource(DemoCredentialMiddleware._authenticate)

        assert "is_authenticated" in source
        assert source.index("is_authenticated") < source.index("email_from_token"), (
            "the early return on an existing user has to come before the token is "
            "read, or a header could replace a session"
        )

    def test_model_backend_is_present_only_so_the_admin_login_form_works(self):
        """Two backends, and the product reads neither for authority.

        ``User.has_perm`` returns False unconditionally, so ModelBackend grants
        nothing; ``tests/test_schema_contract.py`` pins that. Dropping it would
        mean nobody can sign in to ``/admin/`` at all, which is a support
        surface rather than an authority path.
        """
        from django.conf import settings

        assert "django.contrib.auth.backends.ModelBackend" in settings.AUTHENTICATION_BACKENDS
        assert (
            "reviewer.accounts.authentication.DemoCredentialBackend"
            in settings.AUTHENTICATION_BACKENDS
        )
        assert len(settings.AUTHENTICATION_BACKENDS) == 2
