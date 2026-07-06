"""Pipefy GraphQL SDK: typed client, models, and service layer for Pipefy's APIs."""

from __future__ import annotations

__version__ = "0.3.0-alpha.1"

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
from pipefy_sdk.queries.observability_queries import (
    AUTOMATION_EVENT_IDS,
    AUTOMATION_EXECUTION_METRICS_PERIODS,
    AUTOMATION_SORT_BY,
    AUTOMATION_SORT_ORDER,
)
from pipefy_sdk.services.automation_graphql_types import (
    AutomationActionRow,
    AutomationEventRow,
    AutomationRuleRecord,
    AutomationRuleSummary,
)
from pipefy_sdk.services.observability_export_csv import download_bytes, stream_bytes
from pipefy_sdk.services.observability_service import (
    AUTOMATION_EXECUTION_METRICS_MAX_PAGE_SIZE,
)
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
    "AUTOMATION_EVENT_IDS",
    "AUTOMATION_EXECUTION_METRICS_MAX_PAGE_SIZE",
    "AUTOMATION_EXECUTION_METRICS_PERIODS",
    "AUTOMATION_SORT_BY",
    "AUTOMATION_SORT_ORDER",
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
    "infer_content_type",
    "stream_bytes",
]
