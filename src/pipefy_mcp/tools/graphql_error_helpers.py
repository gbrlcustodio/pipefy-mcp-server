"""Shared GraphQL / transport error extraction for MCP tool payloads.

**Enrichment precedence** (4 tiers, most specific first):

1. :func:`enrich_permission_denied_error` — opt-in *at the call site*, runs
   **before** :func:`handle_tool_graphql_error`. Requires a ``PipefyClient``
   because it performs follow-up membership lookups.
2. :func:`enrich_not_found_error` — invoked *inside*
   :func:`handle_tool_graphql_error` when the caller passes ``resource_kind``.
   Rewrites the message to name the missing resource and point at the
   appropriate discovery tool (see :data:`_DISCOVERY_HINTS`).
3. :func:`enrich_invalid_arguments_error` — also invoked *inside* the handler
   when the caller passes ``resource_kind`` or ``invalid_args_hint``. Appends a
   hint clarifying how to discover valid argument values.
4. :func:`enrich_ambiguous_access_error` — invoked *inside* the handler when
   ``resource_kind`` is set and the error code is ``PERMISSION_DENIED``. Covers
   the Pipefy API quirk where a nonexistent ID returns ``PERMISSION_DENIED``
   (indistinguishable from a real access denial without a membership lookup).

Tiers 2–4 run inside :func:`handle_tool_graphql_error` via the shared
:func:`try_enrich_graphql_error` helper. When no enricher matches (or when the
caller does not opt in), the handler falls through to the **legacy path**:
concatenate extracted error strings and return the bare message, preserving
zero-regression behavior for call sites that have not been migrated yet.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipefy_mcp.services.pipefy import PipefyClient

import pipefy_mcp.settings as _settings_mod
from pipefy_mcp.tools.tool_error_envelope import tool_error

# Suffixes appended by InternalApiClient for service-layer diagnostics; MCP tools
# strip these from default user-visible errors.
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
    """Best-effort extraction of error messages from gql/GraphQL exceptions.

    When the exception carries a structured ``errors`` list (e.g. gql
    ``TransportQueryError``), only the extracted ``message`` strings are
    returned; the raw ``str(exc)`` is skipped because it often contains
    the full error dict with ``locations`` / ``extensions`` noise.  The
    raw string is used as a fallback only when no structured messages
    can be extracted.
    """
    structured: list[str] = []

    errors = getattr(exc, "errors", None)
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                msg = item.get("message")
                if isinstance(msg, str) and msg:
                    structured.append(msg)
            elif isinstance(item, str) and item:
                structured.append(item)

    if structured:
        return structured

    raw = str(exc)
    if raw:
        return [raw]
    return []


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
        codes.extend(extract_internal_api_bracket_codes(raw))

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
    return extract_internal_api_bracket_correlation_id(raw)


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


_PERMISSION_DENIED_CODE = "PERMISSION_DENIED"
_NOT_FOUND_CODES = frozenset({"NOT_FOUND", "RESOURCE_NOT_FOUND"})
_INVALID_ARGUMENT_CODES = frozenset({"INVALID_ARGUMENTS", "BAD_USER_INPUT"})
_NOT_FOUND_STRING_MARKERS = ("not found", "does not exist", "doesn't exist")
_GENERIC_NOT_FOUND_HINT = "Verify the ID and try again."
_GENERIC_INVALID_ARGS_HINT = "Check the tool's docstring for required field shapes."

# Per-resource discovery hints for NOT_FOUND / ambiguous access messages.
_DISCOVERY_HINTS: dict[str, str] = {
    "pipe": "Use 'search_pipes' or 'get_organization' to list accessible pipes.",
    "card": "Use 'find_cards' or 'get_cards' to list cards in a pipe.",
    "phase": "Use 'get_pipe' to list phases in a pipe.",
    "phase_field": "Use 'get_phase_fields' to list fields of a phase.",
    "table": "Use 'search_tables' to find tables.",
    "table_record": "Use 'find_records' to find table records.",
    "table_field": "Use 'get_table' to list fields of a table.",
    "field_condition": "Use 'get_field_conditions' to list conditions of a phase.",
    "ai_agent": "Use 'get_ai_agents' to list AI agents of a repo.",
    "ai_agent_log": "Use 'get_ai_agent_logs' to list agent execution logs for a repo.",
    "ai_automation": "Use 'get_ai_automations' to list AI automations.",
    "automation": "Use 'get_automations' to list automations.",
    "label": "Use 'get_labels' to list labels in a pipe.",
    "webhook": "Use 'get_webhooks' to list webhooks of a pipe.",
    "organization": "Use 'get_organization' to verify the organization ID.",
    "organization_report": "Use 'get_organization_reports' to list organization reports.",
    "pipe_report": "Use 'get_pipe_reports' to list reports of a pipe.",
    "member": "Use 'get_pipe_members' to list current members of a pipe.",
    "comment": "Use 'get_card' to list comments on a card.",
    "email_template": "Use 'get_email_templates' to list available templates.",
}

# Pipe-scoped kinds: ambiguous PERMISSION_DENIED messages add get_pipe_members.
_PIPE_CENTRIC_KINDS: frozenset[str] = frozenset(
    {
        "pipe",
        "phase",
        "phase_field",
        "card",
        "label",
        "pipe_report",
        "pipe_relation",
        "field_condition",
        "start_form_field",
    }
)


def _humanize_resource_kind(kind: str) -> str:
    """Render a snake_case resource kind for user-visible messages.

    ``"pipe"`` -> ``"Pipe"``; ``"table_record"`` -> ``"Table record"``.
    """
    if not kind:
        return kind
    humanized = kind.replace("_", " ")
    return humanized[:1].upper() + humanized[1:]


def _looks_like_not_found(exc: BaseException, codes: list[str]) -> bool:
    """Detect NOT_FOUND either via structured code or low-signal text marker."""
    if any(code in _NOT_FOUND_CODES for code in codes):
        return True
    haystack = " ".join(extract_error_strings(exc)).lower()
    return any(marker in haystack for marker in _NOT_FOUND_STRING_MARKERS)


def enrich_not_found_error(
    exc: BaseException,
    *,
    resource_kind: str,
    resource_id: str | None = None,
) -> str | None:
    """Return an enriched message for NOT_FOUND errors, or ``None`` when inapplicable.

    Recognizes both structured GraphQL codes (``NOT_FOUND`` /
    ``RESOURCE_NOT_FOUND``) and raw-text markers (``"not found"``,
    ``"does not exist"``). For unknown resource kinds the hint falls back to a
    generic "Verify the ID and try again." line so the response is still
    actionable.

    Args:
        exc: Root exception from gql/httpx.
        resource_kind: Canonical kind (e.g. ``"pipe"``, ``"card"``,
            ``"phase_field"``). Used both as discovery-hint key and as the
            user-facing label in the rendered message.
        resource_id: Target resource identifier; omitted from the message
            when ``None``.
    """
    codes = extract_graphql_error_codes(exc)
    if not _looks_like_not_found(exc, codes):
        return None

    discovery_hint = _DISCOVERY_HINTS.get(resource_kind, _GENERIC_NOT_FOUND_HINT)
    label = _humanize_resource_kind(resource_kind)
    if resource_id:
        return f"{label} not found (ID: {resource_id}). {discovery_hint}"
    return f"{label} not found. {discovery_hint}"


def enrich_invalid_arguments_error(
    exc: BaseException,
    *,
    hint: str | None = None,
) -> str | None:
    """Append a hint to BAD_USER_INPUT / INVALID_ARGUMENTS messages, or ``None``.

    Args:
        exc: Root exception from gql/httpx.
        hint: Tool-specific guidance (e.g. "Use 'get_phase_fields' to list
            valid field IDs."). When ``None`` a generic docstring-reference
            hint is used.
    """
    codes = extract_graphql_error_codes(exc)
    if not any(code in _INVALID_ARGUMENT_CODES for code in codes):
        return None

    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else "Invalid arguments."
    appended = hint or _GENERIC_INVALID_ARGS_HINT
    return f"{base} Hint: {appended}"


def enrich_ambiguous_access_error(
    exc: BaseException,
    *,
    resource_kind: str,
    resource_id: str | None = None,
) -> str | None:
    """Rewrite PERMISSION_DENIED to an ambiguity-hint message when appropriate.

    Pipefy's GraphQL API returns ``PERMISSION_DENIED`` both for resources the
    service account cannot access AND for resources that do not exist — a
    common security-conscious pattern to prevent resource enumeration. From
    the caller's perspective the two are indistinguishable, and the raw
    "Permission denied" string gives an agent no actionable next step.

    When a call site opts in by passing ``resource_kind``, this enricher
    produces a dual-meaning message that points at BOTH the discovery tool
    (in case the ID is wrong) AND the membership-verification path (in case
    access is the actual issue). Returns ``None`` when the code is not
    ``PERMISSION_DENIED`` so other enrichers get a turn.

    Distinct from :func:`enrich_permission_denied_error` — that async helper
    runs *before* :func:`handle_tool_graphql_error` at specific cross-pipe
    write call sites (``create_card``, ``create_automation``, etc.) with a
    ``PipefyClient`` and performs real membership lookups. This helper is the
    synchronous fallback for **read** tools where we have no client context
    to verify membership; it honors the existing pre-handler enrichment by
    returning ``None`` unless its own predicate matches.

    Args:
        exc: Root exception from gql/httpx.
        resource_kind: Canonical kind (e.g. ``"pipe"``, ``"webhook"``).
        resource_id: Target resource identifier; omitted from the message
            when ``None``.
    """
    codes = extract_graphql_error_codes(exc)
    if _PERMISSION_DENIED_CODE not in codes:
        return None

    discovery_hint = _DISCOVERY_HINTS.get(resource_kind, _GENERIC_NOT_FOUND_HINT)
    label = _humanize_resource_kind(resource_kind)
    id_clause = f" (ID: {resource_id})" if resource_id else ""
    base = (
        f"Cannot access {label.lower()}{id_clause}. The ID may not exist OR "
        f"the service account may lack access. {discovery_hint}"
    )
    if resource_kind in _PIPE_CENTRIC_KINDS:
        base += " If the resource is listed, verify membership with 'get_pipe_members'."
    return base


def try_enrich_graphql_error(
    exc: BaseException,
    *,
    codes: list[str],
    debug: bool,
    correlation_id: str | None,
    resource_kind: str | None,
    resource_id: str | None,
    invalid_args_hint: str | None,
) -> tuple[str, str] | None:
    """Run enrichment tiers. Returns ``(message, code)`` or ``None``.

    Shared by :func:`handle_tool_graphql_error` and
    ``handle_automation_tool_graphql_error`` so the 3-tier precedence lives in
    one place. Callers pass pre-extracted ``codes`` and ``correlation_id`` so
    the expensive extraction is not repeated.

    Args:
        exc: Root exception from gql/httpx.
        codes: GraphQL error codes extracted from ``exc``.
        debug: When True, append codes and ``correlation_id`` to messages.
        correlation_id: Pre-extracted correlation id; appended when ``debug`` is True.
        resource_kind: Optional canonical kind; opts into NOT_FOUND enrichment.
        resource_id: Optional resource id; surfaced in the enriched message.
        invalid_args_hint: Optional tool-specific hint for BAD_USER_INPUT errors.
    """
    first_code = codes[0] if codes else None
    enrichment_opted_in = resource_kind is not None or invalid_args_hint is not None
    if not enrichment_opted_in:
        return None

    if resource_kind is not None:
        enriched = enrich_not_found_error(
            exc, resource_kind=resource_kind, resource_id=resource_id
        )
        if enriched is not None:
            message = with_debug_suffix(
                enriched, debug=debug, codes=codes, correlation_id=correlation_id
            )
            return message, first_code or "NOT_FOUND"

    enriched = enrich_invalid_arguments_error(exc, hint=invalid_args_hint)
    if enriched is not None:
        message = with_debug_suffix(
            enriched, debug=debug, codes=codes, correlation_id=correlation_id
        )
        return message, first_code or "INVALID_ARGUMENTS"

    if resource_kind is not None:
        enriched = enrich_ambiguous_access_error(
            exc, resource_kind=resource_kind, resource_id=resource_id
        )
        if enriched is not None:
            message = with_debug_suffix(
                enriched, debug=debug, codes=codes, correlation_id=correlation_id
            )
            return message, first_code or _PERMISSION_DENIED_CODE

    return None


def handle_tool_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
    resource_kind: str | None = None,
    resource_id: str | None = None,
    invalid_args_hint: str | None = None,
) -> dict[str, Any]:
    """Turn transport/GraphQL failures into a structured :func:`tool_error` payload.

    **Enrichment is opt-in.** When neither ``resource_kind`` nor
    ``invalid_args_hint`` is passed, behavior is identical to the pre-Wave-2
    path: concatenate ``extract_error_strings`` (or ``fallback_msg`` if empty),
    optionally append a debug suffix, and emit the envelope.

    When opted-in, the handler tries (in order):

    * :func:`enrich_not_found_error` with ``resource_kind``/``resource_id``;
    * :func:`enrich_invalid_arguments_error` with ``invalid_args_hint``;
    * :func:`enrich_ambiguous_access_error` with ``resource_kind``/
      ``resource_id`` — covers the Pipefy API case where a nonexistent ID
      returns ``PERMISSION_DENIED`` (indistinguishable from a real
      access-denied). Only fires when ``resource_kind`` was passed.
    * the legacy path, so unrelated codes (e.g. timeouts) still reach clients
      with the original message.

    Call sites that own PERMISSION_DENIED handling should keep invoking
    :func:`enrich_permission_denied_error` *before* this function — it runs at
    a different layer (needs the Pipefy client for membership lookups).

    Args:
        exc: Root exception from gql/httpx.
        fallback_msg: Used when ``extract_error_strings`` is empty.
        debug: When True, append codes and ``correlation_id`` to the message.
        resource_kind: Optional canonical kind; opts this call site into
            NOT_FOUND enrichment.
        resource_id: Optional resource id; surfaced in the enriched message.
        invalid_args_hint: Optional tool-specific hint for BAD_USER_INPUT
            errors; opts this call site into invalid-arguments enrichment.
    """
    codes = extract_graphql_error_codes(exc)
    first_code = codes[0] if codes else None
    cid = extract_graphql_correlation_id(exc) if debug else None

    enriched_result = try_enrich_graphql_error(
        exc,
        codes=codes,
        debug=debug,
        correlation_id=cid,
        resource_kind=resource_kind,
        resource_id=resource_id,
        invalid_args_hint=invalid_args_hint,
    )
    if enriched_result is not None:
        message, code = enriched_result
        return tool_error(message, code=code)

    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    base = with_debug_suffix(base, debug=debug, codes=codes, correlation_id=cid)
    return tool_error(base, code=first_code)


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

    timeout = _settings_mod.settings.pipefy.permission_denied_enrichment_timeout_seconds
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                *(client.get_pipe_members(pid) for pid in unique_ids),
                return_exceptions=True,
            ),
            timeout=timeout,
        )
    except (TimeoutError, asyncio.TimeoutError):
        return None

    sa_ids = set(_settings_mod.settings.pipefy.service_account_ids)

    missing_pipes: list[str] = []
    for pid, result in zip(unique_ids, results):
        if isinstance(result, BaseException):
            missing_pipes.append(
                f"Could not verify membership for pipe {pid}. "
                f"Check if the service account is a member; use invite_members if not."
            )
            continue
        members = result.get("pipe", {}).get("members") or []
        pipe_name = result.get("pipe", {}).get("name") or f"pipe {pid}"
        if not members:
            missing_pipes.append(
                f"Service account may not be a member of {pipe_name} (ID: {pid}). "
                f"Use invite_members to add it."
            )
        elif sa_ids:
            member_ids = {
                str(m.get("user", {}).get("id", ""))
                for m in members
                if isinstance(m, dict)
            }
            if not sa_ids & member_ids:
                missing_pipes.append(
                    f"Service account is not a member of {pipe_name} (ID: {pid}). "
                    f"Use invite_members to add it."
                )

    if not missing_pipes:
        return None

    return "\n".join(missing_pipes)


__all__ = [
    "enrich_ambiguous_access_error",
    "enrich_invalid_arguments_error",
    "enrich_not_found_error",
    "enrich_permission_denied_error",
    "extract_error_strings",
    "extract_graphql_correlation_id",
    "extract_graphql_error_codes",
    "extract_internal_api_bracket_codes",
    "extract_internal_api_bracket_correlation_id",
    "handle_tool_graphql_error",
    "strip_internal_api_diagnostic_markers",
    "try_enrich_graphql_error",
    "with_debug_suffix",
]
