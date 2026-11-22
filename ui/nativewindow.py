"""macOS 原生窗口层级控制。

Qt 的 `Qt.WindowStaysOnTopHint` 在 Cocoa 上只对应 NSFloatingWindowLevel(3)：
切换 Spaces、别的 App 进入全屏、或本 App 失活时，系统都可能把它降到其他窗口后面。
这里直接对 NSWindow 设置更高层级与跨 Spaces 行为，让悬浮球真正「始终最前」。

非 macOS 或 Objective-C 运行时调用失败时静默降级，调用方仍可依赖 Qt 的置顶 flag。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import c_bool, c_char_p, c_int, c_long, c_ulong, c_void_p

from PySide6.QtGui import QGuiApplication

_IS_MAC = sys.platform == "darwin"

# NSScreenSaverWindowLevel = 1000；比它高一级，普通应用窗口与全屏窗口都盖不住
BALL_LEVEL = 1001
PANEL_LEVEL = 1002
LIST_LEVEL = 1003
CONTROL_LEVEL = 1004

# NSWindowCollectionBehavior：
# CanJoinAllSpaces(1<<0) | Stationary(1<<4) | IgnoresCycle(1<<6)
# | FullScreenAuxiliary(1<<8)，跟随全屏 Spaces 且不进入窗口循环
_COLLECTION = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)

_objc = None


def _runtime():
    global _objc
    if _objc is None:
        _objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        # 新版 macOS 的 libobjc 只导出 sel_registerName（sel_registerUid 已不可用）
        try:
            sel = _objc.sel_registerName
        except AttributeError:
            sel = _objc.sel_getUid
        sel.restype = c_void_p
        sel.argtypes = [c_char_p]
        _objc._sel = sel
        _objc.objc_msgSend.restype = c_void_p
    return _objc


def _sel(name: bytes) -> int:
    return _runtime()._sel(name)


def _cocoa_ready() -> bool:
    """离屏/其他 QPA 平台的 winId() 不是 NSView*，绝不能拿去发 Objective-C 消息。"""
    if not _IS_MAC:
        return False
    try:
        return QGuiApplication.platformName() == "cocoa"
    except Exception:  # noqa: BLE001
        return False


def ns_window(widget) -> int:
    """QWidget.winId() 在 Cocoa 上是 NSView*，取其所属的 NSWindow。"""
    if not _cocoa_ready():
        return 0
    try:
        view = c_void_p(int(widget.winId()))
    except (AttributeError, TypeError, ValueError):
        return 0
    if not view.value:
        return 0
    try:
        objc = _runtime()
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
        return objc.objc_msgSend(view, _sel(b"window")) or 0
    except Exception:  # noqa: BLE001 - 原生调用失败一律降级
        return 0


def pin(widget, level: int = BALL_LEVEL) -> bool:
    """把窗口固定在指定层级、跨 Spaces 常驻，并禁止失活时隐藏。"""
    if not _IS_MAC:
        return False
    win = ns_window(widget)
    if not win:
        return False
    try:
        objc = _runtime()
        target = c_void_p(win)

        objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_long]
        objc.objc_msgSend(target, _sel(b"setLevel:"), c_long(level))

        objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_ulong]
        objc.objc_msgSend(target, _sel(b"setCollectionBehavior:"), c_ulong(_COLLECTION))

        objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_bool]
        objc.objc_msgSend(target, _sel(b"setHidesOnDeactivate:"), c_bool(False))
        return True
    except Exception:  # noqa: BLE001
        return False


def _activate_self(objc) -> None:
    """先让本 App 成为前台，否则 macOS 会拒绝 activateWithOptions（防焦点窃取）。"""
    try:
        objc.objc_getClass.restype = c_void_p
        objc.objc_getClass.argtypes = [c_char_p]
        cls = objc.objc_getClass(b"NSApplication")
        objc.objc_msgSend.restype = c_void_p
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
        shared = objc.objc_msgSend(c_void_p(cls), _sel(b"sharedApplication"))
        if shared:
            objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_bool]
            objc.objc_msgSend(c_void_p(shared),
                              _sel(b"activateIgnoringOtherApps:"), c_bool(True))
    except Exception:  # noqa: BLE001
        pass
    finally:
        objc.objc_msgSend.restype = c_void_p


def focus_process(pid: int) -> bool:
    """把指定 PID 的应用（scrcpy 投屏窗口）激活到前台，返回系统是否接受。

    主路径是 NSRunningApplication（不需要辅助功能权限）。若系统拒绝，
    调用方可再试 focus_process_fallback（AppleScript，可能需要自动化授权）。
    """
    if not _cocoa_ready() or pid <= 0:
        return False
    try:
        objc = _runtime()
        _activate_self(objc)

        objc.objc_getClass.restype = c_void_p
        objc.objc_getClass.argtypes = [c_char_p]
        cls = objc.objc_getClass(b"NSRunningApplication")
        if not cls:
            return False

        objc.objc_msgSend.restype = c_void_p
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_int]
        running = objc.objc_msgSend(
            c_void_p(cls),
            _sel(b"runningApplicationWithProcessIdentifier:"),
            c_int(int(pid)),
        )
        if not running:
            return False

        # NSApplicationActivateAllWindows(1) | NSApplicationActivateIgnoringOtherApps(2)
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_ulong]
        objc.objc_msgSend.restype = c_bool
        try:
            return bool(objc.objc_msgSend(
                c_void_p(running), _sel(b"activateWithOptions:"), c_ulong(3)
            ))
        finally:
            objc.objc_msgSend.restype = c_void_p
    except Exception:  # noqa: BLE001 - 原生调用失败一律降级
        return False


def focus_process_fallback(pid: int) -> bool:
    """备用置前：System Events 按 unix id 找到进程，设为前台并取消窗口最小化。

    需要 macOS「自动化 / 辅助功能」授权；未授权时静默失败，不弹错误框。
    供后台线程调用，避免阻塞界面。
    """
    if not _IS_MAC or pid <= 0:
        return False
    import subprocess

    script = f'''tell application "System Events"
  tell (first application process whose unix id is {int(pid)})
    set frontmost to true
    try
      set value of attribute "AXMinimized" of window 1 to false
    end try
  end tell
end tell'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, timeout=2.5,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def window_bounds(pid: int) -> dict | None:
    """读取指定进程第一个正常窗口的位置尺寸（屏幕坐标，点）。

    用公开的 CGWindowListCopyWindowInfo，无需辅助功能权限。
    返回 None 表示进程没有在屏窗口（未创建、已关闭或**已最小化**），
    调用方可以据此判断是否需要走「恢复最小化」路径。
    """
    if not _IS_MAC or pid <= 0:
        return None
    try:
        from ctypes import (
            Structure, byref, c_double, c_long, c_uint32,
        )

        class _Rect(Structure):
            _fields_ = [("x", c_double), ("y", c_double),
                        ("w", c_double), ("h", c_double)]

        cg = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        cf = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        cg.CGWindowListCopyWindowInfo.restype = c_void_p
        cg.CGWindowListCopyWindowInfo.argtypes = [c_uint32, c_uint32]
        cf.CFArrayGetCount.restype = c_long
        cf.CFArrayGetCount.argtypes = [c_void_p]
        cf.CFArrayGetValueAtIndex.restype = c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        cf.CFDictionaryGetValue.restype = c_void_p
        cf.CFDictionaryGetValue.argtypes = [c_void_p, c_void_p]
        cf.CFNumberGetValue.restype = c_bool
        cf.CFNumberGetValue.argtypes = [c_void_p, c_long, c_void_p]
        cf.CFRelease.argtypes = [c_void_p]
        cg.CGRectMakeWithDictionaryRepresentation.restype = c_bool
        cg.CGRectMakeWithDictionaryRepresentation.argtypes = [c_void_p, c_void_p]

        keys = {}
        for name in ("kCGWindowOwnerPID", "kCGWindowBounds", "kCGWindowLayer"):
            keys[name] = c_void_p.in_dll(cg, name).value

        arr = cg.CGWindowListCopyWindowInfo(1, 0)   # onScreenOnly, kCGNullWindowID
        if not arr:
            return None
        try:
            best = None
            for index in range(cf.CFArrayGetCount(c_void_p(arr))):
                info = cf.CFArrayGetValueAtIndex(c_void_p(arr), c_long(index))
                if not info:
                    continue
                owner = cf.CFDictionaryGetValue(
                    c_void_p(info), c_void_p(keys["kCGWindowOwnerPID"])
                )
                if not owner:
                    continue
                owner_pid = c_int(0)
                # kCFNumberIntType = 9
                if not cf.CFNumberGetValue(c_void_p(owner), c_long(9),
                                           byref(owner_pid)) or owner_pid.value != pid:
                    continue
                layer_ref = cf.CFDictionaryGetValue(
                    c_void_p(info), c_void_p(keys["kCGWindowLayer"])
                )
                layer = c_int(0)
                if layer_ref:
                    cf.CFNumberGetValue(c_void_p(layer_ref), c_long(9), byref(layer))
                if layer.value != 0:
                    continue
                bounds_ref = cf.CFDictionaryGetValue(
                    c_void_p(info), c_void_p(keys["kCGWindowBounds"])
                )
                if not bounds_ref:
                    continue
                rect = _Rect()
                if not cg.CGRectMakeWithDictionaryRepresentation(
                        c_void_p(bounds_ref), byref(rect)):
                    continue
                if rect.w < 100 or rect.h < 100:
                    continue
                if best is None or rect.w * rect.h > best["width"] * best["height"]:
                    best = {"x": int(rect.x), "y": int(rect.y),
                            "width": int(rect.w), "height": int(rect.h)}
            return best
        finally:
            cf.CFRelease(c_void_p(arr))
    except Exception:  # noqa: BLE001 - 原生调用失败一律降级
        return None


def level_of(widget) -> int:
    """读取当前层级，供自检使用。"""
    win = ns_window(widget)
    if not win:
        return -1
    try:
        objc = _runtime()
        objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
        objc.objc_msgSend.restype = c_long
        try:
            return int(objc.objc_msgSend(c_void_p(win), _sel(b"level")))
        finally:
            objc.objc_msgSend.restype = c_void_p
    except Exception:  # noqa: BLE001
        return -1
