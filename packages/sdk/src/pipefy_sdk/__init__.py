"""Pipefy GraphQL SDK: typed client, models, and service layer for Pipefy's APIs."""

from __future__ import annotations

from pipefy_sdk.client import PipefyClient
from pipefy_sdk.exceptions import PipefyAPIError, PipefyError
from pipefy_sdk.models import (
    AutomationConditionInput,
    AutomationEventParamsInput,
    BehaviorInput,
    CommentInput,
    CreateAiAgentInput,
    CreateAiAutomationInput,
    CreateSendTaskAutomationInput,
    DeleteCommentInput,
    NonBlankStr,
    PipefyId,
    UpdateAiAgentInput,
    UpdateAiAutomationInput,
    UpdateCommentInput,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)
from pipefy_sdk.models.form import create_form_model
from pipefy_sdk.services.ai_automation_service import AiAutomationService
from pipefy_sdk.services.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
)
from pipefy_sdk.services.internal_api_client import InternalApiClient
from pipefy_sdk.services.types import AiAgentGraphPayload, CardSearch, copy_card_search
from pipefy_sdk.settings import PipefySettings

__all__ = [
    "AiAgentGraphPayload",
    "AiAutomationService",
    "AutomationActionRow",
    "AutomationConditionInput",
    "AutomationEventParamsInput",
    "AutomationEventRow",
    "AutomationRuleRecord",
    "AutomationRuleSummary",
    "BehaviorInput",
    "CardSearch",
    "CommentInput",
    "CreateAiAgentInput",
    "CreateAiAutomationInput",
    "CreateSendTaskAutomationInput",
    "DeleteCommentInput",
    "InternalApiClient",
    "NonBlankStr",
    "PipefyAPIError",
    "PipefyClient",
    "PipefyError",
    "PipefyId",
    "PipefySettings",
    "UpdateAiAgentInput",
    "UpdateAiAutomationInput",
    "UpdateCommentInput",
    "UploadAttachmentToCardInput",
    "UploadAttachmentToTableRecordInput",
    "copy_card_search",
    "create_form_model",
    "infer_content_type",
]
