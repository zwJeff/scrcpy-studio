"""投屏参数的建模、参数拼装与持久化。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .paths import SCRCPY

CONFIG_DIR = Path.home() / "Library/Application Support/ScrcpyStudio"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class MirrorConfig:
    mode: str = "screen"            # screen | app
    package: str = ""

    max_size: int = 0               # 0 = 原始分辨率
    video_bit_rate: str = "8M"
    max_fps: int = 0                # 0 = 不限
    video_codec: str = "h264"

    audio: bool = True
    audio_bit_rate: str = "128K"
    audio_dup: bool = False

    borderless: bool = False
    always_on_top: bool = False
    fullscreen: bool = False
    window_title: str = ""

    turn_screen_off: bool = False
    stay_awake: bool = True
    show_touches: bool = False
    keyboard: str = "default"
    mouse: str = "sdk"
    no_control: bool = False
    power_off_on_close: bool = False

    record: bool = False
    record_path: str = ""

    new_display_size: str = ""      # 空 = 沿用主屏分辨率
    new_display_dpi: int = 0        # 0 = 沿用主屏 DPI

    def copy(self) -> "MirrorConfig":
        return MirrorConfig(**asdict(self))


def build_args(cfg: MirrorConfig, serial: str | None, scrcpy_path: str | None = None) -> list[str]:
    scrcpy = scrcpy_path or SCRCPY
    args: list[str] = [scrcpy]
    if serial:
        args += ["-s", serial]

    if cfg.mode == "app" and cfg.package:
        display = "--new-display"
        if cfg.new_display_size.strip():
            display = f"--new-display={cfg.new_display_size.strip()}"
        if cfg.new_display_dpi:
            display = f"{display}/{cfg.new_display_dpi}" if "=" in display else \
                      f"--new-display=/{cfg.new_display_dpi}"
        args.append(display)
        args.append(f"--start-app=+{cfg.package}")

    if cfg.max_size:
        args += ["-m", str(cfg.max_size)]
    if cfg.video_bit_rate.strip():
        args += ["-b", cfg.video_bit_rate.strip()]
    if cfg.max_fps:
        args += ["--max-fps", str(cfg.max_fps)]
    if cfg.video_codec and cfg.video_codec != "h264":
        args += ["--video-codec", cfg.video_codec]

    if not cfg.audio:
        args.append("--no-audio")
    else:
        if cfg.audio_bit_rate.strip():
            args += ["--audio-bit-rate", cfg.audio_bit_rate.strip()]
        if cfg.audio_dup:
            args.append("--audio-dup")

    if cfg.borderless:
        args.append("--window-borderless")
    if cfg.always_on_top:
        args.append("--always-on-top")
    if cfg.fullscreen:
        args.append("-f")
    if cfg.window_title.strip():
        args += ["--window-title", cfg.window_title.strip()]

    if cfg.turn_screen_off:
        args.append("-S")
    if cfg.stay_awake:
        args.append("-w")
    if cfg.show_touches:
        args.append("-t")
    if cfg.keyboard and cfg.keyboard != "default":
        args += ["--keyboard", cfg.keyboard]
    if cfg.mouse and cfg.mouse != "sdk":
        args += ["--mouse", cfg.mouse]
    if cfg.no_control:
        args.append("-n")
    if cfg.power_off_on_close:
        args.append("--power-off-on-close")

    if cfg.record and cfg.record_path.strip():
        args += ["-r", cfg.record_path.strip()]
    return args


@dataclass
class AppState:
    mirror: MirrorConfig = field(default_factory=MirrorConfig)
    last_serial: str = ""
    last_package: str = ""
    aliases: dict[str, str] = field(default_factory=dict)
    show_package_name: bool = True
    auto_connect: bool = True
    adb_path: str = ""
    scrcpy_path: str = ""

    view_mode: str = "desktop"            # desktop | list
    category: str = "all"
    group_by: bool = True
    dock_packages: list[str] = field(default_factory=list)
    category_overrides: dict[str, str] = field(default_factory=dict)

    input_mode: str = "auto"              # auto | ascii | adbkeyboard
    input_enter: bool = False
    input_history: list[str] = field(default_factory=list)

    # 外观
    theme: str = "auto"                   # auto | light | dark
    launchpad_columns: int = 0            # 0 = 按窗口宽度自适应
    console_visible: bool = False
    input_visible: bool = True

    # USB 连接
    auto_mirror_usb: bool = False         # 插入 USB 设备后自动整屏投屏
    prefer_usb: bool = True               # USB 与无线同时在线时优先选 USB
    usb_port: int = 5555                  # USB → 无线切换使用的端口


def load_state() -> AppState:
    state = AppState()
    if not CONFIG_PATH.exists():
        return state
    try:
        raw = json.loads(CONFIG_PATH.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return state

    mirror_raw = raw.get("mirror") or {}
    valid = {f.name for f in fields(MirrorConfig)}
    state.mirror = MirrorConfig(**{k: v for k, v in mirror_raw.items() if k in valid})
    state.last_serial = raw.get("last_serial", "")
    state.last_package = raw.get("last_package", "")
    state.aliases = raw.get("aliases") or {}
    state.show_package_name = raw.get("show_package_name", True)
    state.auto_connect = raw.get("auto_connect", True)
    state.adb_path = raw.get("adb_path", "")
    state.scrcpy_path = raw.get("scrcpy_path", "")
    state.view_mode = raw.get("view_mode", "desktop")
    state.category = raw.get("category", "all")
    state.group_by = bool(raw.get("group_by", True))
    state.dock_packages = list(raw.get("dock_packages") or [])[:4]
    state.category_overrides = dict(raw.get("category_overrides") or {})
    state.input_mode = raw.get("input_mode", "auto")
    state.input_enter = bool(raw.get("input_enter", False))
    state.input_history = list(raw.get("input_history") or [])[:20]
    state.theme = raw.get("theme", "auto")
    if state.theme not in ("auto", "light", "dark"):
        state.theme = "auto"
    try:
        state.launchpad_columns = max(0, min(12, int(raw.get("launchpad_columns", 0))))
    except (TypeError, ValueError):
        state.launchpad_columns = 0
    state.console_visible = bool(raw.get("console_visible", False))
    state.input_visible = bool(raw.get("input_visible", True))
    if not raw.get("ui_version"):
        # 0.3 首次启动：统一切到 Launchpad 连续网格，输入面板展开，列数自适应
        state.view_mode = "desktop"
        state.group_by = False
        state.input_visible = True
        state.console_visible = False
        state.launchpad_columns = 0
    state.auto_mirror_usb = bool(raw.get("auto_mirror_usb", False))
    state.prefer_usb = bool(raw.get("prefer_usb", True))
    try:
        state.usb_port = int(raw.get("usb_port", 5555))
    except (TypeError, ValueError):
        state.usb_port = 5555
    if not 1 <= state.usb_port <= 65535:
        state.usb_port = 5555
    return state


def save_state(state: AppState) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "mirror": asdict(state.mirror),
        "last_serial": state.last_serial,
        "last_package": state.last_package,
        "aliases": state.aliases,
        "show_package_name": state.show_package_name,
        "auto_connect": state.auto_connect,
        "adb_path": state.adb_path,
        "scrcpy_path": state.scrcpy_path,
        "view_mode": state.view_mode,
        "ui_version": 3,
        "category": state.category,
        "group_by": state.group_by,
        "dock_packages": state.dock_packages,
        "category_overrides": state.category_overrides,
        "input_mode": state.input_mode,
        "input_enter": state.input_enter,
        "input_history": state.input_history,
        "theme": state.theme,
        "launchpad_columns": state.launchpad_columns,
        "console_visible": state.console_visible,
        "input_visible": state.input_visible,
        "auto_mirror_usb": state.auto_mirror_usb,
        "prefer_usb": state.prefer_usb,
        "usb_port": state.usb_port,
    }
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, CONFIG_PATH)
