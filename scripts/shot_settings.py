"""离屏渲染设置对话框截图。用法：shot_settings.py [dark|light]"""
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

from core.config import load_state  # noqa: E402
from ui import style  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "dark"


def main() -> int:
    app = QApplication(sys.argv)
    font = QFont("PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    style.apply(app, MODE)

    dialog = SettingsDialog(None, load_state())
    dialog.resize(520, 600)
    dialog.show()

    target = ROOT / f"screenshot-settings-{MODE}.png"

    def capture() -> None:
        dialog.grab().save(str(target))
        print(f"saved {target}")
        app.quit()

    QTimer.singleShot(700, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
