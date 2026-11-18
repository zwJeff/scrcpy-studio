"""生成 Scrcpy Studio 的 App 图标（1024px PNG）。

设计语义：手机画面投送到外接显示器。白色主体 + 蓝色渐变底，
在 16px 的 Dock 尺寸下仍能辨认轮廓。
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter,
    QPainterPath, QPen,
)

SIZE = 1024


def rounded(painter: QPainter, rect: QRectF, radius: float, color: QColor) -> None:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, QBrush(color))


def main() -> int:
    app = QGuiApplication(sys.argv)
    image = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # 蓝色渐变圆角底
    gradient = QLinearGradient(0, 0, SIZE, SIZE)
    gradient.setColorAt(0, QColor("#0D2A55"))
    gradient.setColorAt(0.55, QColor("#1B4DA8"))
    gradient.setColorAt(1, QColor("#3D8BFF"))
    base = QPainterPath()
    base.addRoundedRect(QRectF(0, 0, SIZE, SIZE), 232, 232)
    painter.fillPath(base, QBrush(gradient))

    white = QColor("#FFFFFF")
    # 显示器外框
    rounded(painter, QRectF(146, 196, 732, 516), 74, white)
    # 屏幕内区
    rounded(painter, QRectF(178, 228, 668, 452), 48, QColor("#12376C"))
    # 顶部三点
    for cx in (232, 288, 344):
        rounded(painter, QRectF(cx - 13, 268, 26, 26), 13, QColor("#6FA5F0"))
    # 分隔线
    rounded(painter, QRectF(200, 318, 624, 6), 3, QColor(255, 255, 255, 42))

    # 手机
    rounded(painter, QRectF(288, 366, 208, 288), 46, white)
    rounded(painter, QRectF(302, 380, 180, 260), 34, QColor("#3D8BFF"))
    rounded(painter, QRectF(360, 392, 64, 12), 6, white)
    # 手机屏幕上的一抹高光
    highlight = QPainterPath()
    highlight.addRoundedRect(QRectF(318, 420, 148, 196), 24, 24)
    painter.fillPath(highlight, QBrush(QColor(255, 255, 255, 46)))

    # 投送箭头
    rounded(painter, QRectF(540, 492, 118, 24), 12, white)
    triangle = QPainterPath()
    triangle.moveTo(646, 452)
    triangle.lineTo(726, 504)
    triangle.lineTo(646, 556)
    triangle.closeSubpath()
    painter.fillPath(triangle, QBrush(white))

    # 支架与底座
    rounded(painter, QRectF(452, 712, 120, 66), 18, white)
    rounded(painter, QRectF(356, 772, 312, 38), 19, white)
    painter.end()

    out_dir = ROOT / "resources"
    if not out_dir.exists():
        out_dir.mkdir(parents=True)
    target = out_dir / "AppIcon.png"
    if not image.save(str(target), "PNG"):
        raise SystemExit("保存 PNG 失败")
    print(f"saved {target} ({target.stat().st_size} bytes)")

    # 用 Qt 直接生成各尺寸，避免 shell 分词与 sips 参数差异
    iconset = pathlib.Path(tempfile.mkdtemp(prefix="scrcpy-iconset-")) / "AppIcon.iconset"
    iconset.mkdir()
    sizes = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for px, name in sizes:
        scaled = image.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled.save(str(iconset / name), "PNG")
    icns = out_dir / "AppIcon.icns"
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"iconutil 失败：{result.stderr.strip()}")
    bundle = ROOT / "ScrcpyStudio.app" / "Contents" / "Resources"
    if not bundle.exists():
        bundle.mkdir(parents=True)
    shutil.copy2(icns, bundle / "AppIcon.icns")
    shutil.rmtree(iconset.parent, ignore_errors=True)
    print(f"saved {icns} ({icns.stat().st_size} bytes)")
    print(f"installed → {bundle / 'AppIcon.icns'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
