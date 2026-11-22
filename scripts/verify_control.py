"""回归自检：投屏控制条、窗口几何记忆、控制条跟随、左右键语义、图标 60%。

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
from core.config import MirrorConfig, build_args  # noqa: E402
from ui import floatball, launchpad, mirrorcontrol, nativewindow, style  # noqa: E402
from ui.main_window import MainWindow, MirrorWindow  # noqa: E402

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
MOVED = {"x": 300, "y": 200, "width": 900, "height": 600}
PID = 4321


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
    bounds_holder = {"value": SAMPLED}

    def fake_start(self, *args, **kwargs):
        captured.append(list(args[1]) if len(args) > 1 else [])

    def bounds_map(pids):
        return {PID: bounds_holder["value"]} if bounds_holder["value"] else {}

    print("=== 固定模式：恢复记忆位置与窗口几何 ===")
    w.state.control_follow_window = False
    with patch.object(QProcess, "start", fake_start), \
         patch.object(QProcess, "state", lambda self: QProcess.Running), \
         patch.object(QProcess, "processId", lambda self: PID), \
         patch.object(paths, "supports_new_display", return_value=True), \
         patch("ui.main_window.nativewindow.window_bounds_map", side_effect=bounds_map):
        w.start_mirror(package=KEY)
        window_id = next(iter(w.processes))
        control = w.controls.get(window_id)

        check("每个投屏窗口都有控制条", control is not None)
        check("窗口 key 按包名记录", w.processes[window_id].key == KEY)
        args = captured[0] if captured else []
        check("scrcpy 恢复上次窗口位置",
              "--window-x" in args and "111" in args and "222" in args)
        check("scrcpy 恢复上次窗口尺寸",
              "--window-width" in args and "800" in args)
        check("固定模式恢复控制条记忆位置",
              control is not None and (control.x(), control.y()) == (30, 40),
              str((control.x(), control.y()) if control else None))
        check("固定模式下控制条不跟随",
              control is not None and not control.is_following())
        check("控制条含导航/发送/复制/跟随/关闭按钮",
              control is not None and len(control.findChildren(QPushButton)) >= 9,
              str(len(control.findChildren(QPushButton)) if control else 0))
        check("控制条输入框存在", control is not None and control.edit is not None)

        print("=== 控制条信号 ===")
        with patch.object(w, "_control_key") as key_slot, \
             patch.object(w, "_control_text") as text_slot, \
             patch.object(w, "stop_mirror") as stop_slot, \
             patch.object(w, "focus_mirror") as focus_slot:
            control.findChildren(QPushButton)[1].click()
            check("返回/菜单键发出按键请求", key_slot.call_count == 1)
            control.edit.setText("你好")
            control.send_btn.click()
            check("文本推送请求带 serial 与内容",
                  text_slot.call_count == 1 and text_slot.call_args[0][1] == "你好")
            control.title.click()
            check("标题点击请求窗口置前", focus_slot.call_count == 1)
            control.close_requested.emit(window_id)
            check("× 请求关闭该窗口", stop_slot.call_count == 1)

        print("=== 跟随模式（方案 D）===")
        w.state.control_follow_window = True
        control.set_following(True)
        w._sample_geometry()
        check("周期采样记录窗口位置",
              w.processes[window_id].last_geometry == SAMPLED)
        pos1 = (control.x(), control.y())
        check("控制条贴到窗口附近（位置已改变）", pos1 != (30, 40), str(pos1))
        check("控制条宽度按窗口自适应",
              mirrorcontrol.MIN_WIDTH <= control.width() <= mirrorcontrol.MAX_WIDTH,
              str(control.width()))
        bounds_holder["value"] = MOVED
        w._sample_geometry()
        pos2 = (control.x(), control.y())
        check("窗口移动后控制条跟随", pos2 != pos1, f"{pos1} → {pos2}")
        area = app.primaryScreen().availableGeometry()
        check("跟随位置 clamp 在屏幕内",
              area.left() <= control.x() and control.y() >= area.top()
              and control.x() + control.width() <= area.right()
              and control.y() + control.height() <= area.bottom(),
              str(pos2))

        print("=== 手动拖动解除跟随 / 按钮恢复跟随 ===")
        control.move(77, 88)
        control.moved.emit(window_id, 77, 88)
        check("拖动后解除跟随", not control.is_following())
        check("拖动位置已持久化",
              w.state.window_geometry[KEY]["control_x"] == 77)
        bounds_holder["value"] = SAMPLED
        w._sample_geometry()
        check("固定后不再被跟随覆盖", (control.x(), control.y()) == (77, 88))
        control.follow_btn.click()
        check("跟随按钮可恢复跟随", control.is_following())
        check("恢复跟随后立刻贴回窗口", (control.x(), control.y()) != (77, 88))

        print("=== 窗口最小化隐藏与恢复 ===")
        bounds_holder["value"] = None
        for _ in range(3):
            w._sample_geometry()
        check("窗口不在屏幕时控制条隐藏", not control.isVisible())
        bounds_holder["value"] = SAMPLED
        w._sample_geometry()
        check("窗口恢复后控制条重新显示", control.isVisible())

        print("=== 关闭跟随开关 / 退出保存 ===")
        w.state.control_follow_window = False
        before = (control.x(), control.y())
        bounds_holder["value"] = MOVED
        w._sample_geometry()
        check("关闭开关后不再跟随", (control.x(), control.y()) == before)
        w.state.control_follow_window = True
        w._on_finished(window_id)
        saved = w.state.window_geometry[KEY]
        check("退出后保存采样位置", saved.get("x") == 300)
        check("退出后保存控制条位置", "control_x" in saved)
        check("退出后销毁控制条", not w.controls)
        check("没有进程时停止采样定时器", not w._geometry_timer.isActive())

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

    fake_proc = QProcess()
    w.processes["w1"] = MirrorWindow("w1", "微信", KEY, "DEVICE1", fake_proc,
                                     key=KEY)
    with patch.object(QProcess, "processId", lambda self: PID), \
         patch("ui.main_window.nativewindow.window_bounds", return_value=None), \
         patch("ui.main_window.nativewindow.focus_process", return_value=False), \
         patch("ui.main_window.nativewindow.focus_process_fallback",
               return_value=True) as fallback, \
         patch("ui.main_window.run_async", fake_run_async):
        w.focus_mirror("w1")
        check("窗口不在屏幕时走恢复最小化的备用路径", fallback.call_count == 1)
    w.processes.pop("w1", None)

    print("=== 图标 60% 与配套窗口参数 ===")
    check("主 Launchpad 图标 84 → 50", launchpad._ICON == 50)
    check("主网格列宽不变（仍 7 列）", launchpad._CELL_W == 128)
    panel = floatball.FloatPanel()
    _cw, _ch, size = panel._cell_metrics()
    check("悬浮球面板图标 ≤ 48", size <= 48, f"icon={size}")
    check("离屏 window_bounds 安全返回 None",
          nativewindow.window_bounds(PID) is None)
    style_args = build_args(
        MirrorConfig(borderless=True, always_on_top=True), "S", None, None
    )
    check("可配合 scrcpy 自带无边框与置顶参数",
          "--window-borderless" in style_args and "--always-on-top" in style_args)

    print(f"\n结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        for item in FAIL:
            print("  失败:", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
