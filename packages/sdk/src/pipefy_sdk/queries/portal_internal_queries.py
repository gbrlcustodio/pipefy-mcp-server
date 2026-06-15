"""GraphQL mutations for portal sub-portals (internal_api endpoint).

These run through ``InternalApiClient``, which accepts a ``gql()`` query like
every other client.
"""

from __future__ import annotations

from gql import gql

UPDATE_SUB_PORTAL_ELEMENT_MUTATION = gql("""
mutation UpdateSubPortalElement($input: UpdateSubPortalElementInput!) {
  updateSubPortalElement(input: $input) {
    success
  }
}
""")

DELETE_SUB_PORTAL_ELEMENT_MUTATION = gql("""
mutation DeleteSubPortalElement($input: DeleteSubPortalElementInput!) {
  deleteSubPortalElement(input: $input) {
    success
  }
}
""")

DELETE_SUB_PORTAL_INTERFACE_MUTATION = gql("""
mutation DeleteSubPortalInterface($input: DeleteSubPortalInterfaceInput!) {
  deleteSubPortalInterface(input: $input) {
    success
  }
}
""")

__all__ = [
    "DELETE_SUB_PORTAL_ELEMENT_MUTATION",
    "DELETE_SUB_PORTAL_INTERFACE_MUTATION",
    "UPDATE_SUB_PORTAL_ELEMENT_MUTATION",
]
