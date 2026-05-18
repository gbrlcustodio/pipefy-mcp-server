"""Single-shot loopback HTTP server for the OAuth Authorization Code callback (RFC 8252)."""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

_LOOPBACK_HOST = "127.0.0.1"
_CALLBACK_PATH = "/callback"
_DEFAULT_TIMEOUT_S = 180.0

_SUCCESS_HTML = b"""<!doctype html>
<html><head><title>Pipefy CLI \xe2\x80\x94 signed in</title></head>
<body style="font-family:system-ui,sans-serif;max-width:420px;margin:80px auto;text-align:center;">
  <h1 style="color:#1a7f37;">You're signed in to Pipefy</h1>
  <p>You can close this tab and return to your terminal.</p>
</body></html>
"""

_ERROR_HTML = b"""<!doctype html>
<html><head><title>Pipefy CLI \xe2\x80\x94 login failed</title></head>
<body style="font-family:system-ui,sans-serif;max-width:420px;margin:80px auto;text-align:center;">
  <h1 style="color:#cf222e;">Login failed</h1>
  <p>Check your terminal for details.</p>
</body></html>
"""


@dataclass(frozen=True)
class CallbackResult:
    """Outcome of the loopback callback: either a code or an error response."""

    code: str | None
    state: str | None
    error: str | None
    error_description: str | None


def find_free_port() -> int:
    """Bind a transient socket to find an OS-assigned ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((_LOOPBACK_HOST, 0))
        return s.getsockname()[1]


def redirect_uri_for(port: int) -> str:
    """Construct the loopback redirect URI for ``port``."""
    return f"http://{_LOOPBACK_HOST}:{port}{_CALLBACK_PATH}"


def await_callback(port: int, *, timeout: float = _DEFAULT_TIMEOUT_S) -> CallbackResult:
    """Serve exactly one callback on ``127.0.0.1:port`` and return what we got.

    Raises:
        TimeoutError: When no callback arrives within ``timeout``.
    """
    captured: dict[str, str | None] = {
        "code": None,
        "state": None,
        "error": None,
        "error_description": None,
    }
    done = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed = urlparse(self.path)
            if parsed.path != _CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            for key in captured:
                values = params.get(key) or [None]
                captured[key] = values[0]

            body = _ERROR_HTML if captured["error"] else _SUCCESS_HTML
            status = 400 if captured["error"] else 200
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Silence BaseHTTPRequestHandler's default stderr access log.
            del format, args
            return

    server = HTTPServer((_LOOPBACK_HOST, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not done.wait(timeout=timeout):
            raise TimeoutError(
                f"No browser callback received within {timeout:.0f}s on "
                f"{_LOOPBACK_HOST}:{port}."
            )
    finally:
        server.shutdown()
        server.server_close()
    return CallbackResult(
        code=captured["code"],
        state=captured["state"],
        error=captured["error"],
        error_description=captured["error_description"],
    )


__all__ = [
    "CallbackResult",
    "await_callback",
    "find_free_port",
    "redirect_uri_for",
]
