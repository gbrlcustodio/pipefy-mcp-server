# MCP package conventions

Scoped to `packages/mcp/`. Repo-wide guidance lives in `../../AGENTS.md`.

## Distribution model

This MCP server is distributed as code that runs in the user's environment as
a subprocess of the agent runtime (Claude Code, Claude Desktop, etc.). The
trust boundary is the user; the server has the same filesystem and network
access the user already has.

Implications for tool design:

- Local filesystem inputs (`file_path`) are first-class. There is no
  path-traversal threat surface beyond what the user can already access.
- SSRF guards, redirect loops, and download size caps that defend a hosted
  server are not appropriate here. They add maintenance cost without buying
  a security boundary.

A hosted/remote distribution profile is in progress (see issue #297). It runs
the server as a multi-user HTTP service. Tool exposure there is **default-deny**:
only tools explicitly marked remote-safe are registered; everything else is
withheld. The marker is described below.

## Transport profiles

Two ways to launch `pipefy-mcp-server`:

- **stdio (default).** No flags: the process speaks MCP on stdin/stdout, launched
  as a subprocess by an MCP client.
- **HTTP (`--remote`).** `pipefy-mcp-server --remote` serves over Streamable HTTP
  and turns on the default-deny remote profile, exposing only the remote-safe tool
  surface. Bind host/port come from `PIPEFY_MCP_HOST` / `PIPEFY_MCP_PORT` (defaults
  `127.0.0.1:8000`), overridable with `--host` / `--port`.

The HTTP profile is foundation work behind the flag (issue #300). It does **not**
yet validate inbound bearers (resource-server role, #301) or carry per-request
on-behalf-of identity (#302); until those land it is unauthenticated and uses the
single identity resolved at startup. Treat `--remote` as local/validation only, not
a production hosted endpoint.

**Public-HTTP safety interlock.** The HTTP path of `run_server` refuses to serve
the full tool surface on a non-loopback host unless the remote profile is on
(`--remote`) or `PIPEFY_MCP_ALLOW_FULL_SURFACE_OVER_HTTP=true` is set. Loopback
binds are always allowed for local development.

## Tool registration

Tools are registered **once, at construction** (via `_register_pipefy_tools` in
`server.py`, reached through `build_pipefy_mcp_server` for stdio and the HTTP path
of `run_server`), not inside the FastMCP `lifespan`. The lifespan owns resources only:
it initializes services and yields the container as the request
`lifespan_context`. This follows the FastMCP contract, where the lifespan can run
per session (per request under Streamable HTTP) and so must not mutate the tool
table.

Tools take no client at registration. Each tool function declares a
`ctx: Context` parameter (FastMCP injects it and keeps it out of the tool's
input schema) and resolves the live client per request with
`get_pipefy_client(ctx)` (`tools/tool_context.py`), which reads
`ctx.request_context.lifespan_context.pipefy_client`. Because the client is
looked up per call, a service re-initialization (a fresh client) is picked up
without re-registering tools, and a per-request identity (issue #302) can vary
the client the lifespan yields without touching any tool. That is why there is
no repeat-visit bookkeeping: registration never repeats.

When adding a tool, give it a `ctx: Context` parameter and start its body with
`client = get_pipefy_client(ctx)`; do not pass a client through `register`.

Both transports launch through the single `run_server` entry point (stdio by
default, HTTP with `http=True`) and share `_register_pipefy_tools`. The stdio app
keeps the resource-only `lifespan`; the HTTP app carries no constructor `lifespan`
(which Streamable HTTP would run per session) and initializes services once before
serving.

## Remote-profile tool marker

When `PIPEFY_MCP_REMOTE_MODE` is true, the server exposes ONLY tools whose
registration carries `meta=REMOTE`. Any unmarked tool is implicitly withheld
(default-deny). When the flag is false (the default, local stdio profile), all
tools register and the marker is inert.

The marker is a single co-located source of truth on the `@mcp.tool` decorator:

```python
from pipefy_mcp.tools.remote_profile import REMOTE

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
async def get_organization(...): ...
```

`ToolRegistry.apply_remote_profile()` reads it back via `is_remote_tool` and
removes every unmarked Pipefy tool at registration time (before the server
serves anything). The marker is greppable (`rg "meta=REMOTE" packages/mcp`) and
machine-enforced, unlike the comment-only `GATED:` convention it replaces.

Inclusion criteria for marking a tool remote-safe: it reaches the API with the
request-scoped bearer and is fully governed by API permissions; it does NOT read
the local filesystem; it does NOT read process-global settings for a per-user
decision. Opting a tool in is a deliberate, reviewed change (it shifts the
`REMOTE_SEED` drift guard in `tests/tools/test_remote_profile.py`).

### Exposure vs input restriction

The `meta` marker expresses **exposure** only: whether a tool is available in the
remote profile. The retired `GATED:` convention could also express *input*
restriction within an exposed tool. Where a remotely-exposed tool needs restricted
inputs (for example the attachment tools tracked in #305, which would accept a
`file_url` rather than a local `file_path`), enforce that in the tool body gated on
`settings.mcp.remote_mode` at call time, not via the marker. A tool whose exclusion deserves
a reason gets a plain code comment pointing at its follow-up issue (the attachment
tools point at #305); the exclusion itself needs no annotation.
