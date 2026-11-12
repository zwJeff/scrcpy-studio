"""设备输入面板：把 Mac 上敲的文本推送到手机当前焦点输入框。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from . import style
from .panels import Card


class _InputEdit(QPlainTextEdit):
    """⌘↵ / Ctrl+↵ 直接发送，而不是插入换行。"""
    send_shortcut = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & (
            Qt.ControlModifier | Qt.MetaModifier
        ):
            self.send_shortcut.emit()
            return
        super().keyPressEvent(event)


class InputPanel(Card):
    send_requested = Signal(str, bool)
    copy_requested = Signal(str)
    key_requested = Signal(str)
    mode_changed = Signal(str)
    enter_changed = Signal(bool)

    def __init__(self):
        super().__init__("设备输入")
        self._serial = ""
        self._history: list[str] = []
        self._status_ok = True

        self.toggle_btn = QPushButton("收起")
        self.toggle_btn.setFixedHeight(24)
        self.toggle_btn.clicked.connect(self._toggle)
        self.head_extra.addWidget(self.toggle_btn)

        self.btn_history = QPushButton("历史")
        self.btn_history.setFixedHeight(24)
        self.btn_history.clicked.connect(self._show_history)
        self.head_extra.addWidget(self.btn_history)

        self.content = QWidget()
        self.body.addWidget(self.content)
        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.edit = _InputEdit()
        self.edit.setObjectName("InputBox")
        self.edit.setPlaceholderText("在这里输入内容，发送到手机当前获得焦点的输入框…")
        self.edit.setFixedHeight(58)
        self.edit.send_shortcut.connect(self.send)
        top.addWidget(self.edit, 1)

        actions = QVBoxLayout()
        actions.setSpacing(5)
        self.btn_send = QPushButton("发送")
        self.btn_send.setObjectName("Primary")
        self.btn_send.setMinimumHeight(30)
        self.btn_send.clicked.connect(self.send)
        actions.addWidget(self.btn_send)
        row_btn = QHBoxLayout()
        row_btn.setSpacing(5)
        btn_copy = QPushButton("复制")
        btn_copy.setToolTip("放进 Mac 剪贴板，再到 scrcpy 窗口按 ⌘V 粘贴（支持中文）")
        btn_copy.clicked.connect(lambda: self.copy_requested.emit(self.text()))
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self.edit.clear)
        row_btn.addWidget(btn_copy)
        row_btn.addWidget(btn_clear)
        actions.addLayout(row_btn)
        top.addLayout(actions)
        lay.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.mode = QComboBox()
        self.mode.addItem("自动", "auto")
        self.mode.addItem("仅英文 (input text)", "ascii")
        self.mode.addItem("ADBKeyBoard（中文）", "adbkeyboard")
        self.mode.setFixedWidth(176)
        self.mode.currentIndexChanged.connect(
            lambda: self.mode_changed.emit(self.mode.currentData())
        )
        bottom.addWidget(self.mode)

        self.enter = QCheckBox("发送后回车")
        self.enter.stateChanged.connect(
            lambda: self.enter_changed.emit(self.enter.isChecked())
        )
        bottom.addWidget(self.enter)
        for text, key in (("回车", "enter"), ("退格", "backspace"), ("返回", "back")):
            btn = QPushButton(text)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _=False, k=key: self.key_requested.emit(k))
            bottom.addWidget(btn)
        bottom.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("Hint")
        bottom.addWidget(self.status)
        lay.addLayout(bottom)

        self.hint = QLabel("⌘↵ 发送 · ⌘K 聚焦 · 中文需 ADBKeyBoard，或「复制」后在 scrcpy 窗口按 ⌘V")
        self.hint.setObjectName("Hint")
        lay.addWidget(self.hint)

    # ---------- 对外 ----------
    def text(self) -> str:
        return self.edit.toPlainText()

    def set_text(self, value: str) -> None:
        self.edit.setPlainText(value)

    def focus_input(self) -> None:
        self.set_expanded(True)
        self.edit.setFocus()
        self.edit.selectAll()

    def set_expanded(self, value: bool) -> None:
        self.content.setVisible(value)
        self.toggle_btn.setText("收起" if value else "展开")
        self.setFixedHeight(158 if value else 44)

    def is_expanded(self) -> bool:
        return self.content.isVisible()

    def _toggle(self) -> None:
        self.set_expanded(not self.is_expanded())

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        self.btn_send.setEnabled(bool(serial))
        self.set_status("已就绪" if serial else "等待设备连接", ok=bool(serial))

    def set_mode(self, mode: str) -> None:
        index = self.mode.findData(mode)
        if index >= 0:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(index)
            self.mode.blockSignals(False)

    def set_enter(self, value: bool) -> None:
        self.enter.blockSignals(True)
        self.enter.setChecked(value)
        self.enter.blockSignals(False)

    def set_history(self, items: list[str]) -> None:
        self._history = list(items)

    def set_status(self, text: str, ok: bool = True) -> None:
        self._status_ok = ok
        self.status.setText(text)
        self._apply_status_color()

    def retheme(self) -> None:
        self._apply_status_color()

    def _apply_status_color(self) -> None:
        p = style.P()
        self.status.setStyleSheet(
            f"font-size:11px; color:{p.ok if self._status_ok else p.danger};"
        )

    def send(self) -> None:
        value = self.text()
        if not value.strip():
            self.set_status("请输入内容", ok=False)
            return
        if not self._serial:
            self.set_status("没有可用设备", ok=False)
            return
        self.send_requested.emit(value, self.enter.isChecked())

    def _show_history(self) -> None:
        if not self._history:
            self.set_status("暂无历史记录", ok=False)
            return
        menu = QMenu(self)
        chosen = [None]

        def pick(value: str) -> None:
            chosen[0] = value

        for item in self._history[:12]:
            action = menu.addAction(item.replace("\n", " ")[:48])
            action.triggered.connect(lambda _=False, v=item: pick(v))
        menu.exec(self.btn_history.mapToGlobal(self.btn_history.rect().bottomLeft()))
        if chosen[0] is not None:
            self.set_text(chosen[0])
            self.focus_input()
