"""GraphQL queries and mutations for Pipefy observability: logs, usage stats, and exports."""

from __future__ import annotations

from gql import gql

# AiAgentLogConnection / AutomationLogConnection: nodes, pageInfo, totalCount.
# Usage queries: StatsDetailsConnection for per-item breakdowns.
# aiCreditUsageStats: PeriodFilter current_month | last_month | last_3_months.

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

_STATS_DETAILS_NODE = """
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
                }"""

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
            agents {"""
    + _STATS_DETAILS_NODE
    + """
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
            automations {"""
    + _STATS_DETAILS_NODE
    + """
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

# CreateAutomationJobsExportInput: organizationId (ID!), filter (PeriodFilter!), optional clientMutationId.

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
    "CREATE_AUTOMATION_JOBS_EXPORT_MUTATION",
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
