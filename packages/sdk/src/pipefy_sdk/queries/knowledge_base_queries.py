"""GraphQL operations for pipe-scoped AI knowledge bases (list + plain text CRUD).

All operations are pipe-scoped by ``pipeUuid`` (the pipe UUID, not the numeric
id). The list query returns every knowledge base item on a pipe (plain text,
documents, data lookups) as a plain ``[AiKnowledgeBase]`` list — there is no
Relay connection and no pagination. Plain-text create/update/delete are Relay
mutations that take a single ``input`` object.
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

__all__ = [
    "CREATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION",
    "DELETE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION",
    "GET_AI_KNOWLEDGE_BASES_QUERY",
    "GET_AI_KNOWLEDGE_BASE_PLAIN_TEXT_QUERY",
    "UPDATE_AI_KNOWLEDGE_BASE_PLAIN_TEXT_MUTATION",
]
