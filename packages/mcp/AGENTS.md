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

Convention: `GATED:<PROFILE>` is a code comment placed on a tool whose
inputs or capabilities are restricted in the current deployment profile and
would be broader under another. Uppercase profile name, no spaces. The
marker annotates a tool that exists today; it is not a deletion changelog.

Greppable as a family: `rg "GATED:" packages/mcp` lists every
deployment-profile marker in the package.

Today's markers:

- `GATED:SELF_HOSTED` on `upload_attachment_to_card` and
  `upload_attachment_to_table_record` in `tools/attachment_tools.py`. These
  tools accept only `file_path` and `file_content_base64` in the
  local-subprocess profile. Under a self-hosted profile they would also
  accept a `file_url`, behind a capability flag, with SSRF and size-cap
  guards initialized from injected settings (not from a fresh
  `PipefySettings()` env read).

### When to add a new marker

Add a `GATED:<PROFILE>` marker on a tool whose surface differs across
deployment profiles. The comment lives next to the tool's registration (or
the relevant restricted parameter) so it reads as an annotation on the tool,
not a paragraph elsewhere in the file. Document the new profile in this
file alongside the existing ones: which tools carry the marker, what they
accept today, what they would accept under the other profile.

If you are merely deleting code that another profile might want later,
that's git history and CHANGELOG territory, not a `GATED:` marker. Re-add
the marker when the gated tool itself returns.
