"""GraphQL queries and mutations for Pipefy observability: logs, usage stats, and exports.

AiAgentLogConnection / AutomationLogConnection: nodes, pageInfo, totalCount. Usage breakdowns use
StatsDetailsConnection. ``aiCreditUsageStats`` accepts PeriodFilter: current_month | last_month |
last_3_months. ``CreateAutomationJobsExportInput``: organizationId (ID!), filter (PeriodFilter!),
optional clientMutationId.
"""

from __future__ import annotations

from gql import gql

GET_AI_AGENT_LOGS_QUERY = gql(
    """
    query AiAgentLogsByRepo(
        $repoUuid: ID!
        $first: Int
        $after: String
        $status: AiAgentLogStatus
        $searchTerm: String
    ) {
        aiAgentLogsByRepo(
            repoUuid: $repoUuid
            first: $first
            after: $after
            status: $status
            searchTerm: $searchTerm
        ) {
            nodes {
                uuid
                agentUuid
                agentName
                automationId
                automationName
                cardId
                cardTitle
                status
                createdAt
                updatedAt
            }
            pageInfo {
                hasNextPage
                endCursor
            }
            totalCount
        }
    }
    """
)

GET_AI_AGENT_LOG_DETAILS_QUERY = gql(
    """
    query AiAgentLogDetails($uuid: ID!) {
        aiAgentLogDetails(uuid: $uuid) {
            uuid
            agentUuid
            agentName
            automation {
                id
                name
            }
            cardId
            cardTitle
            status
            executionTime
            createdAt
            finishedAt
            tracingNodes {
                nodeName
                status
                message
            }
        }
    }
    """
)

GET_AUTOMATION_LOGS_QUERY = gql(
    """
    query AutomationLogs(
        $automationId: ID!
        $first: Int
        $after: String
        $status: AutomationLogStatus
        $searchTerm: String
    ) {
        automationLogs(
            automationId: $automationId
            first: $first
            after: $after
            status: $status
            searchTerm: $searchTerm
        ) {
            nodes {
                uuid
                automationId
                automationName
                cardId
                cardTitle
                datetime
                status
            }
            pageInfo {
                hasNextPage
                endCursor
            }
            totalCount
        }
    }
    """
)

GET_AUTOMATION_LOGS_BY_REPO_QUERY = gql(
    """
    query AutomationLogsByRepo(
        $repoId: ID!
        $first: Int
        $after: String
        $status: AutomationLogStatus
        $searchTerm: String
    ) {
        automationLogsByRepo(
            repoId: $repoId
            first: $first
            after: $after
            status: $status
            searchTerm: $searchTerm
        ) {
            nodes {
                uuid
                automationId
                automationName
                cardId
                cardTitle
                datetime
                status
            }
            pageInfo {
                hasNextPage
                endCursor
            }
            totalCount
        }
    }
    """
)

GET_AGENTS_USAGE_QUERY = gql(
    """
    query AgentsUsageDetails(
        $organizationUuid: ID!
        $filterDate: DateRange!
        $filters: FilterParams
        $search: String
        $sort: SortCriteria
    ) {
        agentsUsageDetails(
            organizationUuid: $organizationUuid
            filterDate: $filterDate
            filters: $filters
            search: $search
            sort: $sort
        ) {
            usage
            agents {
                nodes {
                    id
                    name
                    usage
                    status
                    action
                    event
                    actionRepo {
                        uuid
                        name
                    }
                    eventRepo {
                        uuid
                        name
                    }
                    createdAt
                    updatedAt
                }
                totalCount
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
    }
    """
)

GET_AUTOMATIONS_USAGE_QUERY = gql(
    """
    query AutomationsUsageDetails(
        $organizationUuid: ID!
        $filterDate: DateRange!
        $filters: FilterParams
        $search: String
        $sort: SortCriteria
    ) {
        automationsUsageDetails(
            organizationUuid: $organizationUuid
            filterDate: $filterDate
            filters: $filters
            search: $search
            sort: $sort
        ) {
            usage
            automations {
                nodes {
                    id
                    name
                    usage
                    status
                    action
                    event
                    actionRepo {
                        uuid
                        name
                    }
                    eventRepo {
                        uuid
                        name
                    }
                    createdAt
                    updatedAt
                }
                totalCount
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
    }
    """
)

