"""回归自检：投屏控制条、窗口几何记忆、左右键语义、图标缩至 60% 与最小化恢复。

离线运行，scrcpy 进程、原生窗口读取与置前全部 mock。
    .venv/bin/python scripts/verify_control.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QProcess  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

app = QApplication([])
app.setQuitOnLastWindowClosed(False)

from core import adb, paths  # noqa: E402
from ui import floatball, launchpad, nativewindow, style  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

style.apply(app, "dark")

PASS, FAIL = [], []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' · ' + detail) if detail else ''}")


def fake_run_async(fn, on_done=None, on_error=None, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        if on_error:
            on_error(str(exc))
    else:
        if on_done:
            on_done(result)


KEY = "com.demo.app"
GEOMETRY = {"x": 111, "y": 222, "width": 800, "height": 600,
            "control_x": 30, "control_y": 40}
SAMPLED = {"x": 140, "y": 90, "width": 420, "height": 720}


def main() -> int:
    with patch("ui.main_window.run_async", fake_run_async), \
         patch.object(adb, "list_devices", return_value=[]), \
         patch.object(adb, "system_packages", return_value=set()):
        w = MainWindow()
    w.persist = lambda: None
    for timer in (w.timer, w._info_timer, w._geometry_timer):
        timer.stop()
    w.watcher.stop()
    w._info_pool.shutdown(wait=False, cancel_futures=True)
    w.current_serial = "DEVICE1"
    w.devices = [adb.Device("DEVICE1", "device", model="Phone")]
    w.state.auto_float_on_mirror = False
    w.state.window_geometry[KEY] = dict(GEOMETRY)

    captured = []

    def fake_start(self, *args, **kwargs):
        captured.append(list(args[1]) if len(args) > 1 else [])

    print("=== 控制条创建与窗口几何恢复 ===")
    with patch.object(QProcess, "start", fake_start), \
         patch.object(QProcess, "state", lambda self: QProcess.Running), \
         patch.object(QProcess, "processId", lambda self: 4321), \
         patch.object(paths, "supports_new_display", return_value=True), \
         patch("ui.main_window.nativewindow.window_bounds", return_value=SAMPLED):
        w.start_mirror(package=KEY)

        window_id = next(iter(w.processes))
        control = w.controls.get(window_id)
        check("每个投屏窗口都有控制条", control is not None)
        check("窗口 key 按包名记录", w.processes[window_id].key == KEY)
        args = captured[0] if captured else []
        joined = " ".join(args)
        check("scrcpy 恢复上次窗口位置",
              "--window-x" in args and "111" in args and "222" in args)
        check("scrcpy 恢复上次窗口尺寸",
              "--window-width" in args and "800" in args)
        check("控制条恢复上次位置",
              control is not None and (control.x(), control.y()) == (30, 40),
              str((control.x(), control.y()) if control else None))
        check("控制条含导航/发送/复制/关闭按钮",
              control is not None and len(control.findChildren(QPushButton)) >= 8,
              str(len(control.findChildren(QPushButton)) if control else 0))
        check("控制条输入框存在", control is not None and control.edit is not None)

        print("=== 控制条信号 ===")
        with patch.object(w, "_control_key") as key_slot, \
             patch.object(w, "_control_text") as text_slot, \
             patch.object(w, "stop_mirror") as stop_slot, \
             patch.object(w, "focus_mirror") as focus_slot:
            control.findChildren(QPushButton)[1].click()   # 第一个导航键
            check("返回/菜单键发出按键请求", key_slot.call_count == 1)
            control.edit.setText("你好")
            control.send_btn.click()
            check("文本推送请求带 serial 与内容",
                  text_slot.call_count == 1 and text_slot.call_args[0][1] == "你好")
            control.title.click()
            check("标题点击请求窗口置前", focus_slot.call_count == 1)
            control.close_requested.emit(window_id)
            check("× 请求关闭该窗口", stop_slot.call_count == 1)
            control.move(77, 88)
            control.moved.emit(window_id, 77, 88)
            check("拖动控制条记住位置",
                  w.state.window_geometry[KEY]["control_x"] == 77)

        print("=== 几何采样与退出保存 ===")
        w._sample_geometry()
        check("周期采样记录窗口位置",
              w.processes[window_id].last_geometry == SAMPLED)
        w._on_finished(window_id)
        saved = w.state.window_geometry[KEY]
        check("退出后保存采样位置", saved.get("x") == 140)
        check("退出后保存控制条位置", saved.get("control_x") == 77)
        check("退出后销毁控制条", not w.controls)
        check("没有进程时停止采样定时器", not w._geometry_timer.isActive())

        print("=== 关闭记忆开关后不恢复 ===")
        w.state.remember_window_geometry = False
        captured.clear()
        w.start_mirror(package=KEY)
        check("不再传 --window-x", "--window-x" not in (captured[0] if captured else []))
        w._on_finished(next(iter(w.processes)))

    print("=== 左右键语义与最小化恢复 ===")
    c = w.float_controller
    c.show()
    c.set_running_windows([("w1", "微信")])
    c.toggle_window_list()
    check("右键显示已投屏列表", c.window_list.isVisible() and not c.panel.isVisible())
    c.toggle_panel()
    check("左键改展开应用面板", c.panel.isVisible() and not c.window_list.isVisible())
    c.toggle_window_list()
    check("列表与应用面板互斥", c.window_list.isVisible() and not c.panel.isVisible())
    c._hide_window_list()

    from core.config import MirrorConfig
    from ui.main_window import MirrorWindow
    fake_proc = QProcess()
    w.processes["w1"] = MirrorWindow("w1", "微信", KEY, "DEVICE1", fake_proc,
                                     key=KEY)
    with patch.object(QProcess, "processId", lambda self: 4321), \
         patch("ui.main_window.nativewindow.window_bounds", return_value=None), \
         patch("ui.main_window.nativewindow.focus_process", return_value=False), \
         patch("ui.main_window.nativewindow.focus_process_fallback",
               return_value=True) as fallback, \
         patch("ui.main_window.run_async", fake_run_async):
        w.focus_mirror("w1")
        check("窗口不在屏幕时走恢复最小化的备用路径",
              fallback.call_count == 1)
    w.processes.pop("w1", None)

    print("=== 图标缩至 60% ===")
    check("主 Launchpad 图标 84 → 50", launchpad._ICON == 50 and round(84 * 0.6) == 50)
    check("主网格列宽不变（仍 7 列）", launchpad._CELL_W == 128)
    panel = floatball.FloatPanel()
    cw, ch, size = panel._cell_metrics()
    check("悬浮球面板图标 ≤ 48", size <= 48, f"icon={size}, cell={cw}×{ch}")
    check("悬浮球面板仍固定 7 列", floatball.GRID_COLS == 7)
    check("离屏 window_bounds 安全返回 None",
          nativewindow.window_bounds(4321) is None)

    print(f"\n结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        for item in FAIL:
            print("  失败:", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
