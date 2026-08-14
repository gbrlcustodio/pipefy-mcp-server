"""Tests for GraphQL document mutation detection."""

from pipefy_sdk.graphql_document import document_contains_mutation


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
