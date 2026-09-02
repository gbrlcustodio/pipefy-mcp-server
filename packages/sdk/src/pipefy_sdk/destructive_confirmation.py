"""Pure planner for the HMAC confirmation tokens that order a destructive call.

Derives the per-caller signing key, mints a token, and verifies one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from typing import Any, Literal

DESTRUCTIVE_CONFIRMATION_TTL_SECONDS = 300
_TOKEN_VERSION = "v1"
_B64URL_SEGMENT_RE = re.compile(r"[A-Za-z0-9_-]*")

ConfirmationTokenFailure = Literal["missing", "invalid_or_expired", "identity_mismatch"]


def confirmation_signing_key(caller_secret: str | bytes) -> bytes:
    """Derive one caller's HMAC key from that caller's own credential.

    Deriving per caller is what stops one caller's token from confirming
    another's deletion. A single module-level key defeats that binding, because
    every token then verifies for everyone.

    Args:
        caller_secret: The caller's credential (a bearer token, a session
            secret). Encoded as UTF-8 when given as ``str``. Never stored, and
            never recoverable from the returned key or from a minted token.
    """
    if isinstance(caller_secret, str):
        caller_secret = caller_secret.encode("utf-8")
    return hashlib.sha256(caller_secret).digest()


def mint_confirmation_token(
    *,
    tool_name: str,
    resource_identity: dict[str, Any],
    key: bytes,
    now: int,
) -> str:
    """Mint a time-limited HMAC token bound to a tool and resource identity.

    Args:
        tool_name: Destructive tool this token authorises.
        resource_identity: Resource ids; canonicalised before signing.
        key: HMAC-SHA256 secret. Never included in the token.
        now: Unix timestamp in seconds; expiry is now plus the TTL.
    """
    payload_bytes = _payload_bytes(
        tool_name=tool_name,
        identity=_canonical_identity(resource_identity),
        exp=now + DESTRUCTIVE_CONFIRMATION_TTL_SECONDS,
    )
    mac = hmac.new(key, _mac_message(payload_bytes), hashlib.sha256).digest()
    return (
        f"{_TOKEN_VERSION}." + _b64url_nopad(payload_bytes) + "." + _b64url_nopad(mac)
    )


def verify_confirmation_token(
    token: str | None,
    *,
    tool_name: str,
    resource_identity: dict[str, Any],
    key: bytes,
    now: int,
) -> bool:
    """Return True when the token binds this tool and identity and is unexpired.

    Malformed or mismatched input returns False rather than raising.

    Args:
        token: Wire token, or None.
        tool_name: Tool that must match the payload.
        resource_identity: Resource ids that must match after canonicalisation.
        key: HMAC-SHA256 secret used to mint the token.
        now: Unix timestamp in seconds; valid only while exp is strictly later.
    """
    try:
        if not isinstance(token, str):
            return False
        payload = _authenticated_payload(token, key)
        if payload is None:
            return False
        exp = payload.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, int) or exp <= now:
            return False
        if payload.get("tool") != tool_name:
            return False
        return payload.get("identity") == _canonical_identity(resource_identity)
    except Exception:  # noqa: BLE001
        return False


def classify_confirmation_token_failure(
    token: str | None,
    *,
    tool_name: str,
    resource_identity: dict[str, Any],
    key: bytes,
) -> ConfirmationTokenFailure:
    """Say why verify would fail. Never use this to authorize proceed.

    Decoding and MAC checks here are diagnostic only. Proceed remains behind
    :func:`verify_confirmation_token`.
    """
    if token is None or token == "":
        return "missing"
    payload = _authenticated_payload(token, key)
    if payload is None:
        return "invalid_or_expired"
    if payload.get("tool") != tool_name:
        return "identity_mismatch"
    if payload.get("identity") != _canonical_identity(resource_identity):
        return "identity_mismatch"
    return "invalid_or_expired"


def _authenticated_payload(token: str, key: bytes) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != _TOKEN_VERSION:
            return None
        payload_bytes = _b64url_decode(parts[1])
        given_mac = _b64url_decode(parts[2])
        expected_mac = hmac.new(
            key, _mac_message(payload_bytes), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(given_mac, expected_mac):
            return None
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None


def _mac_message(payload_bytes: bytes) -> bytes:
    return f"{_TOKEN_VERSION}.".encode("ascii") + payload_bytes


def _canonical_identity(resource_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _canonical_value(resource_identity[key])
        for key in sorted(resource_identity)
    }


def _canonical_value(value: Any) -> Any:
    """Reduce one identity value to a JSON-native, order-stable form.

    Numbers and any other non-JSON type become their string form, so ``1`` and
    ``"1"`` bind the same token. Canonicalising here rather than at serialisation
    keeps mint and verify on one definition: a value that reaches the payload as
    a string must also compare as a string, or the minted token could never
    verify and the caller would preview forever.
    """
    if isinstance(value, dict):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=_list_sort_key)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        return value
    return str(value)


def _list_sort_key(item: Any) -> str:
    return json.dumps(item, sort_keys=True, separators=(",", ":"))


def _payload_bytes(*, tool_name: str, identity: dict[str, Any], exp: int) -> bytes:
    return json.dumps(
        {"exp": exp, "identity": identity, "tool": tool_name},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(part: str) -> bytes:
    """Decode one token segment, accepting only the base64url alphabet.

    Rejects whitespace and the standard-alphabet ``+`` and ``/``. Base64 leaves
    trailing bits free, so a segment still has more than one accepted spelling;
    the MAC comparison is what settles authenticity. Raises on anything else,
    and callers treat a raised decode as a failed verification.
    """
    if not _B64URL_SEGMENT_RE.fullmatch(part):
        raise ValueError("token segment is not canonical base64url")
    padding = "=" * ((4 - len(part) % 4) % 4)
    return base64.urlsafe_b64decode(part + padding)
