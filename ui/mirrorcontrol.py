"""每个 scrcpy 投屏窗口配套的控制条。

scrcpy 窗口是独立进程，无法在其中嵌入 Qt 控件；因此为每个窗口提供一个
始终置顶、可拖动的紧凑控制条：导航按键、文本推送到手机输入框、窗口置前与关闭。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from core.config import CONTROL_ITEM_DEFAULTS

from . import style

WIDTH = 660
MIN_WIDTH = 520
MAX_WIDTH = 660
HEIGHT = 58

# (显示符号, 完整说明, textinput.KEYCODE 里的键名)
KEYS = [
    ("◀", "返回（Back）", "back"),
    ("☰", "菜单（Menu）", "menu"),
    ("⌂", "主屏（Home）", "home"),
    ("▤", "最近任务（Recents）", "recents"),
]


class DragHandle(QWidget):
    """控制条顶部的小拖动把手。"""

    def __init__(self, owner: "MirrorControl"):
        super().__init__(owner)
        self.owner = owner
        self.setFixedHeight(9)
        self.setCursor(Qt.SizeAllCursor)
        self._offset: QPoint | None = None
        self._press_at: QPoint | None = None
        self._moved = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 90 if style.is_dark() else 90))
        painter.drawRoundedRect(
            QRectF(self.width() / 2 - 18, 2, 36, 3), 1.5, 1.5
        )
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_at = event.globalPos()
            self._offset = event.globalPos() - self.owner.frameGeometry().topLeft()
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._offset is not None and event.buttons() & Qt.LeftButton:
            if self._press_at is not None and \
                    (event.globalPos() - self._press_at).manhattanLength() > 4:
                self._moved = True
            # 只有真正拖动才移动，避免单击把手被当成拖动
            if self._moved:
                self.owner.move(event.globalPos() - self._offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        # 单击把手不该解除跟随，只有位移超过阈值才算用户手动固定
        if self._moved:
            self.owner.moved.emit(self.owner.window_id, self.owner.x(), self.owner.y())
        self._offset = None
        self._press_at = None
        self._moved = False
        super().mouseReleaseEvent(event)


class MirrorControl(QWidget):
    key_requested = Signal(str, str)              # serial, key name
    text_requested = Signal(str, str, bool)       # serial, text, enter
    copy_requested = Signal(str)                  # text
    close_requested = Signal(str)                 # window_id
    focus_requested = Signal(str)                 # window_id
    moved = Signal(str, int, int)                 # window_id, x, y
    follow_toggled = Signal(str, bool)            # window_id, 是否跟随

    def __init__(self, window_id: str, label: str, serial: str,
                 items: dict | None = None):
        super().__init__()
        self.window_id = window_id
        self.serial = serial
        self._label = label
        self._following = True
        self._items = dict(CONTROL_ITEM_DEFAULTS)
        if items:
            self._items.update({
                key: bool(value) for key, value in items.items()
                if key in CONTROL_ITEM_DEFAULTS
            })
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(2400)
        self._status_timer.timeout.connect(self._restore_title)

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(WIDTH)
        self.setFixedHeight(HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 3, 10, 6)
        outer.setSpacing(3)
        self.drag_handle = DragHandle(self)
        outer.addWidget(self.drag_handle)

        row = QHBoxLayout()
        row.setSpacing(5)
        self.title = QPushButton(label)
        self.title.setObjectName("ControlTitle")
        self.title.setFixedWidth(116)
        self.title.setFixedHeight(26)
        self.title.setCursor(Qt.PointingHandCursor)
        self.title.setToolTip("点击把这个投屏窗口置前")
        self.title.clicked.connect(
            lambda: self.focus_requested.emit(self.window_id)
        )
        row.addWidget(self.title)

        self.key_buttons: dict[str, QPushButton] = {}
        for symbol, tip, key in KEYS:
            btn = QPushButton(symbol)
            btn.setObjectName("ControlKey")
            btn.setFixedSize(30, 26)
            btn.setToolTip(tip)
            btn.clicked.connect(
                lambda _=False, k=key: self.key_requested.emit(self.serial, k)
            )
            self.key_buttons[key] = btn
            row.addWidget(btn)

        self.edit = QLineEdit()
        self.edit.setObjectName("ControlInput")
        self.edit.setPlaceholderText("输入文字推送到手机输入框…")
        self.edit.setFixedHeight(26)
        self.edit.returnPressed.connect(self._send)
        row.addWidget(self.edit, 1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("ControlAction")
        self.send_btn.setFixedHeight(26)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)

        self.copy_btn = QPushButton("复制")
        self.copy_btn.setObjectName("ControlAction")
        self.copy_btn.setFixedHeight(26)
        self.copy_btn.setToolTip("复制到剪贴板，再到投屏窗口按 ⌘V 粘贴（支持中文）")
        self.copy_btn.clicked.connect(self._copy)
        row.addWidget(self.copy_btn)

        self.follow_btn = QPushButton("跟随")
        self.follow_btn.setObjectName("ControlAction")
        self.follow_btn.setFixedSize(52, 26)
        self.follow_btn.setToolTip("点击切换：跟随投屏窗口 / 保持当前位置")
        self.follow_btn.clicked.connect(self._toggle_follow)
        row.addWidget(self.follow_btn)

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("ControlClose")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("关闭这个投屏窗口")
        self.close_btn.clicked.connect(
            lambda: self.close_requested.emit(self.window_id)
        )
        row.addWidget(self.close_btn)
        outer.addLayout(row)
        self._apply_palette()
        self.apply_items(self._items)

    # ---------- 跟随 ----------
    def _toggle_follow(self) -> None:
        self.set_following(not self._following)
        self.follow_toggled.emit(self.window_id, self._following)

    def set_following(self, value: bool) -> None:
        self._following = bool(value)
        self.follow_btn.setText("跟随" if self._following else "固定")
        self.follow_btn.setToolTip(
            "当前跟随投屏窗口，点击改为固定位置"
            if self._following else "当前固定位置，点击恢复跟随"
        )

    def is_following(self) -> bool:
        return self._following

    def apply_items(self, items: dict) -> None:
        """按用户勾选显示/隐藏控制条里的各个控件。"""
        self._items = dict(CONTROL_ITEM_DEFAULTS)
        for key, value in (items or {}).items():
            if key in CONTROL_ITEM_DEFAULTS:
                self._items[key] = bool(value)
        on = self._items
        self.title.setVisible(on["title"])
        for key, btn in self.key_buttons.items():
            btn.setVisible(on.get(key, True))
        self.edit.setVisible(on["input"])
        self.send_btn.setVisible(on["input"])
        self.copy_btn.setVisible(on["copy"])
        self.follow_btn.setVisible(on["follow"])
        self.close_btn.setVisible(on["close"])
        self.drag_handle.setVisible(on["drag"])

    def set_content_width(self, width: int) -> None:
        """窄窗口时收窄控制条并隐藏次要按钮，避免伸出窗口太多。"""
        value = max(MIN_WIDTH, min(MAX_WIDTH, int(width)))
        if value != self.width():
            self.setFixedWidth(value)
        self.copy_btn.setVisible(self._items.get("copy", True) and value >= 580)
        self.title.setFixedWidth(100 if value < 580 else 116)

    # ---------- 交互 ----------
    def _send(self) -> None:
        text = self.edit.text()
        if not text:
            return
        self.text_requested.emit(self.serial, text, False)
        self.edit.clear()

    def _copy(self) -> None:
        text = self.edit.text()
        if text:
            self.copy_requested.emit(text)

    def set_status(self, text: str) -> None:
        self.title.setText(text)
        self._status_timer.start()

    def _restore_title(self) -> None:
        self.title.setText(self._label)

    def set_theme(self) -> None:
        self._apply_palette()
        self.update()

    def _apply_palette(self) -> None:
        dark = style.is_dark()
        fg = "#EEF5FF" if dark else "#1B2534"
        fg2 = "rgba(226,238,255,0.62)" if dark else "rgba(40,60,90,0.62)"
        surface = "rgba(255,255,255,0.10)" if dark else "rgba(30,70,130,0.08)"
        border = "rgba(255,255,255,0.14)" if dark else "rgba(30,70,130,0.18)"
        self.setStyleSheet(f"""
            QPushButton#ControlTitle {{
                color:{fg}; font-size:11px; font-weight:600;
                background:transparent; border:none; text-align:left; padding:0;
            }}
            QPushButton#ControlTitle:hover {{ color:#7FB2FF; }}
            QPushButton#ControlKey, QPushButton#ControlAction {{
                background:{surface}; border:1px solid {border}; border-radius:7px;
                color:{fg}; font-size:12px; padding:0 8px;
            }}
            QPushButton#ControlClose {{
                background:{surface}; border:1px solid {border}; border-radius:7px;
                color:{fg}; font-size:14px; padding:0;
            }}
            QPushButton:hover {{ background:rgba(72,140,255,0.42); color:#FFFFFF; }}
            #ControlInput {{
                background:{surface}; border:1px solid {border}; border-radius:7px;
                color:{fg}; font-size:11px; padding:0 8px; selection-background-color:#3C7BE0;
            }}
            #ControlInput::placeholder {{ color:{fg2}; }}
        """)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        dark = style.is_dark()
        bg = QColor(8, 30, 54, 232) if dark else QColor(247, 251, 255, 238)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), bg)
        painter.setPen(QColor(255, 255, 255, 78) if dark else QColor(30, 60, 100, 60))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12
        )
        painter.end()
