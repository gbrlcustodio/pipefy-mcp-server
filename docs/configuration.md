# Configuration

Runtime settings come from **`pipefy_mcp.settings.Settings`** ([Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)).

- **`.env`**: read from the **current working directory** (usually the repo root when you run `uv run pipefy-mcp-server` there).
- **Precedence**: values already set in the **process environment** override entries from `.env`.
- **Names and examples**: use **[`.env.example`](../.env.example)** as the single list of `PIPEFY_*` keys and placeholder values.

MCP clients (Cursor, Claude, etc.) typically pass the same keys in their `env` JSON block; that populates the process environment for the server process.

## Optional settings

| Key | Default | Effect |
|-----|---------|--------|
| `PIPEFY_SERVICE_ACCOUNT_IDS` | _unset_ | Comma-separated Pipefy user IDs treated as service accounts. Enables [Service Account Protection](tools/members-email-webhooks.md#service-account-protection) on `remove_member_from_pipe` / `set_role`, and proactive membership checks in [`validate_ai_agent_behaviors`](tools/automations-and-ai.md#ai-agent-read--delete) for cross-pipe targets. Leave unset to skip the guards. |
| `PIPEFY_INTERNAL_API_URL` | _see [`.env.example`](../.env.example)_ | Used by tools that go through the internal GraphQL schema (e.g. AI automations, `delete_card_relation`). URLs are validated at startup — `localhost` / private hosts are rejected to avoid SSRF. |
