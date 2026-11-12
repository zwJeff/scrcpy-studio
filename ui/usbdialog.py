"""USB 连接向导：授权引导、实时状态诊断、服务重启、一键投屏与 USB→无线切换。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core import adb
from core.tasks import run_async

from .dialogs import DIALOG_QSS
from .style import ACCENT, BORDER, MONO, OK, TEXT2, TEXT3, WARN

STEPS = """<ol style="margin:0; padding-left:18px; line-height:1.7;">
<li>手机 <b>设置 → 关于本机</b>，连点「版本号」7 次开启开发者选项</li>
<li>进入 <b>开发者选项 → USB 调试</b>，打开开关</li>
<li>用<b>支持数据</b>的数据线连接 Mac，手机弹窗勾选「一律允许」并确定</li>
</ol>"""

STATUS_QSS = f"""
QPlainTextEdit {{
    border: 1px solid {BORDER}; border-radius: 8px; background: #FAF9F5;
    font-family: {MONO}; font-size: 11px; color: {TEXT2}; padding: 8px;
}}
"""


class UsbDialog(QDialog):
    mirror_requested = Signal()
    switched = Signal(str)
    prefer_usb_changed = Signal(bool)
    auto_refresh_changed = Signal(bool)

    def __init__(self, parent=None, port: int = 5555, prefer_usb: bool = True):
        super().__init__(parent)
        self.setWindowTitle("USB 连接")
        self.setMinimumWidth(470)
        self.setStyleSheet(DIALOG_QSS + STATUS_QSS)
        self._closed = False
        self._devices: list[adb.Device] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        title = QLabel("通过 USB 数据线连接设备")
        title.setStyleSheet("font-size:15px; font-weight:600;")
        outer.addWidget(title)

        steps = QLabel(STEPS)
        steps.setWordWrap(True)
        steps.setStyleSheet(f"font-size:11px; color:{TEXT2};")
        outer.addWidget(steps)

        head = QHBoxLayout()
        status_title = QLabel("实时连接状态")
        status_title.setStyleSheet("font-size:12px; font-weight:600;")
        head.addWidget(status_title)
        head.addStretch(1)
        detect = QPushButton("重新检测")
        detect.setFixedHeight(25)
        detect.clicked.connect(self.refresh)
        head.addWidget(detect)
        restart = QPushButton("重启 adb 服务")
        restart.setFixedHeight(25)
        restart.setToolTip("设备显示 offline 或授权卡住时点这个")
        restart.clicked.connect(self.restart_server)
        head.addWidget(restart)
        outer.addLayout(head)

        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setFixedHeight(112)
        self.status.setPlainText("检测中…")
        outer.addWidget(self.status)

        self.diagnosis = QLabel("")
        self.diagnosis.setWordWrap(True)
        self.diagnosis.setStyleSheet(f"font-size:11px; color:{TEXT3};")
        outer.addWidget(self.diagnosis)

        options = QHBoxLayout()
        options.setSpacing(14)
        self.prefer_box = QCheckBox("同时有 USB 与无线设备时优先 USB")
        self.prefer_box.setChecked(prefer_usb)
        self.prefer_box.stateChanged.connect(
            lambda s: self.prefer_usb_changed.emit(s != 0)
        )
        options.addWidget(self.prefer_box, 1)
        outer.addLayout(options)

        outer.addWidget(_separator())

        switch_head = QHBoxLayout()
        switch_title = QLabel("USB → 无线（之后可拔掉数据线）")
        switch_title.setStyleSheet("font-size:12px; font-weight:600;")
        switch_head.addWidget(switch_title)
        switch_head.addStretch(1)
        switch_head.addWidget(QLabel("端口"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(port)
        self.port.setFixedWidth(82)
        switch_head.addWidget(self.port)
        outer.addLayout(switch_head)

        note = QLabel(
            "借用当前 USB 连接让设备监听 TCP/IP，再用 Wi-Fi 地址连回去。"
            "需保证手机与 Mac 在同一 Wi-Fi；切换后 USB 连接会短暂中断。"
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:11px; color:{TEXT3};")
        outer.addWidget(note)

        switch_row = QHBoxLayout()
        switch_row.setSpacing(8)
        self.btn_switch = QPushButton("切换为无线连接")
        self.btn_switch.setObjectName("Primary")
        self.btn_switch.clicked.connect(self.switch_to_wireless)
        switch_row.addWidget(self.btn_switch)
        self.btn_back_usb = QPushButton("切回 USB")
        self.btn_back_usb.setToolTip("把当前无线设备恢复成 USB 模式")
        self.btn_back_usb.clicked.connect(self.switch_to_usb)
        switch_row.addWidget(self.btn_back_usb)
        switch_row.addStretch(1)
        outer.addLayout(switch_row)

        outer.addWidget(_separator())

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.btn_mirror = QPushButton("一键 USB 投屏")
        self.btn_mirror.setObjectName("Primary")
        self.btn_mirror.setEnabled(False)
        self.btn_mirror.clicked.connect(self.request_mirror)
        bottom.addWidget(self.btn_mirror)
        bottom.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        outer.addLayout(bottom)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.refresh)

    # ---------- 状态 ----------
    def refresh(self) -> None:
        self.status.setPlainText("检测中…")
        self.diagnosis.setText("")

        def done(devices: list[adb.Device]) -> None:
            if self._closed:
                return
            self._devices = devices
            lines = ["List of devices attached"]
            for dev in devices:
                lines.append(f"{dev.serial:<20} {dev.state:<12} {dev.model}")
            if not devices:
                lines.append("（没有检测到设备）")
            self.status.setPlainText("\n".join(lines))
            usb = [d for d in devices if not d.wireless]
            ready = [d for d in usb if d.online]
            self.btn_mirror.setEnabled(bool(ready))
            self.btn_switch.setEnabled(bool(ready))
            self.btn_back_usb.setEnabled(
                any(d.wireless and d.online for d in devices)
            )
            problems = [d.problem for d in devices if d.problem]
            if ready:
                names = "、".join(d.display_name for d in ready)
                self._set_diagnosis(f"USB 已就绪：{names}。现在可以直接投屏。", OK)
            elif not devices:
                self._set_diagnosis(
                    "未检测到设备。请确认数据线支持数据传输，并已开启 USB 调试。", TEXT3
                )
            elif problems:
                self._set_diagnosis(problems[0], WARN)
            else:
                self._set_diagnosis("设备已插入但尚未就绪，请点「重新检测」。", WARN)

            for dev in ready:
                extra = adb.usb_status(dev.serial)
                if extra:
                    bits = []
                    if dev.usb:
                        bits.append(f"USB 总线 {dev.usb}")
                    if extra.get("usb_state"):
                        bits.append(f"USB 状态 {extra['usb_state']}")
                    if extra.get("usb_powered") == "true":
                        bits.append("正在通过 USB 供电")
                    if extra.get("level"):
                        bits.append(f"电量 {extra['level']}%")
                    if bits:
                        self.status.appendPlainText("# " + " · ".join(bits))
                break  # 只展示第一台，避免一次发多条 shell

        def fail(message: str) -> None:
            if not self._closed:
                self.status.setPlainText(f"检测失败：{message}")
                self._set_diagnosis("adb 无法执行，请确认已安装 platform-tools。", WARN)

        run_async(adb.list_devices, done, fail)

    def _set_diagnosis(self, text: str, color: str) -> None:
        self.diagnosis.setText(text)
        self.diagnosis.setStyleSheet(f"font-size:11px; color:{color};")

    def restart_server(self) -> None:
        self._set_diagnosis("正在重启 adb 服务，请稍候…", TEXT2)
        self.btn_switch.setEnabled(False)

        def done(_devices) -> None:
            if not self._closed:
                self.refresh()

        def fail(message: str) -> None:
            if not self._closed:
                self._set_diagnosis(f"重启失败：{message}", WARN)

        run_async(adb.restart_server, done, fail)

    # ---------- 操作 ----------
    def request_mirror(self) -> None:
        if self._closed:
            return
        self.mirror_requested.emit()
        self.accept()

    def switch_to_wireless(self) -> None:
        usb = next((d for d in self._devices if not d.wireless and d.online), None)
        if usb is None:
            QMessageBox.information(self, "没有可用的 USB 设备", "请先用数据线连好手机并完成授权。")
            return
        port = self.port.value()
        answer = QMessageBox.question(
            self, "切换为无线连接",
            f"将把 {usb.display_name} 切换到 TCP/IP 端口 {port}，之后可以拔掉数据线。\n\n"
            "需要手机与 Mac 处于同一 Wi-Fi。是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.btn_switch.setEnabled(False)
        self._set_diagnosis("正在切换，USB 连接会短暂断开…", TEXT2)

        def done(addr: str) -> None:
            if self._closed:
                return
            self.switched.emit(addr)
            self._set_diagnosis(f"已切换到无线：{addr}。现在可以拔掉数据线。", OK)
            self.refresh()

        def fail(message: str) -> None:
            if self._closed:
                return
            self.btn_switch.setEnabled(True)
            self._set_diagnosis(f"切换失败：{message}", WARN)
            self.console_note(message)

        run_async(adb.switch_to_wireless, done, fail, usb.serial, port)

    def switch_to_usb(self) -> None:
        wireless = next((d for d in self._devices if d.wireless and d.online), None)
        if wireless is None:
            QMessageBox.information(self, "没有无线设备", "当前没有可切回 USB 的无线连接。")
            return
        self._set_diagnosis("正在把设备切回 USB 模式…", TEXT2)

        def done(_out: str) -> None:
            if not self._closed:
                self._set_diagnosis("已切回 USB 模式，请重新插上数据线。", OK)
                self.refresh()

        def fail(message: str) -> None:
            if not self._closed:
                self._set_diagnosis(f"切回失败：{message}", WARN)

        run_async(adb.usb_mode, done, fail, wireless.serial)

    def console_note(self, message: str) -> None:
        self.status.appendPlainText("# " + message.splitlines()[0])

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closed = True
        super().closeEvent(event)


def _separator() -> QWidget:
    from PySide6.QtWidgets import QFrame

    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color:{BORDER};")
    return line
