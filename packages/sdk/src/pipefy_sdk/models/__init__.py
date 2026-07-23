"""Pydantic models for Pipefy API inputs (SDK public surface)."""

from __future__ import annotations

from pipefy_sdk.models.ai_agent import (
    AiBehaviorActionAttributes,
    AiBehaviorActionParams,
    AiBehaviorCapabilityAttributes,
    AiBehaviorMetadataInput,
    AiBehaviorParams,
    BehaviorInput,
    BehaviorPayload,
    CreateAiAgentInput,
    UpdateAiAgentInput,
)
from pipefy_sdk.models.ai_automation import (
    CONDITION_OPERATIONS,
    AutomationActionParamsInput,
    AutomationConditionInput,
    AutomationEventParamsInput,
    ConditionExpressionInput,
    CreateAiAutomationInput,
    FieldMapInput,
    UpdateAiAutomationInput,
)
from pipefy_sdk.models.attachment import (
    Attachment,
    AttachmentTarget,
    AttachmentUploadError,
    AttachmentUploadResult,
    AttachmentUploadStep,
    CardTarget,
    TableRecordTarget,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)
from pipefy_sdk.models.comment import (
    CommentInput,
    DeleteCommentInput,
    UpdateCommentInput,
)
from pipefy_sdk.models.knowledge_base import DataLookupCondition
from pipefy_sdk.models.member_invite import MemberInvite
from pipefy_sdk.models.portal import (
    CreatePortalElementInput,
    UpdatePortalElementInput,
)
from pipefy_sdk.models.send_task_automation import CreateSendTaskAutomationInput
from pipefy_sdk.models.validators import NonBlankStr, PipefyId

__all__ = [
    "AiBehaviorActionAttributes",
    "AiBehaviorActionParams",
    "AiBehaviorCapabilityAttributes",
    "AiBehaviorMetadataInput",
    "AiBehaviorParams",
    "Attachment",
    "AttachmentTarget",
    "AttachmentUploadError",
    "AttachmentUploadResult",
    "AttachmentUploadStep",
    "AutomationActionParamsInput",
    "AutomationConditionInput",
    "AutomationEventParamsInput",
    "BehaviorInput",
    "BehaviorPayload",
    "CardTarget",
    "CommentInput",
    "CONDITION_OPERATIONS",
    "ConditionExpressionInput",
    "CreateAiAgentInput",
    "CreateAiAutomationInput",
    "CreatePortalElementInput",
    "CreateSendTaskAutomationInput",
    "DataLookupCondition",
    "DeleteCommentInput",
    "FieldMapInput",
    "MemberInvite",
    "NonBlankStr",
    "PipefyId",
    "TableRecordTarget",
    "UpdateAiAgentInput",
    "UpdateAiAutomationInput",
    "UpdateCommentInput",
    "UpdatePortalElementInput",
    "UploadAttachmentToCardInput",
    "UploadAttachmentToTableRecordInput",
    "infer_content_type",
]
