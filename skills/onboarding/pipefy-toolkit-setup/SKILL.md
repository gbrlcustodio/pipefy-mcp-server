---
name: pipefy-toolkit-setup
description: >
  Guide a first-time user through Pipefy AI toolkit setup (hosted MCP,
  local install.sh, or Claude Code plugin). Use when the user asks to
  install Pipefy MCP, connect Claude/Cursor to Pipefy, run /pipefy:install,
  or set up mcp.pipefy.com. Do not use for day-to-day Pipefy workflows
  after MCP is already working.
tags: [pipefy, onboarding, install, mcp, setup, claude, cursor]
---

# Pipefy toolkit setup (first-time onboarding)

**Canonical install snippets** live only in the root [`README.md#installation`](../../../README.md#installation) (#246: no second god-doc of commands). This skill is the agent **checklist** — print or run the README blocks verbatim; do not invent alternate commands.

Edge cases: [`packages/mcp/README.md`](../../../packages/mcp/README.md). Auth: [`docs/cli/auth.md`](../../../docs/cli/auth.md). Env: [`docs/config.md`](../../../docs/config.md).

---

## When to use

- "Set up Pipefy", "install the MCP", "connect Claude/Cursor to Pipefy"
- User mentions `/plugin marketplace add`, `/pipefy:install`, or `mcp.pipefy.com`
- Fresh machine with no `pipefy` on PATH and no Pipefy MCP server

**Do not use** once tools already work — switch to a domain skill (pipes, tables, …).

## Prerequisites

- User has a Pipefy account (Admin access if they need a service account).
- Hosted MCP: Claude Code CLI (`claude`).
- Local toolkit: a shell that can run `curl` (`install.sh` can install `uv`).
- Claude Code **slash commands** (`/plugin …`, `/pipefy:…`) must be typed by the user. Print them; never claim you invoked them.

## Tools needed

Setup is outside the Pipefy MCP tool surface. After auth succeeds, verify with:

| Tool (MCP) | CLI equivalent | Read-only |
|------------|----------------|-----------|
| `get_organization` | `pipefy org get` | Yes |

## Steps

1. **Choose one path** — ask the user; do not pick silently.

   | Path | README section | Outcome |
   |------|----------------|---------|
   | Hosted MCP | [Hosted MCP](../../../README.md#hosted-mcp-claude-code) | HTTPS `mcp.pipefy.com` (remote-safe tools) |
   | Local toolkit | [Quick install](../../../README.md#quick-install-recommended) | `install.sh` → local server + CLI |
   | Claude Code plugin | [Claude Code](../../../README.md#claude-code) | Marketplace + slash install/login |
   | CLI only | [CLI](../../../README.md#cli) | `pipefy` on PATH; no MCP |

   **Never** register both hosted HTTP and local stdio/plugin under the MCP server name `pipefy`.

2. **Execute the chosen README block** — run it in the shell, or print it for the user to paste (required for Claude slash commands). Do not reorder the plugin sequence: marketplace → `/plugin install pipefy` → `/pipefy:install` → `/pipefy:pipefy-login`.

3. **Auth** — hosted: finish the client browser OAuth prompt. Local/plugin/CLI: `pipefy auth login` or `/pipefy:pipefy-login` (see README). Service accounts: [`docs/config.md`](../../../docs/config.md).

4. **Verify**

   - Shell (local / plugin / CLI): `pipefy --version`
   - MCP: call `get_organization` (or another read-only tool the user allows)
   - Confirm exactly one `pipefy` MCP registration

## Success criteria

- One active Pipefy MCP registration for the chosen path (or CLI-only with no MCP).
- Auth completed.
- Read-only MCP call or `pipefy --version` succeeds.

## Failure modes

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| Slash commands missing | Plugin not installed | README [Claude Code](../../../README.md#claude-code) — marketplace + install first |
| Two `pipefy` MCP entries | Hosted + plugin both registered | Remove one (`claude mcp remove` / client settings) |
| `pipefy: command not found` | CLI not on PATH | `/pipefy:install` or README [CLI](../../../README.md#cli); check `$HOME/.local/bin` |
| MCP tools empty / auth errors | Login not done | Re-run login; service accounts → `docs/config.md` |
| macOS `errSecParam` | Keychain write | [`packages/mcp/README.md`](../../../packages/mcp/README.md) |

## See also

- [`README.md#installation`](../../../README.md#installation)
- [`skills/README.md`](../../README.md)
