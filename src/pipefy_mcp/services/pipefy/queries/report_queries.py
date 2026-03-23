"""GraphQL queries and mutations for Pipefy pipe and organization reports."""

from __future__ import annotations

from gql import gql

# Column/filter discovery uses field `name` (not `id`). pipeReports omits cardCount (resolver errors).

_PIPE_REPORT_FIELDS = """
    id
    name
    color
    fields
    filter
    sortBy {
        direction
        field
    }
    createdAt
    lastUpdatedAt"""

_REPORT_EXPORT_FIELDS = """
    id
    state
    fileURL
    startedAt
    finishedAt
    requestedBy {
        id
        name
    }"""

GET_PIPE_REPORTS_QUERY = gql(
    """
    query pipeReports($pipeUuid: String!, $first: Int, $after: String, $search: String, $reportId: ID, $order: PipeReportsOrder) {
        pipeReports(pipeUuid: $pipeUuid, first: $first, after: $after, search: $search, reportId: $reportId, order: $order) {
            edges {
                node {"""
    + _PIPE_REPORT_FIELDS
    + """
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
)

GET_PIPE_REPORT_COLUMNS_QUERY = gql(
    """
    query pipeReportColumns($pipeUuid: String!) {
        pipeReportColumns(pipeUuid: $pipeUuid) {
            name
            label
            type
            visible
            archived
            options {
                id
                name
            }
        }
    }
    """
)

GET_PIPE_REPORT_FILTERABLE_FIELDS_QUERY = gql(
    """
    query pipeReportFilterableFields($pipeUuid: String!) {
        pipeReportFilterableFields(pipeUuid: $pipeUuid) {
            title
            list {
                label
                list {
                    name
                    label
                    type
                    options {
                        id
                        name
                    }
                }
            }
        }
    }
    """
)

GET_ORGANIZATION_REPORT_QUERY = gql(
    """
    query organizationReport($id: ID!) {
        organizationReport(id: $id) {
            id
            name
            cardCount
            color
            fields
            filter
            repos {
                id
                name
            }
            sortBy {
                direction
                field
            }
            createdAt
            lastUpdatedAt
        }
    }
    """
)

GET_ORGANIZATION_REPORTS_QUERY = gql(
    """
    query organizationReports($organizationId: ID!, $first: Int, $after: String) {
        organizationReports(organizationId: $organizationId, first: $first, after: $after) {
            edges {
                node {
                    id
                    name
                    cardCount
                    color
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
)

GET_PIPE_REPORT_EXPORT_QUERY = gql(
    """
    query pipeReportExport($id: ID!) {
        pipeReportExport(id: $id) {"""
    + _REPORT_EXPORT_FIELDS
    + """
        }
    }
    """
)

GET_ORGANIZATION_REPORT_EXPORT_QUERY = gql(
    """
    query organizationReportExport($id: ID!) {
        organizationReportExport(id: $id) {"""
    + _REPORT_EXPORT_FIELDS
    + """
        }
    }
    """
)

CREATE_PIPE_REPORT_MUTATION = gql(
    """
    mutation createPipeReport($input: CreatePipeReportInput!) {
        createPipeReport(input: $input) {
            pipeReport {
                id
                name
            }
        }
    }
    """
)

UPDATE_PIPE_REPORT_MUTATION = gql(
    """
    mutation updatePipeReport($input: UpdatePipeReportInput!) {
        updatePipeReport(input: $input) {
            pipeReport {
                id
                name
            }
        }
    }
    """
)

DELETE_PIPE_REPORT_MUTATION = gql(
    """
    mutation deletePipeReport($input: DeletePipeReportInput!) {
        deletePipeReport(input: $input) {
            success
        }
    }
    """
)

CREATE_ORGANIZATION_REPORT_MUTATION = gql(
    """
    mutation createOrganizationReport($input: CreateOrganizationReportInput!) {
        createOrganizationReport(input: $input) {
            organizationReport {
                id
                name
            }
        }
    }
    """
)

UPDATE_ORGANIZATION_REPORT_MUTATION = gql(
    """
    mutation updateOrganizationReport($input: UpdateOrganizationReportInput!) {
        updateOrganizationReport(input: $input) {
            organizationReport {
                id
                name
            }
        }
    }
    """
)

DELETE_ORGANIZATION_REPORT_MUTATION = gql(
    """
    mutation deleteOrganizationReport($input: DeleteOrganizationReportInput!) {
        deleteOrganizationReport(input: $input) {
            success
        }
    }
    """
)

EXPORT_PIPE_REPORT_MUTATION = gql(
    """
    mutation exportPipeReport($input: ExportPipeReportInput!) {
        exportPipeReport(input: $input) {
            pipeReportExport {
                id
                state
            }
        }
    }
    """
)

EXPORT_ORGANIZATION_REPORT_MUTATION = gql(
    """
    mutation exportOrganizationReport($input: ExportOrganizationReportInput!) {
        exportOrganizationReport(input: $input) {
            organizationReportExport {
                id
                state
            }
        }
    }
    """
)

EXPORT_PIPE_AUDIT_LOGS_MUTATION = gql(
    """
    mutation exportPipeAuditLogsReport($input: ExportPipeAuditLogsReportInput!) {
        exportPipeAuditLogsReport(input: $input) {
            success
        }
    }
    """
)

__all__ = [
    "CREATE_ORGANIZATION_REPORT_MUTATION",
    "CREATE_PIPE_REPORT_MUTATION",
    "DELETE_ORGANIZATION_REPORT_MUTATION",
    "DELETE_PIPE_REPORT_MUTATION",
    "EXPORT_ORGANIZATION_REPORT_MUTATION",
    "EXPORT_PIPE_AUDIT_LOGS_MUTATION",
    "EXPORT_PIPE_REPORT_MUTATION",
    "GET_ORGANIZATION_REPORT_EXPORT_QUERY",
    "GET_ORGANIZATION_REPORT_QUERY",
    "GET_ORGANIZATION_REPORTS_QUERY",
    "GET_PIPE_REPORT_COLUMNS_QUERY",
    "GET_PIPE_REPORT_EXPORT_QUERY",
    "GET_PIPE_REPORT_FILTERABLE_FIELDS_QUERY",
    "GET_PIPE_REPORTS_QUERY",
    "UPDATE_ORGANIZATION_REPORT_MUTATION",
    "UPDATE_PIPE_REPORT_MUTATION",
]
