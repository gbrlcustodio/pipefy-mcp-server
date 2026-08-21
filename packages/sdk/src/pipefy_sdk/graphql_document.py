"""Detect mutation operations in a GraphQL document string."""

from __future__ import annotations

from dataclasses import dataclass

from graphql import GraphQLSyntaxError, parse
from graphql.language.ast import (
    DocumentNode,
    FieldNode,
    OperationDefinitionNode,
    OperationType,
)

_FALLBACK_MUTATION_DESCRIPTOR = "GraphQL mutation"


@dataclass(frozen=True)
class GraphqlDocumentInspection:
    contains_mutation: bool
    mutation_descriptor: str
    too_nested: bool = False


def inspect_graphql_document(document: str) -> GraphqlDocumentInspection:
    """Parse ``document`` once for mutation detection and preview naming.

    Two unparseable documents are reported differently, on purpose. A syntax
    error is invalid everywhere, so the API rejects it too and callers may send
    it: it cannot turn out to be a mutation that runs unconfirmed. A document
    that exhausts the parser's recursion is only unparseable *here*, and the
    API may well accept it, so it comes back with ``too_nested`` set and callers
    refuse it rather than send a document they could not classify.

    The recursion ceiling is whatever stack headroom is left when this runs, not
    a fixed nesting depth. Measurements put it near 246 levels called directly
    and near 232 through the MCP tool path, dropping by roughly one level per
    four frames already on the stack. So the same document can classify one way
    from the CLI and another from a server with deeper middleware, and neither
    result is wrong. Callers must treat ``too_nested`` as a refusal to judge,
    never as a property of the document.
    """
    try:
        doc = parse(document)
    except GraphQLSyntaxError:
        return GraphqlDocumentInspection(
            contains_mutation=False,
            mutation_descriptor=_FALLBACK_MUTATION_DESCRIPTOR,
        )
    except RecursionError:
        return GraphqlDocumentInspection(
            contains_mutation=False,
            mutation_descriptor=_FALLBACK_MUTATION_DESCRIPTOR,
            too_nested=True,
        )
    return GraphqlDocumentInspection(
        contains_mutation=_document_defines_mutation(doc),
        mutation_descriptor=_mutation_descriptor(doc),
    )


def document_contains_mutation(document: str) -> bool:
    """Return True when the document defines at least one mutation operation.

    Syntax errors and documents too nested to parse are not treated as
    mutations, so CLI ``--yes`` is not required for a document that will fail
    to parse.
    """
    return inspect_graphql_document(document).contains_mutation


def _document_defines_mutation(doc: DocumentNode) -> bool:
    for defn in doc.definitions:
        if (
            isinstance(defn, OperationDefinitionNode)
            and defn.operation == OperationType.MUTATION
        ):
            return True
    return False


def _mutation_descriptor(doc: DocumentNode) -> str:
    for defn in doc.definitions:
        if not isinstance(defn, OperationDefinitionNode):
            continue
        if defn.operation != OperationType.MUTATION:
            continue
        return f"{_FALLBACK_MUTATION_DESCRIPTOR} {_mutation_operation_name(defn)}"
    return _FALLBACK_MUTATION_DESCRIPTOR


def _mutation_operation_name(defn: OperationDefinitionNode) -> str:
    if defn.name is not None:
        return defn.name.value
    for selection in defn.selection_set.selections:
        if isinstance(selection, FieldNode):
            return selection.name.value
    return "operation"
