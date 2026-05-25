# CLI authentication

See also the **[CLI docs index](README.md)** and **[`docs/setup.md`](../setup.md)** for the broader `PIPEFY_*` env-var story.

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

Every tier wires the `InternalApiClient` against `PIPEFY_INTERNAL_API_URL` when that variable is set, so features that go through the internal API (AI agent automations, some relation flows) work from any path — not just the service-account one.

If `pipefy auth login` succeeds but a higher-precedence source is set in your shell env, the CLI prints a one-line note so you know your stored session is being shadowed.

---

## Quick start

### Interactive (you, in a browser)

Use this when you want commands to run **as your Pipefy user** — useful for parity with the app's permission model and for AI-automation features that need a real user identity.

```bash
export PIPEFY_AUTH_URL=https://signin.pipefy.com/realms/pipefy
export PIPEFY_GRAPHQL_URL=https://app.pipefy.com/graphql

uv run pipefy auth login
```

This opens your browser, completes an OAuth 2.0 Authorization Code + PKCE flow against the Pipefy identity provider, and writes the resulting session (access token + refresh token + minimal metadata) into your OS keychain.

After login, every other `pipefy <cmd>` invocation transparently reuses that session and refreshes the access token on demand.

### Service account (non-interactive)

Use this for CI, scripts, MCP servers, and any context where opening a browser isn't an option. Get the client id and secret from **Pipefy Admin → Service Accounts** and put them in `.env` at the repo root:

```env
PIPEFY_GRAPHQL_URL=https://app.pipefy.com/graphql
PIPEFY_INTERNAL_API_URL=https://app.pipefy.com/internal_api
PIPEFY_SERVICE_ACCOUNT_URL=https://app.pipefy.com/oauth/token
PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=<SERVICE_ACCOUNT_CLIENT_ID>
PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=<SERVICE_ACCOUNT_CLIENT_SECRET>
```

The CLI loads `.env` from the current working directory; see [`docs/setup.md`](../setup.md) for the full Pydantic precedence rules.

> **Legacy names:** `PIPEFY_OAUTH_URL`, `PIPEFY_OAUTH_CLIENT`, and `PIPEFY_OAUTH_SECRET` are still honored (with a one-shot stderr deprecation warning) for back-compat. They will be removed in a future beta. See [`docs/MIGRATION.md`](../MIGRATION.md#service-account-env-var-rename).

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
| `PIPEFY_GRAPHQL_URL` | All commands | Public GraphQL endpoint. Required for any GraphQL call (default in `.env.example`). |
| `PIPEFY_TOKEN` | Tier 2 | Direct bearer token. Overridden by `--token`. |
| `PIPEFY_SERVICE_ACCOUNT_URL` | Tier 3 | Service-account token URL (e.g. `https://app.pipefy.com/oauth/token`). |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` | Tier 3 | Service-account client id. |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` | Tier 3 | Service-account client secret. |
| `PIPEFY_INTERNAL_API_URL` | Tier 3 | Internal GraphQL endpoint for AI automations / some relation flows. Required for those tools only. |
| `PIPEFY_AUTH_URL` | Tier 4 | **OIDC issuer URL** for interactive login. The CLI appends `/.well-known/openid-configuration` to discover the authorization and token endpoints. **`pipefy auth login` and `pipefy auth logout` fall back to `https://signin.pipefy.com/realms/pipefy` (Pipefy production IdP) when this variable is unset**; set it explicitly to point at a non-prod IdP or to opt into stored-session tier resolution in `pipefy auth status` / the MCP server / the SDK (which leave the tier inactive when the variable is unset). |
| `PIPEFY_AUTH_CLIENT_ID` | Tier 4 | Public client id registered for the CLI. Defaults to `pipefy-cli`. |

`PIPEFY_SERVICE_ACCOUNT_URL` and `PIPEFY_AUTH_URL` are **not** interchangeable: the first is a token URL for client-credentials, the second is an OIDC issuer URL for the user-login flow.

### Global flags

| Flag | Effect |
|------|--------|
| `--token <bearer>` | Tier 1 bearer. Overrides `PIPEFY_TOKEN` if both are set. |
| `--graphql-url <url>` | Override `PIPEFY_GRAPHQL_URL` for this process. |
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
  "refresh_expires_at": "2026-06-19T18:02:00Z",   // ISO 8601, null when not stored-session
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

The command always clears the local keychain entry once it runs, even when the IdP round-trip fails. The two non-happy paths surface a stderr warning so the user knows whether server-side revocation succeeded:

- **Revocation network / non-2xx failure** — stderr `Could not revoke refresh token at the IdP: <reason>. Clearing local session anyway; the refresh token may remain valid at the server until natural expiry.`
- **IdP doesn't advertise `end_session_endpoint`** — stderr `Pipefy auth server does not advertise a logout endpoint; the refresh token could not be revoked server-side. Clearing local session only.` (OIDC Discovery 1.0 makes the field optional; Keycloak ships it.)

When no session is stored, `pipefy auth logout` prints `Not signed in. Nothing to do.` and exits 0 — idempotent, matching `gh auth logout` and similar CLIs.

##### Exit codes

| Case | Exit |
|------|------|
| `PIPEFY_AUTH_URL` is unset | **2** — same gate as `pipefy auth login`. |
| No session stored (no-op) | **0** |
| Session cleared (revoke succeeded, failed, or unsupported) | **0** |

### Pipefy issuer URLs

| Environment | `PIPEFY_AUTH_URL` |
|-------------|--------------------|
| Production | `https://signin.pipefy.com/realms/pipefy` |
| Validation (piporacle) | `https://signin-piporacle.pipefy.com/realms/st-piporacle-pud1m` |

Pair each issuer with the matching `PIPEFY_GRAPHQL_URL` (`https://app.pipefy.com/graphql` for prod, `https://piporacle.pipefy.com/graphql` for piporacle).

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

### `PIPEFY_AUTH_URL is required for pipefy auth login`

You haven't set the issuer URL. Use the value from [Pipefy issuer URLs](#pipefy-issuer-urls). The same env var also gates whether tier 4 can fire from any other command — without it, the CLI never consults the keychain.

### `Login succeeded but the session could not be stored in your OS keychain (<backend>)`

The login worked but `keyring` couldn't write the entry. On macOS / Windows this is rare. On headless Linux it usually means no Secret Service daemon is running — install `gnome-keyring` or `kwallet`, or fall back to a static `PIPEFY_TOKEN`.

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

`keyring` selects an OS backend automatically: macOS Keychain on Darwin, Credential Manager on Windows, Secret Service (gnome-keyring / kwallet) on Linux. `pipefy auth login` prints the resolved backend name on success so you can confirm where the entry landed.
