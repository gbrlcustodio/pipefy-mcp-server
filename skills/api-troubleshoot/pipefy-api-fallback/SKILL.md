---
name: pipefy-api-fallback
description: >
  Use this skill when an MCP tool fails AND the introspection skill could
  not resolve the problem. This is the last-resort fallback (Tier 3):
  call the Pipefy GraphQL API directly using curl or httpx, authenticating
  with the Service Account (OAuth2) or a Personal Access Token (PAT)
  available as env var. Follow the 3-tier resolution strategy before
  reaching this point.
tags: [pipefy, graphql, api, fallback, troubleshooting, curl]
---

# Pipefy API Fallback (Tier 3 — Last Resort)

This skill activates only after Tiers 1 and 2 have failed. Call the Pipefy GraphQL API directly, bypassing the MCP server.

---

## 3-tier resolution strategy (always follow in order)

| Tier | Method | When |
|------|--------|------|
| **1** | Dedicated MCP tool (`create_card`, `update_pipe`, etc.) | Always try first. |
| **2** | Introspection + `execute_graphql` | When no dedicated tool exists or a tool fails unexpectedly. See `skills/introspection/`. |
| **3** | Direct HTTP via curl / httpx (this skill) | When the MCP server itself is unavailable, or `execute_graphql` fails with an infrastructure error. |

**Do not jump to Tier 3 after a single tool failure.** Follow the tiers in order.

---

## Authentication

Two options (use whichever is available in the environment):

**Option A — OAuth2 Client Credentials:**

```bash
TOKEN=$(curl -s -X POST "$PIPEFY_OAUTH_URL" \
  -d "grant_type=client_credentials" \
  -d "client_id=$PIPEFY_OAUTH_CLIENT" \
  -d "client_secret=$PIPEFY_OAUTH_SECRET" | jq -r .access_token)
```

**Option B — Personal Access Token (PAT):**

```bash
TOKEN="$PIPEFY_TOKEN"
```

---

## Execute a GraphQL query

```bash
curl -s -X POST "$PIPEFY_GRAPHQL_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ me { id name } }"}' | jq .
```

## Execute a GraphQL mutation

```bash
curl -s -X POST "$PIPEFY_GRAPHQL_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation CreateCard($input: CreateCardInput!) { createCard(input: $input) { card { id } } }",
    "variables": {
      "input": {
        "pipe_id": 67890,
        "title": "Fallback Card"
      }
    }
  }' | jq .
```

---

## When to use direct API vs MCP tools

| Situation | Use |
|-----------|-----|
| MCP server running normally | MCP tools (Tier 1 or 2) |
| MCP server down / unreachable | Direct API (Tier 3) |
| `execute_graphql` returns 500 error | Direct API (Tier 3) |
| Testing a new mutation before MCP tool exists | `execute_graphql` (Tier 2) — not direct API |

---

## Common introspection queries (Tier 3 fallback)

Discover available types:

```bash
curl -s -X POST "$PIPEFY_GRAPHQL_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ __schema { types { name } } }"}' | jq '.data.__schema.types[].name' | grep -i card
```

---

## Success criteria

- The operation completes without an HTTP 4xx/5xx error.
- The response contains a `data` key (not just `errors`).

## Failure modes

- **401 Unauthorized:** token expired or credentials wrong. Re-fetch with Option A (OAuth).
- **400 Bad Request:** GraphQL syntax error. Validate the query string (escape quotes in shell).
- **500 / service unavailable:** Pipefy API is down. Check [status.pipefy.com](https://status.pipefy.com) and retry later.

## Security notes

- Never log or print tokens in plain text.
- Prefer environment variables over inline credentials.
- Use `PIPEFY_TOKEN` (PAT) only for personal/development use; use OAuth for service accounts.

## See also

- `skills/introspection/` — Tier 2: use `execute_graphql` through the MCP server before falling back to direct HTTP.
