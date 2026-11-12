"""用模拟数据渲染「已连接设备 + Launchpad + 多投屏窗口」截图。

用法：shot_mock.py [dark|light]
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.adb import Device  # noqa: E402
from ui import style  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "dark"

DEVICES = [
    Device("HA1R28RT", "device", model="Pixel_8_Pro", product="husky", usb="337641472X"),
    Device("192.168.31.5:41235", "device", model="M2012K11AC", product="mi"),
]

PACKAGES = [
    "com.tencent.mm", "com.tencent.mobileqq", "com.ss.android.ugc.aweme",
    "tv.danmaku.bili", "com.xingin.xhs", "com.android.chrome",
    "com.miui.home", "com.android.settings", "com.netease.cloudmusic",
    "com.autonavi.minimap", "com.taobao.taobao", "com.eg.android.AlipayGphone",
    "com.tencent.weread", "com.zhihu.android", "com.sina.weibo",
    "com.miHoYo.Yuanshen", "com.tencent.tmgp.sgame", "com.gotokeep.keep",
    "com.baidu.BaiduMap", "com.dianping.v1", "com.jingdong.app.mall",
    "com.tencent.qqlive", "com.tencent.qqmusic", "com.android.camera",
    "cn.wps.moffice_eng", "com.miui.smarthome", "com.unionpay",
    "com.sankuai.meituan", "com.tencent.wework", "com.taobao.idlefish",
    "com.google.android.gm", "com.android.calculator2", "com.miui.weather2",
]
SYSTEM = {"com.miui.home", "com.android.settings", "com.android.camera",
          "com.android.calculator2", "com.miui.weather2", "com.google.android.gm"}


def main() -> int:
    app = QApplication(sys.argv)
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    style.apply(app, MODE)

    window = MainWindow()
    window.persist = lambda: None
    window.resize(1400, 940)
    window.show()

    # 停掉真实逻辑，避免异步刷新覆盖模拟数据
    window.timer.stop()
    window._info_timer.stop()
    window._info_token += 1
    window.watcher.stop()
    window.on_device_selected = lambda *a, **k: None
    window.load_apps = lambda *a, **k: None
    window.load_appinfo = lambda *a, **k: None

    def apply_mock() -> None:
        window.current_serial = "HA1R28RT"
        window.devices = DEVICES
        window.device_panel.set_devices(DEVICES, "HA1R28RT")
        window.device_panel.set_info("<b>Pixel 8 Pro</b><br>Android 14 · 1440x3120<br>192.168.31.7")
        window.app_panel.set_device_label("Pixel 8 Pro")
        window.app_panel.set_data(
            [(p, f"{p}/.MainActivity") for p in PACKAGES], SYSTEM, {}
        )
        running = {"com.tencent.mm", "com.ss.android.ugc.aweme"}
        window.app_panel.set_running(running)
        window.mirror_bar.setVisible(True)
        window.mirror_bar.set_windows([
            ("a1b2c3d4", "微信"),
            ("e5f6a7b8", "抖音"),
        ])
        window._update_status()
        window.input_panel.set_serial("HA1R28RT")
        window.input_panel.set_expanded(True)
        window.console.set_expanded(False)

    target = ROOT / f"screenshot-{MODE}.png"

    def capture() -> None:
        window.grab().save(str(target))
        print(f"saved {target}")
        app.quit()

    QTimer.singleShot(700, apply_mock)
    QTimer.singleShot(1700, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
