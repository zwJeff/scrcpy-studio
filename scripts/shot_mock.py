"""用模拟数据渲染有内容状态的截图（等首轮异步刷新结束后再填充）。"""
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
from core.aliases import BUILTIN_ALIASES  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.style import QSS  # noqa: E402

DEVICES = [
    Device("50ad8317", "device", model="Pixel_8", product="shiba",
           usb="337641472X", transport_id="1"),
    Device("192.168.31.5:41235", "device", model="M2012K11AC", product="mi",
           transport_id="2"),
]
PACKAGES = [
    "com.tencent.mm", "com.tencent.mobileqq", "com.ss.android.ugc.aweme",
    "tv.danmaku.bili", "com.xingin.xhs", "com.android.chrome",
    "com.miui.home", "com.android.settings", "com.netease.cloudmusic",
    "com.autonavi.minimap", "com.taobao.taobao", "com.eg.android.AlipayGphone",
]
SYSTEM = {"com.miui.home", "com.android.settings"}


def apply_mock(w: MainWindow) -> None:
    w.current_serial = "50ad8317"
    w.device_panel.set_devices(DEVICES, "50ad8317")
    w.device_panel.set_info("<b>Pixel 8</b><br>Android 16 · 1080x2400<br>192.168.31.7")
    w.app_panel.set_data(
        [(p, f"{p}/.MainActivity") for p in PACKAGES], SYSTEM, dict(BUILTIN_ALIASES),
    )
    w.status_pill.setText("● Pixel 8")
    w.console.log("（模拟数据：2 台设备 · 12 个应用）")


def main() -> int:
    app = QApplication(sys.argv)
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.timer.stop()
    window.resize(1180, 780)
    window.show()

    QTimer.singleShot(1500, lambda: apply_mock(window))

    target = ROOT / "screenshot-mock.png"

    def capture() -> None:
        window.grab().save(str(target))
        print(f"saved {target}")
        app.quit()

    QTimer.singleShot(3000, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
