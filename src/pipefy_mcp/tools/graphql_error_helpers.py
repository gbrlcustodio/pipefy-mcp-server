"""Shared GraphQL / transport error extraction for MCP tool payloads."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipefy_mcp.services.pipefy import PipefyClient

# Suffixes appended by InternalApiClient for service-layer diagnostics; MCP tools
# should strip these from default user-visible errors (see task 4.2).
_INTERNAL_API_CODE_SUFFIX_RE = re.compile(r"\s*\[code=[^\]]*\]")
_INTERNAL_API_CORRELATION_SUFFIX_RE = re.compile(r"\s*\[correlation_id=[^\]]*\]")
_INTERNAL_API_CODE_BRACKET_CAPTURE_RE = re.compile(r"\[code=([^\]]*)\]")
_INTERNAL_API_CORRELATION_BRACKET_CAPTURE_RE = re.compile(
    r"\[correlation_id=([^\]]*)\]"
)


def strip_internal_api_diagnostic_markers(message: str) -> str:
    """Remove ``[code=…]`` / ``[correlation_id=…]`` markers from a message string.

    ``InternalApiClient`` appends these to GraphQL error text for logs and tests.
    Multiple occurrences (e.g. ``; ``-joined errors) are all removed.

    Args:
        message: Raw error text, often ``str(ValueError(...))`` from the client.
    """
    stripped = _INTERNAL_API_CORRELATION_SUFFIX_RE.sub("", message)
    stripped = _INTERNAL_API_CODE_SUFFIX_RE.sub("", stripped)
    return stripped.strip()


def extract_internal_api_bracket_codes(message: str) -> list[str]:
    """Collect distinct ``code`` values from ``[code=…]`` markers (InternalApiClient).

    Args:
        message: Raw exception text before stripping markers.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw_code in _INTERNAL_API_CODE_BRACKET_CAPTURE_RE.findall(message):
        code = raw_code.strip()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def extract_internal_api_bracket_correlation_id(message: str) -> str | None:
    """Return the first non-empty correlation id from ``[correlation_id=…]`` markers.

    Args:
        message: Raw exception text before stripping markers.
    """
    for raw_cid in _INTERNAL_API_CORRELATION_BRACKET_CAPTURE_RE.findall(message):
        cid = raw_cid.strip()
        if cid:
            return cid
    return None


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


def handle_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    """Turn transport/GraphQL failures into a standard error payload.

    Consolidates the repeated ``handle_*_tool_graphql_error`` pattern used across
    domain helper modules. Returns ``{"success": False, "error": message}``.

    Args:
        exc: Root exception from gql/httpx.
        fallback_msg: Used when ``extract_error_strings`` is empty.
        debug: When True, append codes and ``correlation_id``.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    if not debug:
        return {"success": False, "error": base}
    codes = extract_graphql_error_codes(exc)
    cid = extract_graphql_correlation_id(exc)
    return {
        "success": False,
        "error": with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid),
    }


_PERMISSION_DENIED_CODE = "PERMISSION_DENIED"
_ENRICHMENT_TIMEOUT_SECONDS = 5


async def enrich_permission_denied_error(
    exc: BaseException,
    pipe_ids: list[str],
    client: PipefyClient,
) -> str | None:
    """Enrich PERMISSION_DENIED errors with membership guidance.

    When the exception contains a ``PERMISSION_DENIED`` GraphQL error code,
    checks each ``pipe_id`` for membership and returns an actionable message
    identifying which pipe(s) the service account is not a member of.

    Returns ``None`` when the error is not PERMISSION_DENIED, when the service
    account is already a member, or when enrichment itself fails (timeout,
    network error). The caller falls back to its standard error path.

    Args:
        exc: GraphQL exception from a cross-pipe operation.
        pipe_ids: Pipe IDs involved in the operation (source + target).
        client: PipefyClient for membership lookups.
    """
    codes = extract_graphql_error_codes(exc)
    if _PERMISSION_DENIED_CODE not in codes:
        return None

    unique_ids = list(dict.fromkeys(pid for pid in pipe_ids if pid))
    if not unique_ids:
        return None

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                *(client.get_pipe_members(pid) for pid in unique_ids),
                return_exceptions=True,
            ),
            timeout=_ENRICHMENT_TIMEOUT_SECONDS,
        )
    except (TimeoutError, asyncio.TimeoutError):
        return None

    missing_pipes: list[str] = []
    for pid, result in zip(unique_ids, results):
        if isinstance(result, BaseException):
            # Could not fetch members — could be access denied, network, or pipe not found
            missing_pipes.append(
                f"Could not verify membership for pipe {pid}. "
                f"Check if the service account is a member — use invite_members if not."
            )
            continue
        members = result.get("pipe", {}).get("members") or []
        if not members:
            pipe_name = result.get("pipe", {}).get("name") or f"pipe {pid}"
            missing_pipes.append(
                f"Service account may not be a member of {pipe_name} (ID: {pid}). "
                f"Use invite_members to add it."
            )

    if not missing_pipes:
        return None

    return "\n".join(missing_pipes)
