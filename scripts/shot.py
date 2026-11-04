"""离屏渲染主窗口并截图，用于快速检查布局。"""
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

from ui.main_window import MainWindow  # noqa: E402
from ui.style import QSS  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.resize(1320, 980)
    window.show()

    target = ROOT / "screenshot.png"

    def capture() -> None:
        window.grab().save(str(target))
        print(f"saved {target}")
        app.quit()

    QTimer.singleShot(2200, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
