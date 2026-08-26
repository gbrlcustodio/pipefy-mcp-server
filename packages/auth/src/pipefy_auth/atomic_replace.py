"""POSIX-safe replace of a file via a unique sibling tempfile."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def replace_file_atomically(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` using a unique ``*.tmp`` sibling, then replace.

    Concurrent writers must not share a fixed ``path`` + ``.tmp`` name: two
    processes truncating the same sibling can raise ``ENOENT`` on replace.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        if os.name != "nt":
            tmp_path.chmod(0o600)
        tmp_path.replace(path)
        if os.name != "nt":
            path.chmod(0o600)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
