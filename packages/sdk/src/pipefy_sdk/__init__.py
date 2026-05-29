"""Pipefy GraphQL SDK: typed client, models, and service layer for Pipefy's APIs."""

from __future__ import annotations

__version__ = "0.2.0-beta.1"

from pipefy_sdk.attachment import Attachment
from pipefy_sdk.client import PipefyClient
from pipefy_sdk.exceptions import PipefyAPIError, PipefyError
from pipefy_sdk.models import (
    MAX_ATTACHMENT_SIZE_BYTES,
    AutomationConditionInput,
    AutomationEventParamsInput,
    BehaviorInput,
    CommentInput,
    CreateAiAgentInput,
    CreateAiAutomationInput,
    CreatePortalElementInput,
    CreateSendTaskAutomationInput,
    DeleteCommentInput,
    MemberInvite,
    NonBlankStr,
    PipefyId,
    UpdateAiAgentInput,
    UpdateAiAutomationInput,
    UpdateCommentInput,
    UpdatePortalElementInput,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    assert_attachment_size_within_cap,
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
from pipefy_sdk.services.member_service import (
    format_service_account_removal_block_message,
    service_account_removal_blocked_user_ids,
)
from pipefy_sdk.services.observability_export_csv import download_bytes, stream_bytes
from pipefy_sdk.services.table_service import (
    UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS,
    UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE,
)
from pipefy_sdk.services.types import (
    AiAgentGraphPayload,
    CardSearch,
    MePayload,
    copy_card_search,
)
from pipefy_sdk.settings import PipefySettings

__all__ = [
    "__version__",
    "AiAgentGraphPayload",
    "AiAutomationService",
    "Attachment",
    "UPDATE_TABLE_RECORD_ALLOWED_FIELD_KEYS",
    "UPDATE_TABLE_RECORD_FIELDS_ERROR_MESSAGE",
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
    "CreatePortalElementInput",
    "CreateSendTaskAutomationInput",
    "DeleteCommentInput",
    "download_bytes",
    "InternalApiClient",
    "MAX_ATTACHMENT_SIZE_BYTES",
    "MePayload",
    "MemberInvite",
    "NonBlankStr",
    "PipefyAPIError",
    "PipefyClient",
    "PipefyError",
    "PipefyId",
    "PipefySettings",
    "UpdateAiAgentInput",
    "UpdateAiAutomationInput",
    "UpdateCommentInput",
    "UpdatePortalElementInput",
    "UploadAttachmentToCardInput",
    "UploadAttachmentToTableRecordInput",
    "assert_attachment_size_within_cap",
    "copy_card_search",
    "create_form_model",
    "format_service_account_removal_block_message",
    "infer_content_type",
    "service_account_removal_blocked_user_ids",
    "stream_bytes",
]
