"""Writing chip's JSON files safely."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(path, text: str) -> None:
    """Write to a temporary file in the same folder, then rename it over `path`: readers see the old file
    or the new one, never half of it (even if the Mac sleeps or the process stops mid-write)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
