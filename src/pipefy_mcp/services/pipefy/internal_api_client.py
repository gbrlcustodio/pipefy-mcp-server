"""HTTP client for Pipefy's internal_api endpoint."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from httpx import Timeout
from httpx_auth import OAuth2ClientCredentials

REQUEST_TIMEOUT_SECONDS = 30


class InternalApiClient:
    """HTTP client for Pipefy internal API (AI Automation mutations).

    Uses OAuth2 client credentials for token authentication. Sends GraphQL
    requests as JSON POST to the configured internal_api URL.
    """

    def __init__(
        self,
        url: str,
        oauth_url: str,
        oauth_client: str,
        oauth_secret: str,
    ) -> None:
        """Create an internal API client.

        Args:
            url: URL of the internal_api endpoint (e.g. https://app.pipefy.com/internal_api).
            oauth_url: OAuth token URL.
            oauth_client: OAuth client ID.
            oauth_secret: OAuth client secret.
        """
        for label, val in (("internal_api URL", url), ("OAuth URL", oauth_url)):
            stripped = val.strip().lower()
            if not stripped.startswith("https://"):
                raise ValueError(f"{label} must use HTTPS")
            parsed = urlparse(val.strip())
            if not parsed.hostname:
                raise ValueError(f"{label} must include a hostname")
            if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
                raise ValueError(
                    f"{label} must not point to localhost ({parsed.hostname})"
                )
        self._url = url
        self._auth = OAuth2ClientCredentials(
            token_url=oauth_url,
            client_id=oauth_client,
            client_secret=oauth_secret,
        )

    async def execute_query(self, query: str, variables: dict[str, Any]) -> dict:
        """Execute a GraphQL query/mutation via POST.

        Args:
            query: GraphQL query string.
            variables: Variables for the query.

        Returns:
            Parsed JSON response from the API.

        Raises:
            httpx.HTTPStatusError: When response status is not 2xx.
            httpx.TimeoutException: When the request times out.
            ValueError: When response contains GraphQL errors (HTTP 200 but {"errors": [...]}).
        """
        async with httpx.AsyncClient(
            auth=self._auth,
            timeout=Timeout(timeout=REQUEST_TIMEOUT_SECONDS),
        ) as client:
            response = await client.post(
                self._url,
                json={"query": query, "variables": variables},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            if "errors" in data and data["errors"]:
                error_msgs = []
                for err in data["errors"]:
                    msg = err.get("message", "Unknown error")
                    ext = err.get("extensions", {})
                    code = ext.get("code", "")
                    corr = ext.get("correlation_id", "")
                    # Include extensions for logs and service-layer tests; MCP-facing tools
                    # should omit these suffixes from default user-visible errors.
                    suffix = f" [code={code}]" if code else ""
                    suffix += f" [correlation_id={corr}]" if corr else ""
                    error_msgs.append(f"{msg}{suffix}")
                raise ValueError("; ".join(error_msgs))
            # Unwrap the "data" envelope to match BasePipefyClient.execute_query
            return data.get("data", data)
