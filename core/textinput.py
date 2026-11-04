"""把 Mac 上输入的文本推送到手机当前获得焦点的输入框。

Android 的 `input text` 内部用 KeyCharacterMap 把字符转成按键事件，
只支持 ASCII，中文 / emoji 会直接失败。因此这里做两条通道：

* ASCII：`adb shell input text`，空格转成 `%s`，shell 层用 shlex.quote 包裹；
* 任意 Unicode：ADBKeyBoard 输入法的广播（`ADB_INPUT_B64`，base64 避免编码问题），
  需要设备上安装并启用 com.android.adbkeyboard，否则给出明确提示。

第三种兜底是把文本放进 Mac 剪贴板，由用户在 scrcpy 窗口按 ⌘V —— scrcpy 会把
电脑剪贴板同步到设备并自动粘贴，支持任意语言且不需要额外安装输入法。
"""
from __future__ import annotations

import base64
import shlex
import subprocess
from dataclasses import dataclass

from .paths import ADB

ADBKEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

KEYCODE = {
    "enter": 66, "backspace": 67, "tab": 61, "esc": 111,
    "home": 3, "back": 4, "up": 19, "down": 20, "left": 21, "right": 22,
}


class TextInputError(RuntimeError):
    pass


@dataclass
class SendResult:
    channel: str          # input / adbkeyboard
    detail: str           # 实际执行的命令，用于日志
    enter_sent: bool = False


def _shell(serial: str, command: str, timeout: int = 25) -> str:
    try:
        proc = subprocess.run(
            [ADB, "-s", serial, "shell", command],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise TextInputError(f"找不到 adb：{ADB}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TextInputError("adb 命令超时") from exc
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def has_non_ascii(text: str) -> bool:
    return any(ord(ch) > 127 for ch in text)


def adbkeyboard_available(serial: str) -> bool:
    out = _shell(serial, "ime list -s", timeout=15)
    return "adbkeyboard" in out.lower()


def escape_input_text(text: str) -> str:
    """把文本变成可安全传给 `input text` 的形式。"""
    safe = text.replace("\r", "").replace("\n", " ")
    safe = safe.replace(" ", "%s")   # input 只把 %s 当空格，其余 % 原样保留
    return shlex.quote(safe)


def send_keyevent(serial: str, name: str) -> str:
    code = KEYCODE.get(name)
    if code is None:
        raise TextInputError(f"未知按键：{name}")
    return _shell(serial, f"input keyevent {code}")


def send(serial: str, text: str, mode: str = "auto",
         enter: bool = False) -> SendResult:
    """mode: auto | ascii | adbkeyboard。"""
    if not serial:
        raise TextInputError("没有可用设备")
    if not text:
        raise TextInputError("输入内容为空")

    unicode_text = has_non_ascii(text)
    channel = "input"
    detail = ""

    if unicode_text and mode == "ascii":
        raise TextInputError(
            "这段文本含非 ASCII 字符，input text 无法输入。"
            "请切换到「ADBKeyBoard」模式，或点「复制文本」后在 scrcpy 窗口按 ⌘V。"
        )

    if mode == "adbkeyboard" or (unicode_text and mode == "auto"):
        if not adbkeyboard_available(serial):
            raise TextInputError(
                "设备上没有检测到 ADBKeyBoard 输入法，无法输入中文。\n"
                "可在输入框选「复制文本」，然后到 scrcpy 窗口按 ⌘V 粘贴（支持任意语言）；"
                "或安装 ADBKeyBoard 后执行 ime enable / ime set。"
            )
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        detail = f"am broadcast -a ADB_INPUT_B64 --es msg {payload}"
        out = _shell(serial, detail, timeout=30)
        if "Broadcast completed" not in out and "result=" not in out:
            raise TextInputError(f"广播发送失败：{out or '无返回'}")
        channel = "adbkeyboard"
    else:
        quoted = escape_input_text(text)
        detail = f"input text {quoted}"
        out = _shell(serial, detail, timeout=30)
        if "Error" in out or "Exception" in out or "not found" in out.lower():
            raise TextInputError(f"输入失败：{out}")
        channel = "input"

    if enter:
        _shell(serial, f"input keyevent {KEYCODE['enter']}")
    return SendResult(channel, detail, enter)


def clear_via_adbkeyboard(serial: str) -> str:
    return _shell(serial, "am broadcast -a ADB_CLEAR_TEXT")
