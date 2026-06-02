"""Unit coverage for ``TokenResponse`` and ``OAuthErrorResponse``."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from pipefy_auth.responses import (
    OAuthErrorResponse,
    TokenResponse,
    _format_validation_error,
)

# --------------------------------------------------------------------------- #
# TokenResponse                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestTokenResponseFromPayload:
    def test_minimal_payload_accepts_defaults(self) -> None:
        token = TokenResponse.from_payload({"access_token": "a", "refresh_token": "r"})
        assert token.access_token == "a"
        assert token.refresh_token == "r"
        assert token.token_type == "Bearer"
        assert token.expires_in is None
        assert token.scope is None
        assert token.id_token is None

    def test_full_payload_round_trips_fields(self) -> None:
        token = TokenResponse.from_payload(
            {
                "access_token": "a",
                "refresh_token": "r",
                "token_type": "Bearer",
                "expires_in": 60,
                "refresh_expires_in": 3600,
                "scope": "openid email",
                "id_token": "ID",
            }
        )
        assert token.expires_in == 60
        assert token.refresh_expires_in == 3600
        assert token.scope == "openid email"
        assert token.id_token == "ID"

    def test_unknown_fields_are_ignored(self) -> None:
        """Keycloak ``not-before-policy`` / ``session_state`` must not raise."""
        token = TokenResponse.from_payload(
            {
                "access_token": "a",
                "refresh_token": "r",
                "not-before-policy": 0,
                "session_state": "abc",
            }
        )
        assert token.access_token == "a"

    @pytest.mark.parametrize("missing", ["access_token", "refresh_token"])
    def test_rejects_missing_required_field(self, missing: str) -> None:
        payload = {"access_token": "a", "refresh_token": "r"}
        del payload[missing]
        with pytest.raises(ValidationError) as info:
            TokenResponse.from_payload(payload)
        assert any(
            missing in str(part) for err in info.value.errors() for part in err["loc"]
        )

    @pytest.mark.parametrize("field", ["access_token", "refresh_token"])
    def test_rejects_empty_required_field(self, field: str) -> None:
        payload = {"access_token": "a", "refresh_token": "r", field: ""}
        with pytest.raises(ValidationError):
            TokenResponse.from_payload(payload)

    @pytest.mark.parametrize("field", ["access_token", "refresh_token"])
    def test_rejects_null_required_field(self, field: str) -> None:
        payload: dict[str, object] = {
            "access_token": "a",
            "refresh_token": "r",
            field: None,
        }
        with pytest.raises(ValidationError):
            TokenResponse.from_payload(payload)

    @pytest.mark.parametrize("field", ["expires_in", "refresh_expires_in"])
    def test_rejects_bool_in_int_fields(self, field: str) -> None:
        """``isinstance(True, int)`` is True; StrictInt must reject this."""
        payload: dict[str, object] = {
            "access_token": "a",
            "refresh_token": "r",
            field: True,
        }
        with pytest.raises(ValidationError):
            TokenResponse.from_payload(payload)

    def test_accepts_null_optional_lifetime(self) -> None:
        token = TokenResponse.from_payload(
            {"access_token": "a", "refresh_token": "r", "expires_in": None}
        )
        assert token.expires_in is None

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            ("scope", "  openid  ", "openid"),
            ("scope", "", None),
            ("scope", "   ", None),
            ("id_token", "  ID  ", "ID"),
            ("id_token", "", None),
        ],
    )
    def test_optional_strings_strip_and_coerce_empty_to_none(
        self, field: str, value: str, expected: str | None
    ) -> None:
        token = TokenResponse.from_payload(
            {"access_token": "a", "refresh_token": "r", field: value}
        )
        assert getattr(token, field) == expected

    @pytest.mark.parametrize("field", ["scope", "id_token"])
    def test_non_string_optional_coerces_to_none(self, field: str) -> None:
        """A numeric scope is a malformed wire value; drop to ``None`` rather than stringify."""
        token = TokenResponse.from_payload(
            {"access_token": "a", "refresh_token": "r", field: 0}
        )
        assert getattr(token, field) is None

    def test_is_frozen(self) -> None:
        token = TokenResponse.from_payload({"access_token": "a", "refresh_token": "r"})
        with pytest.raises(ValidationError):
            token.access_token = "different"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# OAuthErrorResponse                                                          #
# --------------------------------------------------------------------------- #


def _error_response(status: int, body: object) -> httpx.Response:
    """Build an httpx.Response with JSON or raw text content."""
    if isinstance(body, (dict, list)) or body is None:
        return httpx.Response(status_code=status, json=body)
    return httpx.Response(status_code=status, content=str(body).encode())


@pytest.mark.unit
class TestOAuthErrorResponseFromResponse:
    def test_parses_oauth_envelope(self) -> None:
        err = OAuthErrorResponse.from_response(
            _error_response(
                400, {"error": "invalid_grant", "error_description": "stale"}
            )
        )
        assert err.status_code == 400
        assert err.error == "invalid_grant"
        assert err.error_description == "stale"

    def test_non_json_body_yields_no_error_fields(self) -> None:
        err = OAuthErrorResponse.from_response(
            _error_response(502, "<html>upstream down</html>")
        )
        assert err.error is None
        assert err.error_description is None

    def test_non_dict_json_body_yields_no_error_fields(self) -> None:
        err = OAuthErrorResponse.from_response(_error_response(400, ["x"]))
        assert err.error is None
        assert err.error_description is None

    def test_missing_error_field_yields_none(self) -> None:
        err = OAuthErrorResponse.from_response(_error_response(400, {"other": "thing"}))
        assert err.error is None
        assert err.error_description is None

    def test_strips_and_coerces_blank_error_to_none(self) -> None:
        err = OAuthErrorResponse.from_response(
            _error_response(400, {"error": "   ", "error_description": ""})
        )
        assert err.error is None
        assert err.error_description is None

    def test_numeric_error_value_falls_through_to_none(self) -> None:
        """A non-string ``error`` is not OAuth-shaped; drop to ``None`` so callers
        render the fallback rather than crash on ValidationError."""
        err = OAuthErrorResponse.from_response(_error_response(400, {"error": 0}))
        assert err.error is None
        assert (
            err.render(fallback="Refresh failed (HTTP 400)", prefix="Refresh failed")
            == "Refresh failed (HTTP 400)"
        )


@pytest.mark.unit
class TestOAuthErrorResponseRender:
    def test_fallback_when_error_absent(self) -> None:
        err = OAuthErrorResponse(status_code=500, error=None, error_description=None)
        assert err.render(fallback="Generic failure", prefix="X") == "Generic failure"

    def test_prefix_and_error_when_description_absent(self) -> None:
        err = OAuthErrorResponse(
            status_code=400, error="invalid_grant", error_description=None
        )
        assert (
            err.render(fallback="ignored", prefix="Refresh failed")
            == "Refresh failed: invalid_grant"
        )

    def test_prefix_error_and_description(self) -> None:
        err = OAuthErrorResponse(
            status_code=400,
            error="invalid_grant",
            error_description="stale refresh token",
        )
        assert (
            err.render(fallback="ignored", prefix="Refresh failed")
            == "Refresh failed: invalid_grant: stale refresh token"
        )


# --------------------------------------------------------------------------- #
# format_validation_error                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestFormatValidationError:
    def test_renders_loc_and_msg_per_error(self) -> None:
        with pytest.raises(ValidationError) as info:
            TokenResponse.from_payload({})
        rendered = _format_validation_error(info.value)
        assert "access_token" in rendered
        assert "refresh_token" in rendered
        assert "; " in rendered

    def test_no_pydantic_doc_urls_in_output(self) -> None:
        with pytest.raises(ValidationError) as info:
            TokenResponse.from_payload({"access_token": "a", "refresh_token": ""})
        assert "https://" not in _format_validation_error(info.value)
