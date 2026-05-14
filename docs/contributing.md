# Contributing

Development setup for people working on the Pipefy MCP server itself. If you only want to **use** the server in your MCP client, see [Quickstart](quickstart.md) — you do not need to clone this repo.

| Section | What it covers |
|---------|------------------|
| [Prerequisites](#prerequisites) | Python, `uv`, a Pipefy Service Account |
| [Clone and install](#clone-and-install) | `git clone`, `uv sync` |
| [Local `.env` file](#local-env-file) | `cp .env.example .env`, Pydantic Settings precedence |
| [Smoke test](#smoke-test) | `uv run pipefy-mcp-server` |
| [Unit tests](#unit-tests) | `uv run pytest -m "not integration"` |
| [Manual MCP testing](#manual-mcp-testing) | Cursor MCP, MCP Inspector |
| [Bootstrap script](#bootstrap-script) | One-shot `./bootstrap.sh` |
| [Release process](#release-process) | Tag bumps and `docs/quickstart.md` |

---

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for dependency management
- A [Pipefy Service Account](https://developers.pipefy.com/reference/service-accounts) (Admin → Members and Permissions → Service Accounts). Add the service account to every pipe you intend to exercise.

---

## Clone and install

```bash
git clone https://github.com/gbrlcustodio/pipefy-mcp-server.git
cd pipefy-mcp-server
uv sync
```

On Windows, run the same commands in **PowerShell** or **Git Bash** (with `uv` on `PATH`).

---

## Local `.env` file

From the repo root:

```bash
cp .env.example .env
```

Edit **`.env`** and set at least `PIPEFY_OAUTH_CLIENT` and `PIPEFY_OAUTH_SECRET` from your service account. Canonical names and defaults: **[`../.env.example`](../.env.example)**.

Runtime settings come from **`pipefy_mcp.settings.Settings`** ([Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)):

- **`.env`** is read from the **current working directory** when you run `uv run pipefy-mcp-server` from the clone root (or when your MCP client sets `cwd` to the clone).
- Values already in the **process environment** override entries from `.env`.
- The same keys work in `.env` and in an MCP client's `env` block — see [Environment variables](quickstart.md#environment-variables).

### Dev-only env overrides

User-facing keys (required and optional) live in [`docs/quickstart.md` → Environment variables](quickstart.md#environment-variables). The only key meant strictly for local development is:

- **`PIPEFY_ALLOW_INSECURE_URLS=true`** — allow `http://` and internal hosts for GraphQL / OAuth / internal API / webhooks. **Never enable in production**; credentials must not leave HTTPS. Off by default.

---

## Smoke test

Confirm the process starts (stop with Ctrl+C when satisfied):

```bash
uv run pipefy-mcp-server
```

---

## Unit tests

No `PIPEFY_*` credentials required:

```bash
uv run pytest -m "not integration"
```

Integration tests (`-m integration`) call the live Pipefy GraphQL API and need a real service account in `.env`.

---

## Manual MCP testing

Point your MCP client at the local clone instead of the published flow in [Quickstart](quickstart.md). Use this config (replace the absolute path with your clone path):

```json
{
    "mcpServers": {
        "pipefy": {
            "command": "uv",
            "args": [
                "run",
                "--directory",
                "/absolute/path/to/pipefy-mcp-server",
                "pipefy-mcp-server"
            ]
        }
    }
}
```

Set `cwd` to the clone root (or include `--directory` as above) so the server reads `.env` from there; the `env` block in JSON can be empty for local dev.

For protocol-level debugging without an MCP client UI:

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

See [AGENTS.md](../AGENTS.md) under **Manual tool testing (E2E)** for the broader conventions maintainers follow.

---

## Bootstrap script

From the repo root, after installing `uv`:

```bash
./bootstrap.sh
```

The script:

- Runs **`uv sync`**.
- If **`.env`** is missing, copies **`.env.example`** → **`.env`** (does not overwrite an existing `.env`).

On Windows without Git Bash, run the [Clone and install](#clone-and-install) and [Local `.env` file](#local-env-file) steps manually.

---

## Release process

When cutting a new tag, **bump the `@vX.Y.Z` references in [`docs/quickstart.md`](quickstart.md)** so end-user examples pin to the latest release. The doc currently pins to `v0.1.0`; grep for `@v` under `docs/quickstart.md` to find every occurrence.
