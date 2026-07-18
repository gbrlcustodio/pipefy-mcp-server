"""GraphQL operations for pipe-scoped AI knowledge bases (list, plain text, documents).

All operations are pipe-scoped by ``pipeUuid`` (the pipe UUID, not the numeric
id). The list query returns every knowledge base item on a pipe (plain text,
documents, data lookups) as a plain ``[AiKnowledgeBase]`` list — there is no
Relay connection and no pagination. Plain-text and document create/update/delete
are Relay mutations that take a single ``input`` object.

Documents are created from an already-uploaded PDF: the ``documentUrl`` is the
persistent download URL returned by the ``createPresignedUrl`` mutation (in
``attachment_queries``) after the bytes are PUT to its presigned upload URL. The
presigned request needs the pipe's organization, resolved from the pipe UUID via
:data:`GET_PIPE_ORGANIZATION_QUERY`.
"""

from __future__ import annotations

from gql import gql

# aiKnowledgeBases(pipeUuid) returns a plain list (not a connection). Each node
# is one data source; `type` is the JSON:API resource type (e.g.
# `knowledge_base_plain_texts`, `knowledge_base_documents`, `data_lookups`).
GET_AI_KNOWLEDGE_BASES_QUERY = gql(
    """
    query aiKnowledgeBases($pipeUuid: ID!) {
        aiKnowledgeBases(pipeUuid: $pipeUuid) {
            id
            type
            name
            description
            updatedAt
        }
    }
    """
)

GET_AI_KNOWLEDGE_BASE_PLAIN_TEXT_QUERY = gql(
    """
    query aiKnowledgeBasePlainText($id: ID!, $pipeUuid: ID!) {
        aiKnowledgeBasePlainText(id: $id, pipeUuid: $pipeUuid) {
            id
            name
            description
            content
            updatedAt
        }
    }
    """
)

CREATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION = gql(
    """
    mutation createAiKnowledgeBasePlainText(
        $input: CreateKnowledgeBasePlainTextInput!
    ) {
        createAiKnowledgeBasePlainText(input: $input) {
            knowledgeBasePlainText {
                id
                name
                description
                content
                updatedAt
            }
        }
    }
    """
)

UPDATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION = gql(
    """
    mutation updateAiKnowledgeBasePlainText(
        $input: UpdateKnowledgeBasePlainTextInput!
    ) {
        updateAiKnowledgeBasePlainText(input: $input) {
            knowledgeBasePlainText {
                id
                name
                description
                content
                updatedAt
            }
        }
    }
    """
)

DELETE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION = gql(
    """
    mutation deleteAiKnowledgeBasePlainText(
        $input: DeleteKnowledgeBasePlainTextInput!
    ) {
        deleteAiKnowledgeBasePlainText(input: $input) {
            success
            errors
        }
    }
    """
)

# Resolves the organization that owns a pipe from the pipe UUID. The document
# upload flow needs an organization id for the presigned URL, but the tools are
# pipe-scoped, so the id is derived here rather than asked of the caller. The
# ``pipe`` root field accepts the pipe UUID as its ``id`` argument.
GET_PIPE_ORGANIZATION_QUERY = gql(
    """
    query pipeOrganization($id: ID!) {
        pipe(id: $id) {
            organization {
                id
                uuid
            }
        }
    }
    """
)

GET_AI_KNOWLEDGE_BASE_DOCUMENT_QUERY = gql(
    """
    query aiKnowledgeBaseDocument($id: ID!, $pipeUuid: ID!) {
        aiKnowledgeBaseDocument(id: $id, pipeUuid: $pipeUuid) {
            id
            name
            description
            content
            updatedAt
        }
    }
    """
)

CREATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION = gql(
    """
    mutation createAiKnowledgeBaseDocument(
        $input: CreateKnowledgeBaseDocumentInput!
    ) {
        createAiKnowledgeBaseDocument(input: $input) {
            knowledgeBaseDocument {
                id
                name
                description
                content
                updatedAt
            }
        }
    }
    """
)

UPDATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION = gql(
    """
    mutation updateAiKnowledgeBaseDocument(
        $input: UpdateKnowledgeBaseDocumentInput!
    ) {
        updateAiKnowledgeBaseDocument(input: $input) {
            knowledgeBaseDocument {
                id
                name
                description
                content
                updatedAt
            }
        }
    }
    """
)

DELETE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION = gql(
    """
    mutation deleteAiKnowledgeBaseDocument(
        $input: DeleteKnowledgeBaseDocumentInput!
    ) {
        deleteAiKnowledgeBaseDocument(input: $input) {
            success
            errors
        }
    }
    """
)

__all__ = [
    "CREATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION",
    "CREATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION",
    "DELETE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION",
    "DELETE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION",
    "GET_AI_KNOWLEDGE_BASES_QUERY",
    "GET_AI_KNOWLEDGE_BASE_DOCUMENT_QUERY",
    "GET_AI_KNOWLEDGE_BASE_PLAIN_TEXT_QUERY",
    "GET_PIPE_ORGANIZATION_QUERY",
    "UPDATE_AI_KNOWLEDGE_BASE_DOCUMENT_MUTATION",
    "UPDATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION",
]
