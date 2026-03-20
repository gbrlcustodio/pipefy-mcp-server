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
    """Build a success payload for traditional automation mutation tools.

    Args:
        automation: ``automation`` object from the mutation response (may be empty for delete).
        action: Short action key for the user-facing message (e.g. ``created``, ``updated``, ``deleted``).
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
    """Build a success payload for traditional automation read tools.

    Args:
        data: Automation record, list of summaries, or catalog entries from the API.
        label: Short user-facing message (shown as ``message``).
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
    """Build an error payload for automation tools.

    Args:
        message: Primary error text for the caller.
        debug: Optional extra detail (e.g. correlation hints) appended in brackets.
    """
    text = message if not debug else f"{message} [{debug}]"
    return {"success": False, "error": text}


def handle_automation_tool_graphql_error(
    exc: BaseException,
    ctx: Context,
    debug: bool,
) -> AutomationToolErrorPayload:
    """Map a GraphQL/client exception to an automation-tool error payload.

    Args:
        exc: Exception from the Pipefy client or transport layer.
        ctx: MCP context (``debug`` logging in MCP clients such as Cursor when ``debug`` is True).
        debug: When True, log exception detail and append GraphQL codes / correlation_id.
    """
    msgs = extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else "Automation request failed."
    if debug:
        ctx.debug(f"automation GraphQL error: {exc!r}")
        codes = extract_graphql_error_codes(exc)
        cid = extract_graphql_correlation_id(exc)
        base = with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid)
    return build_automation_error_payload(message=base)
