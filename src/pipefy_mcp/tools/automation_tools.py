"""MCP tools for traditional Pipefy automations (trigger/action rules)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.automation_tool_helpers import (
    build_automation_error_payload,
    build_automation_mutation_success_payload,
    build_automation_read_success_payload,
    handle_automation_tool_graphql_error,
)
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.validation_helpers import (
    mutation_error_if_not_optional_dict,
    valid_repo_id,
)


def _normalize_optional_filter(value: str | int | None) -> tuple[bool, str | None]:
    """Return (ok, value) for optional org/pipe filters; ok False when value is syntactically invalid."""
    if value is None:
        return True, None
    if not valid_repo_id(value):
        return False, None
    if isinstance(value, int):
        return True, str(value)
    return True, value.strip()


def _normalize_required_id(value: str | int) -> str | None:
    if not valid_repo_id(value):
        return None
    if isinstance(value, int):
        return str(value)
    return value.strip()


class AutomationTools:
    """MCP tools for traditional (non-AI) pipe automations."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automation(
            ctx: Context, automation_id: str | int
        ) -> dict[str, Any]:
            """Load one automation rule by ID (name, active flag, pipe, trigger, actions).

            Use this before ``update_automation`` to inspect the current configuration.
            For new rules, discover trigger and action IDs via ``get_automation_events`` and
            ``get_automation_actions`` on the target pipe, then call ``create_automation``.

            Args:
                automation_id: Automation rule ID.
            """
            aid = _normalize_required_id(automation_id)
            if aid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'automation_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )
            try:
                raw = await client.get_automation(aid)
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, False)
            message = (
                "No automation found for the given ID."
                if not raw
                else "Automation retrieved."
            )
            return build_automation_read_success_payload(raw, message)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automations(
            ctx: Context,
            organization_id: str | int | None = None,
            pipe_id: str | int | None = None,
        ) -> dict[str, Any]:
            """List traditional automation rules, optionally filtered by organization and/or pipe.

            Combine with ``get_automation`` for full detail. Use pipe-scoped listings to plan
            ``create_automation`` / ``update_automation`` without pulling every org rule.

            When only ``pipe_id`` is set (no ``organization_id``), the server resolves the org from
            the pipe first, then lists automations — two sequential API calls vs. one when you pass
            ``organization_id`` directly.

            Args:
                organization_id: When set, restrict to this organization.
                pipe_id: When set, restrict to this pipe.
            """
            ok_o, org = _normalize_optional_filter(organization_id)
            ok_p, pipe = _normalize_optional_filter(pipe_id)
            if not ok_o:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'organization_id': provide a non-empty string or "
                        "positive integer when supplied."
                    ),
                )
            if not ok_p:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'pipe_id': provide a non-empty string or "
                        "positive integer when supplied."
                    ),
                )
            try:
                rows = await client.get_automations(
                    organization_id=org,
                    pipe_id=pipe,
                )
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, False)
            return build_automation_read_success_payload(
                rows,
                "Automations listed.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automation_actions(
            ctx: Context,
            pipe_id: str | int,
        ) -> dict[str, Any]:
            """List automation action types available on a pipe (labels, fields, IDs).

            Call this before ``create_automation`` or ``update_automation`` to choose valid
            ``action_id`` values and required ``actionFields`` for the Pipefy API payload.

            Args:
                pipe_id: Pipe ID.
            """
            pid = _normalize_required_id(pipe_id)
            if pid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'pipe_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )
            try:
                rows = await client.get_automation_actions(pid)
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, False)
            return build_automation_read_success_payload(
                rows,
                "Automation actions catalog retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        async def get_automation_events(
            ctx: Context, pipe_id: str | int
        ) -> dict[str, Any]:
            """List automation trigger event definitions (IDs and metadata).

            Pipefy's schema exposes one global event catalog (no per-pipe GraphQL filter);
            ``pipe_id`` is kept so callers anchor to a workflow context. Use results with
            ``get_automation_actions`` on the same pipe before ``create_automation``.

            Args:
                pipe_id: Pipe ID (context for the agent; required by the tool).
            """
            pid = _normalize_required_id(pipe_id)
            if pid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'pipe_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )
            try:
                rows = await client.get_automation_events(pid)
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, False)
            return build_automation_read_success_payload(
                rows,
                "Automation events catalog retrieved.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_automation(
            ctx: Context,
            pipe_id: str | int,
            name: str,
            trigger_id: str | int,
            action_id: str | int,
            active: bool = True,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Create a traditional automation rule on a pipe (event + action).

            Use ``get_automation_events`` and ``get_automation_actions`` on ``pipe_id`` first to obtain
            valid ``trigger_id`` and ``action_id``. Optional ``extra_input`` merges API fields for
            ``CreateAutomationInput`` (camelCase keys). Use ``update_automation`` with ``active: false``
            to disable a rule after creation.

            Args:
                pipe_id: Pipe ID (automation context).
                name: Rule name.
                trigger_id: Event ID from ``get_automation_events``.
                action_id: Action type ID from ``get_automation_actions``.
                active: When True (default), the rule is created **enabled**. Set False to start disabled. If ``extra_input`` includes ``active``, that value wins.
                extra_input: Optional extra fields for the mutation input.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            pid = _normalize_required_id(pipe_id)
            tid = _normalize_required_id(trigger_id)
            aid = _normalize_required_id(action_id)
            if pid is None or tid is None or aid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'pipe_id', 'trigger_id', or 'action_id': use non-empty "
                        "strings or positive integers."
                    ),
                )
            if not isinstance(name, str) or not name.strip():
                return build_automation_error_payload(
                    message="Invalid 'name': provide a non-empty string.",
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.create_automation(
                    pid,
                    name.strip(),
                    tid,
                    aid,
                    active=active,
                    extra_input=extra_input,
                )
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, debug)
            block = raw.get("createAutomation") or {}
            automation = block.get("automation") or {}
            if not isinstance(automation, dict):
                automation = {}
            return build_automation_mutation_success_payload(automation, "created")

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_automation(
            ctx: Context,
            automation_id: str | int,
            extra_input: Any | None = None,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Update an existing traditional automation (partial ``UpdateAutomationInput``).

            Optional ``extra_input`` holds fields to change (camelCase keys). Discover current shape
            with ``get_automation`` when unsure.

            Args:
                automation_id: Automation rule ID.
                extra_input: Optional fields to patch on the rule.
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            rid = _normalize_required_id(automation_id)
            if rid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'automation_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )
            bad = mutation_error_if_not_optional_dict(
                extra_input, arg_name="extra_input"
            )
            if bad is not None:
                return bad
            try:
                raw = await client.update_automation(
                    rid,
                    extra_input=extra_input,
                )
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, debug)
            block = raw.get("updateAutomation") or {}
            automation = block.get("automation") or {}
            if not isinstance(automation, dict):
                automation = {}
            return build_automation_mutation_success_payload(automation, "updated")

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        async def delete_automation(
            ctx: Context[ServerSession, None],
            automation_id: str | int,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict[str, Any]:
            """Delete an automation rule permanently.

            Two-step operation: call without ``confirm`` to preview, then with
            ``confirm=True`` after user approval. When the MCP client supports
            elicitation, the user is prompted interactively instead.

            Args:
                automation_id: Automation rule ID to delete.
                confirm: Set to True to execute the deletion (step 2).
                debug: When True, append GraphQL codes and correlation_id to errors.
            """
            rid = _normalize_required_id(automation_id)
            if rid is None:
                return build_automation_error_payload(
                    message=(
                        "Invalid 'automation_id': provide a non-empty string or "
                        "positive integer."
                    ),
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"automation (ID: {automation_id})",
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_automation(rid)
            except Exception as exc:
                return handle_automation_tool_graphql_error(exc, ctx, debug)
            if not raw.get("success"):
                return build_automation_error_payload(
                    message="Delete automation did not succeed.",
                )
            return build_automation_mutation_success_payload({}, "deleted")
