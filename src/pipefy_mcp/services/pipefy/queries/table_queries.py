"""GraphQL queries and mutations for Pipefy database tables, records, and fields."""

from __future__ import annotations

from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.

GET_TABLE_QUERY = gql(
    """
    query GetTable($id: ID!) {
        table(id: $id) {
            id
            name
            description
            table_fields {
                id
                label
                type
                required
                options
            }
            authorization
        }
    }
    """
)

GET_TABLES_QUERY = gql(
    """
    query GetTables($ids: [ID!]!) {
        tables(ids: $ids) {
            id
            name
            description
            table_fields {
                id
                label
                type
                required
                options
            }
            authorization
        }
    }
    """
)

GET_TABLE_RECORDS_QUERY = gql(
    """
    query GetTableRecords($tableId: ID!, $first: Int, $after: String) {
        table_records(table_id: $tableId, first: $first, after: $after) {
            edges {
                node {
                    id
                    title
                    record_fields {
                        name
                        value
                    }
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

GET_TABLE_RECORD_QUERY = gql(
    """
    query GetTableRecord($id: ID!) {
        table_record(id: $id) {
            id
            title
            record_fields {
                name
                value
            }
        }
    }
    """
)

FIND_RECORDS_QUERY = gql(
    """
    query FindRecords(
        $tableId: String!
        $fieldId: String!
        $fieldValue: String!
        $first: Int
        $after: String
    ) {
        findRecords(
            tableId: $tableId
            search: { fieldId: $fieldId, fieldValue: $fieldValue }
            first: $first
            after: $after
        ) {
            edges {
                node {
                    id
                    title
                    fields {
                        name
                        value
                    }
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

CREATE_TABLE_MUTATION = gql(
    """
    mutation CreateTable($input: CreateTableInput!) {
        createTable(input: $input) {
            table {
                id
                name
            }
        }
    }
    """
)

UPDATE_TABLE_MUTATION = gql(
    """
    mutation UpdateTable($input: UpdateTableInput!) {
        updateTable(input: $input) {
            table {
                id
                name
            }
        }
    }
    """
)

DELETE_TABLE_MUTATION = gql(
    """
    mutation DeleteTable($input: DeleteTableInput!) {
        deleteTable(input: $input) {
            success
        }
    }
    """
)

CREATE_TABLE_RECORD_MUTATION = gql(
    """
    mutation CreateTableRecord($input: CreateTableRecordInput!) {
        createTableRecord(input: $input) {
            table_record {
                id
                title
            }
        }
    }
    """
)

UPDATE_TABLE_RECORD_MUTATION = gql(
    """
    mutation UpdateTableRecord($input: UpdateTableRecordInput!) {
        updateTableRecord(input: $input) {
            table_record {
                id
                title
            }
        }
    }
    """
)

DELETE_TABLE_RECORD_MUTATION = gql(
    """
    mutation DeleteTableRecord($input: DeleteTableRecordInput!) {
        deleteTableRecord(input: $input) {
            success
        }
    }
    """
)

SET_TABLE_RECORD_FIELD_VALUE_MUTATION = gql(
    """
    mutation SetTableRecordFieldValue($input: SetTableRecordFieldValueInput!) {
        setTableRecordFieldValue(input: $input) {
            table_record {
                id
                title
            }
            table_record_field {
                name
                value
            }
        }
    }
    """
)

CREATE_TABLE_FIELD_MUTATION = gql(
    """
    mutation CreateTableField($input: CreateTableFieldInput!) {
        createTableField(input: $input) {
            table_field {
                id
                label
                type
            }
        }
    }
    """
)

UPDATE_TABLE_FIELD_MUTATION = gql(
    """
    mutation UpdateTableField($input: UpdateTableFieldInput!) {
        updateTableField(input: $input) {
            table_field {
                id
                label
                type
            }
        }
    }
    """
)

DELETE_TABLE_FIELD_MUTATION = gql(
    """
    mutation DeleteTableField($input: DeleteTableFieldInput!) {
        deleteTableField(input: $input) {
            success
        }
    }
    """
)

__all__ = [
    "CREATE_TABLE_FIELD_MUTATION",
    "CREATE_TABLE_MUTATION",
    "CREATE_TABLE_RECORD_MUTATION",
    "DELETE_TABLE_FIELD_MUTATION",
    "DELETE_TABLE_MUTATION",
    "DELETE_TABLE_RECORD_MUTATION",
    "FIND_RECORDS_QUERY",
    "GET_TABLE_QUERY",
    "GET_TABLE_RECORDS_QUERY",
    "GET_TABLE_RECORD_QUERY",
    "GET_TABLES_QUERY",
    "SET_TABLE_RECORD_FIELD_VALUE_MUTATION",
    "UPDATE_TABLE_FIELD_MUTATION",
    "UPDATE_TABLE_MUTATION",
    "UPDATE_TABLE_RECORD_MUTATION",
]
