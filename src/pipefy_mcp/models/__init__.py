"""Pipefy MCP Pydantic models (package exports)."""

from __future__ import annotations

from pipefy_mcp.models.ai_agent import (
    BehaviorInput,
    CreateAiAgentInput,
    UpdateAiAgentInput,
)
from pipefy_mcp.models.ai_automation import (
    AutomationConditionInput,
    AutomationEventParamsInput,
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_mcp.models.attachment import (
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)
from pipefy_mcp.models.send_task_automation import CreateSendTaskAutomationInput
from pipefy_mcp.models.validators import NonBlankStr, PipefyId

__all__ = [
    "AutomationConditionInput",
    "AutomationEventParamsInput",
    "BehaviorInput",
    "CreateAiAgentInput",
    "CreateAiAutomationInput",
    "CreateSendTaskAutomationInput",
    "NonBlankStr",
    "PipefyId",
    "UpdateAiAgentInput",
    "UpdateAiAutomationInput",
    "UploadAttachmentToCardInput",
    "UploadAttachmentToTableRecordInput",
    "infer_content_type",
]
