"""MCP tools for AI Agent operations (create, read, update, delete)."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.ai_agent import CreateAiAgentInput, UpdateAiAgentInput
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.ai_tool_helpers import (
    build_ai_tool_error,
    build_create_agent_partial_failure,
    build_create_agent_success,
    build_delete_agent_success,
    build_get_agent_success,
    build_get_agents_success,
    build_toggle_agent_status_success,
    build_update_agent_success,
)
from pipefy_mcp.tools.graphql_error_helpers import extract_error_strings


class AiAgentTools:
    """Declares MCP tools for AI Agent CRUD and status."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register AI Agent tools on the MCP server."""

        def error_payload_from_exception(exc: BaseException) -> dict:
            msgs = extract_error_strings(exc)
            text = "; ".join(msgs) if msgs else str(exc)
            return build_ai_tool_error(text)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_ai_agent(
            ctx: Context,
            name: str,
            repo_uuid: str,
            instruction: str,
            behaviors: list[dict],
            data_source_ids: list[str] | None = None,
        ) -> dict:
            """Create an AI Agent and configure it in one call (GraphQL create + update).

            Requires a non-empty instruction and 1–5 behaviors. Instruction maps to the agent's
            Description field in the Pipefy UI (agent-level purpose). Each behavior's prompt/instruction
            lives in ``actionParams.aiBehaviorParams.instruction`` when sent to the API.

            Each behavior must also include ``actionParams.aiBehaviorParams.actionsAttributes`` with
            at least one action; otherwise the API rejects the update.

            Discovery workflow (call these tools first):
              1. ``get_pipe(pipe_id)`` → obtain ``uuid`` (use as ``repo_uuid``) and phase IDs.
              2. ``get_automation_events(pipe_id)`` → pick a valid ``event_id`` for the behavior
                 (e.g. ``card_created``, ``card_moved``, ``field_updated``).
              3. ``get_automation_actions(pipe_id)`` → find available ``actionType`` values.

            Behavior dict example::

              {
                "name": "When card is created: move to Doing",
                "event_id": "card_created",
                "actionParams": {
                  "aiBehaviorParams": {
                    "instruction": "Analyze the card and summarize key points.",
                    "actionsAttributes": [
                      {
                        "name": "Move to Doing",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": "<phase_id from get_pipe>"}
                      }
                    ]
                  }
                }
              }

            Known ``actionType`` values and their required ``metadata``:
              - ``move_card`` → ``{"destinationPhaseId": "<phase_id>"}``
              - ``update_card_field`` → ``{"fieldsAttributes": [{"fieldId": "...", "value": "..."}]}``
              - ``create_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [...]}``
              - ``create_connected_card`` → ``{"pipeId": "<pipe_id>", "fieldsAttributes": [...]}``

            Args:
                name: Agent display name.
                repo_uuid: UUID of the pipe (from ``get_pipe``), not the numeric pipe ID.
                instruction: Agent-level purpose (Pipefy UI "Description"; API ``instruction``).
                behaviors: 1–5 behavior dicts. Each requires ``name``, ``event_id``, and
                    ``actionParams.aiBehaviorParams`` with a non-empty ``actionsAttributes`` list.
                    See example above for the full shape.
                data_source_ids: Optional knowledge-source IDs (same as ``update_ai_agent``).
            """
            ctx.debug(
                f"create_ai_agent: name={name}, repo_uuid={repo_uuid}, "
                f"instruction_len={len(instruction)}, behaviors_count={len(behaviors)}, "
                f"data_source_ids={data_source_ids!r}"
            )
            try:
                validated = CreateAiAgentInput(
                    name=name,
                    repo_uuid=repo_uuid,
                    instruction=instruction,
                    behaviors=behaviors,
                    data_source_ids=data_source_ids or [],
                )
            except ValidationError as exc:
                return build_ai_tool_error(str(exc))

            try:
                create_result = await client.create_ai_agent(validated)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)

            agent_uuid = create_result["agent_uuid"]

            update_input = UpdateAiAgentInput(
                uuid=agent_uuid,
                name=validated.name,
                repo_uuid=validated.repo_uuid,
                instruction=validated.instruction,
                behaviors=validated.behaviors,
                data_source_ids=validated.data_source_ids,
            )
            try:
                await client.update_ai_agent(update_input)
            except Exception as exc:  # noqa: BLE001
                msgs = extract_error_strings(exc)
                text = "; ".join(msgs) if msgs else str(exc)
                return build_create_agent_partial_failure(
                    agent_uuid=agent_uuid,
                    error=text,
                )

            msg = f"AI Agent created and configured successfully. UUID: {agent_uuid}"
            return build_create_agent_success(agent_uuid=agent_uuid, message=msg)

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
            """Update an AI Agent — replaces the entire config, so always send the complete behaviors list.

            Each behavior must include ``actionParams.aiBehaviorParams.actionsAttributes`` with at least
            one action (same constraint and shape as ``create_ai_agent`` — see its docstring for the
            full behavior dict example, discovery workflow, and known ``actionType`` values).

            Args:
                uuid: UUID of the agent to update.
                name: Agent display name.
                repo_uuid: UUID of the pipe (from ``get_pipe``).
                instruction: Agent-level purpose (Pipefy UI "Description"; API ``instruction``).
                behaviors: 1–5 behavior dicts. Same shape as ``create_ai_agent``: each needs ``name``,
                    ``event_id``, and ``actionParams.aiBehaviorParams.actionsAttributes``.
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
                result = await client.update_ai_agent(validated)
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
                result = await client.toggle_ai_agent_status(
                    agent_uuid=agent_uuid, active=active
                )
            except Exception as exc:  # noqa: BLE001
                return build_ai_tool_error(str(exc))

            return build_toggle_agent_status_success(message=result["message"])

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_agent(ctx: Context, uuid: str) -> dict:
            """Get an AI Agent by UUID. Use get_pipe to find the pipe's uuid field, then get_ai_agents to list agents.

            Args:
                uuid: Agent UUID.
            """
            agent_uuid = uuid.strip()
            ctx.debug(f"get_ai_agent: uuid={agent_uuid}")
            if not agent_uuid:
                return build_ai_tool_error("uuid must not be blank")
            try:
                agent = await client.get_ai_agent(agent_uuid)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)
            if not agent:
                return build_ai_tool_error(f"AI Agent not found: {agent_uuid}")
            return build_get_agent_success(agent)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True),
        )
        async def get_ai_agents(ctx: Context, repo_uuid: str) -> dict:
            """List all AI Agents for a pipe. Use before creating an agent to avoid duplicates.

            Args:
                repo_uuid: UUID of the pipe.
            """
            pipe_uuid = repo_uuid.strip()
            ctx.debug(f"get_ai_agents: repo_uuid={pipe_uuid}")
            if not pipe_uuid:
                return build_ai_tool_error("repo_uuid must not be blank")
            try:
                agents = await client.get_ai_agents(pipe_uuid)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)
            return build_get_agents_success(agents)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )
        async def delete_ai_agent(ctx: Context, uuid: str) -> dict:
            """Delete an AI Agent permanently. This action is irreversible. Always confirm with the user before executing.

            Args:
                uuid: Agent UUID.
            """
            agent_uuid = uuid.strip()
            ctx.debug(f"delete_ai_agent: uuid={agent_uuid}")
            if not agent_uuid:
                return build_ai_tool_error("uuid must not be blank")
            try:
                result = await client.delete_ai_agent(agent_uuid)
            except Exception as exc:  # noqa: BLE001
                return error_payload_from_exception(exc)
            if not result.get("success"):
                return build_ai_tool_error(
                    "delete_ai_agent failed: API returned success=false"
                )
            return build_delete_agent_success(
                message=f"AI Agent deleted successfully. UUID: {agent_uuid}",
            )
