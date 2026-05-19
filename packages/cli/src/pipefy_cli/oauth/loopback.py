"""Single-shot loopback HTTP server for the OAuth Authorization Code callback (RFC 8252)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import TracebackType
from urllib.parse import parse_qs, urlparse

_LOOPBACK_HOST = "127.0.0.1"
_CALLBACK_PATH = "/callback"
_DEFAULT_TIMEOUT_S = 180.0

# Colors from Pipefy's design system (bricks/lumen-base):
# - success heading = brand.300 (#005EFC) — the brand-primary; success state is a
#   brand moment, not a generic green. The design system has no
#   ``sys.color.text.positive`` — that's deliberate (success isn't typecast as green).
# - failure heading = sys.color.text.negative (#C22E00 = feedback.negative.400) —
#   the documented system-level "this text means error" color.
_SUCCESS_HTML = b"""<!doctype html>
<html><head><title>Pipefy CLI \xe2\x80\x94 signed in</title></head>
<body style="font-family:'Inter',system-ui,sans-serif;max-width:420px;margin:80px auto;text-align:center;color:#101820;">
  <h1 style="color:#005EFC;">You're signed in to Pipefy</h1>
  <p>You can close this tab and return to your terminal.</p>
</body></html>
"""

_ERROR_HTML = b"""<!doctype html>
<html><head><title>Pipefy CLI \xe2\x80\x94 login failed</title></head>
<body style="font-family:'Inter',system-ui,sans-serif;max-width:420px;margin:80px auto;text-align:center;color:#101820;">
  <h1 style="color:#C22E00;">Login failed</h1>
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


def redirect_uri_for(port: int) -> str:
    """Construct the loopback redirect URI for ``port``."""
    return f"http://{_LOOPBACK_HOST}:{port}{_CALLBACK_PATH}"


class LoopbackCapture:
    """Bind a loopback HTTP server immediately, then serve exactly one callback.

    The port is bound at construction so the caller can open the browser without
    a race window where another process could grab the ephemeral port.
    """

    def __init__(self) -> None:
        self._captured: dict[str, str | None] = {
            "code": None,
            "state": None,
            "error": None,
            "error_description": None,
        }
        self._done = threading.Event()
        self._server = HTTPServer((_LOOPBACK_HOST, 0), self._make_handler())
        self._thread: threading.Thread | None = None
        self._closed = False

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def redirect_uri(self) -> str:
        return redirect_uri_for(self.port)

    def __enter__(self) -> LoopbackCapture:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the bound socket. Idempotent; safe to call multiple times."""
        if self._closed:
            return
        self._closed = True
        if self._thread is not None and self._thread.is_alive():
            self._server.shutdown()
            self._thread.join(timeout=1.0)
        self._server.server_close()

    def await_callback(self, *, timeout: float = _DEFAULT_TIMEOUT_S) -> CallbackResult:
        """Run the server until one callback arrives (or ``timeout`` elapses)."""
        if self._closed:
            raise RuntimeError("LoopbackCapture is already closed.")
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        try:
            if not self._done.wait(timeout=timeout):
                raise TimeoutError(
                    f"No browser callback received within {timeout:.0f}s on "
                    f"{_LOOPBACK_HOST}:{self.port}."
                )
        finally:
            self.close()
        return CallbackResult(**self._captured)

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        captured = self._captured
        done = self._done

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

        return _Handler


__all__ = [
    "CallbackResult",
    "LoopbackCapture",
    "redirect_uri_for",
]
