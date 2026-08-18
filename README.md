<div align="center">
  <img
    src="docs/images/pipefy-developers-banner.png"
    alt="Pipefy Developers — AI Toolkit (MCP Server, Pipefy CLI, GraphQL SDK, Agent Skills)"
    width="100%"
  />
</div>

<p align="center">
  <a href="https://github.com/pipefy/ai-toolkit/actions/workflows/ci.yml"><img src="https://github.com/pipefy/ai-toolkit/actions/workflows/ci.yml/badge.svg" alt="CI Status" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

<p align="center">
  <a href="#overview">Overview</a> •
  <a href="#installation">Installation</a> •
  <a href="#repository-layout">Repository layout</a> •
  <a href="#mcp-server">MCP server</a> •
  <a href="#command-line-interface">CLI</a> •
  <a href="#agent-skills">Agent skills</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#development">Development</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#legal">Legal</a>
</p>

---

## Overview

| Component | Package / path | Purpose |
|-----------|----------------|---------|
| **MCP server** | `pipefy-mcp-server` | Exposes **187** tools to MCP clients (Cursor, Claude Desktop, Claude Code, and others) when it runs locally. The hosted URL that the Cursor Marketplace plugin and Hosted MCP use serves **184**, see [MCP server](#mcp-server). |
| **CLI** | `pipefy-cli` | Terminal commands aligned with MCP capabilities; see [`docs/parity.md`](docs/parity.md). |
| **SDK** | `pipefy` | Vendor GraphQL client, services, and models shared by MCP and CLI. |
| **Skills** | [`skills/`](skills/) | Markdown playbooks (Anthropic Skills format) for common Pipefy workflows. |

Feedback and issues: [GitHub Issues](https://github.com/pipefy/ai-toolkit/issues) · **dev@pipefy.com**

---

## Installation

**Six ways to use the toolkit** — pick one based on your client and whether you need the full tool set:

- **In Cursor and want the fastest start with no local setup?** → **Cursor Marketplace plugin**.
- **In Claude Code and want the fastest start with no local setup?** → **Hosted MCP**.
- **In Claude Code and want the CLI, `/pipefy:*` slash commands, or the few local-only tools?** → **Claude Code plugin**.
- **On Cursor, Claude Desktop, or Codex and need the local-file tools, the CLI, or one command for everything?** → **Quick-install script**.
- **Terminal, scripting, or CI, with no agent?** → **CLI only**.
- **Just want the workflow playbooks in any agent?** → **Skills only**.

| Install path | MCP server runs on | Tools available | Auth | Also installs | Best for |
|---|---|---|---|---|---|
| **[Cursor Marketplace plugin](#6-cursor-marketplace-plugin)** | Pipefy cloud (HTTPS) | Remote-safe surface: **184** hosted tools; local-file tools withheld | In-client OAuth | nothing else | Fastest start in Cursor; zero local Python |
| **[Hosted MCP](#1-hosted-mcp-claude-code)** | Pipefy cloud (HTTPS) | Remote-safe surface: all but the few local-file tools | In-client OAuth | nothing else | Fastest start in Claude Code; zero local Python |
| **[Claude Code plugin](#2-claude-code-plugin)** | Your machine (`uvx` stdio) | Full [tool surface](#mcp-server) | `pipefy` CLI OAuth | slash commands + skills + CLI | Claude Code users who want the CLI, slash commands & the local-only tools |
| **[Quick-install script](#3-quick-install-script)** | Your machine (stdio) | Full [tool surface](#mcp-server) | `pipefy auth login` | CLI + skills, wired into your client config | Local-file tools, CLI, Claude Desktop / Codex, or one-command full setup |
| **[CLI only](#4-cli-only)** | — (no MCP) | CLI commands ([parity](docs/parity.md)) | login or service account | — | Terminal use, scripting, CI |
| **[Skills only](#5-skills-only)** | — | — | — | markdown playbooks | Adding playbooks to any agent |

> **Claude Code is the recommended client** and the most complete, best-tested path today. In Cursor, prefer the [Marketplace plugin](#6-cursor-marketplace-plugin) over the Quick-install script unless you need the local-file tools or the CLI. The Marketplace listing is submitted from `main` after this packaging is released; until it is live, contributors load a local copy (section 6) rather than treating a catalog 404 as a missing plugin. Claude Desktop and Codex still use the script.

> **Register exactly one Pipefy MCP server** — do not mix the hosted HTTP server with a local stdio or plugin server, whatever they are named. To check a machine, including one this repository never installed for you:
>
> ```sh
> curl -LsSf https://raw.githubusercontent.com/pipefy/ai-toolkit/main/uninstall.sh | sh -s -- --scan
> ```
>
> That reports every registration and how each one is reached. It removes nothing, edits nothing, and exits `0` when it finds nothing, `1` when findings remain, `2` when a source could not be inspected. A registration is matched on what it **runs** — the `pipefy-mcp-server` command, a known runner invoking it, or the host `mcp.pipefy.com` — so one registered under any other name is still found. First-time setup checklist to hand your agent: [`skills/onboarding/pipefy-toolkit-setup/SKILL.md`](skills/onboarding/pipefy-toolkit-setup/SKILL.md). Removing a path, or moving between them: [Uninstalling](#uninstalling-and-switching-between-paths) and [`docs/uninstall.md`](docs/uninstall.md).

> **Too many tools for your client?** The local paths can expose a subset instead of the whole catalog — by subject domain, by persona profile, or as four catalog meta-tools the agent searches on demand. See [Choosing a tool surface](#choosing-a-tool-surface). That selection (`PIPEFY_MCP_TOOLSETS`) applies to the local stdio path only. The Cursor Marketplace plugin and Hosted MCP always serve the hosted floor.

**Authentication** (for the local paths; the hosted server uses its own in-client OAuth):

- **Human OAuth (interactive):** `pipefy auth login` runs the browser flow and stores a session in your OS keychain. Pipe access is whatever the signed-in user already has.
- **Service account (unattended / CI):** provision one in [Pipefy Admin](https://app.pipefy.com/) (Admin → Service Accounts), add it to every pipe the tools should touch, and set `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` / `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`.

Full env-var reference and `config.toml` precedence: [`docs/config.md`](docs/config.md).

> **Pre-1.0 note:** builds ship as pre-releases to PyPI on every tag (`uvx` and `uv tool install` resolve them automatically; the stable default lands at **v1.0**). Current line: **`v0.3.0-beta.*`** ([latest tag](https://github.com/pipefy/ai-toolkit/releases/tag/v0.3.0-beta.1)). Installing `pipefy-cli` pulls `pipefy` and `pipefy-auth` transitively. To pin a version use the PEP 440 form `pipefy-cli==0.3.0b1`; do **not** pass a global `--prerelease allow` (it lets transitive deps jump to their own pre-releases and can pull a broken build).

### 1. Hosted MCP (Claude Code)

**Pick this when:** you're in Claude Code and want the fastest start with zero local Python. The server runs on Pipefy's infrastructure and exposes the **remote-safe surface**: reads, create / update / delete, and the raw GraphQL escape hatch — everything your own API permissions allow. Withheld are only the tools whose input is a file on your machine (knowledge-base document upload, custom LLM-provider credential files); attachment uploads still work from a URL or a presigned upload target instead of a local path.

```bash
claude mcp add --transport http --scope user --client-id pipefy-mcp pipefy https://mcp.pipefy.com/mcp
```

Complete the browser login when prompted (`claude mcp login pipefy` if the client reports *Needs authentication*). If a local or plugin Pipefy MCP server is already registered, remove it first — under whatever name it carries, since a second registration shadows this one and a plugin-provided server ranks below user scope. `./uninstall.sh --scan` names them; the switch is in [`docs/uninstall.md`](docs/uninstall.md#to-hosted). Need the CLI and slash commands too? Use the [Claude Code plugin](#2-claude-code-plugin) instead. Hand-wired local stdio: [`packages/mcp/README.md`](packages/mcp/README.md).

### 2. Claude Code plugin

**Pick this when:** you're in Claude Code and want the full local surface — every tool (including the local-file ones the hosted server withholds), the `/pipefy:*` slash commands, and the skill catalog. The MCP server runs locally via `uvx`.

```text
/plugin marketplace add pipefy/ai-toolkit
/plugin install pipefy
/pipefy:install
/pipefy:pipefy-login
```

Type the slash commands **in order** (the model cannot invoke `/plugin …` for you). `/plugin install pipefy` registers the local MCP server plus the `/pipefy:install` and `/pipefy:pipefy-login` commands; `/pipefy:install` runs `uv tool install` once to put `pipefy` on PATH (idempotent); `/pipefy:pipefy-login` runs the OAuth browser flow. Hand-wired setups, the macOS `errSecInvalidOwnerEdit` keychain note, and the contributor local-clone alternative: [`packages/mcp/README.md`](packages/mcp/README.md). To run a local branch as the plugin, see [Test the plugin from a local checkout](#test-the-claude-code-plugin-from-a-local-checkout).

### 3. Quick-install script

**Pick this when:** you need the local-file tools or the CLI, or you're on Claude Desktop or Codex — one command installs the CLI + local MCP server, optionally adds skills, and registers the server in your client config. In Cursor, prefer the [Marketplace plugin](#6-cursor-marketplace-plugin) unless you need that local surface.

```sh
curl -fsSL https://raw.githubusercontent.com/pipefy/ai-toolkit/main/install.sh \
  | sh -s -- --client cursor
```

Replace `--client cursor` with one of `claude-code`, `claude-desktop`, `codex`, or `none` (prints the snippet to paste). Useful flags: `--yes` (skip prompts), `--no-skills` (skip `npx skills add`), `--version vX.Y.Z` (pin a [Release](https://github.com/pipefy/ai-toolkit/releases)), `--dry-run` (print commands without executing), `--allow-root` (opt-in; refused by default). After install, run `pipefy auth login` (`--device` on headless systems). The installer puts `pipefy-mcp-server` on PATH, so each client's config collapses to `{"command": "pipefy-mcp-server"}`.

> **Production / shared environments:** pin an explicit release with `--version vX.Y.Z` (and prefer fetching `install.sh` from that same [Release](https://github.com/pipefy/ai-toolkit/releases) tag, not the floating `main` branch). Untagged/`@latest`-style installs are fine for local experiments; they are not the default practice for reproducible or corporate rollouts.

### 4. CLI only

**Pick this when:** you want terminal commands, scripting, or CI — no agent or MCP.

```sh
uvx --from pipefy-cli pipefy --help        # ad-hoc, no install

uv tool install pipefy-cli                 # permanent install
pipefy --install-completion bash           # or zsh, fish
pipefy auth login                          # browser OAuth, session in OS keychain
```

CLI deep-dives (auth precedence, `--token` / `PIPEFY_TOKEN`, parity matrix): [`packages/cli/README.md`](packages/cli/README.md) and [`docs/cli/`](docs/cli/README.md).

### 5. Skills only

**Pick this when:** you just want the workflow playbooks in any Markdown-aware agent (Cursor, Claude Code, Codex, and others).

```sh
npx skills add pipefy/ai-toolkit                           # all skills
npx skills add pipefy/ai-toolkit --skill pipefy-pipes-and-cards
```

Catalog and authoring guide: [`skills/README.md`](skills/README.md).

### 6. Cursor Marketplace plugin

**Pick this when:** you're in Cursor and want the hosted MCP server with browser sign-in and no local Python. The plugin ships the skill catalog and points Cursor at `https://mcp.pipefy.com/mcp`. Cursor runs the OAuth flow. The surface is the hosted deployment's remote-safe floor: **184** tools as of 2026-08-17 (Cloud Agents against production). Withheld are the tools whose input is a file on your machine; attachment uploads still work from a URL or a presigned upload target. Per-client toolset selection (`PIPEFY_MCP_TOOLSETS`) does not apply to this URL — use the [Quick-install script](#3-quick-install-script) when you need that, or the local-file tools.

Install **Pipefy** from the Cursor Marketplace once the listing is published (it tracks `main`). Complete the browser sign-in when Cursor prompts, then fully restart Cursor before the first tool call. No `uv`, no CLI, no token paste. This path has no `/install` or `/pipefy-login` commands (those files belong to the [Claude Code plugin](#2-claude-code-plugin), where they surface namespaced as `/pipefy:install` and `/pipefy:pipefy-login`). Skills may appear in the slash palette as `/pipefy-*`.

This path and any user-config Pipefy MCP entry (including one written by `install.sh --client cursor`) both occupy Cursor's MCP list. They are mutually exclusive — the same rule as mixing hosted HTTP with local stdio. The registration key is free text: delete the matching key from `~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`) and keep the Marketplace plugin. `./uninstall.sh --scan` prints the name it found; the switch is in [`docs/uninstall.md`](docs/uninstall.md#to-the-cursor-marketplace-plugin).

To load this checkout as a local plugin (contributors): Cursor rejects a symlink whose target is outside `~/.cursor/plugins/local` (it logs `loadUserLocalPlugin pipefy rejected`). Copy the plugin files into that directory as a real folder, then fully restart Cursor. If `~/.cursor/plugins/local/pipefy` is already a symlink to this checkout, `rm` the link first - that does not delete the repo. Copying `commands/` is optional: the Cursor manifest declares `"commands": []`, so neither a local copy nor a Marketplace tarball of this repo surfaces `/install` or `/pipefy-login`. Include it if you want the copy to match what ships.

```sh
dest="$HOME/.cursor/plugins/local/pipefy"
if [ -L "$dest" ]; then rm "$dest"; fi
mkdir -p "$dest/assets"
cp -R .cursor-plugin skills LICENSE NOTICE README.md mcp.json "$dest/"
cp assets/logo.svg "$dest/assets/"
```

Remove a copy with `rm -rf ~/.cursor/plugins/local/pipefy`. Remove only a leftover symlink with `rm ~/.cursor/plugins/local/pipefy`.

### Uninstalling, and switching between paths

`uninstall.sh` sits beside `install.sh` and reverses the script, CLI, hosted-user-config, and Claude Code plugin paths, including one this repository never installed for you. It does **not** uninstall the Cursor Marketplace plugin (that lives in Cursor's plugin UI). `--scan` still reports a competing `~/.cursor/mcp.json` registration if one exists (including `install.sh --client cursor`).

```sh
# Report only: what is on this machine, across every channel and client.
curl -LsSf https://raw.githubusercontent.com/pipefy/ai-toolkit/main/uninstall.sh | sh -s -- --scan

# Then remove what you approve. Approval is asked in three tiers.
curl -LsSf https://raw.githubusercontent.com/pipefy/ai-toolkit/main/uninstall.sh | sh
```

`--scan` changes nothing and exits `0` clean / `1` findings remain / `2` a source could not be inspected. A registration is matched on what it **runs** — the `pipefy-mcp-server` command, a known runner invoking it, or the host `mcp.pipefy.com` — so an entry registered under any other name is still found, and removed under that name. Useful flags: `--dry-run`, `--yes`, `--keep-credentials`, `--keep-config`, `--client <id>`.

**Switching paths is remove-then-add**: register exactly one Pipefy MCP server at a time, since a plugin-provided server ranks below user scope and a leftover entry silently wins. Full teardown reference, the per-channel switching recipes, and what is never removed by design: [`docs/uninstall.md`](docs/uninstall.md).

### Post-1.0 (PyPI, preview)

Once the stable line lands, the MCP server and CLI resolve straight from PyPI by name:

```sh
uvx pipefy-mcp-server
uv tool install pipefy-cli
```

Deprecation and semver (post-1.0): [`docs/DEPRECATION.md`](docs/DEPRECATION.md).

---

## Repository layout

`uv` workspace with three Python packages and a skills catalog. **`pipefy`** is the vendor GraphQL layer; MCP and CLI depend on it and do not import each other.

| Path | Distribution | Role |
|------|--------------|------|
| [`packages/sdk/`](packages/sdk/) | `pipefy` | GraphQL transport, services, queries, Pydantic models. [Package README](packages/sdk/README.md) |
| [`packages/mcp/`](packages/mcp/) | `pipefy-mcp-server` | MCP tool registration and server lifecycle. [Package README](packages/mcp/README.md) |
| [`packages/cli/`](packages/cli/) | `pipefy-cli` | Typer CLI (`pipefy` command). [Package README](packages/cli/README.md) |
| [`skills/`](skills/) | — | Agent skill playbooks. [Catalog](skills/README.md) |

---

## MCP server

The server registers **187 tools** across fourteen domains locally. Canonical names: `PIPEFY_TOOL_NAMES` in [`packages/mcp/src/pipefy_mcp/tools/registry.py`](packages/mcp/src/pipefy_mcp/tools/registry.py). The Cursor Marketplace plugin and Hosted MCP path expose the hosted remote-safe floor instead: **184** tools as of 2026-08-17 (the three-tool gap is the local-file tools that URL withholds).

Tool descriptions and `Args:` blocks come from Python docstrings (what MCP clients show to models). Per-area reference docs cover parameters, edge cases, and cross-cutting behavior.

**Shared conventions** (pagination, IDs, permissions, error shape): [`docs/mcp/tools/cross-cutting.md`](docs/mcp/tools/cross-cutting.md).

| Domain | Tools | Summary | Reference |
|--------|:-----:|---------|-----------|
| **Pipes & cards** | 41 | Pipes, phases, fields, labels, cards, field conditions, attachments. Phase inventory (`get_phase_cards`, `get_phase_cards_count`), move discovery (`get_phase_allowed_move_targets`), and `create_card(phase_id=…)` reduce raw GraphQL for agent seeding. | [docs](docs/mcp/tools/pipes-and-cards.md) |
| **Database tables** | 17 | Tables, records, schema, table-record attachments. | [docs](docs/mcp/tools/database-tables.md) |
| **Relations** | 8 | Pipe and card relations. | [docs](docs/mcp/tools/relations.md) |
| **Reports** | 17 | Pipe and organization reports, async exports. | [docs](docs/mcp/tools/reports.md) |
| **Automations & AI** | 23 | Automations, AI automations, AI agents, validators. | [docs](docs/mcp/tools/automations-and-ai.md) |
| **LLM providers** | 11 | Discovery reads (custom + Pipefy-managed providers, vendor model lists, owner defaults, dependencies, read-access probe) plus custom-provider writes: create/update/delete, active-status toggle, and organization default set/reset. | [docs](docs/mcp/tools/llm-providers.md) |
| **Knowledge bases** | 14 | Pipe-scoped AI knowledge bases: list all items, plain text / document (one-shot PDF upload) / data lookup CRUD, and a read-access probe. Attach sources to agents/behaviors via `dataSourceIds`. | [docs](docs/mcp/tools/knowledge-bases.md) |
| **iPaaS** | 4 | Lazy discovery, invocation, and app-connection setup for a pipe's iPaaS (Advanced Automations) workspace (`get_ipaas_tools`, `call_ipaas_tool`, plus the connection meta-tools). | [docs](docs/mcp/tools/ipaas.md) |
| **Observability** | 11 | Logs, usage, credits, execution metrics, job exports. | [docs](docs/mcp/tools/observability.md) |
| **Members, email & webhooks** | 12 | Membership, inbox email, webhooks. | [docs](docs/mcp/tools/members-email-webhooks.md) |
| **Service accounts** | 2 | Create and delete organization service accounts (OAuth2 machine identities); attach them to pipes with `add_service_account_to_pipe`. | [docs](docs/mcp/tools/service-accounts.md) |
| **Organization** | 2 | Organization metadata and discovery. | [docs](docs/mcp/tools/organization.md) |
| **Portals** | 20 | Portal read/CRUD, pages, elements, sub-portals (publish/unpublish). | [docs](docs/mcp/tools/portal.md) |
| **Introspection** | 5 | Schema discovery and raw GraphQL. | [docs](docs/mcp/tools/introspection.md) |

### Choosing a tool surface

Not every client wants every tool. Three independent controls decide what `tools/list` returns:

| Control | Set with | Effect |
|---|---|---|
| **Launch profile** | `--profile local` / `remote` | The security floor. `local` registers every tool; `remote` serves only the remote-safe surface and validates an inbound bearer per request. |
| **Toolset selection** | `--toolsets` / `PIPEFY_MCP_TOOLSETS` | Narrows within that floor — by **subject domain** (`workflow`, `database`, `interfaces`, `automation`, `intelligence`, `analytics`, `governance`, `integration`) or by **persona profile** (`requester`, `operator`, `manager`, `builder`, `admin`, `auditor`), unioned. Selection never widens past the floor. |
| **Power discovery** | `--toolsets power` | Replaces the curated tools with four catalog meta-tools (`get_tool_categories`, `search_tools`, `describe_tool`, `execute_tool`) plus the raw-GraphQL tools, so the working set stays small no matter how large the catalog grows. |

The toolset names are a **different grouping from the table above**: that table is organized by documentation area (the reference docs you read), while subject domains partition tools by the job they serve — card relations land in `workflow`, table relations in `database`. Passing an unrecognized name is a startup error that prints the full list of valid ones. `--toolsets` / `PIPEFY_MCP_TOOLSETS` is a process-level switch: it applies to the local stdio server only, not to the Cursor Marketplace plugin or Hosted MCP URL.

Per-name definitions and precedence: [`docs/config.md`](docs/config.md). Taxonomy rationale (why subject domains, why personas overlap): [`packages/mcp/AGENTS.md`](packages/mcp/AGENTS.md).

---

## Command-line interface

The **`pipefy`** CLI mirrors shipped MCP capabilities where parity is defined in **[`docs/parity.md`](docs/parity.md)**. Conventions: Rich output by default, **`--json`** for scripts, **`--yes`** on destructive commands.

```sh
pipefy pipe list --json
pipefy card get 123456789
pipefy introspect query --name getPipe
```

CLI-specific guides: **[`docs/cli/`](docs/cli/README.md)** (including [introspect-then-execute](docs/cli/self-healing.md)).

---

## Agent skills

The [`skills/`](skills/) directory holds workflow playbooks: prerequisites, tool tables (MCP + CLI), steps, and success criteria. Compatible with any agent that reads Markdown (Cursor, Claude Code, Codex, and others). Distribution is via [`skills.sh`](https://github.com/vercel-labs/skills) (55+ agent targets); install commands are under [Installation](#installation) above.

Full catalog: [`skills/README.md`](skills/README.md). Authoring: [`skills/AGENTS.md`](skills/AGENTS.md). Contributions: [`CONTRIBUTING.md`](CONTRIBUTING.md).

**Card & phase agent ergonomics:** use [`skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md`](skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md) (workflow *Seed pipe across phases*; prefer dedicated tools over `execute_graphql`).

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/README.md`](docs/README.md) | Index by surface (MCP, CLI, SDK). |
| [`docs/config.md`](docs/config.md) | `PIPEFY_*` environment variables, `config.toml` schema and path, precedence chain. |
| [`docs/parity.md`](docs/parity.md) | MCP tool ↔ CLI command matrix. |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | Notes for existing MCP users. |
| [`AGENTS.md`](AGENTS.md) | Repository guidelines for contributors and agents. |
| [`RELEASE.md`](RELEASE.md) | Versioning and release process. |

---

## Development

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it, then from the repository root:

```bash
uv sync
[[ -f .env ]] || cp .env.example .env   # first-time setup; then fill in PIPEFY_SERVICE_ACCOUNT_*
uv run pytest -m "not integration"    # unit tests (no live API)
uv run pytest -m integration -v     # live API (requires PIPEFY_*)
uv run ruff check . && uv run ruff format .
```

**MCP Inspector** (protocol debugging):

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

**Adding an MCP tool:** implement under `packages/mcp/src/pipefy_mcp/tools/`, register in `ToolRegistry`, add the name to `PIPEFY_TOOL_NAMES`, and ship the matching CLI command (or document a deferral in `docs/parity.md`). See [`AGENTS.md`](AGENTS.md) for the full TDD workflow.

### Test the Claude Code plugin from a local checkout

The [Claude Code plugin install](#2-claude-code-plugin) adds the marketplace from the `pipefy/ai-toolkit` GitHub repo, which tracks `main`. To run **your local branch** (e.g. `dev`) as the plugin instead, point the marketplace at your clone:

```text
/plugin marketplace add /absolute/path/to/ai-toolkit
/plugin install pipefy@pipefy
```

Whatever is checked out in that clone — any branch — is what loads. Use the `plugin@marketplace` form (`pipefy@pipefy`) since the marketplace and the plugin share the name `pipefy`. After editing plugin files (skills, commands), run `/reload-plugins` to pick up changes without restarting.

> **Already installed the GitHub version?** A marketplace named `pipefy` can be registered only once, and a marketplace declared in `~/.claude/settings.json` under `extraKnownMarketplaces` is locked — `/plugin marketplace add` becomes a no-op (`already on disk — declared in user settings`) and keeps pointing at GitHub. Run `/plugin marketplace remove pipefy` first (or delete that `extraKnownMarketplaces` entry), **then** add the local path. Why removing a marketplace does not always stick: [`docs/uninstall.md`](docs/uninstall.md#two-things-that-come-back).

---

## Contributing

Contributions are welcome via issues and pull requests. Commits must include a [DCO](https://developercertificate.org/) sign-off (`git commit -s`); see [`CONTRIBUTING.md`](CONTRIBUTING.md).

| Area | How to contribute |
|------|-------------------|
| **Skills** | Markdown only — see [`CONTRIBUTING.md`](CONTRIBUTING.md). |
| **MCP / CLI / SDK** | Follow [`AGENTS.md`](AGENTS.md) and [`docs/parity.md`](docs/parity.md). |
| **Field mapping gaps** | Open an issue with the field type and expected behavior. |
| **Existing MCP setups** | [`docs/MIGRATION.md`](docs/MIGRATION.md) — configuration remains compatible. |

---

## Legal

This toolkit (MCP server, CLI, SDK, and skill/blueprint playbooks) is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for trademark reservations.

Your access to and use of the Pipefy platform through this toolkit is governed by the [Pipefy Solutions Terms and Conditions](https://www.pipefy.com/terms-and-conditions/) ([versão em português](https://www.pipefy.com/pt-br/termos-e-condicoes/)) and, for AI features, by the Pipefy AI Additional Terms (to be published and incorporated by reference into those terms), including their acceptable use provisions. Using this toolkit requires a Pipefy account; nothing in the Apache 2.0 license grants rights to the Pipefy service.

**Templates, not advice.** Skills and blueprints are configurable templates provided for general informational purposes. They do not constitute legal, HR, financial, tax, or other professional advice, and must be reviewed, configured, and validated by qualified professionals before production use. Each published blueprint ships with a `COMPLIANCE.md` describing its intended purpose, out-of-scope uses, AI risk classification, and default human-oversight settings (see [`docs/compliance/COMPLIANCE.template.md`](docs/compliance/COMPLIANCE.template.md)).

**AI-generated output.** Outputs produced by AI features may contain errors or omissions and must be independently verified before being relied upon.

**Beta software.** Pre-1.0 releases are provided “AS IS”, without warranties of any kind, and may change or be discontinued at any time. See the full disclaimer in [TERMS.md](TERMS.md).

Security reports: see [SECURITY.md](SECURITY.md). Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md).
