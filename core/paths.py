"""adb 与 scrcpy 的可执行文件定位、版本检测与子进程环境。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

HOME = Path.home()


def _first_existing(candidates: list[Path]) -> str | None:
    for path in candidates:
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def find_scrcpy() -> str:
    from_path = shutil.which("scrcpy")
    if from_path:
        return from_path
    return _first_existing([
        HOME / ".local/opt/scrcpy/scrcpy",
        HOME / ".local/bin/scrcpy",
        Path("/opt/homebrew/bin/scrcpy"),
        Path("/usr/local/bin/scrcpy"),
        Path("/Applications/scrcpy/scrcpy"),
    ]) or "scrcpy"


def find_adb() -> str:
    from_path = shutil.which("adb")
    if from_path:
        return from_path
    # 官方 macOS 发行包把 scrcpy 与 adb 放在同一目录，优先复用这一份
    scrcpy = SCRCPY if os.path.isabs(SCRCPY) else find_scrcpy()
    candidates: list[Path] = []
    if os.path.isabs(scrcpy):
        candidates.append(Path(scrcpy).parent / "adb")
    candidates += [
        HOME / ".local/opt/platform-tools/adb",
        HOME / ".local/opt/scrcpy/adb",
        HOME / ".local/bin/adb",
        Path("/opt/homebrew/bin/adb"),
        Path("/usr/local/bin/adb"),
    ]
    return _first_existing(candidates) or "adb"


SCRCPY = find_scrcpy()
ADB = find_adb()


def set_overrides(adb_path: str = "", scrcpy_path: str = "") -> None:
    """应用用户在设置里手填的路径；所有模块通过 paths.ADB / paths.SCRCPY 动态读取。"""
    global ADB, SCRCPY
    SCRCPY = resolve_scrcpy(scrcpy_path) if scrcpy_path.strip() else find_scrcpy()
    ADB = resolve_adb(adb_path) if adb_path.strip() else find_adb()
    scrcpy_version.cache_clear()


def resolve_adb(override: str = "") -> str:
    """自定义路径优先，否则回退到自动定位结果。"""
    path = (override or "").strip() or ADB
    if not os.path.isabs(path):
        return shutil.which(path) or path
    return path


def resolve_scrcpy(override: str = "") -> str:
    path = (override or "").strip() or SCRCPY
    if not os.path.isabs(path):
        return shutil.which(path) or path
    return path


@lru_cache(maxsize=16)
def scrcpy_version(override: str = "") -> tuple[int, int, str] | None:
    """返回 (主版本, 次版本, 原始首行)。检测不到时返回 None。"""
    executable = resolve_scrcpy(override)
    try:
        proc = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=6
        )
        text = (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"scrcpy\s+(\d+)\.(\d+)(?:\.\d+)?", text)
    if not match:
        return None
    first = text.strip().splitlines()[0] if text.strip() else ""
    return int(match.group(1)), int(match.group(2)), first


def supports_new_display(override: str = "") -> bool:
    """--new-display / --start-app 从 scrcpy 5.0 起才提供。"""
    version = scrcpy_version(override)
    return version is None or version[0] >= 5


def version_text(override: str = "") -> str:
    version = scrcpy_version(override)
    return version[2] if version else "未检测到（请确认 scrcpy 路径）"


def child_environment(adb_override: str = "", scrcpy_override: str = "") -> dict[str, str]:
    """scrcpy 子进程需要额外覆盖的环境变量。

    从 Finder 启动的 .app 只有 launchd 的最小 PATH，scrcpy 自己找不到 adb，
    会报 "Could not execute adb start-server"。scrcpy 官方支持用 ADB 环境变量
    指定 adb 的完整路径，这里同时补齐 PATH 与自带的 scrcpy-server。
    """
    adb_path = resolve_adb(adb_override)
    scrcpy_path = resolve_scrcpy(scrcpy_override)
    env: dict[str, str] = {"ADB": adb_path, "LC_ALL": "C"}

    dirs: list[str] = []
    for executable in (adb_path, scrcpy_path):
        if os.path.isabs(executable):
            directory = str(Path(executable).parent)
            if directory and directory not in dirs:
                dirs.append(directory)
    if dirs:
        env["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])

    if os.path.isabs(scrcpy_path):
        real = Path(scrcpy_path).resolve()
        for parent in (Path(scrcpy_path).parent, real.parent):
            server = parent / "scrcpy-server"
            if server.exists():
                env["SCRCPY_SERVER_PATH"] = str(server)
                break
    return env
