# Uninstalling, and switching channels

`uninstall.sh` reports Pipefy toolkit state across every install channel and MCP client, then removes what you approve. It lives beside `install.sh` at the repository root.

```sh
# Report only. Removes nothing, edits nothing, moves nothing.
curl -LsSf https://raw.githubusercontent.com/pipefy/ai-toolkit/main/uninstall.sh | sh -s -- --scan

# Scan, show the plan it derived, ask for approval in tiers, remove.
curl -LsSf https://raw.githubusercontent.com/pipefy/ai-toolkit/main/uninstall.sh | sh
```

Piping into `sh` still prompts: the script reads its answers from `/dev/tty` when its own stdin is the pipe. Where there is no terminal at all — CI, a provisioning script — pass `--yes`, or the run refuses rather than assuming an answer.

## Scope

In scope: the CLI and MCP server installed as uv tools, MCP registrations in every client config, the Claude Code plugin and its marketplace, the skills `npx skills add` installed, stored credentials, `~/.config/pipefy`, shell completions, and `PIPEFY_*` assignments in your shell rc files and client `env` blocks.

Out of scope: your git checkouts. Uninstalling is about tooling, not source.

## Scan first

`--scan` reads and reports. The only paths it writes are its own tempfiles, and it never runs a client CLI that changes anything.

```sh
./uninstall.sh --scan
```

| Exit | Meaning |
|------|---------|
| `0` | no Pipefy toolkit state found |
| `1` | findings remain |
| `2` | the run itself failed, or a source could not be inspected |

Exit `2` is the one worth reading carefully. Every JSON source — the client configs, the plugin registry, each project `.mcp.json` — is read by a single `python3` program, and without `python3` those sources report `not inspected` rather than `clean`. A partial scan can therefore never be mistaken for a clean machine. The non-JSON sources (`PATH`, the keychain, `~/.config/pipefy`, completions, skills, and the Codex TOML) are inspected with POSIX text tools alone.

Removal needs `python3`. Without it, a teardown planned from a partial scan would leave exactly the state that causes duplicate-registration conflicts, so the run refuses and points at `--scan`.

## A registration is matched on what it runs

The registration key is free text. A real environment had the server registered as `pipefy-dev`, so keying on the name misses exactly the entries that shadow a working one.

Detection is structural and exact — never a substring search for "pipefy", which turns up unrelated hostnames and directory names. An entry matches when **either** of these fires:

- its `command` is `pipefy-mcp-server`, or a known runner (`uvx`, `uv`, `npx`, `python`, `python3`, `pipx`) with `pipefy-mcp-server` as an exact argument
- its URL **host** is exactly `mcp.pipefy.com`

The two fields are read independently, and a declared transport `type` is required for neither. Clients disagree about what a `type`-less entry is: Cursor and Codex read a bare `url` as a remote server, while Claude Code reads an entry with no `type` as stdio and skips it with `has a "url" but no "type"`. Judging the shape by one client's rule would leave a registration the others do run invisible to the scan and alive after a teardown, so the entry is matched as written and the report adds the caveat where it applies — such an entry in Claude Code's config is reported as registered but not running, and is still removed.

Everything else that carries a weak signal — a name in this toolkit's namespace, one of its environment variables, some other Pipefy-shaped HTTP endpoint — is reported as unverified for you to judge, and never removed. The name an entry was really registered under is reported as data, and removal uses that name.

## Teardown

A bare invocation scans, prints the plan it derived from that scan, asks for approval, removes, then scans again — because "uninstalled" has to be an observed fact. A `uv tool uninstall` can succeed while a binary of the same name is still earlier on `PATH`.

### Approval is tiered, not per action

Around twenty individual prompts pushes everyone to `--yes` and loses the safety entirely. There are three:

| Tier | Contents | Undo |
|------|----------|------|
| `[1]` | what this toolkit installed | reinstalling restores it |
| `[2]` | stored credentials | cannot be undone |
| `[3]` | your own files | each is copied to `<file>.bak.<timestamp>` before editing |

Declining a tier leaves everything in it untouched; the run continues with the others.

### Flags

| Flag | Effect |
|------|--------|
| `--scan` | report and exit; changes nothing |
| `--dry-run` | scan, print the plan, exit without removing anything |
| `--yes`, `-y` | approve every tier; required when there is no terminal |
| `--keep-credentials` | skip tier 2 — stored credentials stay where they are |
| `--keep-config` | keep your own configuration: `config.toml`, `.env`, and non-credential `PIPEFY_*` settings in files you wrote |
| `--client <id>` | limit **registration edits** to one client's config (`claude-code`, `claude-desktop`, `codex`, `cursor`, or `none` for no client at all) |
| `--allow-root` | run as root, refused by default |

`--client` narrows what is edited, never what is looked at: detection always sweeps every client, since the point is finding state you forgot about, and tools, credentials, skills and the plugin are not narrowed by it.

### Order

The order is load-bearing, not cosmetic:

1. **Revoke.** Only `pipefy auth logout` reaches the identity provider, and that ability disappears with the tool environment, so it leads. A credential deleted locally but never revoked stays valid at the provider until it expires, and the report says so when that happens.
2. **Credentials.** The local stores, once revocation has had its chance.
3. **Client configs.** Before the tools, so no registration is left pointing at a binary that no longer exists.
4. **Tools.**
5. **Skills.**
6. **Runtime state**, last: `pipefy auth logout` and `pipefy auth status` both recreate `~/.config/pipefy` with a lock file, so clearing it any earlier clears nothing.

