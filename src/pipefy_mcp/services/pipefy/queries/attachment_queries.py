"""GraphQL mutations for Pipefy attachment uploads (presigned URLs)."""

from __future__ import annotations

from gql import gql

__all__ = [
    "CREATE_PRESIGNED_URL_MUTATION",
]

CREATE_PRESIGNED_URL_MUTATION = gql(
    """
    mutation createPresignedUrl(
        $organizationId: ID!,
        $fileName: String!,
        $contentType: String,
        $contentLength: Int
    ) {
        createPresignedUrl(
            input: {
                organizationId: $organizationId,
                fileName: $fileName,
                contentType: $contentType,
                contentLength: $contentLength
            }
        ) {
            url
            downloadUrl
            clientMutationId
        }
    }
    """
)
