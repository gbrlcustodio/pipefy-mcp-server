"""Payload builders and GraphQL error mapping for traditional automation MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context
from typing_extensions import TypedDict

from pipefy_mcp.services.pipefy.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
)
from pipefy_mcp.tools.graphql_error_helpers import (
    extract_error_strings,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    with_debug_suffix,
)

AutomationReadToolData = (
    AutomationRuleRecord
    | list[AutomationRuleSummary]
    | list[AutomationActionRow]
    | list[AutomationEventRow]
)


class AutomationReadSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    data: AutomationReadToolData


class AutomationMutationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    automation: dict[str, Any]


class AutomationToolErrorPayload(TypedDict):
    success: Literal[False]
    error: str


def build_automation_mutation_success_payload(
    automation: dict[str, Any],
    action: str,
) -> AutomationMutationSuccessPayload:
    """``success`` plus labeled ``message`` and raw ``automation`` dict.

    Args:
        automation: ``automation`` key from the mutation (possibly empty for delete).
        action: Verb for the canned label (``created`` / ``updated`` / ``deleted`` / other).
    """
    labels = {
        "created": "Automation created.",
        "updated": "Automation updated.",
        "deleted": "Automation deleted.",
    }
    message = labels.get(action, f"Automation {action}.")
    return {
        "success": True,
        "message": message,
        "automation": automation,
    }


def build_automation_read_success_payload(
    data: AutomationReadToolData,
    label: str,
) -> AutomationReadSuccessPayload:
    """``success``, ``message``, and typed read ``data`` (record or list).

    Args:
        data: Record, summary list, or catalog rows from the API.
        label: Shown as ``message``.
    """
    return {
        "success": True,
        "message": label,
        "data": data,
    }


def build_automation_error_payload(
    message: str,
    debug: str | None = None,
) -> AutomationToolErrorPayload:
    """``success: False``; optional ``debug`` suffix in brackets.

    Args:
        message: Primary error text.
        debug: Extra detail appended as ``… [debug]`` when set.
    """
    text = message if not debug else f"{message} [{debug}]"
    return {"success": False, "error": text}


def handle_automation_tool_graphql_error(
    exc: BaseException,
    ctx: Context,
    debug: bool,
) -> AutomationToolErrorPayload:
    """Format ``exc`` as ``build_automation_error_payload``; optional MCP debug log.

    Args:
        exc: Root exception from gql/httpx.
        ctx: MCP context for ``ctx.debug`` when ``debug`` is True.
        debug: Log raw exception and append codes / ``correlation_id`` to the message.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else "Automation request failed."
    if debug:
        ctx.debug(f"automation GraphQL error: {exc!r}")
        codes = extract_graphql_error_codes(exc)
        cid = extract_graphql_correlation_id(exc)
        base = with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid)
    return build_automation_error_payload(message=base)
