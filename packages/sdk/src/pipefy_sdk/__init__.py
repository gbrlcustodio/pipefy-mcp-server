"""Pipefy GraphQL SDK: typed client, models, and service layer for Pipefy's APIs."""

from __future__ import annotations

__version__ = "0.2.0-beta.3"

from pipefy_sdk.client import PipefyClient
from pipefy_sdk.exceptions import PipefyAPIError, PipefyError
from pipefy_sdk.models import (
    Attachment,
    AttachmentTarget,
    AttachmentUploadError,
    AttachmentUploadResult,
    AttachmentUploadStep,
    AutomationConditionInput,
    AutomationEventParamsInput,
    BehaviorInput,
    CardTarget,
    CommentInput,
    CreateAiAgentInput,
    CreateAiAutomationInput,
    CreatePortalElementInput,
    CreateSendTaskAutomationInput,
    DeleteCommentInput,
    MemberInvite,
    NonBlankStr,
    PipefyId,
    TableRecordTarget,
    UpdateAiAgentInput,
    UpdateAiAutomationInput,
    UpdateCommentInput,
    UpdatePortalElementInput,
    UploadAttachmentToCardInput,
    UploadAttachmentToTableRecordInput,
    infer_content_type,
)
from pipefy_sdk.models.form import create_form_model
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
    "Attachment",
    "AttachmentTarget",
    "AttachmentUploadError",
    "AttachmentUploadResult",
    "AttachmentUploadStep",
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
    "CardTarget",
    "CommentInput",
    "CreateAiAgentInput",
    "CreateAiAutomationInput",
    "CreatePortalElementInput",
    "CreateSendTaskAutomationInput",
    "DeleteCommentInput",
    "download_bytes",
    "InternalApiClient",
    "MePayload",
    "MemberInvite",
    "NonBlankStr",
    "PipefyAPIError",
    "PipefyClient",
    "PipefyError",
    "PipefyId",
    "PipefySettings",
    "TableRecordTarget",
    "UpdateAiAgentInput",
    "UpdateAiAutomationInput",
    "UpdateCommentInput",
    "UpdatePortalElementInput",
    "UploadAttachmentToCardInput",
    "UploadAttachmentToTableRecordInput",
    "copy_card_search",
    "create_form_model",
    "format_service_account_removal_block_message",
    "infer_content_type",
    "service_account_removal_blocked_user_ids",
    "stream_bytes",
]
