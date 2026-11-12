"""主窗口：设备、手机桌面应用、投屏参数、设备输入与 scrcpy 进程。"""
from __future__ import annotations

import shlex
import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from core import adb, apkinfo, textinput
from core.aliases import display_name
from core.config import build_args, load_state, save_state
from core.paths import ADB, SCRCPY
from core.tasks import run_async
from core.usbwatch import DeviceWatcher

from .dialogs import WirelessDialog
from .inputpanel import InputPanel
from .panels import AppPanel, ConsolePanel, DevicePanel, SettingsPanel
from .style import ACCENT, ACCENT_SOFT, BORDER, OK, TEXT, TEXT2, TEXT3, WARN
from .usbdialog import UsbDialog


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
    # 后台 APK 解析线程通过信号把结果送回主线程
    info_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scrcpy Studio")
        self.setWindowIcon(_app_icon())
        self.resize(1320, 980)
        self.setMinimumSize(1140, 840)

        self.state = load_state()
        self.devices: list[adb.Device] = []
        self.app_cache: dict[str, list[tuple[str, str]]] = {}
        self.system_cache: dict[str, set[str]] = {}
        self.current_serial: str = ""
        self.proc: QProcess | None = None

        # USB 热插拔：track-devices 事件流 + 新设备自动投屏
        self._prev_usb: set[str] = set()
        self._watcher_seeded = False
        self._pending_auto_mirror = ""
        self.watcher = DeviceWatcher(self)
        self.watcher.devices_changed.connect(self.on_device_event)
        self.watcher.watcher_error.connect(
            lambda m: self.console.log(f"[设备监视] {m}")
        )

        # 应用信息提取（线程池 + 主线程批量刷新，避免每拉一个 APK 就重绘桌面）
        self._info_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="appinfo")
        self._info_lock = threading.Lock()
        self._info_pending: dict[str, apkinfo.AppInfo] = {}
        self._info_token = 0
        self._info_done = 0
        self._info_total = 0
        self.info_ready.connect(self._collect_info)
        self._info_timer = QTimer(self)
        self._info_timer.setInterval(900)
        self._info_timer.timeout.connect(self._flush_info)
        self._info_timer.start()

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
        self.input_panel = InputPanel()
        self.input_panel.setFixedHeight(166)

        middle = QVBoxLayout()
        middle.setSpacing(10)
        middle.addWidget(self.app_panel, 1)
        middle.addWidget(self.input_panel)
        body.addWidget(self.device_panel)
        body.addLayout(middle, 1)
        body.addWidget(self.settings_panel)
        outer.addLayout(body, 1)

        self.console = ConsolePanel()
        outer.addWidget(self.console)

        self.settings_panel.set_config(self.state.mirror)
        self._wire()
        self._init_from_state()
        self._install_shortcuts()

        self.timer = QTimer(self)
        self.timer.setInterval(15000)   # 轮询仅作兜底，实时性由 track-devices 提供
        self.timer.timeout.connect(lambda: self.refresh_devices(silent=True))
        self.timer.start()

        self.watcher.start()
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
        self.device_panel.usb_mirror_clicked.connect(lambda: self.usb_mirror())
        self.device_panel.usb_setup_clicked.connect(self.open_usb_dialog)
        self.device_panel.restart_adb_clicked.connect(self.restart_adb)
        self.device_panel.to_wireless_clicked.connect(self.to_wireless)
        self.device_panel.auto_mirror_changed.connect(
            lambda v: self._set_state(auto_mirror_usb=v)
        )

        self.app_panel.reload_clicked.connect(lambda: self.load_apps(force=True))
        self.app_panel.info_refresh_clicked.connect(lambda: self.load_appinfo(force=True))
        self.app_panel.launch_requested.connect(self.launch_app)
        self.app_panel.alias_requested.connect(self.edit_alias)
        self.app_panel.dock_toggled.connect(self.toggle_dock)
        self.app_panel.recategory_requested.connect(self.recategorize)
        self.app_panel.category_changed.connect(lambda k: self._set_state(category=k))
        self.app_panel.view_changed.connect(lambda v: self._set_state(view_mode=v))
        self.app_panel.group_changed.connect(lambda g: self._set_state(group_by=g))

        self.settings_panel.start_clicked.connect(lambda: self.start_mirror())
        self.settings_panel.stop_clicked.connect(self.stop_mirror)
        self.settings_panel.changed.connect(self.persist)

        self.input_panel.send_requested.connect(self.send_text)
        self.input_panel.copy_requested.connect(self.copy_text)
        self.input_panel.key_requested.connect(self.send_key)
        self.input_panel.mode_changed.connect(lambda m: self._set_state(input_mode=m))
        self.input_panel.enter_changed.connect(lambda e: self._set_state(input_enter=e))

    def _init_from_state(self) -> None:
        self.device_panel.set_auto_mirror(self.state.auto_mirror_usb)
        self.app_panel.set_dock(self.state.dock_packages)
        self.app_panel.set_overrides(self.state.category_overrides)
        self.app_panel.set_appinfo(apkinfo.all_cached())
        self.app_panel.set_group_by(self.state.group_by)
        self.app_panel.set_category(self.state.category)
        self.app_panel.set_view(self.state.view_mode)
        self.input_panel.set_mode(self.state.input_mode)
        self.input_panel.set_enter(self.state.input_enter)
        self.input_panel.set_history(self.state.input_history)
        self.input_panel.set_serial("")

    def _install_shortcuts(self) -> None:
        for seq in ("Ctrl+Return", "Meta+Return"):
            QShortcut(QKeySequence(seq), self).activated.connect(self.input_panel.send)
        for seq in ("Ctrl+U", "Meta+U"):
            QShortcut(QKeySequence(seq), self).activated.connect(
                lambda: self.usb_mirror()
            )
        for seq in ("Ctrl+K", "Meta+K"):
            QShortcut(QKeySequence(seq), self).activated.connect(
                self.input_panel.focus_input
            )
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self.input_panel.edit.clear()
            if self.input_panel.edit.hasFocus() else None
        )

    def _set_state(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self.state, key, value)
        self.persist()

    # ---------- 设备 ----------
    def refresh_devices(self, silent: bool = False) -> None:
        def done(devices: list[adb.Device]) -> None:
            self.devices = devices
            online = [d for d in devices if d.online]
            serials = {d.serial for d in online}
            target = self.current_serial or self.state.last_serial
            if self._pending_auto_mirror in serials:
                target = self._pending_auto_mirror
            elif target not in serials and online:
                target = self._pick_preferred(online)
            self.device_panel.set_devices(devices, target)
            self.input_panel.set_serial(target if target in serials else "")
            self._update_status()
            if not silent:
                self.console.log(f"发现 {len(devices)} 台设备")

            pending, self._pending_auto_mirror = self._pending_auto_mirror, ""
            if pending and pending in serials and self.proc is None \
                    and self.state.auto_mirror_usb:
                QTimer.singleShot(500, lambda: self.usb_mirror(pending))

        def fail(message: str) -> None:
            self.console.log(f"[错误] {message}")
            self._update_status()

        run_async(adb.list_devices, done, fail)

    def _pick_preferred(self, online: list[adb.Device]) -> str:
        """USB 与无线同时在线时，可配置优先走 USB（延迟更低、更稳定）。"""
        if self.state.prefer_usb:
            usb = [d for d in online if not d.wireless]
            if usb:
                return usb[0].serial
        return online[0].serial

    def on_device_event(self, snapshot) -> None:
        """track-devices 推送的状态快照：秒级感知 USB 插拔。"""
        usb_now = {
            serial for serial, state in snapshot
            if state == "device" and ":" not in serial
        }
        first_frame = not self._watcher_seeded
        self._watcher_seeded = True
        added = usb_now - self._prev_usb
        self._prev_usb = usb_now
        if added and not first_frame:
            self.console.log(f"[USB] 检测到设备插入：{'、'.join(sorted(added))}")
            if self.state.auto_mirror_usb and self.proc is None:
                self._pending_auto_mirror = sorted(added)[0]
        self.refresh_devices(silent=True)

    def _update_status(self) -> None:
        online = [d for d in self.devices if d.online]
        dev = next((d for d in online if d.serial == self.current_serial), None)
        if dev is None and online:
            dev = online[0]
        if online:
            suffix = f" · 共 {len(online)} 台" if len(online) > 1 else ""
            label = f"{dev.display_name} · {dev.label}{suffix}" if dev else f"{len(online)} 台设备在线"
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
        self.input_panel.set_serial(serial)
        self.app_panel.set_device_label(serial.split(":")[0])
        self.load_apps()
        self.load_device_info(serial)

    def load_device_info(self, serial: str) -> None:
        def done(info: adb.DeviceInfo) -> None:
            if serial != self.current_serial:
                return
            parts = []
            if info.model:
                parts.append(f"<b>{info.model}</b>")
                self.app_panel.set_device_label(info.model)
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
        dev = self.device_panel.current_device()
        if dev is None:
            return
        if not dev.wireless:
            QMessageBox.information(
                self, "USB 设备无法远程断开",
                "USB 连接直接拔下数据线即可。\n\n"
                "如果想拔线后继续投屏，点「USB → 无线」先切换到 Wi-Fi 连接。",
            )
            return
        run_async(adb.disconnect, lambda out: self.console.log(out.strip()),
                  lambda m: self.console.log(f"[错误] {m}"), dev.serial)
        self.current_serial = ""
        self.input_panel.set_serial("")
        QTimer.singleShot(800, lambda: self.refresh_devices())

    # ---------- USB 连接 ----------
    def usb_mirror(self, serial: str | None = None) -> None:
        """一键：选中 USB 设备并以整屏模式启动 scrcpy。"""
        if self.proc is not None:
            self.console.log("已有投屏进程在运行，请先停止")
            return
        usb = [d for d in self.devices if not d.wireless]
        ready = [d for d in usb if d.online]
        if not ready:
            problem = next((d.problem for d in usb if d.problem), "")
            QMessageBox.information(
                self, "没有可用的 USB 设备",
                problem or "请用数据线连接手机，开启开发者选项里的「USB 调试」并授权。\n"
                           "详细步骤见「USB 连接…」。",
            )
            return
        target = serial if serial in {d.serial for d in ready} else ready[0].serial
        self.device_panel.select_serial(target)
        self.settings_panel.mode.setCurrentIndex(0)   # 整屏模式
        self.console.log(f"[USB] 启动投屏：{target}")
        self.start_mirror(serial=target)

    def open_usb_dialog(self) -> None:
        dialog = UsbDialog(
            self, port=self.state.usb_port, prefer_usb=self.state.prefer_usb
        )
        dialog.mirror_requested.connect(lambda: QTimer.singleShot(120, self.usb_mirror))
        dialog.switched.connect(self.on_switched)
        dialog.prefer_usb_changed.connect(lambda v: self._set_state(prefer_usb=v))
        dialog.exec()
        self.state.usb_port = dialog.port.value()
        self.persist()

    def restart_adb(self) -> None:
        self.console.log("正在重启 adb 服务…")

        def done(devices: list[adb.Device]) -> None:
            self.console.log(f"adb 服务已重启，检测到 {len(devices)} 台设备")
            self.refresh_devices()

        def fail(message: str) -> None:
            self.console.log(f"[错误] 重启 adb 失败：{message}")

        run_async(adb.restart_server, done, fail)

    def to_wireless(self) -> None:
        """借当前 USB 连接把设备切到 TCP/IP，之后可拔线继续投屏。"""
        dev = self.device_panel.current_device()
        if dev is None or dev.wireless or not dev.online:
            QMessageBox.information(
                self, "需要 USB 设备", "请先选中一台已通过 USB 连接并授权的设备。"
            )
            return
        port = self.state.usb_port
        answer = QMessageBox.question(
            self, "切换为无线连接",
            f"把 {dev.display_name} 切换到 TCP/IP 端口 {port}，之后可以拔掉数据线。\n\n"
            "需要手机与 Mac 处于同一 Wi-Fi，切换时 USB 连接会短暂中断。是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.console.log(f"[USB → 无线] 正在切换 {dev.serial} → 端口 {port}…")
        run_async(
            adb.switch_to_wireless,
            self.on_switched,
            lambda m: self.console.log(f"[错误] 切换失败：{m}"),
            dev.serial, port,
        )

    def on_switched(self, addr: str) -> None:
        self.console.log(f"[USB → 无线] 已连接 {addr}，现在可以拔掉数据线")
        self.device_panel.set_hint(f"已切换到无线 {addr}，可以拔掉数据线了。", "ok")
        self.state.last_serial = addr
        self.current_serial = addr
        self.persist()
        QTimer.singleShot(1200, lambda: self.refresh_devices())

    def open_wireless_dialog(self) -> None:
        dialog = WirelessDialog(self)
        dialog.connected.connect(lambda _addr: QTimer.singleShot(600, self.refresh_devices))
        dialog.exec()

    def open_pair_dialog(self) -> None:
        dialog = WirelessDialog(self, start_tab=1)
        dialog.connected.connect(lambda _addr: QTimer.singleShot(600, self.refresh_devices))
        dialog.exec()

    # ---------- 应用列表 ----------
    def load_apps(self, force: bool = False) -> None:
        serial = self.current_serial
        if not serial:
            self.app_panel.set_data([], set(), self.state.aliases)
            return
        if not force and serial in self.app_cache:
            self.app_panel.set_data(self.app_cache[serial], self.system_cache.get(serial, set()),
                                    self.state.aliases)
            self._info_timer.start()
            return

        self.app_panel.count.setText("读取中…")

        def done(packages: list[tuple[str, str]]) -> None:
            if serial != self.current_serial:
                return
            self.app_cache[serial] = packages
            self.app_panel.set_data(packages, self.system_cache.get(serial, set()),
                                    self.state.aliases)
            self.console.log(f"读取到 {len(packages)} 个可投屏应用")
            self.load_appinfo(force=force)

        def fail(message: str) -> None:
            self.app_panel.count.setText("读取失败")
            self.console.log(f"[错误] 读取应用列表：{message}")

        run_async(adb.list_apps, done, fail, serial)

        def system_done(pkgs: set[str]) -> None:
            self.system_cache[serial] = pkgs
            if serial == self.current_serial and serial in self.app_cache:
                self.app_panel.set_data(self.app_cache[serial], pkgs, self.state.aliases)

        run_async(adb.system_packages, system_done, lambda _m: None, serial)

    # ---------- 应用名称 / 图标提取 ----------
    def load_appinfo(self, force: bool = False) -> None:
        serial = self.current_serial
        packages = self.app_cache.get(serial) or []
        self._info_token += 1
        token = self._info_token
        with self._info_lock:
            self._info_pending.clear()
        self._info_done = 0
        self._info_total = len(packages)
        if not serial or not packages:
            self.app_panel.set_progress("")
            return

        if force:
            apkinfo.invalidate()
            self.app_panel.set_appinfo({})
            self.console.log("正在重新提取应用名称与图标…")
        else:
            self.app_panel.set_appinfo(apkinfo.all_cached())
        self.app_panel.set_progress(f"提取 0/{self._info_total}")

        def worker(package: str):
            if token != self._info_token:
                return package, None
            try:
                return package, apkinfo.fetch(serial, package, force=force)
            except Exception:  # noqa: BLE001 - 单个应用失败不影响其余
                return package, None

        def submitted(future) -> None:
            try:
                package, info = future.result()
            except Exception:  # noqa: BLE001
                package, info = "", None
            self.info_ready.emit((token, package, info))

        for package, _activity in packages:
            self._info_pool.submit(worker, package).add_done_callback(submitted)

    def _collect_info(self, payload) -> None:
        token, package, info = payload
        if token != self._info_token:
            return
        self._info_done += 1
        if info is not None and package and info.usable:
            with self._info_lock:
                self._info_pending[package] = info
        if self._info_done < self._info_total:
            self.app_panel.set_progress(f"提取 {self._info_done}/{self._info_total}")
        else:
            self._flush_info()

    def _flush_info(self) -> None:
        with self._info_lock:
            batch = dict(self._info_pending)
            self._info_pending.clear()
        if batch:
            self.app_panel.merge_appinfo(batch)
        if self._info_total and self._info_done >= self._info_total:
            self.app_panel.set_progress(f"已提取 {self._info_total} 个应用")

    def toggle_dock(self, package: str) -> None:
        dock = [p for p in self.state.dock_packages if p != package]
        if package in self.state.dock_packages:
            self.state.dock_packages = dock
        else:
            self.state.dock_packages = (dock + [package])[-4:]
        self.app_panel.set_dock(self.state.dock_packages)
        self.app_panel.refresh()
        self.persist()

    def recategorize(self, package: str, key: str) -> None:
        overrides = dict(self.state.category_overrides)
        if key:
            overrides[package] = key
        else:
            overrides.pop(package, None)
        self.state.category_overrides = overrides
        self.app_panel.set_overrides(overrides)
        self.app_panel.refresh()
        self.persist()

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

    # ---------- 设备输入 ----------
    def send_text(self, text: str, enter: bool) -> None:
        serial = self.current_serial or self.device_panel.current_serial()
        if not serial:
            self.input_panel.set_status("没有可用设备", ok=False)
            return
        mode = self.state.input_mode
        self.input_panel.set_status("发送中…")

        def done(result: textinput.SendResult) -> None:
            channel = "ADBKeyBoard" if result.channel == "adbkeyboard" else "input text"
            self.input_panel.set_status(f"已发送 · {channel}")
            self.console.log("$ " + result.detail +
                             (" + keyevent 66" if result.enter_sent else ""))
            history = [text] + [item for item in self.state.input_history if item != text]
            self.state.input_history = history[:20]
            self.input_panel.set_history(self.state.input_history)
            self.persist()

        def fail(message: str) -> None:
            self.input_panel.set_status(message.splitlines()[0], ok=False)
            self.console.log(f"[输入失败] {message}")

        run_async(lambda: textinput.send(serial, text, mode, enter), done, fail)

    def copy_text(self, text: str) -> None:
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.input_panel.set_status("已复制 · 到 scrcpy 窗口按 ⌘V")
        self.console.log(f"已复制 {len(text)} 个字符到剪贴板")

    def send_key(self, name: str) -> None:
        serial = self.current_serial or self.device_panel.current_serial()
        if not serial:
            self.input_panel.set_status("没有可用设备", ok=False)
            return
        run_async(textinput.send_keyevent,
                  lambda out: self.console.log(f"keyevent {name} → {out.strip()}"),
                  lambda m: self.input_panel.set_status(m, ok=False),
                  serial, name)

    # ---------- 投屏 ----------
    def launch_app(self, package: str) -> None:
        self.settings_panel.mode.setCurrentIndex(1)
        self.state.last_package = package
        self.start_mirror(package=package)

    def start_mirror(self, package: str | None = None,
                     serial: str | None = None) -> None:
        if self.proc is not None:
            self.console.log("已有投屏进程在运行，请先停止")
            return
        serial = serial or self.device_panel.current_serial()
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
        self._info_token += 1
        self._info_timer.stop()
        self.timer.stop()
        self.watcher.stop()
        self.persist()
        if self.proc is not None:
            self.proc.terminate()
        self._info_pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
