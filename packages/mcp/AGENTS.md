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

## Tool registration

Tools are registered **once, at construction** (`build_pipefy_mcp_server` ->
`_register_pipefy_tools` in `server.py`), not inside the FastMCP `lifespan`. The
lifespan owns resources only: it initializes services and yields the container
as the request `lifespan_context`. This follows the FastMCP contract, where the
lifespan can run per session (per request under Streamable HTTP) and so must not
mutate the tool table.

To register before services exist, tools bind a `PipefyClientProxy`
(`core/container.py`) rather than a concrete `PipefyClient`. The proxy resolves
`container.pipefy_client` on each access, so a service re-initialization (a fresh
client) is picked up without re-registering tools. That is why there is no
repeat-visit bookkeeping: registration never repeats.

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
`mcp_remote_mode` at call time, not via the marker. A tool whose exclusion deserves
a reason gets a plain code comment pointing at its follow-up issue (the attachment
tools point at #305); the exclusion itself needs no annotation.
