"""Ed25519 key material, and the one rule about where it may live.

**Keys live on their own volume and nowhere else.** That is a deployment posture,
not a KMS integration we are pretending to have, and this module enforces it in
three places so a mistake is impossible rather than merely discouraged:

1. **Generation writes only inside ``settings.KEYS_DIR``**, which the compose file
   mounts as a separate named volume.
2. **Loading refuses a key file that is not in the key directory.** A private key
   under the source tree would land in every image layer and in ``git status``; one
   in the data volume would be destroyed by the same ``down -v`` that resets the
   demo, so every signature would become unverifiable the moment anyone ran the
   break protocol.
3. **The key is never stored in the database.** ``JudgeCredential`` holds the
   **public** key and the signature, and that is the whole of it.

Why the separation is load-bearing rather than tidy
---------------------------------------------------
A judge's signed record is evidence that survives the portal. If the signing key
is destroyed by the same command that resets the demo database, the evidence is
destroyed with it -- and the reset is a thing this project runs at every
verification break. A backup of the data volume is safe to hand to somebody
because it contains no key material, and that is a property you cannot retrofit
after the first backup you already gave away.

The key file format, and why it is a plain file
-----------------------------------------------
A **raw 32-byte Ed25519 seed**, written with mode ``0600``, named
``<judge-source-key>.ed25519``. Not PKCS#8, not a PEM, not a passphrase-wrapped
container. The reasons are the usual ones for a self-hosted single-container
portal: the bytes are the spec, so a reviewer can read them with ``xxd`` and
confirm what they are signing with; there is no passphrase to put in an env file
that then has to be protected as carefully as the key; and ``cryptography``
round-trips the format in three lines. **A key format that needs a library to
read is a key format that will eventually be read by the wrong library.**
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

#: 0600 on the key file, 0700 on the directory. **Set explicitly rather than
#: inherited**, because a umask of 022 would otherwise leave a private key
#: world-readable inside a container that is otherwise single-tenant.
KEY_MODE = 0o600
DIR_MODE = 0o700

#: The seed is 32 bytes. Checked on read so a truncated or text-mode-corrupted
#: file fails as "this is not a key" rather than as an opaque crypto error.
SEED_BYTES = 32


class KeyMaterialError(Exception):
    """Raised for a missing, malformed, or wrongly-placed key."""


def keys_dir() -> Path:
    """The one directory key material may live in."""
    from django.conf import settings

    return Path(settings.KEYS_DIR)


def _assert_inside_keys_dir(path: Path) -> Path:
    """Refuse any key file that is not in the key directory.

    The check is on the **resolved** path, so a symlink out of the key directory
    is refused too -- which is the whole reason to resolve before comparing rather
    than comparing the strings.
    """
    root = keys_dir().resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root):
        raise KeyMaterialError(
            f"{resolved} is outside the key directory {root}. Signing keys live on "
            "their own volume on purpose: one under the source tree would be copied "
            "into every image layer, and one on the data volume would be destroyed by "
            "the same `down -v` that resets the demo -- taking every signature with it."
        )
    return resolved


def key_path(judge_key: str) -> Path:
    """Where one judge's seed lives."""
    safe = "".join(ch for ch in judge_key if ch.isalnum() or ch in "-_@.") or "unknown"
    return keys_dir() / f"{safe}.ed25519"


def generate(judge_key: str, *, overwrite: bool = False) -> Path:
    """Create a judge's signing key if it does not exist. Returns its path.

    **Refuses to overwrite.** Regenerating a key silently would orphan every record
    the old one signed, and the records would still look valid -- they carry a
    public key, and a *different* public key is a difference nothing in the schema
    would notice. Losing a key is recoverable; losing it without noticing is not.
    """
    path = key_path(judge_key)
    _assert_inside_keys_dir(path)
    if path.exists() and not overwrite:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, DIR_MODE)
    except OSError:  # pragma: no cover - Windows, and CI on Windows
        pass

    seed = Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(seed)
    try:
        os.chmod(path, KEY_MODE)
    except OSError:  # pragma: no cover - Windows
        pass
    return path


def has_key(judge_key: str) -> bool:
    return key_path(judge_key).exists()


def load_private(judge_key: str) -> Ed25519PrivateKey:
    """Read a judge's signing key, or say precisely what is wrong."""
    path = _assert_inside_keys_dir(key_path(judge_key))
    if not path.exists():
        raise KeyMaterialError(
            f"no signing key for {judge_key!r} at {path}. Run `manage.py issue_keys` "
            "first. A judge with no key cannot sign, and a record with no signature "
            "is not evidence of anything."
        )
    seed = path.read_bytes()
    if len(seed) != SEED_BYTES:
        raise KeyMaterialError(
            f"{path} is {len(seed)} bytes, not the {SEED_BYTES} an Ed25519 seed is. "
            "The file is truncated or was written in text mode; delete it and "
            "re-issue rather than trying to repair it."
        )
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_bytes(judge_key: str) -> bytes:
    """The raw 32-byte public key, which is what ``JudgeCredential`` stores."""
    return (
        load_private(judge_key)
        .public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    )


def load_public(public_bytes: bytes) -> Ed25519PublicKey:
    """The inverse, for verification by a party holding only a credential."""
    if len(public_bytes) != SEED_BYTES:
        raise KeyMaterialError(
            f"an Ed25519 public key is {SEED_BYTES} bytes, got {len(public_bytes)}"
        )
    return Ed25519PublicKey.from_public_bytes(public_bytes)


def public_key_fingerprint(public_bytes: bytes) -> str:
    """A short, quotable identifier for a key: the first 16 hex of its SHA-256.

    **Present so a human can say "key ``a3f1...``" in an audit conversation.**
    A record that names a key only by its full 32 bytes is not something anyone
    will read aloud, and the fingerprint is derived rather than stored, so it
    cannot drift from the key it names.
    """
    import hashlib

    return hashlib.sha256(public_bytes).hexdigest()[:16]
