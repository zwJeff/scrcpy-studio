"""主窗口：把设备、应用、参数三栏和 scrcpy 进程串起来。"""
from __future__ import annotations

import shlex

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from core import adb
from core.aliases import display_name
from core.config import build_args, load_state, save_state
from core.paths import ADB, SCRCPY
from core.tasks import run_async

from .dialogs import WirelessDialog
from .panels import AppPanel, ConsolePanel, DevicePanel, SettingsPanel
from .style import ACCENT, ACCENT_SOFT, BORDER, OK, TEXT, TEXT2, TEXT3, WARN


def _app_icon() -> QIcon:
    pix = QPixmap(128, 128)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(ACCENT))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(8, 8, 112, 112, 26, 26)
    font = QFont("Helvetica Neue")
    font.setPixelSize(64)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(pix.rect(), Qt.AlignCenter, "S")
    painter.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scrcpy Studio")
        self.setWindowIcon(_app_icon())
        self.resize(1180, 780)
        self.setMinimumSize(1040, 700)

        self.state = load_state()
        self.devices: list[adb.Device] = []
        self.app_cache: dict[str, list[tuple[str, str]]] = {}
        self.system_cache: dict[str, set[str]] = {}
        self.current_serial: str = ""
        self.proc: QProcess | None = None

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        self.device_panel = DevicePanel()
        self.device_panel.setFixedWidth(262)
        self.app_panel = AppPanel()
        self.settings_panel = SettingsPanel()
        self.settings_panel.setFixedWidth(340)
        body.addWidget(self.device_panel)
        body.addWidget(self.app_panel, 1)
        body.addWidget(self.settings_panel)
        outer.addLayout(body, 1)

        self.console = ConsolePanel()
        outer.addWidget(self.console)

        self.settings_panel.set_config(self.state.mirror)
        self._wire()

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(lambda: self.refresh_devices(silent=True))
        self.timer.start()

        self.refresh_devices()
        self.console.log(f"adb     → {ADB}")
        self.console.log(f"scrcpy  → {SCRCPY}")

    # ---------- 顶部 ----------
    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(_app_icon().pixmap(34, 34))
        row.addWidget(mark)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Scrcpy Studio")
        title.setObjectName("HeaderTitle")
        sub = QLabel("Android 投屏与设备管理")
        sub.setObjectName("HeaderSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        row.addLayout(titles)
        row.addStretch(1)

        self.status_pill = QLabel("未连接")
        self.status_pill.setStyleSheet(
            f"font-size:11px; color:{TEXT2}; background:#EFEDE6;"
            "border-radius:9px; padding:3px 10px;"
        )
        row.addWidget(self.status_pill)

        refresh = QPushButton("刷新设备")
        refresh.clicked.connect(lambda: self.refresh_devices())
        row.addWidget(refresh)
        return row

    # ---------- 信号 ----------
    def _wire(self) -> None:
        self.device_panel.refresh_clicked.connect(lambda: self.refresh_devices())
        self.device_panel.device_selected.connect(self.on_device_selected)
        self.device_panel.wireless_clicked.connect(self.open_wireless_dialog)
        self.device_panel.pair_clicked.connect(self.open_pair_dialog)
        self.device_panel.disconnect_clicked.connect(self.disconnect_device)

        self.app_panel.reload_clicked.connect(lambda: self.load_apps(force=True))
        self.app_panel.launch_requested.connect(self.launch_app)
        self.app_panel.alias_requested.connect(self.edit_alias)

        self.settings_panel.start_clicked.connect(lambda: self.start_mirror())
        self.settings_panel.stop_clicked.connect(self.stop_mirror)
        self.settings_panel.changed.connect(self.persist)

    # ---------- 设备 ----------
    def refresh_devices(self, silent: bool = False) -> None:
        def done(devices: list[adb.Device]) -> None:
            self.devices = devices
            online = [d for d in devices if d.online]
            target = self.current_serial or self.state.last_serial
            serials = {d.serial for d in online}
            if target not in serials and online:
                target = online[0].serial
            self.device_panel.set_devices(devices, target)
            self._update_status()
            if not silent:
                self.console.log(f"发现 {len(devices)} 台设备")

        def fail(message: str) -> None:
            self.console.log(f"[错误] {message}")
            self._update_status()

        run_async(adb.list_devices, done, fail)

    def _update_status(self) -> None:
        online = [d for d in self.devices if d.online]
        if online:
            label = online[0].display_name if len(online) == 1 else f"{len(online)} 台设备在线"
            self.status_pill.setText(f"● {label}")
            self.status_pill.setStyleSheet(
                f"font-size:11px; color:{OK}; background:#E1F5EE;"
                "border-radius:9px; padding:3px 10px;"
            )
        else:
            self.status_pill.setText("未连接设备")
            self.status_pill.setStyleSheet(
                f"font-size:11px; color:{TEXT2}; background:#EFEDE6;"
                "border-radius:9px; padding:3px 10px;"
            )

    def on_device_selected(self, serial: str) -> None:
        if not serial or serial == self.current_serial:
            return
        self.current_serial = serial
        self.state.last_serial = serial
        self.persist()
        self.load_apps()
        self.load_device_info(serial)

    def load_device_info(self, serial: str) -> None:
        def done(info: adb.DeviceInfo) -> None:
            if serial != self.current_serial:
                return
            parts = []
            if info.model:
                parts.append(f"<b>{info.model}</b>")
            meta = []
            if info.android:
                meta.append(f"Android {info.android}")
            if info.resolution:
                meta.append(info.resolution)
            if meta:
                parts.append(" · ".join(meta))
            if info.ip:
                parts.append(info.ip)
            self.device_panel.set_info("<br>".join(parts) if parts else serial)

        run_async(adb.device_info, done, lambda _m: None, serial)

    def disconnect_device(self) -> None:
        serial = self.device_panel.current_serial()
        if not serial:
            return
        run_async(adb.disconnect, lambda out: self.console.log(out.strip()),
                  lambda m: self.console.log(f"[错误] {m}"), serial)
        self.current_serial = ""
        QTimer.singleShot(800, lambda: self.refresh_devices())

    def open_wireless_dialog(self) -> None:
        dialog = WirelessDialog(self)
        dialog.connected.connect(lambda _addr: QTimer.singleShot(600, self.refresh_devices))
        dialog.exec()

    def open_pair_dialog(self) -> None:
        dialog = WirelessDialog(self, start_tab=1)
        dialog.connected.connect(lambda _addr: QTimer.singleShot(600, self.refresh_devices))
        dialog.exec()

    # ---------- 应用 ----------
    def load_apps(self, force: bool = False) -> None:
        serial = self.current_serial
        if not serial:
            self.app_panel.set_data([], set(), self.state.aliases)
            return
        if not force and serial in self.app_cache:
            self.app_panel.set_data(self.app_cache[serial], self.system_cache.get(serial, set()),
                                    self.state.aliases)
            return

        self.app_panel.count.setText("读取中…")

        def done(packages: list[tuple[str, str]]) -> None:
            if serial != self.current_serial:
                return
            self.app_cache[serial] = packages
            self.app_panel.set_data(packages, self.system_cache.get(serial, set()),
                                    self.state.aliases)
            self.console.log(f"读取到 {len(packages)} 个可投屏应用")

        def fail(message: str) -> None:
            self.app_panel.count.setText("读取失败")
            self.console.log(f"[错误] 读取应用列表：{message}")

        run_async(adb.list_apps, done, fail, serial)

        def system_done(pkgs: set[str]) -> None:
            self.system_cache[serial] = pkgs
            if serial == self.current_serial and serial in self.app_cache:
                self.app_panel.set_data(self.app_cache[serial], pkgs, self.state.aliases)

        run_async(adb.system_packages, system_done, lambda _m: None, serial)

    def edit_alias(self, package: str) -> None:
        current = self.state.aliases.get(package, "")
        text, ok = QInputDialog.getText(
            self, "设置显示名称", f"{package}\n给它起个短名字：", text=current,
        )
        if not ok:
            return
        text = text.strip()
        if text:
            self.state.aliases[package] = text
        else:
            self.state.aliases.pop(package, None)
        self.persist()
        if self.current_serial in self.app_cache:
            self.app_panel.set_data(self.app_cache[self.current_serial],
                                    self.system_cache.get(self.current_serial, set()),
                                    self.state.aliases)

    # ---------- 投屏 ----------
    def launch_app(self, package: str) -> None:
        self.settings_panel.mode.setCurrentIndex(1)
        self.state.last_package = package
        self.start_mirror(package=package)

    def start_mirror(self, package: str | None = None) -> None:
        if self.proc is not None:
            self.console.log("已有投屏进程在运行，请先停止")
            return
        serial = self.device_panel.current_serial()
        if not serial:
            QMessageBox.information(self, "没有可用设备", "请先用 USB 连接或在「无线连接」里连上手机。")
            return

        cfg = self.settings_panel.config()
        if cfg.mode == "app":
            cfg.package = package or self.state.last_package
            if not cfg.package:
                QMessageBox.information(self, "未选择应用", "单应用模式需要先在应用列表里双击一个应用。")
                return
            self.console.log(f"单应用投屏：{display_name(cfg.package, self.state.aliases)}")
        else:
            cfg.package = ""

        self.state.mirror = cfg
        self.persist()

        args = build_args(cfg, serial)
        self.console.log("$ " + shlex.join(args))

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._drain(proc))
        proc.finished.connect(lambda *_: self._on_proc_finished())
        proc.errorOccurred.connect(
            lambda err: self.console.log(f"[scrcpy 启动失败] {err}")
        )
        proc.start(args[0], args[1:])
        self.proc = proc
        self.settings_panel.set_running(True)

    def _drain(self, proc: QProcess) -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.console.log(data.rstrip())

    def stop_mirror(self) -> None:
        if self.proc is None:
            return
        self.console.log("正在停止投屏…")
        self.proc.terminate()
        QTimer.singleShot(2500, self._force_kill)

    def _force_kill(self) -> None:
        if self.proc is not None and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()

    def _on_proc_finished(self) -> None:
        self.console.log("投屏进程已退出")
        self.proc = None
        self.settings_panel.set_running(False)

    # ---------- 其他 ----------
    def persist(self) -> None:
        self.state.mirror = self.settings_panel.config()
        save_state(self.state)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.persist()
        if self.proc is not None:
            self.proc.terminate()
        super().closeEvent(event)
