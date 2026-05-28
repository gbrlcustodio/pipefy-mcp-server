"""GraphQL mutation strings for portal sub-portals (internal_api endpoint).

Mutations are plain strings (not ``gql()``) because ``InternalApiClient``
sends raw GraphQL text via JSON POST. See ``ai_automation_queries.py``.
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
