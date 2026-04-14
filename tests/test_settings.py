"""Tests for ``Settings`` / ``PipefySettings`` (env loading and coercion)."""

import pytest

from pipefy_mcp.settings import PipefySettings, Settings


@pytest.mark.unit
def test_service_account_ids_defaults_to_empty_list():
    assert PipefySettings().service_account_ids == []


@pytest.mark.unit
def test_service_account_ids_accepts_list_and_strips_whitespace():
    settings = PipefySettings(service_account_ids=["  id1  ", "id2"])
    assert settings.service_account_ids == ["id1", "id2"]


@pytest.mark.unit
def test_service_account_ids_accepts_comma_separated_string():
    settings = PipefySettings(service_account_ids="alpha, beta ,gamma")
    assert settings.service_account_ids == ["alpha", "beta", "gamma"]


@pytest.mark.unit
def test_service_account_ids_from_env_comma_separated(monkeypatch):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_IDS", "user-1,user-2, user-3 ")
    settings = Settings()
    assert settings.pipefy.service_account_ids == ["user-1", "user-2", "user-3"]


@pytest.mark.unit
def test_service_account_ids_empty_env_is_empty_list(monkeypatch):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_IDS", "")
    settings = Settings()
    assert settings.pipefy.service_account_ids == []
