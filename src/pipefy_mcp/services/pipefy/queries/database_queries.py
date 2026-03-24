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
        }
    }
    """
)

GET_TABLE_RECORDS_QUERY = gql(
    """
    query GetTableRecords($table_id: ID!, $first: Int, $after: String) {
        table_records(table_id: $table_id, first: $first, after: $after) {
            totalCount
            nodes {
                id
                title
                created_at
                updated_at
                status { id name }
                record_fields {
                    name
                    value
                    array_value
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
            created_at
            updated_at
            status { id name }
            record_fields {
                name
                value
                array_value
            }
        }
    }
    """
)

SEARCH_TABLES_QUERY = gql(
    """
    {
        organizations {
            id
            name
            tables {
                nodes {
                    id
                    name
                    description
                }
            }
        }
    }
    """
)
