"""插 USB 自动启动 App 的 LaunchAgent 守护管理。

只在用户在设置里显式点「启用」时才会写入 ~/Library/LaunchAgents/。
macOS 没有「USB 设备插入即启动 App」的 launchd 键，因此用一个
每 3 秒检查一次 adb devices 的轻量后台脚本来实现。
"""
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

from .paths import ADB, HOME, ROOT

LABEL = "local.jeff.scrcpy-studio.usbwatch"
PLIST = HOME / "Library" / "LaunchAgents" / f"{LABEL}.plist"
WATCH = ROOT / "scripts" / "usb_watch.sh"
LOG = HOME / "Library" / "Logs" / "ScrcpyStudio-usbwatch.log"


def app_path() -> str:
    """定位当前运行的 .app（兼容源码目录与自包含产物两种布局）。"""
    current = ROOT
    for _ in range(5):
        if current.suffix == ".app":
            return str(current)
        current = current.parent
    candidate = ROOT / "ScrcpyStudio.app"
    return str(candidate) if candidate.exists() else ""


def is_installed() -> bool:
    return PLIST.exists()


def install() -> tuple[bool, str]:
    app = app_path()
    if not app:
        return False, "找不到 ScrcpyStudio.app，无法配置自启"
    if not WATCH.exists():
        return False, f"找不到守护脚本：{WATCH}"
    if not PLIST.parent.exists():
        PLIST.parent.mkdir(parents=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", str(WATCH), ADB, app],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    try:
        PLIST.write_bytes(plistlib.dumps(payload))
    except OSError as exc:
        return False, f"写入 LaunchAgent 失败：{exc}"
    subprocess.run(["launchctl", "unload", str(PLIST)],
                   capture_output=True, text=True)
    result = subprocess.run(["launchctl", "load", "-w", str(PLIST)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "launchctl load 失败"
    return True, "已启用：插入 USB 设备时会自动启动 Scrcpy Studio"


def uninstall() -> tuple[bool, str]:
    if not PLIST.exists():
        return True, "未启用"
    subprocess.run(["launchctl", "unload", "-w", str(PLIST)],
                   capture_output=True, text=True)
    try:
        PLIST.unlink()
    except OSError as exc:
        return False, f"移除 LaunchAgent 失败：{exc}"
    return True, "已停用插 USB 自动启动"


def log_path() -> Path:
    return LOG
