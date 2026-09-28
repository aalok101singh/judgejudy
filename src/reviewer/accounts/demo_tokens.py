"""The demo credential: a role-proving bearer token, and the trade it makes explicit.

**What this is for.** The organizers' checker never logs in (``run.py`` reads
``[auth]`` from ``.dogfood.toml`` and attaches whatever header we hand it). So
the portal has to be able to say "this request is a judge" from something it
can read out of a committed file, with no login round-trip and no browser.

**The shape.** ``Authorization: JJ1.<email>.<hmac>`` -- the identity in the
token, an HMAC-SHA256 over it, truncated to 128 bits. No session table, no
database row, nothing to revoke except the key, and printable on boot.

**Why not a session row with a fixed key** (the organizers' own example, and a
reasonable design). Because a session row lives in the database, and
``just check`` starts from ``down -v``. The credential would be wiped on every
reset, ``.dogfood.toml`` would have to be repasted after each one, and an
acceptance config that is stale by default is an acceptance check that passes
for the wrong reason -- F-40, the failure this project is most afraid of. So
there is no row.

**And why the signing key is a constant, stated here rather than buried.**
``SECRET_KEY`` would be the obvious choice, and it is the wrong one for exactly
the same reason: it is generated per instance volume and rotated by ``down -v``,
so a token signed with it expires on every reset. The key is therefore a
**published, non-secret constant**, overridable with ``DJUDGE_DEMO_TOKEN_KEY``.

**The consequence, stated rather than hidden: anyone who can read this
repository can mint a token for any of the 121 fixture identities.** That is a
real property of this design and it is not a bug being papered over -- it is
the same posture as the organizers' guessable fixed session value, applied to a
single-tenant self-hosted portal whose entire dataset is a public fixture file
and whose only secrets (signed judge records) are produced by ``cryptography``'s
own key management, not by this token. The README says so in the same words.
What the token is *not*: an organizer credential, a way in without a
``RoleBinding``, or anything that survives into a real deployment -- see
``README.md`` and ``bible/07`` §3.4 P-12.

**What it is not allowed to be is silent.** ``mint`` and ``verify`` are pure
functions over strings, so the tests can assert on a forged token, a truncated
one, a token for a different key, and an unknown identity without a database.
"""

from __future__ import annotations

import hashlib
import hmac
import os

#: The scheme. A token that does not start with this is not ours, which is what
#: lets the middleware ignore an unrelated ``Authorization`` header -- a bearer
#: token from some other tool pointed at this port -- instead of reporting it as
#: a bad credential.
TOKEN_SCHEME = "JJ1"

#: What a whole ``.dogfood.toml`` value looks like: ``<header>: <token>``.
#: ``run.py`` splits on the FIRST colon, so the scheme deliberately contains no
#: colon of its own.
HEADER_NAME = "Authorization"
HEADER_TEMPLATE = f"{HEADER_NAME}: {{token}}"

#: Bytes of the HMAC we keep, and therefore the exact length of the signature
#: field. 16 bytes (128 bits) is the standard truncation and is far more than the
#: 30 bits of guessing a 1-of-121 identity would need; the token is a bearer
#: value on a loopback-only demo portal, not a signature.
SIGNATURE_BYTES = 16
SIGNATURE_LENGTH = SIGNATURE_BYTES * 2

#: The published key. See the module docstring for why this is a constant and
#: not ``SECRET_KEY`` -- and for what that costs.
PUBLISHED_DEMO_KEY = b"judgejudy-demo-credential-key/2026-03-01"

#: The environment variable that rotates it. Rotating invalidates every token
#: already pasted into a ``.dogfood.toml``, so the seed prints the new ones.
KEY_ENV_VAR = "DJUDGE_DEMO_TOKEN_KEY"


def signing_key() -> bytes:
    """The key in force right now.

    Read from the environment on every call rather than at import, so a test can
    rotate it without reimporting the module -- and so a key set in the
    container's environment cannot be masked by an import-order accident.
    """
    override = os.environ.get(KEY_ENV_VAR)
    if override:
        return override.encode("utf-8")
    return PUBLISHED_DEMO_KEY


