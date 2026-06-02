# pipefy-infra

Schema-agnostic infrastructure helpers shared by `pipefy-sdk` and `pipefy-auth`. Sits at the bottom of the workspace dependency graph; depends only on stdlib + `pydantic` / `pydantic-settings`.

Adapter layer between Pipefy's application code (`pipefy-sdk`, `pipefy-auth`) and external concerns (filesystem, OS, network boundary). Each submodule owns one bounded context; the package root exposes only `__version__`.

## `pipefy_infra.config`

Pipefy on-disk configuration: where it lives and how it's read.

- `config_dir() -> Path`. Resolves the OS-appropriate config directory (`$XDG_CONFIG_HOME/pipefy` on POSIX, `%APPDATA%\pipefy` on Windows, falling back to `~/.config/pipefy` when `XDG_CONFIG_HOME` is unset).
- `config_file_path() -> Path`. Resolves the TOML file path, honouring the `PIPEFY_CONFIG_FILE` environment override.
- `PipefyTomlConfigSource`. A `pydantic-settings` source that loads top-level TOML keys from `config_file_path()`. The source knows nothing about specific field names; each consuming `BaseSettings` subclass filters via its own field definitions plus `extra="ignore"`.

```python
from pipefy_infra.config import config_dir, config_file_path, PipefyTomlConfigSource
```

## `pipefy_infra.security`

SSRF defenses on URLs destined for outbound HTTP. Layered gates: shape regex at field declaration, synchronous internal-IP check at settings construction, asynchronous DNS-rebinding check at request time.

- `URL_SHAPE_PATTERN`. Regex for `Field(..., pattern=...)` on URL settings fields.
- `validate_https_url(url, field_label, *, allow_insecure=False)`. Synchronous scheme + literal-IP gate. Enforces HTTPS and rejects literal IPs in private/loopback/link-local/multicast/reserved/unspecified ranges. With `allow_insecure=True` (driven by `PIPEFY_ALLOW_INSECURE_URLS`) both http and the literal-IP gate are skipped for dev mode; production callers must follow up with the async DNS gate.
- `assert_hostname_is_not_internal(hostname, *, context)`. Rejects localhost and literal IPs in blocked ranges.
- `assert_hostname_resolves_to_public_ips(hostname)`. Asynchronous DNS gate used right before issuing a request; defends against DNS-rebinding.
- `validate_and_assert_public_url(url, *, field_label, allow_insecure=False) -> str`. Composite helper that runs the sync gate plus the DNS gate in one call and returns the validated hostname. Use from any new outbound-URL surface.
- `assert_url_is_host_root(url, *, field_label)`. Rejects non-root paths (including `//`, `///`), query strings, and fragments. For base-URL fields that derive endpoints via f-string concatenation.
- `assert_url_has_no_query_or_fragment(url, *, field_label)`. Path is allowed; rejects only query and fragment. For URLs that legitimately have a path (OIDC issuer URLs with a realm path) but where a stray query/fragment would corrupt downstream concatenation.

This is the **SSRF audit namespace**: import the module and call through it so every call site is greppable for audits, matching the stdlib idiom (`hmac.compare_digest`, `secrets.token_urlsafe`).

```python
from pipefy_infra import security

security.validate_https_url(url, "graphql_url", allow_insecure=False)
await security.assert_hostname_resolves_to_public_ips(host)
```

## Field definitions

This package owns **no schema**. Field definitions live with the settings models that use them (`pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`).
