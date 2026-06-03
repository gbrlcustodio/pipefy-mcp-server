"""GraphQL mutation strings for portal sub-portals (internal_api endpoint).

Mutations are plain strings (not ``gql()``) because
``InternalApiClient.execute_query`` takes a raw string and parses it with
``gql()`` itself before sending, unlike the public client which expects an
already-parsed ``DocumentNode``.
"""

from __future__ import annotations

UPDATE_SUB_PORTAL_ELEMENT_MUTATION = """
mutation UpdateSubPortalElement($input: UpdateSubPortalElementInput!) {
  updateSubPortalElement(input: $input) {
    success
  }
}
"""

DELETE_SUB_PORTAL_ELEMENT_MUTATION = """
mutation DeleteSubPortalElement($input: DeleteSubPortalElementInput!) {
  deleteSubPortalElement(input: $input) {
    success
  }
}
"""

DELETE_SUB_PORTAL_INTERFACE_MUTATION = """
mutation DeleteSubPortalInterface($input: DeleteSubPortalInterfaceInput!) {
  deleteSubPortalInterface(input: $input) {
    success
  }
}
"""

__all__ = [
    "DELETE_SUB_PORTAL_ELEMENT_MUTATION",
    "DELETE_SUB_PORTAL_INTERFACE_MUTATION",
    "UPDATE_SUB_PORTAL_ELEMENT_MUTATION",
]
