from __future__ import annotations

from typing import Any, Literal, Self

from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_infra import security
from pipefy_infra.config import PipefyTomlConfigSource
from pipefy_sdk import PipefySettings
from pydantic import (
    AliasChoices,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

McpLogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class McpSettings(BaseSettings):
    """MCP-server runtime knobs: transport, tool exposure, and envelope shape.

    These are consumed only by the MCP server, so they live here rather than in
    the SDK's API-connection settings. Fields drop the ``mcp_`` prefix because
    the ``settings.mcp`` namespace already supplies it; ``env_prefix="PIPEFY_MCP_"``
    re-attaches it so the operator-facing ``PIPEFY_MCP_*`` env vars stay
    byte-identical. The shared ``config.toml`` source keys off the bare field
    names, so TOML keys are ``unified_envelope``, ``profile``, ``transport``,
    ``host``, ``port``, ``log_level``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        # Reads the shared config.toml; keys are this class's bare field names.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )

    unified_envelope: bool = Field(
        default=True,
        description=(
            "When true (env: PIPEFY_MCP_UNIFIED_ENVELOPE), migrated MCP tools return "
            "{success, data, message?, pagination?}. When false, legacy shapes. "
            "Read at call time, not cached at import."
        ),
    )

    profile: Literal["local", "remote"] = Field(
        default="local",
        description=(
            "Launch profile (env: PIPEFY_MCP_PROFILE). 'local' (default) registers "
            "every tool and acts as one startup credential. 'remote' exposes ONLY "
            "tools explicitly marked remote-safe (default-deny) and validates an "
            "inbound bearer per request. Read at registration time, a startup "
            "decision, not per call."
        ),
    )

    toolsets: str | None = Field(
        default=None,
        description=(
            "Comma-separated toolset selection (env: PIPEFY_MCP_TOOLSETS), applied "
            "after the remote floor to narrow the exposed surface. Names are "
            "subject domains (workflow, database, interfaces, automation, "
            "intelligence, analytics, governance, integration); 'all'/'default' or "
            "unset keep the full surface. An unknown name is a startup error. "
            "Resolved once at registration, not per call."
        ),
    )

    transport: Literal["stdio", "http"] | None = Field(
        default=None,
        description=(
            "Wire the server speaks (env: PIPEFY_MCP_TRANSPORT). Left unset it "
            "defaults from the profile: 'local' speaks stdio, 'remote' serves over "
            "Streamable HTTP. Set it explicitly to run 'local' over loopback HTTP. "
            "'remote' over stdio is rejected: a per-request bearer has no stdio "
            "equivalent."
        ),
    )

    host: str = Field(
        default="127.0.0.1",
        description=(
            "Bind host for the Streamable HTTP transport (env: PIPEFY_MCP_HOST). "
            "Only consulted when serving over HTTP (--transport http); the stdio "
            "transport ignores it. Under the unauthenticated 'local' profile a "
            "non-loopback bind is refused unless PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND "
            "is set; the authenticated 'remote' profile binds any host."
        ),
    )

    port: int = Field(
        default=8000,
        description=(
            "Bind port for the Streamable HTTP transport (env: PIPEFY_MCP_PORT). "
            "Only consulted when serving over HTTP (--transport http)."
        ),
    )

    log_level: McpLogLevel = Field(
        default="INFO",
        description=(
            "Log level for the FastMCP root logger on stderr "
            "(env: PIPEFY_MCP_LOG_LEVEL). Hosted structured JSON events use a "
            "dedicated logger pinned at INFO and are not governed by this knob. "
            "Accepts DEBUG, INFO, WARNING, ERROR, or CRITICAL; normalized to "
            "uppercase."
        ),
    )

    allow_insecure_http_bind: bool = Field(
        default=False,
        description=(
            "When true (env: PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND), the "
            "unauthenticated 'local' profile may serve HTTP on a non-loopback "
            "host. The escape hatch for exposing the full tool surface with no "
            "inbound bearer to callers that are not on the local machine. The "
            "authenticated 'remote' profile never needs it: it validates a "
            "per-request bearer, so its bind host is unrestricted."
        ),
    )

    allowed_hosts: list[str] | None = Field(
        default=None,
        description=(
            "Extra Host header values the HTTP transport accepts, on top of "
            "loopback and the resource_server_url host (env: "
            "PIPEFY_MCP_ALLOWED_HOSTS as a JSON array). Needed only when a proxy "
            "forwards a public Host that differs from the resource-server URL; the "
            "standard fronted deployment derives its allowlist from "
            "resource_server_url and sets none. An entry matches an exact Host or, "
            "as 'host:*', any port on that host."
        ),
    )

    allowed_origins: list[str] | None = Field(
        default=None,
        description=(
            "Origin header values the HTTP transport accepts (env: "
            "PIPEFY_MCP_ALLOWED_ORIGINS as a JSON array). Unset derives the "
            "scheme://host origins from the allowed hosts; a non-empty array replaces "
            "them with a custom set, and an empty array is the strictest override, "
            "rejecting any request that sends an Origin header."
        ),
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @model_validator(mode="after")
    def _resolve_transport(self) -> Self:
        """Fill the profile-derived transport default and reject 'remote' over stdio.

        Left unset, the transport follows the profile: 'local' speaks stdio,
        'remote' serves over HTTP. 'remote' cannot run over stdio, because it
        validates an inbound bearer per request and stdio carries none. After this
        runs, ``transport`` is always concrete.
        """
        if self.transport is None:
            self.transport = "http" if self.profile == "remote" else "stdio"
        elif self.profile == "remote" and self.transport == "stdio":
            raise ValueError(
                "the 'remote' profile requires the 'http' transport "
                "(a per-request bearer has no stdio equivalent)"
            )
        return self

    @model_validator(mode="after")
    def _enforce_bind_safety(self) -> Self:
        """Refuse to serve the unauthenticated tool surface off loopback.

        The property protected is auth posture, not bind interface: an
        unauthenticated profile must not be reachable by untrusted callers. The
        'local' profile registers every tool and wires no inbound bearer, so
        over HTTP on a non-loopback host it exposes the full surface to whoever
        can reach the port. The 'remote' profile validates a per-request bearer,
        so its bind host is irrelevant and is not checked here (a container
        binds 0.0.0.0 legitimately). Runs after :meth:`_resolve_transport`, so
        ``transport`` is concrete.

        Enforcing at the settings boundary means every serving path inherits the
        guarantee: :func:`build_pipefy_mcp_server` and a caller building the ASGI
        app directly both take a resolved ``Settings``, so none re-checks the bind
        or routes around it.

        ``allow_insecure_http_bind`` is the explicit escape hatch for operators
        who accept an unauthenticated public bind.
        """
        if (
            self.transport == "http"
            and self.profile == "local"
            and not self.allow_insecure_http_bind
            and not security.is_loopback_host(self.host)
        ):
            raise ValueError(
                "the 'local' profile serves every tool with no inbound bearer, "
                f"so it refuses a non-loopback HTTP bind ({self.host!r}). Bind a "
                "loopback host, switch to '--profile remote' with a resource "
                "server to validate per-request callers, or set "
                "PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND to accept an "
                "unauthenticated public bind."
            )
        return self

    @field_validator("allowed_hosts", "allowed_origins", mode="after")
    @classmethod
    def _normalize_allowlist(
        cls, values: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        """Trim entries and reject a blank one; ``None`` stays ``None``.

        Each entry is a Host or Origin the operator vouches for, so surrounding
        whitespace is trimmed (a stray space would break the transport's exact
        match), but a blank entry (an empty string, or an unfilled template value)
        raises rather than being silently dropped: a dropped entry hides the typo,
        and for ``allowed_origins`` it could collapse the list to the strict
        reject-all-Origin posture. An explicitly empty list is a deliberate value
        and is kept. This does not run the internal-host SSRF gate (``localhost``
        is a wanted loopback entry).
        """
        if values is None:
            return None
        cleaned: list[str] = []
        for value in values:
            entry = value.strip()
            if not entry:
                raise ValueError(
                    f"{info.field_name} contains a blank entry; remove it or give "
                    "a real Host/Origin value (an empty list is accepted, a blank "
                    "entry is not)."
                )
            cleaned.append(entry)
        return cleaned


class ResourceServerSettings(BaseSettings):
    """This MCP server's identity as an OAuth protected resource (HTTP profile).

    The resource-server profile activates when ``resource_server_url`` is set: the
    ``remote`` profile's HTTP transport then validates inbound bearers and serves
    RFC 9728 metadata, and the unauthenticated foundation profile is left untouched.

    Token *validation* knobs (issuer, audience, JWKS) are an auth concern and live
    in :class:`pipefy_auth.JwtValidationSettings`, alongside the validator they
    feed. This model carries only what is specific to *this* server's resource
    identity: its public URL and the scopes it requires.

    ``env_prefix="PIPEFY_MCP_RS_"`` does not collide with ``McpSettings``'
    ``PIPEFY_MCP_``: that model has no ``rs_*`` fields, so ``PIPEFY_MCP_RS_*``
    vars fall through its ``extra="ignore"`` gate. ``allow_insecure_urls`` is
    aliased to the shared ``PIPEFY_ALLOW_INSECURE_URLS`` so the whole deployment
    has a single insecure-URL posture.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_MCP_RS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )

    resource_server_url: str | None = Field(
        default=None,
        description=(
            "Public canonical URL of this MCP server as an OAuth protected "
            "resource (env: PIPEFY_MCP_RS_RESOURCE_SERVER_URL). Decoupled from the "
            "bind host, so behind a proxy it is the public origin, not host/port. "
            "Include the /mcp endpoint path, e.g. https://mcp.pipefy.com/mcp: it "
            "becomes the RFC 9728 resource identifier and the base for the "
            "protected-resource metadata route. Setting it activates the profile."
        ),
    )

    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "Scopes a token must carry (env: PIPEFY_MCP_RS_REQUIRED_SCOPES as "
            "JSON). FastMCP returns 403 when any is missing."
        ),
    )

    allow_insecure_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS"),
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS, shared across the "
            "deployment), resource_server_url may use http:// and internal hosts; "
            "local development only."
        ),
    )

    @model_validator(mode="after")
    def _validate_configuration(self) -> Self:
        if self.resource_server_url is None:
            return self
        # Persist the stripped value: surrounding whitespace in an env var would
        # otherwise survive into the RFC 9728 resource identifier. The /mcp
        # endpoint path is expected, so only a query or fragment is forbidden.
        stripped = self.resource_server_url.strip()
        self.resource_server_url = stripped
        security.assert_url_has_no_query_or_fragment(
            stripped, field_label="resource_server_url"
        )
        security.validate_https_url(
            stripped, "resource_server_url", allow_insecure=self.allow_insecure_urls
        )
        return self


