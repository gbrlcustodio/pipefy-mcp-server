"""Guard: the SDK public API takes refined value objects, never a config instance.

Encodes the parse-don't-validate rule from ``AGENTS.md`` as an executable check:
the public ``__init__`` exports no ``*Config`` / ``*Settings`` symbol, and the
public entry points (``PipefyClient``, ``build_executors``) annotate no parameter
with such a type. A regression (re-exporting a reader, or widening a signature
back to a config instance) fails here rather than in review.
"""

from __future__ import annotations

import inspect

import pytest

import pipefy_sdk
from pipefy_sdk import PipefyClient
from pipefy_sdk.client import build_executors

_BANNED_SUFFIXES = ("Config", "Settings")


@pytest.mark.unit
def test_public_api_exports_no_config_or_settings_symbol():
    offenders = [name for name in pipefy_sdk.__all__ if name.endswith(_BANNED_SUFFIXES)]
    assert offenders == [], (
        "pipefy_sdk public API must expose refined value objects, not config "
        f"instances; found: {offenders}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "func", [PipefyClient.__init__, build_executors], ids=lambda f: f.__qualname__
)
def test_signatures_take_no_config_instance(func):
    for name, param in inspect.signature(func).parameters.items():
        annotation = str(param.annotation)
        assert not annotation.endswith(_BANNED_SUFFIXES), (
            f"{func.__qualname__} parameter {name!r} is annotated {annotation!r}; "
            "public APIs take refined value objects, never a *Config / *Settings."
        )
