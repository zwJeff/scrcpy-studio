"""离屏渲染 USB 连接向导（使用真机状态）并截图。"""
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

from ui.style import QSS  # noqa: E402
from ui.usbdialog import UsbDialog  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(QSS)

    dialog = UsbDialog(port=5555, prefer_usb=True)
    dialog.show()
    target = ROOT / "screenshot-usb.png"

    def capture() -> None:
        dialog.grab().save(str(target))
        print(f"saved {target}")
        print("状态区:\n" + dialog.status.toPlainText())
        print("诊断:", dialog.diagnosis.text())
        dialog._closed = True
        app.quit()

    QTimer.singleShot(2600, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
