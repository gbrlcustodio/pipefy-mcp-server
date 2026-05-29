"""Local filesystem I/O with normalized error handling.

:class:`LocalFile` resolves a path on disk to its bytes, expanding ``~``,
checking the path is a regular file, and (optionally) enforcing a size cap
before reading. Every failure mode surfaces as :class:`LocalFileError` so
callers handle a single exception type.

Schema-agnostic: no Pipefy concepts here. Callers that need a domain-policy
cap (e.g. the attachment 100 MiB ceiling) pass ``max_size_bytes``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "LocalFile",
    "LocalFileError",
]


class LocalFileError(Exception):
    """Raised when a :class:`LocalFile` cannot be read.

    Covers unknown ``~user`` in the path, missing path, non-regular file,
    permission denied, generic OS read failure, and oversize files when a
    cap is configured. The message is user-facing and safe to surface in
    error envelopes or CLI errors.
    """


class LocalFile:
    """A local file resolved to its bytes.

    Construct with a path, optionally a size cap, then call :meth:`read` to
    perform the I/O. All read-time failures land as :class:`LocalFileError`
    so callers catch one exception type.

    Path/bytes properties raise :class:`RuntimeError` if accessed before
    :meth:`read` succeeds.

    Args:
        path: Local path. Supports ``~`` expansion against the user's home.
        max_size_bytes: Optional ceiling enforced after ``stat()``. ``None``
            (default) means no cap.
    """

    def __init__(self, path: Path, *, max_size_bytes: int | None = None):
        self._path = path
        self._max_size_bytes = max_size_bytes
        self._expanded: Path | None = None
        self._bytes: bytes | None = None

    def read(self) -> None:
        """Expand ``~``, validate, and read the file into memory.

        Raises:
            LocalFileError: For any failure mode (unknown ``~user``, missing
                file, directory, permission denied, oversize when a cap is
                configured).
        """
        try:
            expanded = self._path.expanduser()
        except RuntimeError as exc:
            raise LocalFileError(f"Cannot expand ~ in {self._path}: {exc}") from exc

        if not expanded.is_file():
            raise LocalFileError(f"File not found or not a regular file: {expanded}")

        if self._max_size_bytes is not None:
            size = expanded.stat().st_size
            if size > self._max_size_bytes:
                cap_mib = self._max_size_bytes // (1024 * 1024)
                raise LocalFileError(
                    f"File too large: {expanded} is {size} bytes, exceeding "
                    f"the {cap_mib} MiB cap."
                )

        try:
            data = expanded.read_bytes()
        except PermissionError as exc:
            raise LocalFileError(
                f"Permission denied reading {expanded}: {exc.strerror}"
            ) from exc
        except OSError as exc:
            raise LocalFileError(f"Could not read {expanded}: {exc}") from exc

        self._expanded = expanded
        self._bytes = data

    @property
    def path(self) -> Path:
        """The post-``expanduser()`` path. Available after :meth:`read`."""
        if self._expanded is None:
            raise RuntimeError("LocalFile.read() has not been called yet.")
        return self._expanded

    @property
    def name(self) -> str:
        """The expanded path's basename. May be empty for paths like ``/``."""
        return self.path.name

    @property
    def bytes(self) -> bytes:
        if self._bytes is None:
            raise RuntimeError("LocalFile.read() has not been called yet.")
        return self._bytes

    @property
    def size(self) -> int:
        return len(self.bytes)
