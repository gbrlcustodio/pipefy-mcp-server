"""Pydantic models for Pipefy API inputs (SDK public surface)."""

from __future__ import annotations

from pipefy_sdk.models.ai_agent import (
    BehaviorInput,
    CreateAiAgentInput,
    UpdateAiAgentInput,
)
from pipefy_sdk.models.ai_automation import (
    AutomationConditionInput,
    AutomationEventParamsInput,
    CreateAiAutomationInput,
    UpdateAiAutomationInput,
)
from pipefy_sdk.models.attachment import (
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)
from pipefy_sdk.models.comment import (
    CommentInput,
    DeleteCommentInput,
    UpdateCommentInput,
)
from pipefy_sdk.models.member_invite import MemberInvite
from pipefy_sdk.models.send_task_automation import CreateSendTaskAutomationInput
from pipefy_sdk.models.validators import NonBlankStr, PipefyId

__all__ = [
    "AutomationConditionInput",
    "AutomationEventParamsInput",
    "BehaviorInput",
    "CommentInput",
    "CreateAiAgentInput",
    "CreateAiAutomationInput",
    "CreateSendTaskAutomationInput",
    "MemberInvite",
    "DeleteCommentInput",
    "NonBlankStr",
    "PipefyId",
    "UpdateAiAgentInput",
    "UpdateAiAutomationInput",
    "UpdateCommentInput",
    "UploadAttachmentToCardInput",
    "UploadAttachmentToTableRecordInput",
    "infer_content_type",
]