`~/.config/pipefy` is removed only if it ends up empty. Its presence after a later `pipefy` invocation is not a failed removal.

## The install receipt, and heuristic mode

`install.sh` appends one record per run to `${XDG_STATE_HOME:-~/.local/state}/pipefy/install-receipt`, including whether it *created* each client registration or found one already there and left it. With that record, teardown removes the entry it made and leaves the entry you made.

Without a receipt the run is in **heuristic mode**, which is permanent rather than transitional: every install made before the receipt existed has none, and only a version of `install.sh` that writes one produces one. Heuristic mode removes less. In a config the installer writes, it deletes a registration only where the value is exactly the single command the installer writes, reports everything else for you to judge, and never treats uv as this toolkit's.

## The stored session lives in one of two places

`PIPEFY_KEYCHAIN_BACKEND=file` puts the session in `~/.config/pipefy/keyring.cfg`; without it, the session is in the OS keychain. Removing that line from a shell rc **moves the store** rather than clearing it: the next login writes to the keychain while anything already in `keyring.cfg` stays there, still signed in and invisible to a keychain-only sweep. The scan resolves and reports the effective backend and checks both stores regardless of which one is active.

## Never removed, by design

- **uv itself**, and the `PATH` lines its installer added to your shell rc. By now other tools depend on it, and a uv tool directory is not uv. Edit those lines yourself if you want them gone.
- **The uv cache.** Never run a bare `uv cache clean`: with no package argument it clears the cache for every package on the machine, and uv hardlinks tool environments into it, so an already-running MCP server breaks with a missing-module error until its client restarts. `uv cache prune` is the safe form, and only while nothing is running.
- **Editable-install entries in the uv cache** (`archive-v0/*_editable_impl_*.pth`). They belong to other repositories' virtualenvs; removing one breaks that checkout until its next sync.
- **A git-tracked `.mcp.json`.** Editing it is not durable — the next checkout, branch switch, or stash pop restores it from the index — so the entry is disabled through `disabledMcpjsonServers` instead.
- **A `pipefy` binary inside a project virtualenv.** It is reported for shadowing purposes and classified as belonging to that checkout.
- **Your git checkouts.**

## Two things that come back

**The marketplace.** Unregistering it is not necessarily durable: a later session re-adds it from a settings file that still lists it under `extraKnownMarketplaces`, or from a plugin that still needs it. Clear those entries too, then confirm with a fresh session rather than trusting the first removal.

**A git-tracked `.mcp.json`.** See above: disable, do not edit.

## Switching channels

There are three ways to run the Pipefy MCP server: the **hosted** HTTPS endpoint, a **local** install (`install.sh`, `uv tool`, or `uvx`), and the **Claude Code plugin**. Register exactly one of them at a time — a duplicate registration under a second name shadows the one you meant to use, and precedence runs local → project → user → plugin-provided → connectors, with the whole entry taken from the winning source and no merging across scopes.

Switching is *remove the old channel, then add the new one*. Scan first to find what is actually registered, since it may not be called `pipefy`:

```sh
./uninstall.sh --scan
```

### To hosted

```sh
claude mcp remove <name> -s user          # the name the scan printed
claude mcp add --transport http --scope user --client-id pipefy-mcp pipefy https://mcp.pipefy.com/mcp
```

Complete the browser login when prompted, or run `claude mcp login pipefy` if the client reports *Needs authentication*. The hosted server exposes the remote-safe surface: everything except the tools whose input is a file on your machine.

Coming from the plugin, uninstall the plugin as well — a plugin-provided server ranks below user scope, so removing only the user-scope entry falls through to the plugin's own `uvx pipefy-mcp-server`:

```text
/plugin uninstall pipefy@pipefy
/plugin marketplace remove pipefy
```

### To a local install

```sh
claude mcp logout <name>                  # hosted OAuth token, per server
claude mcp remove <name> -s user
curl -fsSL https://raw.githubusercontent.com/pipefy/ai-toolkit/main/install.sh \
  | sh -s -- --client cursor              # or claude-code, claude-desktop, codex, none
pipefy auth login
```

`claude mcp logout` clears the stored OAuth credentials for that one server. When the verb is unavailable, run `/mcp`, pick the server, and choose **Clear authentication**. Teardown probes for the verb rather than inferring it from a client version, and falls back to telling you to do it by hand.

### To the plugin

```text
/plugin marketplace add pipefy/ai-toolkit
/plugin install pipefy
/pipefy:install
/pipefy:pipefy-login
```

Remove the hosted or hand-wired registration first, for the same precedence reason.

## Removing pieces by hand

The scan prints this list too, filled in with the names it found:

| Piece | Command |
|-------|---------|
| local install | `uv tool uninstall pipefy-cli pipefy-mcp-server` |
| Claude Code MCP | `claude mcp remove <name> -s user` (also `-s local`) |
| Claude Code plugin | `/plugin uninstall pipefy@pipefy`, then `/plugin marketplace remove pipefy` |
| other clients | delete the `mcpServers.<name>` key, or the `[mcp_servers.<name>]` section for Codex |
| credentials | `pipefy auth logout` |
| hosted OAuth token | `claude mcp logout <name>` |
| macOS keychain item | `security delete-generic-password -s pipefy` |

Use the names the report printed: a registration can be called anything.

## Related

- [`../README.md#installation`](../README.md#installation) — the install paths this reverses
- [`cli/auth.md`](cli/auth.md) — where credentials live, and `pipefy auth logout` in detail
- [`config.md`](config.md) — every `PIPEFY_*` variable the scan looks for
