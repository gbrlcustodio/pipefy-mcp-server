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
- Base64-over-MCP-transport is reserved for in-memory bytes the agent
  generated and never wrote to disk. For anything on disk, prefer
  `file_path` to avoid the ~33% transport inflation.

If a future distribution profile (self-hosted, streaming, etc.) changes this
trust model, deferred code paths are tagged with `GATED:<PROFILE>` markers.
See below.

## Greppable deployment-profile markers

Convention: `GATED:<PROFILE>` in a code comment marks a code path that is
intentionally absent or restricted in the current deployment but would be
needed under a different profile. Uppercase profile name, no spaces.

Greppable as a family: `rg "GATED:" packages/mcp` lists every
deployment-profile marker in the package.

Today's markers:

- `GATED:SELF_HOSTED` (`tools/attachment_tools.py`): URL-based attachment
  ingestion (`file_url` parameter, SSRF guard, redirect loop, 100 MiB cap)
  was removed because the local distribution doesn't need it. Past code is in
  git history before the commit that introduced this marker. Under a
  self-hosted MCP profile, bring URL ingestion back behind a capability flag
  rather than as unconditional behavior, and read the SSRF policy from
  injected settings (not from a fresh `PipefySettings()` env read).

### When to add a new marker

Add a new `GATED:<PROFILE>` marker when you deliberately delete or omit a
code path that another deployment profile would need. Document the new
profile in this file alongside the existing ones with the same shape:
location, what was removed, when to bring it back, where to find past code.

Don't use `GATED:` for "TODO refactor later" or for incomplete work. Those
belong in issues, not in greppable code markers.
