#!/usr/bin/env python3
"""Scrcpy Studio 入口。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402
from ui.style import QSS  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Scrcpy Studio")
    app.setApplicationDisplayName("Scrcpy Studio")
    app.setApplicationVersion("0.1.0")
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
