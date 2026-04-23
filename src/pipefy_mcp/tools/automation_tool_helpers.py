"""Payload builders and GraphQL error mapping for traditional automation MCP tools."""

from __future__ import annotations

from typing import Any, Literal, cast

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
from pipefy_mcp.tools.tool_error_envelope import ToolErrorDetail, tool_error

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


class AutomationSimulationSuccessPayload(TypedDict):
    success: Literal[True]
    message: str
    simulation_id: str
    automation_simulation: dict[str, Any]


class AutomationToolErrorPayload(TypedDict):
    success: Literal[False]
    error: ToolErrorDetail


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


def build_automation_simulation_success_payload(
    simulation_id: str,
    automation_simulation: dict[str, Any],
) -> AutomationSimulationSuccessPayload:
    """Success payload with full ``automationSimulation`` row and the mutation ``simulationId``."""

    return {
        "success": True,
        "message": "Automation simulation completed.",
        "simulation_id": simulation_id,
        "automation_simulation": automation_simulation,
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
    *,
    code: str | None = None,
) -> AutomationToolErrorPayload:
    """``success: False``; optional ``debug`` suffix in brackets.

    Args:
        message: Primary error text.
        debug: Extra detail appended as ``… [debug]`` when set.
        code: Optional machine-readable code (e.g. GraphQL ``extensions.code``).
    """
    text = message if not debug else f"{message} [{debug}]"
    return cast(AutomationToolErrorPayload, tool_error(text, code=code))


async def handle_automation_tool_graphql_error(
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
    codes = extract_graphql_error_codes(exc)
    first_code = codes[0] if codes else None
    if debug:
        await ctx.debug(f"automation GraphQL error: {exc!r}")
        cid = extract_graphql_correlation_id(exc)
        base = with_debug_suffix(base, debug=True, codes=codes, correlation_id=cid)
    return build_automation_error_payload(message=base, code=first_code)


__all__ = [
    "AutomationMutationSuccessPayload",
    "AutomationReadSuccessPayload",
    "AutomationReadToolData",
    "AutomationSimulationSuccessPayload",
    "AutomationToolErrorPayload",
    "build_automation_error_payload",
    "build_automation_mutation_success_payload",
    "build_automation_read_success_payload",
    "build_automation_simulation_success_payload",
    "handle_automation_tool_graphql_error",
]
