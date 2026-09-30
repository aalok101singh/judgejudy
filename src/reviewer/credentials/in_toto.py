"""in-toto Statement v1 inside a DSSE envelope, byte-exactly as both specs say.

Two formats, one file, and **the reason it is hand-written rather than pulled from
a library is the reason a reader is suspicious of it.** DSSE's payload
authentication is a *length-prefixed* encoding, and a length-prefixed encoding
that is one byte wrong is still a perfectly ordinary string: the signature
verifies against your PAE and against nothing else, so a subtly wrong
implementation is indistinguishable from a right one until someone else's
verifier disagrees. `bible/05` §9b's own note is that there is no independent
witness here, which makes getting the bytes right the *only* defence.

DSSE Pre-Authentication Encoding, exactly
-----------------------------------------
::

    PAE(payloadType, payload) =
        "DSSEv1" SP LEN(payloadType) SP payloadType SP LEN(payload) SP payload

where ``SP`` is a single space (0x20) and ``LEN`` is the **ASCII decimal** byte
count. Three ways to be wrong, all of which still produce a valid string:

* **prefixing the type without a separator** -- ``DSSEv1application/...``
* **using the character count instead of the byte count** -- which is only correct
  for ASCII, and a payload type is ASCII, so *the type is always fine* and the bug
  hides in the **payload**, which is UTF-8 JSON and contains ``em`` dashes and
  accented judge names
* **encoding the lengths as JSON numbers** (``"32"``) rather than bare digits

:func:`pae` therefore encodes lengths with ``str(len(bs))`` over the **encoded
bytes**, and its own test asserts the exact prefix against the spec's worked
example rather than against itself.

in-toto Statement v1, exactly
-----------------------------
``_type`` is the literal ``https://in-toto.io/Statement/v1``; ``subject`` is a
**list** of ``{name, digest}``; ``digest`` maps algorithm to hex; ``predicateType``
is a URI; ``predicate`` is arbitrary. Two of those are routinely got wrong:
``subject`` as an object rather than a list, and ``sha256`` as base64.

What the statement claims, and what it deliberately does not
------------------------------------------------------------
**No scores.** The subject is the judge's *work*, named by natural key and
committed by digest; the predicate carries counts, a rubric version, the audit
sequence range their work occupies, the chain head at publication, and the
results hash. Every field is public or a digest, so the record can be handed to
any third party without leaking a single score -- which is what makes "N judges
each hold a copy" possible, and that is the entire value of D-09.

``issued_at`` is inside the predicate, **not** Django's ``auto_now_add`` column,
and :func:`build_statement` is given an explicit timestamp. A signature over a
record whose timestamp is chosen by the database at insert time is a signature
over a value the signer did not choose, so re-importing the row would verify a
*different* payload than the one that was signed.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json

from reviewer.io.bundle import canonical

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
PAE_PREFIX = b"DSSEv1"
SP = b" "


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding. **The exact bytes that get signed.**

    Lengths are byte counts of the **encoded** forms, written as bare ASCII
    decimal. See the module docstring for the three ways to be wrong here, all of
    which produce a valid-looking string.
    """
    type_bytes = payload_type.encode("utf-8")
    return b"".join(
        [
            PAE_PREFIX,
            SP,
            str(len(type_bytes)).encode("ascii"),
            SP,
            type_bytes,
            SP,
            str(len(payload)).encode("ascii"),
            SP,
            payload,
        ]
    )


def b64(data: bytes) -> str:
    """Standard base64 **with padding**, which DSSE requires and URL-safe does not.

    Two alphabets, and a verifier that expects one and is handed the other fails
    with a signature mismatch that reads like tampering. So the choice is stated
    here rather than left to whichever helper was imported.
    """
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def subject(name: str, data: bytes) -> dict:
    """One in-toto subject: a name and a digest, never the bytes themselves."""
    return {"name": name, "digest": {"sha256": sha256_hex(data)}}


