"""回归自检：首次连接空结果、刷新语义与网格重建开销。

离线运行，不访问真实设备（adb / APK 提取全部 mock）。
    .venv/bin/python scripts/verify_connect.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
app.setQuitOnLastWindowClosed(False)

from core import adb, apkinfo  # noqa: E402
from core.config import AppState  # noqa: E402
from ui import launchpad, style  # noqa: E402
from ui.desktop import AppData  # noqa: E402
from ui.floatball import FloatController  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

style.apply(app, "dark")

PASS, FAIL = [], []


def check(label: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' · ' + detail) if detail else ''}")


def fake_run_async(fn, on_done=None, on_error=None, *args, **kwargs):
    """把线程池回调同步化，便于确定性地断言状态机。"""
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        if on_error:
            on_error(str(exc))
    else:
        if on_done:
            on_done(result)


DEVICES = [adb.Device("DEVICE1", "device", model="TestPhone")]
PKGS = [(f"com.demo.app{i:02d}", f".Main{i}") for i in range(51)]


def main() -> int:
    print("=== 首次连接：空结果不缓存 + 自动重试 ===")
    seq = iter([[], [], PKGS])
    with patch("ui.main_window.run_async", fake_run_async), \
         patch.object(adb, "list_devices", return_value=DEVICES), \
         patch.object(adb, "list_apps", side_effect=lambda _s: next(seq)), \
         patch.object(adb, "system_packages", return_value=set()), \
         patch.object(MainWindow, "load_appinfo", lambda self, force=False: None):
        w = MainWindow()
        w.persist = lambda: None
        w.timer.stop()
        w._info_timer.stop()
        w.watcher.stop()

        check("首次读取后 current_serial 已设置", w.current_serial == "DEVICE1",
              w.current_serial)
        check("空结果未写入 app_cache", not w.app_cache.get("DEVICE1"),
              str(list(w.app_cache)))
        check("已安排重试", w._apps_retry.get("DEVICE1") == 1,
              str(w._apps_retry))
        check("没有卡住的 loading 标记", not w._apps_loading,
              str(w._apps_loading))

        w._retry_apps("DEVICE1")          # 第二次仍然空
        check("第二次空结果继续重试", w._apps_retry.get("DEVICE1") == 2)
        check("第二次仍未污染缓存", not w.app_cache.get("DEVICE1"))

        w._retry_apps("DEVICE1")          # 第三次返回真实列表
        check("成功后 app_cache 写入 51 个应用", len(w.app_cache.get("DEVICE1", [])) == 51,
              str(len(w.app_cache.get("DEVICE1", []))))
        check("成功后重试计数清零", w._apps_retry.get("DEVICE1") is None)
        check("界面已渲染 51 个应用", len(w.app_panel.all_apps()) == 51)
        check("进度文字已清空", w.app_panel._progress_text == "")

        print("=== 手动刷新：只重读列表，不重抓图标 ===")
        with patch.object(apkinfo, "invalidate") as invalidated, \
             patch.object(adb, "list_apps", return_value=PKGS):
            w.load_apps(force=True)
            check("重新读取应用不触发 invalidate", invalidated.call_count == 0,
                  f"调用 {invalidated.call_count} 次")

        w._info_pool.shutdown(wait=False, cancel_futures=True)

    print("=== APK 路径批量预取 ===")
    sample = ("package:/data/app/~~abc/base.apk=com.demo.a\n"
              "package:/system/priv-app/B.apk=com.demo.b\n"
              "garbage line\n")
    with patch.object(apkinfo, "_shell_text", return_value=sample):
        paths = apkinfo.prefetch_paths("S")
    check("一次调用解析出 2 条路径", paths == {
        "com.demo.a": "/data/app/~~abc/base.apk",
        "com.demo.b": "/system/priv-app/B.apk",
    }, str(paths))

    print("=== 网格增量更新 ===")
    apps = [AppData(f"com.demo.a{i}", f"应用{i}") for i in range(51)]
    lp = launchpad.Launchpad()
    lp.set_data(apps)
    first = lp._icons[0]
    lp.set_data(list(apps))
    check("相同数据不重建 widget", lp._icons[0] is first)
    renamed = list(apps)
    renamed[0] = AppData(renamed[0].package, "新名称")
    lp.set_data(renamed)
    check("名称变化仍复用同一 widget", lp._icons[0] is first,
          lp._icons[0].name_label.text())
    check("名称已局部更新", "新名称" in lp._icons[0].name_label.text())

    a, b = apps[0], apps[1]
    launchpad.app_pixmap(a, 84)
    launchpad.app_pixmap(b, 84)
    before = len(launchpad._PIX_CACHE)
    launchpad.clear_pixmap_cache({a.package})
    check("变化包的缓存已清除",
          not any(k[0] == a.package for k in launchpad._PIX_CACHE),
          f"{before} → {len(launchpad._PIX_CACHE)}")
    check("其他包的缓存未受影响",
          any(k[0] == b.package for k in launchpad._PIX_CACHE))

    print("=== 悬浮球面板隐藏时延迟构建 ===")
    c = FloatController()
    c.show()
    c.set_apps(apps)
    check("隐藏时不构建图标", len(c.panel._icons) == 0)
    c.toggle_panel()
    check("展开后一次性构建 51 个", len(c.panel._icons) == 51)

    print(f"\n结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        for item in FAIL:
            print("  失败:", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