class IpaasSettings(BaseSettings):
    """iPaaS (Advanced Automations) connection knobs.

    Per-deployment values consumed only at the composition root: the runtime
    builds the iPaaS gateway from them at startup, and tools reach the built
    gateway through the lifespan context, never these settings (the
    import-linter contract keeps it that way).

    Works out of the box: the default OAuth client is Pipefy's canonical
    *public* PKCE client (``token_endpoint_auth_method: none``), registered
    once on the production iPaaS host — sharable by design, like the
    ``pipefy-cli`` OIDC client. The client id names the software, never the
    caller: authorization is carried entirely by the caller's pipe-scoped
    session and PKCE. Override the id (plus a secret, for a confidential
    registration) for staging or single-tenant hosts; blank the id to disable
    the iPaaS tools, which then answer with a clear "disabled" error.

    ``env_prefix="PIPEFY_IPAAS_"`` keeps these apart from the SDK's
    ``PIPEFY_*`` connection vars. ``allow_insecure_urls`` is aliased to the
    shared ``PIPEFY_ALLOW_INSECURE_URLS`` so the whole deployment has a single
    insecure-URL posture.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPEFY_IPAAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init_kwargs > env > dotenv > config.toml > file_secret.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            PipefyTomlConfigSource(settings_cls),
            file_secret_settings,
        )

    url: str = Field(
        default="https://ipaas.pipefy.com",
        description=(
            "Base URL of the iPaaS (Advanced Automations) host (env: "
            "PIPEFY_IPAAS_URL). The default is the production host the product "
            "already surfaces to users; override for staging or single-tenant "
            "deployments."
        ),
    )

    oauth_client_id: str | None = Field(
        default="1RLshr5qYWxeFda1H-2wI_HuaaQfWxwn",
        description=(
            "Client ID of the OAuth client registered on the iPaaS host "
            "(env: PIPEFY_IPAAS_OAUTH_CLIENT_ID). Defaults to Pipefy's canonical "
            "public PKCE client on the production host — a publishable "
            "identifier, not a secret. Override for staging or single-tenant "
            "hosts; set blank to disable the iPaaS tools."
        ),
    )

    oauth_client_secret: str | None = Field(
        default=None,
        description=(
            "Client secret paired with oauth_client_id "
            "(env: PIPEFY_IPAAS_OAUTH_CLIENT_SECRET). Only needed when the "
            "configured client is a confidential registration "
            "(client_secret_post); the default public client has none. A "
            "secret; never defaulted."
        ),
    )

    oauth_redirect_uri: str = Field(
        default="https://localhost/pipefy-mcp-callback",
        description=(
            "Redirect URI registered on the OAuth client (env: "
            "PIPEFY_IPAAS_OAUTH_REDIRECT_URI). Never followed — the flow is "
            "headless and reads the authorization code out of the approve "
            "response — but it must byte-match one of the client's registered "
            "redirect URIs."
        ),
    )

    allow_insecure_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIPEFY_ALLOW_INSECURE_URLS"),
        description=(
            "When true (env: PIPEFY_ALLOW_INSECURE_URLS, shared across the "
            "deployment), url may use http:// and internal hosts; local "
            "development only."
        ),
    )

    @property
    def configured(self) -> bool:
        """Whether an OAuth client id is present (blank = iPaaS tools disabled)."""
        return bool(self.oauth_client_id and self.oauth_client_id.strip())

    @model_validator(mode="after")
    def _validate_configuration(self) -> Self:
        # Persist the normalized value so the gateway can join paths naively.
        stripped = self.url.strip().rstrip("/")
        self.url = stripped
        security.assert_url_has_no_query_or_fragment(stripped, field_label="url")
        security.validate_https_url(
            stripped, "url", allow_insecure=self.allow_insecure_urls
        )
        return self


class Settings(BaseSettings):
    """Application configuration via pydantic-settings.

    Each nested model owns its own env loading (``env_prefix="PIPEFY_"``).
    The composition deliberately does NOT set ``env_nested_delimiter`` — that
    flag splits any matching env var (e.g. ``AUTH_BASE_URL``) into a nested
    path, which would bypass each model's prefix gate and let unprefixed env
    vars hijack auth fields. Both nested models run their own SSRF / shape
    checks at construction; no parent-side ``_validate_*`` validator is needed.
    """

    model_config = SettingsConfigDict(extra="ignore")

    pipefy: PipefySettings = Field(default_factory=PipefySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    jwt: JwtValidationSettings = Field(default_factory=JwtValidationSettings)
    rs: ResourceServerSettings = Field(default_factory=ResourceServerSettings)
    ipaas: IpaasSettings = Field(default_factory=IpaasSettings)


def resolve_mcp_settings(
    *,
    profile: str | None,
    transport: str | None,
    host: str | None,
    port: int | None,
    toolsets: str | None = None,
) -> Settings:
    """Resolve the full :class:`Settings` honoring the launch flags as init-kwargs.

    The composition root for the serve path, mirroring
    :func:`pipefy_cli.settings.resolve_cli_settings`: the launch flags are folded
    into the ``mcp`` model as init-kwargs, so argv outranks the environment
    (``init_kwargs > env > dotenv > config.toml``, per ``settings_customise_sources``).
    Only the flags actually passed override the environment; the rest fall back to
    ``PIPEFY_MCP_*`` (or the field defaults). The returned ``mcp`` has a concrete
    ``transport`` (the profile-derived default is applied by the model validator).

    The credential, resource-server, and Pipefy models come from the process
    environment (each nested model's own loading), so the caller receives one
    fully-resolved ``Settings`` and reads no process globals.

    Raises:
        ValueError: On an unknown value or an incompatible profile/transport pair
            (e.g. 'remote' over stdio); the message is user-facing.
    """
    init: dict[str, Any] = {}
    if profile is not None:
        init["profile"] = profile
    if transport is not None:
        init["transport"] = transport
    if host is not None:
        init["host"] = host
    if port is not None:
        init["port"] = port
    if toolsets is not None:
        init["toolsets"] = toolsets
    try:
        return Settings(mcp=McpSettings(**init))
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


settings = Settings()

__all__ = [
    "AuthSettings",
    "JwtValidationSettings",
    "McpLogLevel",
    "McpSettings",
    "PipefySettings",
    "ResourceServerSettings",
    "Settings",
    "resolve_mcp_settings",
    "settings",
]
