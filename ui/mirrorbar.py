"""投屏窗口条：显示所有正在运行的 scrcpy 窗口，可单独或全部关闭。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from . import style


class MirrorBar(QWidget):
    close_requested = Signal(str)
    close_all_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MirrorBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 7, 10, 7)
        lay.setSpacing(8)

        self.caption = QLabel("正在投屏")
        self.caption.setObjectName("CardTitle")
        lay.addWidget(self.caption)

        self.chips_lay = QHBoxLayout()
        self.chips_lay.setSpacing(6)
        lay.addLayout(self.chips_lay, 1)

        self.close_all = QPushButton("全部关闭")
        self.close_all.setFixedHeight(24)
        self.close_all.clicked.connect(self.close_all_requested)
        lay.addWidget(self.close_all)

    def set_windows(self, windows: list[tuple[str, str]]) -> None:
        """windows: [(窗口 id, 显示名)]"""
        while self.chips_lay.count():
            item = self.chips_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        p = style.P()
        for window_id, label in windows:
            chip = QFrame()
            chip.setObjectName("WindowChip")
            chip.setStyleSheet(
                f"#WindowChip {{ background:{p.accent_soft};"
                f" border:1px solid {p.border}; border-radius:10px; }}"
            )
            row = QHBoxLayout(chip)
            row.setContentsMargins(9, 3, 4, 3)
            row.setSpacing(5)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{p.ok}; font-size:9px; background:transparent;")
            row.addWidget(dot)
            name = QLabel(label)
            name.setObjectName("Hint")
            name.setStyleSheet(f"font-size:11px; color:{p.text}; background:transparent;")
            row.addWidget(name)
            close = QPushButton("×")
            close.setObjectName("CloseChip")
            close.clicked.connect(
                lambda _=False, wid=window_id: self.close_requested.emit(wid)
            )
            row.addWidget(close)
            self.chips_lay.addWidget(chip)
        self.chips_lay.addStretch(1)
        self.caption.setText(f"正在投屏 · {len(windows)} 个窗口" if windows else "正在投屏")
