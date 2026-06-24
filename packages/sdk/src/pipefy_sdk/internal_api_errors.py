"""Error envelope for the internal_api GraphQL endpoint.

The internal_api executor decorates each GraphQL error with ``[code=…]`` /
``[correlation_id=…]`` suffixes drawn from ``extensions``. Service-layer tests
assert the fully suffixed text.
"""

from __future__ import annotations


def format_internal_api_error(errors: list[dict]) -> str:
    parts: list[str] = []
    for err in errors:
        msg = err.get("message", "Unknown error")
        ext = err.get("extensions", {})
        code = ext.get("code", "")
        corr = ext.get("correlation_id", "")
        suffix = f" [code={code}]" if code else ""
        suffix += f" [correlation_id={corr}]" if corr else ""
        parts.append(f"{msg}{suffix}")
    return "; ".join(parts)
