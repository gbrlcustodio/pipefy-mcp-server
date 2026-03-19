"""MCP tools for AI Agent operations (create + update)."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput
from pipefy_mcp.services.pipefy.ai_agent_service import AiAgentService
from pipefy_mcp.tools.ai_tool_helpers import (
    build_ai_tool_error,
    build_create_agent_success,
    build_toggle_agent_status_success,
    build_update_agent_success,
)


class AiAgentTools:
    """Declares MCP tools for AI Agent create and update."""

    @staticmethod
    def register(mcp: FastMCP, service: AiAgentService) -> None:
        """Register AI Agent tools on the MCP server."""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_ai_agent(
            ctx: Context,
            name: str,
            repo_uuid: str,
        ) -> dict:
            """Create an AI Agent (empty, no behaviors) attached to a pipe.

            Use update_ai_agent to configure 1 to 5 behaviors.
            repo_uuid is the pipe's unique identifier — not the numeric pipe ID from the URL.
            Resolve it via pipe query.

            Args:
                name: Agent display name.
                repo_uuid: UUID of the pipe the agent belongs to.
            """
            ctx.debug(f"create_ai_agent: name={name}, repo_uuid={repo_uuid}")
            try:
                validated = CreateAiAgentInput(name=name, repo_uuid=repo_uuid)
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                result = await service.create_agent(validated)
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(str(exc))

            return build_create_agent_success(
                agent_uuid=result["agent_uuid"],
                message=result["message"],
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_ai_agent(
            ctx: Context,
            uuid: str,
            name: str,
            repo_uuid: str,
            instruction: str,
            behaviors: list[dict],
            data_source_ids: list[str] | None = None,
        ) -> dict:
            """Update an AI Agent with an instruction and 1 to 5 behaviors that can execute complex actions (e.g. move card, update fields conditionally).

            The API replaces the entire agent payload, so always send the complete list of behaviors.
            Other agents (e.g. OpenClaw) can use this tool to configure Pipefy AI Agents programmatically.

            Args:
                uuid: UUID of the agent to update.
                name: Agent display name.
                repo_uuid: UUID of the pipe the agent belongs to.
                instruction: Global instruction for the agent.
                behaviors: List of 1 to 5 behavior dicts (name, event_id required per behavior).
                data_source_ids: Optional list of data source IDs.
            """
            ctx.debug(f"update_ai_agent: uuid={uuid}, behaviors_count={len(behaviors)}")
            try:
                validated = UpdateAiAgentInput(
                    uuid=uuid,
                    name=name,
                    repo_uuid=repo_uuid,
                    instruction=instruction,
                    behaviors=behaviors,
                    data_source_ids=data_source_ids or [],
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                result = await service.update_agent(validated)
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(str(exc))

            return build_update_agent_success(
                agent_uuid=result["agent_uuid"],
                message=result["message"],
            )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def toggle_ai_agent_status(
            ctx: Context,
            uuid: str,
            active: bool,
        ) -> dict:
            """Enable or disable an AI Agent.

            Set active=true to activate or active=false to deactivate.
            Does not require resending the agent configuration.

            Args:
                uuid: UUID of the agent to enable/disable.
                active: True to activate, False to deactivate.
            """
            ctx.debug(f"toggle_ai_agent_status: uuid={uuid}, active={active}")
            agent_uuid = uuid.strip()
            if not agent_uuid:
                return build_ai_tool_error("uuid must not be blank")

            try:
                result = await service.toggle_agent_status(
                    agent_uuid=agent_uuid, active=active
                )
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(str(exc))

            return build_toggle_agent_status_success(message=result["message"])
