"""Tests for GraphQL document mutation detection."""

from pipefy_sdk.graphql_document import (
    document_contains_mutation,
    inspect_graphql_document,
)


def test_document_contains_mutation_detects_mutation():
    assert document_contains_mutation("mutation { __typename }") is True


def test_document_contains_mutation_rejects_query():
    assert document_contains_mutation("query { __typename }") is False


def test_document_contains_mutation_syntax_error_is_not_mutation():
    assert document_contains_mutation("not graphql {{{") is False


def test_document_contains_mutation_mixed_query_and_mutation():
    document = "query Q { __typename }\nmutation M { __typename }"
    assert document_contains_mutation(document) is True


def test_document_contains_mutation_rejects_subscription_only():
    assert document_contains_mutation("subscription { __typename }") is False


def test_inspect_syntax_error_is_not_too_nested():
    inspection = inspect_graphql_document("not graphql {{{")
    assert inspection.contains_mutation is False
    assert inspection.too_nested is False


def test_inspect_too_nested_document_is_not_a_mutation():
    nested = "{a" * 400 + "}" * 400
    inspection = inspect_graphql_document(nested)
    assert inspection.contains_mutation is False
    assert inspection.too_nested is True
    assert document_contains_mutation(nested) is False


def test_inspect_too_nested_mutation_is_not_a_mutation():
    nested = "mutation { " + "a { " * 400 + "x " + "} " * 401
    inspection = inspect_graphql_document(nested)
    assert inspection.contains_mutation is False
    assert inspection.too_nested is True


def test_mutation_descriptor_uses_operation_name():
    inspection = inspect_graphql_document(
        "mutation DeletePipe { deletePipe(id: 1) { id } }"
    )
    assert inspection.contains_mutation is True
    assert "DeletePipe" in inspection.mutation_descriptor


def test_mutation_descriptor_uses_root_field_when_unnamed():
    inspection = inspect_graphql_document("mutation { deletePipe(id: 1) { id } }")
    assert inspection.contains_mutation is True
    assert "deletePipe" in inspection.mutation_descriptor
    unnamed = inspect_graphql_document("mutation { deleteCard(id: 1) { id } }")
    assert inspection.mutation_descriptor != unnamed.mutation_descriptor