def build_statement(
    *,
    event_key: str,
    judge_key: str,
    rubric_source_key: str,
    review_digests: list[tuple[str, str]],
    audit_seq_from: int,
    audit_seq_to: int,
    issued_at: dt.datetime | None = None,
    audit_chain_head: str = "",
    results_hash: str = "",
) -> dict:
    """An in-toto Statement v1 for one judge's participation in one event.

    ``review_digests`` is ``[(review_source_key, digest)]`` -- **the digest, not
    the score.** The record commits to *which reviews exist and that they have not
    changed*, which is checkable by anyone holding the export, and to nothing
    about what was in them. A record that leaked the scores would not be shareable,
    and an unshareable record replicates nothing.

    ``issued_at`` is taken as an argument rather than read from the clock **by
    default**, because the caller is usually replaying a known moment (a bulk
    signer walking the fixture) and a signature must cover a value the signer
    chose. Left as ``None`` it becomes "now", and then it is in the payload.
    """
    when = issued_at or dt.datetime.now(dt.UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            subject(f"review:{key}", digest.encode("utf-8")) for key, digest in review_digests
        ],
        "predicateType": "https://judgejudy.example/participation/v1",
        "predicate": {
            "event": event_key,
            "judge": judge_key,
            "rubric_version": rubric_source_key,
            "reviews_signed": len(review_digests),
            "review_digests": dict(review_digests),
            "audit_sequence": {"from": audit_seq_from, "to": audit_seq_to},
            "audit_chain_head": audit_chain_head,
            "results_hash": results_hash,
            "issued_at": when.astimezone(dt.UTC).isoformat(),
        },
    }


def statement_bytes(statement: dict) -> bytes:
    """The canonical payload bytes.

    **Canonical, not ``json.dumps`` as found.** A signature covers a byte string,
    so the serialisation has to be fixed: keys sorted, no incidental whitespace,
    UTF-8. Without this, re-serialising the same statement with a different
    separator or key order produces a different payload, the signature fails, and
    the natural conclusion is that the record was tampered with. It was not -- it
    was re-serialised.
    """
    return canonical(statement).encode("utf-8")


def build_envelope(statement: dict, signature: bytes) -> dict:
    """Wrap a signed payload in a DSSE envelope.

    Two entries, ``payloads`` (a **list**, base64 of the payload bytes) and
    ``signatures`` (one per payload). The signature is over :func:`pae`, never over
    the payload directly -- that is the entire point of the PAE, and signing the
    bare payload is the single most common DSSE mistake.
    """
    return {
        "payloads": [b64(statement_bytes(statement))],
        "signatures": [{"keyid": "", "sig": b64(signature)}],
    }


def envelope_payload_bytes(envelope: dict) -> tuple[str, bytes]:
    """Recover ``(payload_type, payload)`` from an envelope.

    **Exactly one payload is required and the refusal is explicit**, because
    "take the first one" is how a verifier ends up validating something the
    signer did not mean to sign when a record carries several.

    The payload type is **not stored in the envelope**. DSSE takes it from the
    authentication scheme, and this build has exactly one scheme, so a record
    claiming to be some other type is a record we cannot interpret -- and saying so
    is better than interpreting it as the type we happen to support.
    """
    payloads = envelope.get("payloads") or []
    if len(payloads) != 1:
        raise ValueError(
            f"a DSSE envelope here must carry exactly one payload, found {len(payloads)}"
        )
    return DSSE_PAYLOAD_TYPE, unb64(payloads[0])


def envelope_statement(envelope: dict) -> dict:
    """The statement inside an envelope, as a dict."""
    return json.loads(envelope_payload_bytes(envelope)[1].decode("utf-8"))


def verify_envelope(
    envelope: dict, public_key_bytes_: bytes, payload_type: str = DSSE_PAYLOAD_TYPE
) -> bool:
    """True when the envelope's signature is valid for the payload it carries.

    **This recomputes the PAE from the envelope rather than trusting any stored
    digest.** A verifier that compares a stored hash to a stored hash is checking
    that two things the signer produced agree with each other, which is not what a
    signature is for. The only meaningful check is: does the key verify *these
    bytes*, reconstructed by this code.
    """
    from cryptography.exceptions import InvalidSignature

    import reviewer.credentials.keys as keys_module

    signatures = envelope.get("signatures") or []
    payloads = envelope.get("payloads") or []
    if len(signatures) != 1 or len(payloads) != 1:
        return False
    public = keys_module.load_public(public_key_bytes_)
    try:
        public.verify(unb64(signatures[0]["sig"]), pae(payload_type, unb64(payloads[0])))
    except (InvalidSignature, ValueError, KeyError):
        return False
    return True