AUTOMATION_EXECUTION_METRICS_PERIODS: tuple[str, ...] = (
    "FIFTEEN_MINUTES",
    "SIXTY_MINUTES",
    "TWELVE_HOURS",
    "TWENTY_FOUR_HOURS",
)

# AutomationsEvents enum values accepted by the `automations` query's `eventId`
# filter. Single source so the MCP validation set and CLI help stay in step with
# the schema instead of drifting across hand-copied prose.
AUTOMATION_EVENT_IDS: tuple[str, ...] = (
    "card_moved",
    "field_updated",
    "card_created",
    "scheduler",
    "sla_based",
    "card_left_phase",
    "card_inbox_received_email",
    "all_children_in_phase",
    "http_response_received",
    "manually_triggered",
)

# AutomationSortCriteria fields: `by` (AutomationSortBy) and `order` (SortDirection).
AUTOMATION_SORT_BY: tuple[str, ...] = ("created_at", "name")
AUTOMATION_SORT_ORDER: tuple[str, ...] = ("asc", "desc")

GET_AUTOMATION_EXECUTION_METRICS_QUERY = gql(
    """
    query AutomationExecutionMetrics(
        $organizationId: ID!
        $repoId: ID
        $automationIds: [ID!]
        $actionIds: [ID!]
        $eventId: AutomationsEvents
        $active: Boolean
        $search: String
        $sort: AutomationSortCriteria
        $period: AutomationExecutionMetricsPeriod
        $first: Int
        $after: String
    ) {
        automations(
            organizationId: $organizationId
            repoId: $repoId
            automationIds: $automationIds
            actionIds: $actionIds
            eventId: $eventId
            active: $active
            search: $search
            sort: $sort
            first: $first
            after: $after
        ) {
            pageInfo {
                hasNextPage
                endCursor
            }
            edges {
                node {
                    id
                    name
                    event_id
                    action_id
                    event_repo {
                        id
                        name
                    }
                    executionMetrics(period: $period) {
                        lastRun
                        failureRate
                        successRate
                        averageDuration
                        totalRuns
                    }
                }
            }
        }
    }
    """
)

RESOLVE_ORGANIZATION_UUID_QUERY = gql(
    """
    query ResolveOrganizationUuid($id: ID!) {
        organization(id: $id) {
            uuid
        }
    }
    """
)

GET_AI_CREDIT_USAGE_QUERY = gql(
    """
    query AiCreditUsageStats($organizationUuid: ID!, $period: PeriodFilter!) {
        aiCreditUsageStats(organizationUuid: $organizationUuid, period: $period) {
            active
            usage
            limit
            hasAddon
            updatedAt
            aiAutomation {
                enabled
                usage
            }
            assistants {
                enabled
                usage
            }
            freeAiCredit {
                limit
                usage
            }
            filterDate {
                from
                to
            }
        }
    }
    """
)

CREATE_AUTOMATION_JOBS_EXPORT_MUTATION = gql(
    """
    mutation CreateAutomationJobsExport($input: CreateAutomationJobsExportInput!) {
        createAutomationJobsExport(input: $input) {
            automationJobsExport {
                id
                status
                fileUrl
            }
        }
    }
    """
)

GET_AUTOMATION_JOBS_EXPORT_QUERY = gql(
    """
    query AutomationJobsExport($id: ID!) {
        automationJobsExport(id: $id) {
            id
            status
            fileUrl
        }
    }
    """
)

__all__ = [
    "AUTOMATION_EVENT_IDS",
    "AUTOMATION_EXECUTION_METRICS_PERIODS",
    "AUTOMATION_SORT_BY",
    "AUTOMATION_SORT_ORDER",
    "CREATE_AUTOMATION_JOBS_EXPORT_MUTATION",
    "GET_AUTOMATION_EXECUTION_METRICS_QUERY",
    "GET_AUTOMATION_JOBS_EXPORT_QUERY",
    "GET_AGENTS_USAGE_QUERY",
    "GET_AI_AGENT_LOG_DETAILS_QUERY",
    "GET_AI_AGENT_LOGS_QUERY",
    "GET_AI_CREDIT_USAGE_QUERY",
    "GET_AUTOMATION_LOGS_BY_REPO_QUERY",
    "GET_AUTOMATION_LOGS_QUERY",
    "GET_AUTOMATIONS_USAGE_QUERY",
    "RESOLVE_ORGANIZATION_UUID_QUERY",
]
