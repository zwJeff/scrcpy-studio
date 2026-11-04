"""无线连接与配对对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from core import adb
from core.tasks import run_async

from .style import ACCENT, BORDER, OK, TEXT2, TEXT3, WARN

DIALOG_QSS = f"""
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 9px; background: #FFFFFF; }}
QTabBar::tab {{
    background: transparent; border: none; padding: 5px 14px; margin-right: 4px;
    color: {TEXT2}; font-size: 12px;
}}
QTabBar::tab:selected {{ color: {ACCENT}; font-weight: 600; }}
"""


class WirelessDialog(QDialog):
    connected = Signal(str)

    def __init__(self, parent=None, start_tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("无线连接")
        self.setFixedWidth(430)
        self.setStyleSheet(DIALOG_QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        title = QLabel("连接无线设备")
        title.setStyleSheet("font-size:15px; font-weight:600;")
        outer.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_direct(), "直连")
        tabs.addTab(self._build_pair(), "配对（Android 11+）")
        tabs.setCurrentIndex(1 if start_tab else 0)
        outer.addWidget(tabs)

        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        outer.addLayout(row)

    # ---------- 直连 ----------
    def _build_direct(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(9)

        tip = QLabel("手机已经开启「无线调试」并与本机配对过时，填地址直接连接。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"font-size:11px; color:{TEXT3};")
        lay.addWidget(tip)

        self.direct_addr = QLineEdit()
        self.direct_addr.setPlaceholderText("192.168.1.23:41235（端口见手机无线调试页）")
        lay.addWidget(self.direct_addr)

        connect_btn = QPushButton("连接")
        connect_btn.setObjectName("Primary")
        connect_btn.clicked.connect(self._do_connect)
        lay.addWidget(connect_btn)

        self.direct_status = QLabel("")
        self.direct_status.setWordWrap(True)
        self.direct_status.setStyleSheet(f"font-size:11px; color:{TEXT2};")
        lay.addWidget(self.direct_status)

        lay.addSpacing(4)
        scan_row = QHBoxLayout()
        scan_label = QLabel("局域网自动发现")
        scan_label.setStyleSheet(f"font-size:11px; color:{TEXT3};")
        scan_row.addWidget(scan_label)
        scan_row.addStretch(1)
        scan_btn = QPushButton("扫描")
        scan_btn.setFixedHeight(24)
        scan_btn.clicked.connect(lambda: self._scan(scan_btn))
        scan_row.addWidget(scan_btn)
        lay.addLayout(scan_row)

        self.mdns_list = QListWidget()
        self.mdns_list.setFixedHeight(92)
        self.mdns_list.itemDoubleClicked.connect(self._connect_item)
        lay.addWidget(self.mdns_list)
        lay.addStretch(1)
        return page

    def _scan(self, button: QPushButton) -> None:
        button.setEnabled(False)
        button.setText("扫描中…")
        self.mdns_list.clear()

        def done(services):
            button.setEnabled(True)
            button.setText("扫描")
            for name, stype, addr in services:
                if "tls-connect" not in stype:
                    continue
                item = QListWidgetItem(f"{addr}    {name}")
                item.setData(Qt.UserRole, addr)
                self.mdns_list.addItem(item)
            if not self.mdns_list.count():
                self.mdns_list.addItem("未发现设备：请确认手机已开启无线调试、与本机在同一 Wi-Fi")

        def fail(message: str):
            button.setEnabled(True)
            button.setText("扫描")
            self.mdns_list.addItem(f"扫描失败：{message}")

        run_async(adb.mdns_services, done, fail)

    def _connect_item(self, item: QListWidgetItem) -> None:
        addr = item.data(Qt.UserRole)
        if addr:
            self.direct_addr.setText(addr)
            self._do_connect()

    def _do_connect(self) -> None:
        addr = self.direct_addr.text().strip()
        if not addr:
            self._status(self.direct_status, "请先填写地址", WARN)
            return
        if ":" not in addr:
            addr = f"{addr}:5555"
        self._status(self.direct_status, "连接中…", TEXT2)

        def done(output: str):
            if "connected" in output.lower() and "cannot" not in output.lower() \
                    and "failed" not in output.lower():
                self._status(self.direct_status, output.strip(), OK)
                self.connected.emit(addr)
                self.accept()
            else:
                self._status(self.direct_status, output.strip() or "连接失败", WARN)

        run_async(adb.connect, done, lambda m: self._status(self.direct_status, m, WARN), addr)

    # ---------- 配对 ----------
    def _build_pair(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(9)

        tip = QLabel(
            "手机：设置 → 开发者选项 → 无线调试 → 使用配对码配对设备，"
            "把弹窗里的地址和 6 位码填到这里。配对只需一次。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"font-size:11px; color:{TEXT3};")
        lay.addWidget(tip)

        self.pair_addr = QLineEdit()
        self.pair_addr.setPlaceholderText("配对地址，例如 192.168.1.23:37123")
        lay.addWidget(self.pair_addr)

        self.pair_code = QLineEdit()
        self.pair_code.setPlaceholderText("6 位配对码")
        self.pair_code.setMaxLength(8)
        lay.addWidget(self.pair_code)

        pair_btn = QPushButton("配对")
        pair_btn.setObjectName("Primary")
        pair_btn.clicked.connect(self._do_pair)
        lay.addWidget(pair_btn)

        self.pair_status = QLabel("")
        self.pair_status.setWordWrap(True)
        self.pair_status.setStyleSheet(f"font-size:11px; color:{TEXT2};")
        lay.addWidget(self.pair_status)
        lay.addStretch(1)
        return page

    def _do_pair(self) -> None:
        addr = self.pair_addr.text().strip()
        code = self.pair_code.text().strip()
        if not addr or not code:
            self._status(self.pair_status, "地址和配对码都要填", WARN)
            return
        self._status(self.pair_status, "配对中…", TEXT2)

        def done(output: str):
            if "successfully" in output.lower():
                self._status(
                    self.pair_status,
                    "配对成功。请切到「直连」页填入无线调试页面上的地址完成连接。",
                    OK,
                )
            else:
                self._status(self.pair_status, output.strip() or "配对失败", WARN)

        run_async(adb.pair, done, lambda m: self._status(self.pair_status, m, WARN), addr, code)

    @staticmethod
    def _status(label: QLabel, text: str, color: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"font-size:11px; color:{color};")
