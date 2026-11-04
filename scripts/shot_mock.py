"""用模拟数据渲染「已连接设备 + 手机桌面」状态的截图。"""
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
from core.apkinfo import AppInfo  # noqa: E402
from core.categories import categorize, color_of  # noqa: E402
from ui.desktop import placeholder  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.style import QSS  # noqa: E402

PACKAGES = [
    ("com.tencent.mm", "微信"), ("com.tencent.mobileqq", "QQ"),
    ("com.xingin.xhs", "小红书"), ("com.sina.weibo", "微博"),
    ("tv.danmaku.bili", "哔哩哔哩"), ("com.ss.android.ugc.aweme", "抖音"),
    ("com.netease.cloudmusic", "网易云音乐"), ("com.qiyi.video", "爱奇艺"),
    ("com.tencent.qqlive", "腾讯视频"), ("com.miHoYo.Yuanshen", "原神"),
    ("com.tencent.tmgp.sgame", "王者荣耀"), ("com.supercell.clashofclans", "部落冲突"),
    ("com.taobao.taobao", "淘宝"), ("com.jingdong.app.mall", "京东"),
    ("com.xunmeng.pinduoduo", "拼多多"), ("com.sankuai.meituan", "美团"),
    ("com.eg.android.AlipayGphone", "支付宝"), ("com.unionpay", "云闪付"),
    ("com.cmbchina.ccd.pluto.cmbactivity", "招商银行"), ("com.autonavi.minimap", "高德地图"),
    ("com.sdu.didi.psnger", "滴滴出行"), ("com.tencent.weread", "微信读书"),
    ("com.zhihu.android", "知乎"), ("com.android.chrome", "Chrome"),
    ("com.android.camera", "相机"), ("com.android.settings", "设置"),
    ("com.miui.smarthome", "米家"), ("com.gotokeep.keep", "Keep"),
    ("com.alibaba.android.rimet", "钉钉"), ("com.miui.home", "桌面"),
]
SYSTEM = {"com.android.settings", "com.miui.home", "com.android.camera"}


def make_icons() -> dict[str, AppInfo]:
    out: dict[str, AppInfo] = {}
    folder = pathlib.Path("/tmp/scrcpy-studio-mock-icons")
    folder.mkdir(parents=True, exist_ok=True)
    for package, name in PACKAGES:
        category = categorize(package, package in SYSTEM)
        path = folder / f"{package.replace('.', '_')}.png"
        placeholder(name, color_of(category), 96).save(str(path))
        out[package] = AppInfo(package, name, str(path), "mock")
    return out


def main() -> int:
    app = QApplication(sys.argv)
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.resize(1320, 980)
    window.show()
    window.timer.stop()
    window._info_timer.stop()
    window._info_token += 1

    target = ROOT / "screenshot-mock.png"

    def apply_mock() -> None:
        devices = [
            Device("50ad8317", "device", model="Pixel_8", product="shiba", usb="337641472X"),
            Device("192.168.31.5:41235", "device", model="M2012K11AC", product="mi"),
        ]
        window.current_serial = "50ad8317"
        window.device_panel.set_devices(devices, "50ad8317")
        window.device_panel.set_info(
            "<b>Pixel 8</b><br>Android 16 · 1080x2400<br>192.168.31.7"
        )
        window.status_pill.setText("● Pixel 8")

        window.app_panel.set_appinfo(make_icons())
        window.app_panel.set_dock(["com.tencent.mm", "com.android.chrome",
                                   "com.ss.android.ugc.aweme", "com.eg.android.AlipayGphone"])
        window.app_panel.set_device_label("Pixel 8")
        window.app_panel.set_data([(p, "") for p, _ in PACKAGES], SYSTEM, {})
        window.app_panel.set_progress("已提取 30 个应用")
        window.input_panel.set_serial("50ad8317")
        window.input_panel.set_status("已就绪")
        window.console.log("$ scrcpy --new-display --start-app=+com.tencent.mm")

    def capture() -> None:
        window.grab().save(str(target))
        print(f"saved {target}")
        app.quit()

    QTimer.singleShot(1600, apply_mock)
    QTimer.singleShot(3000, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
