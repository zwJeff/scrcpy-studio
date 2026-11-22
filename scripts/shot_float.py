"""离屏渲染悬浮球 + 展开面板的合成效果图。用法：shot_float.py [dark|light]"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import apkinfo  # noqa: E402
from ui import style  # noqa: E402
from ui.desktop import AppData  # noqa: E402
from ui.floatball import FloatController  # noqa: E402
from ui.mirrorcontrol import MirrorControl  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "dark"
CATEGORIES = ["social", "media", "game", "shopping", "finance", "tools", "other"]


def mock_apps() -> list[AppData]:
    cached = apkinfo.all_cached()
    apps: list[AppData] = []
    for index, (pkg, info) in enumerate(list(cached.items())[:33]):
        apps.append(AppData(
            package=pkg,
            name=(info.label if info and info.label else pkg),
            icon=(info.icon if info and info.usable else ""),
            category=CATEGORIES[index % len(CATEGORIES)],
        ))
    if len(apps) < 33:
        for i in range(len(apps), 33):
            apps.append(AppData(f"com.demo.app{i}", f"应用 {i}",
                                category=CATEGORIES[i % len(CATEGORIES)]))
    return apps


def render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    widget.render(painter, QPoint())
    painter.end()
    return image


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    style.apply(app, MODE)

    controller = FloatController()
    controller.set_apps(mock_apps())
    controller.set_device_label("TB570FU")
    controller.show((60, 60))
    controller.set_running_windows([
        ("a1", "微信"), ("b2", "WPS Office"), ("c3", "抖音"),
    ])

    controller.panel.setFixedSize(830, 620)
    controller.panel.move(300, 150)
    controller.panel.ensure_built()   # 面板隐藏时数据延迟构建，截图前显式触发
    controller.panel.show()

    # 右键出现的「已投屏窗口」列表（截图里固定放到小球下方，避免与应用面板重叠）
    controller.window_list.move(60, 140)
    controller.window_list.show()

    # 每个投屏窗口配套的控制条示意
    control = MirrorControl("demo", "WPS Office", "DEVICE1")
    control.edit.setText("季度汇报")
    control.show()

    canvas = QImage(1240, 880, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    style.paint_wallpaper(painter, canvas.rect())
    painter.drawImage(300, 150, render(controller.panel))
    painter.drawImage(60, 140, render(controller.window_list))
    painter.drawImage(300, 792, render(control))
    painter.drawImage(60, 60, render(controller.ball))
    painter.end()
    control.hide()

    target = ROOT / (f"screenshot-float-{MODE}.png" if MODE != "dark"
                     else "screenshot-float.png")
    canvas.save(str(target), "PNG")
    print(f"saved {target}")
    controller.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
