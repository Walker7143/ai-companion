from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

_WINDOWS_DRIVE_FILE_URL_RE = re.compile(r"^/[A-Za-z]:[\\/]")


def resolve_book_path(raw: str, *, cwd: Path | None = None) -> Path:
    """Resolve a user-supplied local book path.

    Supports absolute paths, relative paths, ``~``, environment variables, and
    ``file://`` URLs produced by some desktop file pickers.
    """
    value = str(raw or "").strip()
    if not value:
        raise ValueError("书籍路径不能为空")

    # Users sometimes paste quoted paths from a shell or file picker.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    parsed = urlparse(value)
    if parsed.scheme == "file":
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            raise ValueError(f"只支持本地 file:// 路径，不支持远程主机: {parsed.netloc}")
        value = _decode_file_url_path(parsed.path)

    value = os.path.expandvars(value)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    return path.resolve()


def _decode_file_url_path(path: str, *, platform: str | None = None) -> str:
    value = unquote(path)
    if (platform or sys.platform) == "win32" and _WINDOWS_DRIVE_FILE_URL_RE.match(value):
        return value[1:]
    return value
