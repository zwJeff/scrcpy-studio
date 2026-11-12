"""离屏渲染主窗口（空状态）并截图。用法：shot.py [dark|light]"""
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

from ui import style  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "dark"


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

    target = ROOT / ("screenshot.png" if MODE == "dark"
                     else f"screenshot-{MODE}-empty.png")

    def capture() -> None:
        window.grab().save(str(target))
        print(f"saved {target}")
        window.timer.stop()
        window._info_timer.stop()
        window._info_token += 1
        window.watcher.stop()
        window._info_pool.shutdown(wait=False, cancel_futures=True)
        app.quit()

    QTimer.singleShot(1800, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
