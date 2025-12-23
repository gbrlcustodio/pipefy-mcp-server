from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.

GET_PIPE_QUERY = gql(
    """
    query ($pipe_id: ID!) {
        pipe(id: $pipe_id) {
            id
            name
            phases {
                id
                name
            }
            labels {
                id
                name
            }
            start_form_fields {
                id
                label
                required
                type
                options
            }
        }
    }
    """
)

GET_START_FORM_FIELDS_QUERY = gql(
    """
    query ($pipe_id: ID!) {
        pipe(id: $pipe_id) {
            start_form_fields {
                id
                label
                type
                required
                editable
                options
                description
                help
            }
        }
    }
    """
)

SEARCH_PIPES_QUERY = gql(
    """
    {
        organizations {
            id
            name
            pipes {
                id
                name
                description
            }
        }
    }
    """
)
