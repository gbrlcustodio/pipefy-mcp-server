from __future__ import annotations

from gql import gql

# NOTE: Keep this module free of runtime logic. Only GraphQL operation constants.

INTROSPECT_TYPE_QUERY = gql(
    """
    query IntrospectType($typeName: String!) {
        __type(name: $typeName) {
            name
            kind
            description
            fields {
                name
                description
                type {
                    name
                    kind
                    ofType {
                        name
                        kind
                    }
                }
            }
            inputFields {
                name
                description
                type {
                    name
                    kind
                    ofType {
                        name
                        kind
                    }
                }
            }
            enumValues {
                name
                description
            }
        }
    }
    """
)

INTROSPECT_MUTATION_QUERY = gql(
    """
    query IntrospectMutationFields {
        __type(name: "Mutation") {
            fields {
                name
                description
                args {
                    name
                    type {
                        name
                        kind
                        ofType {
                            name
                            kind
                        }
                    }
                    defaultValue
                }
                type {
                    name
                    kind
                }
            }
        }
    }
    """
)

SCHEMA_TYPES_QUERY = gql(
    """
    query SchemaTypes {
        __schema {
            types {
                name
                kind
                description
            }
        }
    }
    """
)
