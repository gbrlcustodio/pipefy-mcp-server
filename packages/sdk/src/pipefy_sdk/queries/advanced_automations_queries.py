"""GraphQL query for the advanced-automations (iPaaS) access token (Internal API endpoint).

Runs through the Internal API executor, which accepts a ``gql()`` query like
every other executor.
"""

from __future__ import annotations

from gql import gql

GET_ADVANCED_AUTOMATIONS_TOKEN_QUERY = gql("""
query GetAdvancedAutomationsToken($repoId: ID!) {
  advancedAutomationsToken(repoId: $repoId) {
    token
  }
}
""")

__all__ = ["GET_ADVANCED_AUTOMATIONS_TOKEN_QUERY"]
