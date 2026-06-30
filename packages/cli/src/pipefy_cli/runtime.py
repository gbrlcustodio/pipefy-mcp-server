"""Resolve the CLI runtime: parse the environment into value objects (the CLI edge).

This is the CLI's composition root, one of the two that own env reading (the
other is ``pipefy_mcp``). It does not define env readers of its own for the SDK
or auth concerns: those parsers live in the libraries' ``env`` modules. Here we
compose them around the one :class:`~pipefy_infra.deployment.DeploymentConfig`
(applying the CLI flags as overrides) and read the CLI-only ``org_id``.

The result, :class:`CliRuntime`, holds only parsed value objects and primitives
(endpoints, the credential bundle, knobs); no ``*Config`` reader instance escapes
into it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pipefy_auth.env import load_auth
from pipefy_auth.resolver import CredentialSources
from pipefy_infra.env import load_deployment
from pipefy_infra.settings_base import PipefyBaseSettings
from pipefy_sdk.endpoints import PipefyEndpoints
from pipefy_sdk.env import load_sdk
from pydantic import Field, ValidationError
from pydantic_settings import SettingsConfigDict  # noqa: TID251

# Pipefy organization IDs are ASCII numeric strings. ``\d`` is Unicode-aware in
# Python ``re`` (Arabic-Indic / Devanagari would pass), so pin to ``[0-9]``.
_ORG_ID_PATTERN = r"^[0-9]+$"

TokenSource = Literal["flag", "env"]


class CliEdgeSettings(PipefyBaseSettings):
    """CLI-only edge values that are not part of the SDK / auth libraries."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")

    org_id: str | None = Field(default=None, pattern=_ORG_ID_PATTERN)


@dataclass(frozen=True)
class CliRuntime:
    """The resolved CLI runtime: parsed value objects + CLI-only knobs.

    ``token_source`` records whether the static token came from ``--token`` or
    ``PIPEFY_TOKEN`` (for ``pipefy auth status``); it sits beside the credential
    bundle rather than inside it, since the source is a display concern, not part
    of the credential identity.
    """

    endpoints: PipefyEndpoints
    allow_insecure_urls: bool
    reuse_schema: bool
    default_webhook_name: str
    credentials: CredentialSources
    token_source: TokenSource | None
    keychain_backend: str
    org_id: str | None = None


def resolve_cli_runtime(
    *,
    base_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
    token_flag: str | None,
) -> CliRuntime:
    """Resolve :class:`CliRuntime`, composing the library loaders around one deployment.

    The ``--base-url`` / ``--allow-insecure-urls`` flags land as init kwargs on
    the one :class:`DeploymentConfig` (the only place they apply, outranking
    env). The ``--token`` flag overrides ``PIPEFY_TOKEN`` and its origin is
    tracked in ``token_source``.

    Raises:
        ValueError: When validation fails (SSRF guard, bad shape); message is
            user-facing.
    """
    try:
        deployment = load_deployment(
            base_url=base_url_flag, allow_insecure_urls=allow_insecure_urls_flag
        )
        endpoints, allow_insecure_urls, reuse_schema, default_webhook_name = load_sdk(
            deployment
        )
        sources, keychain_backend = load_auth(deployment)
        edge = CliEdgeSettings()
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    cli_token = token_flag.strip() if token_flag else None
    token_source: TokenSource | None
    if cli_token:
        static_token: str | None = cli_token
        token_source = "flag"
    elif sources.static_token:
        static_token = sources.static_token
        token_source = "env"
    else:
        static_token = None
        token_source = None

    credentials = CredentialSources(
        static_token=static_token,
        service_account=sources.service_account,
        oidc_client=sources.oidc_client,
    )

    return CliRuntime(
        endpoints=endpoints,
        allow_insecure_urls=allow_insecure_urls,
        reuse_schema=reuse_schema,
        default_webhook_name=default_webhook_name,
        credentials=credentials,
        token_source=token_source,
        keychain_backend=keychain_backend,
        org_id=edge.org_id,
    )


__all__ = ["CliEdgeSettings", "CliRuntime", "TokenSource", "resolve_cli_runtime"]
