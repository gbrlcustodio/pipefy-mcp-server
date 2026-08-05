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

**Canonical install snippets** live only in the root [`README.md#installation`](../../../README.md#installation) — there is no second copy of the commands. This skill is the agent **checklist** — print or run the README blocks verbatim; do not invent alternate commands.

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

**Who does what**

| Actor | Does |
|-------|------|
| **Agent** | Asks path; prints README commands verbatim; runs shell `claude mcp add` / `install.sh` when the user agrees; checks `claude mcp get` / list |
| **User types** | Claude slash commands (`/plugin …`, `/pipefy:…`) — the model cannot invoke them |
| **User in browser** | OAuth for hosted (`claude mcp login …`) or `/pipefy:pipefy-login` / `pipefy auth login` |

## Tools needed

Setup is outside the Pipefy MCP tool surface. After auth succeeds, verify with:

| Tool (MCP) | CLI equivalent | Read-only |
|------------|----------------|-----------|
| `list_organizations` | `pipefy org list` | Yes |
| `get_organization` | `pipefy org get` | Yes |

## Steps

1. **Choose one path** — ask the user; do not pick silently.

   If they only say “Claude Code” (no path), ask a **closed** question:

   > Hosted MCP (zero local Python, `mcp.pipefy.com`) or the Claude Code plugin (slash commands + local CLI)? If you’re unsure, Hosted is the usual first try.

   | Path | README section | Outcome |
   |------|----------------|---------|
   | Hosted MCP | [Hosted MCP](../../../README.md#1-hosted-mcp-claude-code) | HTTPS `mcp.pipefy.com` (remote-safe tools) |
   | Local toolkit | [Quick install](../../../README.md#3-quick-install-script) | `install.sh` → local server + CLI |
   | Claude Code plugin | [Claude Code plugin](../../../README.md#2-claude-code-plugin) | Marketplace + slash install/login |
   | CLI only | [CLI](../../../README.md#4-cli-only) | `pipefy` on PATH; no MCP |

   **Never** register both a hosted HTTP and a local stdio/plugin Pipefy server, whatever they are named: a second registration shadows the one you meant to use. Switching between paths is remove-then-add — [`docs/uninstall.md`](../../../docs/uninstall.md#switching-channels).

2. **Execute the chosen README block** — run it in the shell, or print it for the user to paste (required for Claude slash commands). Do not reorder the plugin sequence: marketplace → `/plugin install pipefy` → `/pipefy:install` → `/pipefy:pipefy-login`.

3. **Auth** — hosted: finish the client browser OAuth prompt (`claude mcp login <name>` if status is Needs authentication). Local/plugin/CLI: `pipefy auth login` or `/pipefy:pipefy-login` (see README). Service accounts: [`docs/config.md`](../../../docs/config.md).

4. **Verify**

   - Shell (local / plugin / CLI): `pipefy --version`
   - MCP: call `list_organizations` (needs no id — the natural first read; confirms the credential works and surfaces the org ids other tools need) or another read-only tool the user allows
   - Run `curl -LsSf https://raw.githubusercontent.com/pipefy/ai-toolkit/main/uninstall.sh | sh -s -- --scan` (reports only, removes nothing; `./uninstall.sh --scan` from a checkout does the same) and confirm it reports exactly one registration, for the path you chose. It matches on what an entry **runs** — the `pipefy-mcp-server` command, a known runner invoking it, or the host `mcp.pipefy.com` — so a server registered under any other name is still found. Exit `0` nothing found, `1` findings remain, `2` a source could not be inspected.

## Success criteria

- The `--scan` above reports one registration, for the chosen path (or CLI-only with no MCP).
- Auth completed.
- Read-only MCP call or `pipefy --version` succeeds.

## Failure modes

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| Slash commands missing | Plugin not installed | README [Claude Code plugin](../../../README.md#2-claude-code-plugin) — marketplace + install first |
| More than one Pipefy MCP registration | Hosted + local/plugin both registered, possibly under different names | The `--scan` above names each one and where it lives; remove-then-add recipes in [`docs/uninstall.md`](../../../docs/uninstall.md#switching-channels). A plugin-provided server ranks below user scope, so removing the user entry alone falls through to it |
| `Needs authentication` after hosted add | OAuth not finished | `claude mcp login <name>` + browser |
| `pipefy: command not found` | CLI not on PATH | `/pipefy:install` or README [CLI](../../../README.md#4-cli-only); check `$HOME/.local/bin` |
| MCP tools empty / auth errors | Login not done | Re-run login; service accounts → `docs/config.md` |
| macOS `errSecInvalidOwnerEdit` | Keychain write | [`packages/mcp/README.md`](../../../packages/mcp/README.md) |

## See also

- [`README.md#installation`](../../../README.md#installation)
- [`docs/uninstall.md`](../../../docs/uninstall.md) — `uninstall.sh --scan`, teardown, and switching between hosted, local, and plugin
- [`skills/README.md`](../../README.md)
