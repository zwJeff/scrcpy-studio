"""回归自检：投屏去重/置前、悬浮球角标、hover 小列表、投屏后自动进入悬浮球。

离线运行，scrcpy 进程与原生置前全部 mock。
    .venv/bin/python scripts/verify_mirror.py
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
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
app.setQuitOnLastWindowClosed(False)

from core import adb, apkinfo, paths  # noqa: E402
from ui import style  # noqa: E402
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


def main() -> int:
    with patch("ui.main_window.run_async", fake_run_async), \
         patch.object(adb, "list_devices", return_value=[]), \
         patch.object(adb, "system_packages", return_value=set()):
        w = MainWindow()
    w.persist = lambda: None
    w.timer.stop()
    w._info_timer.stop()
    w.watcher.stop()
    w._info_pool.shutdown(wait=False, cancel_futures=True)
    w.current_serial = "DEVICE1"
    w.devices = [adb.Device("DEVICE1", "device", model="Phone")]
    w.state.auto_float_on_mirror = False     # 去重测试期间不自动隐藏主窗口

    print("=== 重复点击不再启动第二个投屏进程 ===")
    with patch.object(QProcess, "start", lambda self, *a, **k: None), \
         patch.object(QProcess, "state", lambda self: QProcess.Running), \
         patch.object(QProcess, "processId", lambda self: 4321), \
         patch("ui.main_window.build_args",
               return_value=["scrcpy", "-s", "DEVICE1"]), \
         patch.object(paths, "supports_new_display", return_value=True), \
         patch("ui.main_window.nativewindow.window_bounds",
               return_value={"x": 10, "y": 10, "width": 400, "height": 600}), \
         patch("ui.main_window.nativewindow.focus_process",
               return_value=True) as focus:
        for pkg in ("com.a", "com.b", "com.c"):
            w.start_mirror(package=pkg)
        check("3 个应用各自开窗口", len(w.processes) == 3, str(len(w.processes)))

        before = len(w.processes)
        w.start_mirror(package="com.a")
        check("重复点击同一应用不新增进程", len(w.processes) == before,
              str(len(w.processes)))
        check("重复点击触发置前", focus.call_count == 1,
              f"focus 调用 {focus.call_count} 次")

        w.start_mirror()                       # 整屏
        check("整屏可与应用窗口并存", len(w.processes) == 4)
        w.start_mirror()
        check("重复整屏不新增进程", len(w.processes) == 4)
        check("角标数字 = 4", w.float_controller.ball._count == 4,
              str(w.float_controller.ball._count))
        check("hover 列表条目 = 4",
              w.float_controller.window_list.rows.count() == 4)

        wid = next(iter(w.processes))
        w._on_finished(wid)
        check("单个窗口退出后角标 = 3",
              w.float_controller.ball._count == 3,
              str(w.float_controller.ball._count))

    print("=== 右键已投屏列表 ===")
    c = w.float_controller
    c.show()
    c.toggle_window_list()
    check("右键后列表可见", c.window_list.isVisible())
    check("列表跟随球定位", c.window_list.x() >= 0 and c.window_list.y() >= 0)
    seen = []
    c.focus_requested.connect(lambda value: seen.append(value))
    c.window_list.rows.itemAt(0).widget().click()
    check("点击条目发出置前请求", len(seen) == 1, str(seen))
    check("点击后列表收起", not c.window_list.isVisible())
    c.toggle_window_list()
    c.toggle_window_list()
    check("再次右键可收起列表", not c.window_list.isVisible())

    print("=== 单击悬浮球仍展开应用面板 ===")
    c.ball.hovered.emit(False)
    c.toggle_panel()
    check("单击展开面板", c.panel.isVisible())
    c.toggle_panel()
    check("再次单击收起面板", not c.panel.isVisible())

    print("=== 投屏成功后自动进入悬浮球并收起面板 ===")
    c.toggle_panel()
    check("投屏前面板处于展开态", c.panel.isVisible())
    w.state.auto_float_on_mirror = True
    w._after_mirror_started()
    check("已进入悬浮球模式", w._float_mode)
    check("应用面板已收起", not c.panel.isVisible())
    check("hover 列表也已收起", not c.window_list.isVisible())
    w.state.auto_float_on_mirror = False
    w.exit_float_mode()
    check("关闭开关后不自动进入", not w._float_mode)

    print("=== 离屏平台原生置前安全降级 ===")
    from ui import nativewindow
    check("离屏 focus_process 返回 False 且不崩",
          nativewindow.focus_process(4321) is False)

    print(f"\n结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        for item in FAIL:
            print("  失败:", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
