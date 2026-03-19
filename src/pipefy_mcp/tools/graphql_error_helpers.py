"""Shared GraphQL / transport error extraction for MCP tool payloads."""

from __future__ import annotations

import re


def extract_error_strings(exc: BaseException) -> list[str]:
    """Best-effort extraction of error messages from gql/GraphQL exceptions."""
    messages: list[str] = []

    raw = str(exc)
    if raw:
        messages.append(raw)

    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                msg = item.get("message")
                if isinstance(msg, str) and msg:
                    messages.append(msg)
            elif isinstance(item, str) and item:
                messages.append(item)

    return messages


def extract_graphql_error_codes(exc: BaseException) -> list[str]:
    """Extract GraphQL ``extensions.code`` values from gql/GraphQL exceptions."""
    codes: list[str] = []

    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            extensions = item.get("extensions")
            if not isinstance(extensions, dict):
                continue
            code = extensions.get("code")
            if isinstance(code, str) and code:
                codes.append(code)

    raw = str(exc)
    if raw:
        for match in re.findall(r"""['"]code['"]\s*[:=]\s*['"]([A-Z_]+)['"]""", raw):
            codes.append(match)

    seen: set[str] = set()
    unique: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique


def extract_graphql_correlation_id(exc: BaseException) -> str | None:
    """Best-effort extraction of correlation_id from GraphQL exception strings."""
    raw = str(exc)
    if not raw:
        return None

    match = re.search(r"""['"]correlation_id['"]\s*[:=]\s*['"]([^'"]+)['"]""", raw)
    if match:
        return match.group(1)
    return None


def with_debug_suffix(
    message: str, *, debug: bool, codes: list[str], correlation_id: str | None
) -> str:
    """Append debug context to a single error string without changing payload shape."""
    if not debug:
        return message

    parts: list[str] = []
    if codes:
        parts.append(f"codes={','.join(codes)}")
    if correlation_id:
        parts.append(f"correlation_id={correlation_id}")

    if not parts:
        return message
    return f"{message} (debug: {'; '.join(parts)})"
