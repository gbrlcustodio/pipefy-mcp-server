# CLI authentication

See also the **[CLI docs index](README.md)** and **[`docs/config.md`](../config.md)** for the broader `PIPEFY_*` env-var story and the optional `~/.config/pipefy/config.toml` file that pins defaults across CLI and MCP invocations. To find and remove every credential this toolkit stored, whichever backend holds it, see **[`docs/uninstall.md`](../uninstall.md)**.

The `pipefy` CLI accepts authentication from four sources. This page covers all of them, how the CLI picks one, and how to recover when something goes wrong.

## Contents

- [Credential precedence](#credential-precedence)
- [Quick start](#quick-start)
- [Reference](#reference)
- [Headless / SSH](#headless--ssh)
- [Troubleshooting](#troubleshooting)
- [How it works](#how-it-works)

---

## Credential precedence

Most-explicit wins. The CLI walks this list top-down and stops at the first source it can resolve:

| # | Source | Identity | Notes |
|---|--------|----------|-------|
| 1 | `--token <bearer>` | Whoever owns the token | Skips OAuth entirely |
| 2 | `PIPEFY_TOKEN` env var | Whoever owns the token | Same path as `--token` |
| 3 | `PIPEFY_SERVICE_ACCOUNT_*` triple | Service account | OAuth2 client-credentials grant |
| 4 | Stored user session | You (the signed-in user) | Eager refresh inside a 60 s leeway window |

Every tier wires the `InternalApiClient` against `<PIPEFY_BASE_URL>/internal_api` (derived from `PIPEFY_BASE_URL`), so features that go through the internal API (AI agent automations, some relation flows) work from any path — not just the service-account one.

If `pipefy auth login` succeeds but a higher-precedence source is set in your shell env, the CLI prints a one-line note so you know your stored session is being shadowed.

---

## Quick start

### Interactive (you, in a browser)

Use this when you want commands to run **as your Pipefy user** — useful for parity with the app's permission model and for AI-automation features that need a real user identity.

```bash
uv run pipefy auth login
```

`PIPEFY_BASE_URL` defaults to `https://app.pipefy.com` (drives the four API endpoints) and `PIPEFY_AUTH_URL` defaults to `https://signin.pipefy.com/realms/pipefy` (the OIDC issuer). Export non-prod values only when targeting a non-prod environment.

This opens your browser, completes an OAuth 2.0 Authorization Code + PKCE flow against the Pipefy identity provider, and writes the resulting session (access token + refresh token + minimal metadata) into your OS keychain.

After login, every other `pipefy <cmd>` invocation transparently reuses that session and refreshes the access token on demand.

### Service account (non-interactive)

Use this for CI, scripts, MCP servers, and any context where opening a browser isn't an option. Get the client id and secret from **Pipefy Admin → Service Accounts** and put them in `.env` at the repo root:

```env
PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=<SERVICE_ACCOUNT_CLIENT_ID>
PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=<SERVICE_ACCOUNT_CLIENT_SECRET>
# Non-prod environments only:
# PIPEFY_BASE_URL=https://<your-api-host>
# PIPEFY_AUTH_URL=https://<your-signin-host>/realms/<realm>
```

The CLI loads `.env` from the current working directory; see [`docs/config.md#precedence`](../config.md#precedence) for the full pydantic-settings precedence rules.

> **Legacy names:** `PIPEFY_OAUTH_CLIENT` and `PIPEFY_OAUTH_SECRET` are still honored (with a one-shot stderr deprecation warning) for back-compat. They will be removed in a future beta. `PIPEFY_OAUTH_URL` has no alias — the OAuth token endpoint now derives from `PIPEFY_BASE_URL`. See [`docs/MIGRATION.md`](../MIGRATION.md#service-account-env-var-rename).

### Static bearer (one-off)

For a single command — or to override the precedence chain on the fly:

```bash
uv run pipefy --token "$MY_BEARER" pipe list
# or
PIPEFY_TOKEN="$MY_BEARER" uv run pipefy pipe list
```

`--token` wins over every other source, including a stored session and `PIPEFY_SERVICE_ACCOUNT_*`.

---

## Reference

### Environment variables

| Key | Used by | Effect |
|-----|---------|--------|
| `PIPEFY_BASE_URL` | All commands | Pipefy API host root. Defaults to `https://app.pipefy.com`. Drives the GraphQL, internal-API, interfaces, and service-account OAuth token URLs (all four are computed from this base). Set to a different host for non-prod / regional / proxy / local-dev deployments. |
| `PIPEFY_AUTH_URL` | Tier 4 | Full OIDC issuer URL for interactive login. The CLI appends `/.well-known/openid-configuration` to discover the authorization and token endpoints. Defaults to `https://signin.pipefy.com/realms/pipefy`. Set to the full issuer URL for a non-prod IdP. |
| `PIPEFY_TOKEN` | Tier 2 | Direct bearer token. Overridden by `--token`. |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` | Tier 3 | Service-account client id. |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` | Tier 3 | Service-account client secret. |
| `PIPEFY_AUTH_CLIENT_ID` | Tier 4 | Public client id registered for the CLI. Defaults to `pipefy-cli`. |
| `PIPEFY_DISABLE_STORED_SESSION` | Tier 4 | When `1` / `true`, the stored-session tier is skipped end-to-end: tier resolution never probes the keychain, and `pipefy auth login` / `pipefy auth logout` refuse with exit code 2. Use to avoid the keyring backend-discovery cost on cold start (headless Linux, CI) or to opt out of OS-keychain storage entirely. TOML key: `disable_stored_session`. |
| `PIPEFY_KEYCHAIN_BACKEND` | Tier 4 | Active `keyring` backend. `auto` (default) uses OS-keyring discovery; `file` swaps to a plaintext on-disk keyring under `~/.config/pipefy/keyring.cfg` (POSIX) / `%APPDATA%/pipefy/keyring.cfg` (Windows). TOML key: `keychain_backend`. |

The service-account OAuth token URL (Tier 3) and the OIDC issuer URL (Tier 4) are **not** interchangeable: the first is `<base>/oauth/token` for client-credentials, the second is the full OIDC discovery root for the user-login flow.

**Empty / malformed values raise.** Any `PIPEFY_*` env var that does not match its pattern is rejected at settings load. Unset the variable to fall back to the default.

### Global flags

| Flag | Effect |
|------|--------|
| `--token <bearer>` | Tier 1 bearer. Overrides `PIPEFY_TOKEN` if both are set. |
| `--base-url <url>` | Override `PIPEFY_BASE_URL` for this process. |
| `--allow-insecure-urls` | Allow `http://` and private hosts for this process (dev only). |

### Commands

| Command | Status | Notes |
|---------|--------|-------|
| `pipefy auth login` | Available | Browser-based PKCE login; persists the session in the OS keychain. |
| `pipefy auth status` | Available | Print which auth source is active, identity, and session expiry. |
| `pipefy auth logout` | Available | Revoke the refresh token at the IdP and clear the stored session. |

#### `pipefy auth login` flags

| Flag | Default | Effect |
|------|---------|--------|
| `--no-browser` | _off_ | Print the authorization URL to stdout instead of trying to launch a browser. |
| `--callback-timeout <s>` | `180.0` | Seconds to wait for the browser callback (minimum 5). |

#### `pipefy auth status` flags

| Flag | Default | Effect |
|------|---------|--------|
| `--json` / `-j` | _off_ | Emit a stable JSON schema instead of human-readable text. |

The command answers four diagnostic questions: am I signed in, as whom, via which precedence tier, and (for stored sessions) when does the access/refresh token expire. It also reports which *other* credential sources are configured, so a CI failure where `PIPEFY_SERVICE_ACCOUNT_*` masks a stored login is one command away from being obvious.

##### JSON schema

```jsonc
{
  "signed_in": true,
  "identity": {"email": "user@pipefy.com", "name": "Pipefy User"},
  "auth_source": "stored-session",                // or "flag-token" | "env-token" | "service-account" | "none"
  "detected_sources": ["stored-session"],         // every configured source (winner + masked)
  "issuer": "https://signin.pipefy.com/realms/pipefy",
  "state": "active",                              // or "refresh-expired" | "needs-login" | "n/a"
  "access_expires_at": "2026-05-20T22:14:03Z",    // ISO 8601, null for static-bearer
  "refresh_expires_at": "2026-06-19T18:02:00Z",   // ISO 8601; null when not a stored session, or when the IdP advertises no refresh-token expiry (refresh_expires_in: 0)
  "token_rejected": false,                        // true only when the identity `me` query returned 401
  "keychain_backend": "Keyring",                  // null for non-stored-session sources
  "masking_env_vars": []                          // env vars masking a stored session, if any
}
```

The shape is stable across all sources (fields you don't have are `null` rather than absent), so a script can `jq .auth_source` without branching on which tier is active.

##### Exit codes

| Case | Exit |
|------|------|
| `auth_source == "none"` | **2** — same code as a domain command that fails on missing credentials. |
| Stored session present but refresh grant rejected (`state` ∈ {`refresh-expired`, `needs-login`}) | **2** |
| Signed in, but the identity `me` query returned 401 or transport-failed | **1** |
| Signed in, identity fetched successfully | **0** |

#### `pipefy auth logout`

POSTs the stored refresh token to the IdP's `end_session_endpoint` (advertised in the OIDC discovery document) and removes the keychain entry. Without server-side revocation the refresh token would remain valid at the IdP until natural expiry — anyone who recovered it from a backup could still mint new access tokens.

Whether there is anything to clear is decided by the **presence** of a keychain entry, not by whether that entry parses: a stale, corrupt, or schema-drifted entry is still a credential on disk and is removed. The command always clears the local entry once it runs, even when the IdP round-trip fails. The non-happy paths surface a stderr warning so the user knows whether server-side revocation succeeded:

- **Revocation network / non-2xx failure** — stderr `Could not revoke refresh token at the IdP: <reason>. Clearing local session anyway; the refresh token may remain valid at the server until natural expiry.`
- **IdP doesn't advertise `end_session_endpoint`** — stderr `Pipefy auth server does not advertise a logout endpoint; the refresh token could not be revoked server-side. Clearing local session only.` (OIDC Discovery 1.0 makes the field optional; Keycloak ships it.)
- **Entry present but unreadable** — revocation needs a readable refresh token, so the entry is delete-only: stdout `Removed an unreadable Pipefy session entry (<issuer>).` and stderr `The stored session entry could not be read, so its refresh token could not be revoked at the IdP; that token remains valid at the server until natural expiry.` Nothing was revoked server-side, so the unrevoked refresh token stays usable at the IdP until it expires on its own.
- **Keychain read failed and nothing was deleted** — presence could not be established, so the command claims neither removal nor a clean machine: stderr `Could not read the keychain to check for a stored session (<issuer>), and no entry was removed. A credential may still be present; check for it manually via your OS keychain (service: 'pipefy').` and exit 1.

When no entry is stored, `pipefy auth logout` prints `Not signed in. Nothing to do.` and exits 0 — idempotent, matching `gh auth logout` and similar CLIs.

##### Exit codes

| Case | Exit |
|------|------|
| `PIPEFY_AUTH_URL=""` (or any other `PIPEFY_*` env var set to empty) | **2** — pydantic rejects empty values at settings load. Unset the var to fall back to the prod default. |
| No entry stored (no-op) | **0** |
| Session cleared (revoke succeeded, failed, or unsupported) | **0** |
| Unreadable entry cleared (no server-side revoke) | **0** |
| Keychain rejected the delete | **1** — the credential may survive; the message names the manual removal step. |
| Keychain read failed and no entry was deleted | **1** — presence unknown, so neither removal nor "nothing to do" can be claimed. |

### Pipefy issuer URLs

Production: `https://signin.pipefy.com/realms/pipefy` (the `PIPEFY_AUTH_URL` default). For a non-prod IdP, set `PIPEFY_AUTH_URL` to the full issuer URL (host + realm) directly — the CLI doesn't try to derive it from any tenant convention.

---

## Headless / SSH

The PKCE flow needs a loopback HTTP server on `127.0.0.1:<ephemeral>` and a browser that can reach it. SSH sessions and headless boxes break both assumptions.

Options today:

1. **Run `pipefy auth login` on your laptop**, then copy `.env` plus the relevant secrets over. The keychain entry itself doesn't transfer between machines.
2. **Use a service account** (`PIPEFY_SERVICE_ACCOUNT_*`) on the headless box — this is the canonical answer for CI and servers.
3. **Static bearer** via `PIPEFY_TOKEN` for short-lived debugging.

Forthcoming: an OAuth 2.0 Device Authorization Grant (`pipefy auth login --device`) that swaps the loopback callback for a code you paste into a browser elsewhere. Tracked in issue #138.

---

## Troubleshooting

### `Stored Pipefy session could not be refreshed: <reason>`

The keychain has a session but its refresh token won't exchange. Most common causes: the refresh token's absolute lifetime expired, you signed out of the IdP, or the issuer URL changed (e.g. you switched between prod and piporacle without re-logging). Re-run `pipefy auth login`.

### `String should match pattern '<regex>'` (any `PIPEFY_*` env var)

Every `PIPEFY_*` env var is validated against a semantically meaningful regex at settings load — URL env vars (`PIPEFY_BASE_URL`, `PIPEFY_AUTH_URL`) must start with `http(s)://`, credentials must not begin/end with whitespace, `PIPEFY_ORG_ID` must be a numeric string. Empty / blank / specially-charactered values are rejected at construction — there's no overload of `PIPEFY_<NAME>=""` for opt-out semantics. To turn the stored-session tier off without unsetting `PIPEFY_AUTH_URL`, use `PIPEFY_DISABLE_STORED_SESSION=1` (see [Keychain backends](#keychain-backends)). Otherwise unset the variable to fall back to the prod default (for URLs) or to leave the tier unconfigured (for credentials). The error message names the offending field plus the violated pattern.

> **`VAR= command` is not "unset".** A shell command-prefix assignment (`PIPEFY_AUTH_URL= pipefy auth status`) sets the variable to the empty string for the child process; it does **not** unset it. Pydantic then rejects the empty value and the command exits with a `ValidationError`. To actually unset a variable for a single command, use `env -u VAR command` (POSIX one-shot, leaves the parent shell untouched):
>
> ```sh
> env -u PIPEFY_AUTH_URL pipefy auth status
> ```
>
> To unset for the remainder of the current shell session, `unset PIPEFY_AUTH_URL` (bash / zsh) or `set -e PIPEFY_AUTH_URL` (fish).

### `Login succeeded but the session could not be stored in your keychain (<backend>)`

The login worked but `keyring` couldn't write the entry.

**macOS (Keychain / `Keyring` backend).** OAuth can succeed while persistence fails with `Can't store password on keychain: (-25244, 'Unknown Error')`. That code is `errSecInvalidOwnerEdit` from Security.framework ("Invalid attempt to change the owner of this item") — not `errSecParam` (`-50`). The `keyring` macOS backend deletes any existing item and re-adds it on every write, so a stale entry created by another Python binary (for example a previous `uvx` cache path, or a login from Terminal.app followed by a write from an IDE/agent host) can surface this error. The root cause is not fully pinned; treat the steps below as remediation, not a proven mechanism.

1. Clear the entry with `pipefy auth logout`, which removes a stored entry even when that entry can no longer be parsed. If it fails, remove the entry directly with `security delete-generic-password -s pipefy`.
2. Run `pipefy auth login` again.
3. Prefer running that login from a regular **Terminal.app** session; if macOS prompts for keychain access, click **Always Allow**.
4. If the OS keychain remains unusable, set `PIPEFY_KEYCHAIN_BACKEND=file` (plaintext under the Pipefy config directory) or use a static `PIPEFY_TOKEN`.

Stable installs (`uv tool install` / wheel) keep a stable Python binary path across runs; with `uvx`, a path change after `uvx --refresh` or a uv version bump can recreate a cross-binary ownership mismatch and require clearing the entry again.

**Linux (headless / CI).** Usually no Secret Service daemon — install `gnome-keyring` or `kwallet`, set `PIPEFY_KEYCHAIN_BACKEND=file` for a plaintext file backend under the Pipefy config directory, or use a static `PIPEFY_TOKEN`.

**Windows.** Credential Manager may reject the write (including from non-interactive callers). Run `pipefy auth login` once from an interactive Command Prompt or PowerShell window, or use `PIPEFY_KEYCHAIN_BACKEND=file` / `PIPEFY_TOKEN`.

When `PIPEFY_KEYCHAIN_BACKEND=file` is active the backend reports as `PlaintextKeyring` and the CLI hint switches to a config-directory writability check (the file backend writes to `keyring.cfg` under the resolved config directory).

### `Missing Pipefy authentication. Set PIPEFY_TOKEN, configure PIPEFY_SERVICE_ACCOUNT_*, or run \`pipefy auth login\`.`

No source resolved. Pick one from [Credential precedence](#credential-precedence). You can also pass `--token <bearer>` for a one-off override.

### `Note: PIPEFY_SERVICE_ACCOUNT_* is set in your environment; other pipefy commands will continue to use it ...`

You ran `pipefy auth login` successfully, but a higher-precedence source is set in your shell. That source will keep being used until you unset it. Common when a `.env` file sets `PIPEFY_SERVICE_ACCOUNT_*` and the user expects the stored session to take over. During the deprecation window the warning fires identically for the legacy `PIPEFY_OAUTH_*` triple, naming whichever form is actually set.

### Identity mismatch (commands run as the wrong user)

Run `whoami`-style queries (e.g. `pipefy graphql exec --query '{ me { email name } }'`) to confirm which identity the CLI is actually using. If you expected your own user but see a service account, check whether `--token`, `PIPEFY_TOKEN`, or a complete `PIPEFY_SERVICE_ACCOUNT_*` triple (or the legacy `PIPEFY_OAUTH_*` form) is set in your environment — any of them outranks the stored session.

### `State mismatch on OAuth callback (possible CSRF)`

The browser came back with a different `state` than the CLI sent. Re-run `pipefy auth login`. If it happens repeatedly, suspect a stale browser tab from a previous login attempt.

---

## How it works

### Login (`pipefy auth login`)

1. Read `PIPEFY_AUTH_URL` (issuer) and `PIPEFY_AUTH_CLIENT_ID` (default `pipefy-cli`).
2. Fetch `<issuer>/.well-known/openid-configuration` to discover the authorization and token endpoints.
3. Bind a loopback socket on `127.0.0.1:<ephemeral>` **before** opening the browser (so no other process can grab the port mid-flight).
4. Open the browser at the authorization URL with `code_challenge_method=S256` and scopes `openid profile email offline_access` (the last one is what makes the IdP issue a refresh token).
5. The IdP redirects back to the loopback callback with `?code=...&state=...`.
6. The CLI verifies `state`, POSTs the code + PKCE verifier to the token endpoint, and persists the response in the OS keychain.

The stored shape is keyed by `(issuer_host, client_id)` — one active session per (IdP, client) pair, per machine. Re-running `pipefy auth login` against the same issuer replaces the previous entry.

### Eager refresh

Each `pipefy <cmd>` invocation calls `ensure_fresh_session` before building the client. If the access token has less than **60 s** of life left, the CLI POSTs `grant_type=refresh_token` to the token endpoint, persists the rotated tokens back to the keychain, and uses the new access token. Failure surfaces as `Stored Pipefy session could not be refreshed: ...`, with no fallback to other tiers — the precedence chain is evaluated before refresh, so if the user explicitly chose tier 4 they get a hard "re-login" signal rather than a silent service-account swap.

Reactive refresh-on-401 (for tokens revoked mid-session) is a separate slice, tracked in issue #137.

### Keychain backends

`keyring` selects an OS backend automatically: macOS Keychain on Darwin, Credential Manager on Windows, Secret Service (gnome-keyring / kwallet) on Linux. `pipefy auth login` prints the resolved backend name on success so you can confirm where the entry landed; `pipefy auth status` reports it as `Keychain: <BackendName>`.

#### Opting out of the OS keychain

Two env vars (mirrored as TOML keys) override the default behaviour:

- `PIPEFY_DISABLE_STORED_SESSION=1` skips the keychain entirely. `pipefy auth login` refuses with exit 2, tier resolution never probes the backend, and `pipefy auth status` omits the `stored-session` tier. Use when only `PIPEFY_TOKEN` / `PIPEFY_SERVICE_ACCOUNT_*` matter (CI runners, automation) and the cold-start keyring backend-discovery cost (~30-80 ms on Darwin, more on a Linux box with no Secret Service daemon) is undesirable.

- `PIPEFY_KEYCHAIN_BACKEND=file` swaps the active backend to a plaintext on-disk keyring under `config_dir() / "keyring.cfg"` (`~/.config/pipefy/keyring.cfg` on POSIX, `%APPDATA%/pipefy/keyring.cfg` on Windows). Unblocks headless Linux without Secret Service. **The file is plaintext, not OS-secured**: anyone with read access to the file (including a co-tenant on a shared CI runner) reads the refresh token. Opt-in only.

These are independent: `PIPEFY_DISABLE_STORED_SESSION=1` takes precedence (the file backend is never read or written). `pipefy auth status` will reflect the active backend name regardless (`Keyring`, `PlaintextKeyring`, etc.).

Removing `PIPEFY_KEYCHAIN_BACKEND=file` **moves** the store rather than clearing it: the next login writes to the OS keychain while whatever is already in `keyring.cfg` stays there, still signed in and invisible to a keychain-only sweep. `./uninstall.sh --scan` resolves the effective backend and reads both stores regardless of which one is active — see [`docs/uninstall.md`](../uninstall.md).
