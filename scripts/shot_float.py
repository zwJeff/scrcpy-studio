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
    controller.panel.setFixedSize(830, 620)
    controller.panel.move(150, 130)
    controller.panel.show()

    canvas = QImage(1120, 820, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    style.paint_wallpaper(painter, canvas.rect())
    painter.drawImage(150, 130, render(controller.panel))
    painter.drawImage(60, 60, render(controller.ball))
    painter.end()

    target = ROOT / (f"screenshot-float-{MODE}.png" if MODE != "dark"
                     else "screenshot-float.png")
    canvas.save(str(target), "PNG")
    print(f"saved {target}")
    controller.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
