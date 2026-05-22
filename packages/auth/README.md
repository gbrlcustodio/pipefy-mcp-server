# pipefy-auth

Shared OAuth + keychain helpers for Pipefy CLI and MCP server.

## What lives here

- **`storage`** — keychain-backed `StoredSession` (one entry per `(issuer, client_id)` tuple, under the OS keychain service name `pipefy`).
- **`flow`** — OAuth 2.0 Authorization Code with PKCE login flow.
- **`refresh`** — refresh-token grant + eager pre-use freshness check (`ensure_fresh_session`).
- **`discovery`** — OIDC `.well-known/openid-configuration` fetch + validation.
- **`revoke`** — IdP-side token invalidation (RFC 7009).
- **`identity`** — `OidcClient` dataclass + the `DEFAULT_AUTH_CLIENT_ID` constant (the registered Keycloak public client_id).

## Consumers

- `pipefy-cli` builds an authenticated `PipefyClient` by reading the stored session and handing the bearer to the SDK.
- `pipefy-mcp-server` (planned, see issue #213) reads the same keychain entry so an MCP client launched per-user picks up the session without service-account env vars.
