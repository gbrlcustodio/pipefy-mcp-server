"""Resolve Pipefy + auth settings for the CLI at the application edge.

Env / ``.env`` / ``config.toml`` reading lives in the ``pipefy_infra`` edge
readers (:func:`read_client_env`, :func:`read_auth_env`); this resolver feeds
their raw mappings into the pure value objects, injects the deployment-derived
values, and applies the CLI flags. ``--base-url`` is applied in exactly one
place (the ``read_client_env`` call), and the auth token URL follows from the
SDK ``oauth_token_url`` by injection.

``org_id`` is CLI policy (the SDK never reads it), so it lives on this composite
and is sourced from ``PIPEFY_ORG_ID`` by a small CLI-owned reader.
"""

from __future__ import annotations

from pipefy_auth import AuthSettings
from pipefy_infra.coerce import strip_if_str
from pipefy_infra.config import PipefyBaseSettings, read_auth_env, read_client_env
from pipefy_sdk import ClientSettings
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_settings import SettingsConfigDict

# Pipefy organization IDs are ASCII numeric strings. ``\d`` is Unicode-aware in
# Python ``re`` (Arabic-Indic / Devanagari digits would pass), so pin to [0-9].
_ORG_ID_PATTERN = r"^[0-9]+$"


class _CliEnv(PipefyBaseSettings):
    """Reads the CLI-owned ``PIPEFY_*`` knobs (currently just ``org_id``)."""

    model_config = SettingsConfigDict(env_prefix="PIPEFY_")

    org_id: str | None = Field(default=None)


class CliSettings(BaseModel):
    """Composes :class:`ClientSettings` + :class:`AuthSettings` for CLI use.

    A pure composite the resolver builds; it does not read env itself.
    """

    sdk: ClientSettings
    auth: AuthSettings
    org_id: str | None = Field(
        default=None,
        pattern=_ORG_ID_PATTERN,
        description=(
            "Optional default organization id (numeric string) for CLI commands that "
            "allow an implicit org, e.g. ``pipefy org get`` when the id argument is "
            "omitted (env: PIPEFY_ORG_ID). Must be a numeric string; empty or "
            "non-numeric values are rejected."
        ),
    )

    _strip_org_id = field_validator("org_id", mode="before")(strip_if_str)


def resolve_cli_settings(
    *,
    base_url_flag: str | None,
    allow_insecure_urls_flag: bool | None,
) -> CliSettings:
    """Resolve :class:`CliSettings`, applying CLI flags as overrides.

    The SDK settings are built from :func:`read_client_env` with the flags
    overriding env (the single ``--base-url`` application point); the auth
    settings are built from :func:`read_auth_env` with the SDK-derived OAuth
    token URL and shared insecure-URL posture injected.

    Raises:
        ValueError: When validation fails (e.g. SSRF guard); message is user-facing.
    """
    try:
        sdk = ClientSettings(
            **read_client_env(
                base_url=base_url_flag, allow_insecure=allow_insecure_urls_flag
            )
        )
        auth = AuthSettings(
            **read_auth_env(),
            service_account_token_url=sdk.oauth_token_url,
            allow_insecure_urls=sdk.allow_insecure_urls,
        )
        return CliSettings(
            sdk=sdk, auth=auth, **_CliEnv().model_dump(exclude_unset=True)
        )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


__all__ = ["CliSettings", "resolve_cli_settings"]
