"""Detect mutation operations in a GraphQL document string."""

from __future__ import annotations

from graphql import GraphQLSyntaxError, parse
from graphql.language.ast import OperationDefinitionNode, OperationType


def document_contains_mutation(document: str) -> bool:
    """Return True when the document defines at least one mutation operation.

    Syntax errors are not treated as mutations, so CLI ``--yes`` is not required
    for a document that will fail to parse.

    Args:
        document: GraphQL document string (query, mutation, subscription, or mixed).
    """
    try:
        doc = parse(document)
    except GraphQLSyntaxError:
        return False
    for defn in doc.definitions:
        if (
            isinstance(defn, OperationDefinitionNode)
            and defn.operation == OperationType.MUTATION
        ):
            return True
    return False
