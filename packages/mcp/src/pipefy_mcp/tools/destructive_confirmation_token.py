"""Pure planner that mints and verifies HMAC confirmation tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

DESTRUCTIVE_CONFIRMATION_TTL_SECONDS = 300


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
    mac = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    return "v1." + _b64url_nopad(payload_bytes) + "." + _b64url_nopad(mac)


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
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "v1":
            return False
        payload_bytes = _b64url_decode(parts[1])
        given_mac = _b64url_decode(parts[2])
        expected_mac = hmac.new(key, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(given_mac, expected_mac):
            return False
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            return False
        exp = payload.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, int) or exp <= now:
            return False
        if payload.get("tool") != tool_name:
            return False
        return payload.get("identity") == _canonical_identity(resource_identity)
    except Exception:  # noqa: BLE001
        return False


def _canonical_identity(resource_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _canonical_value(resource_identity[key])
        for key in sorted(resource_identity)
    }


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=_list_sort_key)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return str(value)
    return value


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
    padding = "=" * ((4 - len(part) % 4) % 4)
    return base64.urlsafe_b64decode(part + padding)
