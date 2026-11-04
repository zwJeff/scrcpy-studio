"""adb 与 scrcpy 的可执行文件定位。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

HOME = Path.home()


def _first_existing(candidates: list[Path]) -> str | None:
    for path in candidates:
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def find_adb() -> str:
    """优先使用 system PATH 里的 adb，其次退回随 scrcpy 安装的副本。"""
    from_path = shutil.which("adb")
    if from_path:
        return from_path
    return _first_existing([
        HOME / ".local/opt/platform-tools/adb",
        HOME / ".local/opt/scrcpy/adb",
        Path("/opt/homebrew/bin/adb"),
        Path("/usr/local/bin/adb"),
    ]) or "adb"


def find_scrcpy() -> str:
    from_path = shutil.which("scrcpy")
    if from_path:
        return from_path
    return _first_existing([
        HOME / ".local/opt/scrcpy/scrcpy",
        Path("/opt/homebrew/bin/scrcpy"),
        Path("/usr/local/bin/scrcpy"),
    ]) or "scrcpy"


ADB = find_adb()
SCRCPY = find_scrcpy()