def is_published_key() -> bool:
    """Whether the key in force is the one in this file. Printed by the seed."""
    return hmac.compare_digest(signing_key(), PUBLISHED_DEMO_KEY)


def _signature(email: str) -> str:
    """HMAC-SHA256 over the scheme and the identity, truncated, hex."""
    payload = f"{TOKEN_SCHEME}|{email}".encode()
    digest = hmac.new(signing_key(), payload, hashlib.sha256).digest()
    return digest[:SIGNATURE_BYTES].hex()


def mint(email: str) -> str:
    """The token for ``email``. Pure; no database, no settings, no clock.

    **The signature comes FIRST**, and that ordering is the whole parse. The
    identity is an email address, and an email address contains dots:
    ``priya1@example.org`` is three dot-separated fields. The first version of
    this was ``JJ1.<email>.<sig>`` split on ``.`` into three parts, and every
    single token in the fixture failed to verify -- silently, because
    ``email_from_token`` returns ``None`` for "malformed" and for "wrong
    signature" alike, so the symptom was a demo identity that simply never
    authenticated. Putting the fixed-length hex signature first makes the split
    unambiguous: the signature cannot contain a dot, and the email is everything
    after the second one.
    """
    return f"{TOKEN_SCHEME}.{_signature(email)}.{email}"


def header_value(email: str) -> str:
    """The exact string to paste into ``.dogfood.toml``'s ``[auth]`` block."""
    return HEADER_TEMPLATE.format(token=mint(email))


def email_from_token(token: str | None) -> str | None:
    """The identity a token claims, or ``None`` if it does not verify.

    Takes the **token**, not a whole ``Authorization: ...`` header line --
    ``run.py`` splits that pair itself and attaches the token as the header
    value, and Django's ``request.headers`` only ever hands us the value.
    Whitespace is stripped, because the value is operator-supplied: a stray
    space from a copy-and-paste must not turn a working credential into an
    anonymous request.

    The signature's length is checked before it is compared, which is what makes
    the split unambiguous rather than merely lucky: it is fixed-width hex, so a
    token whose "signature" field is empty or absurd is rejected before any
    ``compare_digest`` is attempted.

    Three failure modes all return ``None`` and are deliberately not told
    apart: malformed, wrongly signed, and signed by a different key. Returning
    the reason would put an oracle on this endpoint, and the caller cannot act
    on the difference anyway -- an unverifiable token is an anonymous request.
    """
    if not token:
        return None
    scheme, separator, rest = token.strip().partition(".")
    if not separator or scheme != TOKEN_SCHEME:
        return None
    signature, separator, email = rest.partition(".")
    if not separator or len(signature) != SIGNATURE_LENGTH or not email or "@" not in email:
        return None
    if not hmac.compare_digest(signature, _signature(email)):
        return None
    return email


def email_from_config_value(value: str | None) -> str | None:
    """The identity in a ``.dogfood.toml`` ``[auth]`` value.

    ``run.py`` splits each value on the **first** colon and attaches the
    remainder as a header, so our value is ``Authorization: <token>`` and the
    token itself contains no colon. The split is done here rather than trusted,
    because a stale credential in a committed file is one of the ways the
    acceptance check ends up passing for the wrong reason -- and this function
    is what the test that reads ``.dogfood.toml`` goes through.
    """
    if not value:
        return None
    head, separator, rest = value.partition(":")
    if not separator or head.strip().lower() != HEADER_NAME.lower():
        return None
    return email_from_token(rest.strip())


def describe() -> str:
    """One line for the seed banner, so the operator knows what they are holding."""
    source = "the published key in this file" if is_published_key() else f"{KEY_ENV_VAR}"
    return (
        f"demo credentials are HMAC-SHA256 over the identity, signed with {source}; "
        "anyone holding this repository can mint one, which is why they are demo "
        "credentials and not secrets"
    )
