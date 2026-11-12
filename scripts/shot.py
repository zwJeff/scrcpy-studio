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
    # 截图脚本不改写用户配置：避免 closeEvent 里 persist 触发磁盘写入
    window.persist = lambda: None
    window.resize(1320, 980)
    window.show()

    target = ROOT / "screenshot.png"

    def capture() -> None:
        window.grab().save(str(target))
        print(f"saved {target}")
        # 离屏渲染不需要继续跑真机轮询 / 图标提取，主动收尾避免退出卡顿
        window.timer.stop()
        window._info_timer.stop()
        window._info_token += 1
        window.watcher.stop()
        window._info_pool.shutdown(wait=False, cancel_futures=True)
        app.quit()

    QTimer.singleShot(3200, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
