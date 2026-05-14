# Migration Guide — v0.1 Cutover (pipefy-mcp-server → pipefy-labs)

Existing users of `pipefy-mcp-server`: this guide covers what changed and what to do. **TL;DR:** almost nothing breaks.

---

## Package name — unchanged

`pipefy-mcp-server` is the same PyPI package name as before. Your `pip install pipefy-mcp-server` or `uvx pipefy-mcp-server` still works. The existing PyPI version is frozen at the pre-monorepo release; new versions ship at v1.0 via the same name.

**Pre-launch (v0.1 → v0.5):** install from git to get the latest:

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-mcp-server
```

---

## MCP client config — unchanged

Your existing Cursor, Claude Desktop, or Claude Code JSON config needs **no changes**. The entry point (`pipefy-mcp-server`) and tool names are identical.

Example Cursor config (still valid):

```json
{
  "mcpServers": {
    "pipefy": {
      "command": "uvx",
      "args": ["pipefy-mcp-server"]
    }
  }
}
```

---

## Tool names and parameters — unchanged

All 128 MCP tools have the same names, parameters, and behavior. No renames, no removed tools. If you have agent prompts or workflows referencing specific tool names, they continue to work.

---

## Repo URL

The repository was renamed from `pipefy-mcp-server` to `pipefy-labs` on GitHub. GitHub preserves redirects — your existing `git remote` URLs for the old repo keep working for `git fetch`, `git pull`, and `git push`.

Update your remote at your convenience:

```sh
git remote set-url origin https://github.com/<owner>/pipefy-labs.git
```

---

## New in v0.1

These are new additions — all optional to adopt:

**`pipefy-cli`** — a terminal CLI with the same capabilities as the MCP server.

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-cli
pipefy card get 12345
pipefy skills list
```

**`skills/` catalog** — Anthropic Skills-format playbooks for common Pipefy workflows, consumable by any LLM agent.

```sh
pipefy skills show pipes-and-cards | pbcopy   # paste into agent context
```

---

## Environment variables — unchanged

The same `PIPEFY_*` variables (`PIPEFY_OAUTH_CLIENT`, `PIPEFY_OAUTH_SECRET`, `PIPEFY_GRAPHQL_URL`, etc.) work for both MCP and CLI. A working `.env` for `pipefy-mcp-server` gives you `pipefy-cli` auth immediately.

See [`docs/setup.md`](setup.md) for the full list.

---

## Questions?

Open an issue at [github.com/<owner>/pipefy-labs/issues](https://github.com/<owner>/pipefy-labs/issues) or email **dev@pipefy.com**.
