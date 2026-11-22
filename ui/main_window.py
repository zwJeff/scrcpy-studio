"""主窗口：玻璃工具栏 + Launchpad 舞台 + 多窗口 scrcpy 进程管理。"""
from __future__ import annotations

import os
import shlex
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QProcess, QProcessEnvironment, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QIcon, QKeySequence, QPainter,
    QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from core import adb, apkinfo, paths, textinput
from core.aliases import display_name
from core.config import build_args, load_state, save_state
from core.tasks import run_async
from core.usbwatch import DeviceWatcher

from . import nativewindow, style
from .dialogs import WirelessDialog
from .floatball import FloatController
from .inputpanel import InputPanel
from .mirrorbar import MirrorBar
from .mirrorcontrol import MirrorControl
from .panels import AppPanel, ConsolePanel, DevicePanel
from .settings_dialog import SettingsDialog
from .usbdialog import UsbDialog


@dataclass
class MirrorWindow:
    id: str
    label: str
    package: str
    serial: str
    proc: QProcess
    key: str = ""                       # 配置键：包名，整屏用 "__screen__"
    last_geometry: dict | None = None  # 最近一次采样到的窗口位置尺寸
    ever_visible: bool = False          # 窗口是否曾经在屏幕上出现过
    missing_frames: int = 0             # 连续读不到窗口的次数（用于最小化判定）
    minimized_hidden: bool = False      # 控制条是否因窗口最小化被隐藏


def _app_icon() -> QIcon:
    if paths.ICON_PNG.exists():
        return QIcon(str(paths.ICON_PNG))
    # 资源缺失时的兜底
    pix = QPixmap(128, 128)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(style.P().accent))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(8, 8, 112, 112, 28, 28)
    font = QFont("Helvetica Neue")
    font.setPixelSize(64)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(pix.rect(), Qt.AlignCenter, "S")
    painter.end()
    return QIcon(pix)


class GlassRoot(QWidget):
    """绘制柔和光斑壁纸，子面板用半透明材质叠加形成毛玻璃。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        style.paint_wallpaper(painter, self.rect())
        painter.end()


class MainWindow(QMainWindow):
    info_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scrcpy Studio")
        self.setWindowIcon(_app_icon())
        self.resize(1400, 940)
        self.setMinimumSize(1080, 720)

        self.state = load_state()
        paths.set_overrides(self.state.adb_path, self.state.scrcpy_path)
        self.devices: list[adb.Device] = []
        self.app_cache: dict[str, list[tuple[str, str]]] = {}
        self.system_cache: dict[str, set[str]] = {}
        self.current_serial: str = ""
        self.processes: dict[str, MirrorWindow] = {}
        self.controls: dict[str, MirrorControl] = {}
        self._controls_visible = self.state.show_control_bar
        self._follow_diagnosed = False
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setInterval(120)   # 控制条跟随需要足够短的采样间隔
        self._geometry_timer.timeout.connect(self._sample_geometry)
        self._float_mode = False
        self._had_online = False

        # USB 热插拔
        self._prev_usb: set[str] = set()
        self._watcher_seeded = False
        self._pending_auto_mirror = ""
        self._apps_loading: set[str] = set()      # 防止并行重复提交读取任务
        self._apps_retry: dict[str, int] = {}      # 设备刚上线时的空结果重试计数
        self.watcher = DeviceWatcher(self)
        self.watcher.devices_changed.connect(self.on_device_event)
        self.watcher.watcher_error.connect(lambda m: self.console.log(f"[设备监视] {m}"))

        # APK 名称 / 图标提取
        self._info_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="appinfo")
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

        root = GlassRoot()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        outer.addWidget(self._build_toolbar())

        self.mirror_bar = MirrorBar()
        self.mirror_bar.setVisible(False)
        self.mirror_bar.close_requested.connect(self.stop_mirror)
        self.mirror_bar.close_all_requested.connect(lambda: self.stop_mirror())
        outer.addWidget(self.mirror_bar)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.device_panel = DevicePanel()
        self.device_panel.setFixedWidth(238)
        self.app_panel = AppPanel()
        self.input_panel = InputPanel()
        self.input_panel.setFixedHeight(158)
        self.console = ConsolePanel()

        middle = QVBoxLayout()
        middle.setSpacing(10)
        middle.addWidget(self.app_panel, 1)
        middle.addWidget(self.input_panel)
        middle.addWidget(self.console)
        body.addWidget(self.device_panel)
        body.addLayout(middle, 1)
        outer.addLayout(body, 1)

        self.float_controller = FloatController(self)
        self._wire()
        self._init_from_state()
        self._install_shortcuts()

        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(lambda: self.refresh_devices(silent=True))
        self.timer.start()

        # 跟随 macOS 深浅色切换
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(
                self._on_system_theme
            )
        except (AttributeError, TypeError):
            pass

        self.watcher.start()
        self.refresh_devices()
        self.console.log(f"adb     → {paths.ADB}")
        version = paths.scrcpy_version(self.state.scrcpy_path)
        self.console.log(
            f"scrcpy  → {paths.SCRCPY}  ({paths.version_text(self.state.scrcpy_path)})"
        )
        if version and version[0] < 5:
            self.console.log(
                "[兼容提示] 当前 scrcpy < 5.0：单应用投屏会降级为「整屏 + 在手机上启动应用」，"
                "升级到 5.x 可恢复独立窗口与多窗口投屏"
            )

    # ---------- 工具栏 ----------
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Toolbar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setFixedHeight(62)
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 12, 8)
        row.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(_app_icon().pixmap(36, 36))
        row.addWidget(mark)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Scrcpy Studio")
        title.setObjectName("HeaderTitle")
        sub = QLabel("Android 投屏工作台")
        sub.setObjectName("HeaderSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        row.addLayout(titles)

        row.addSpacing(12)
        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("搜索应用…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedWidth(240)
        row.addWidget(self.search_box)
        row.addStretch(1)

        self.status_pill = QLabel("未连接")
        row.addWidget(self.status_pill)

        self.float_btn = QPushButton("◉")
        self.float_btn.setObjectName("Round")
        self.float_btn.setToolTip("进入悬浮球模式（⌘⇧F）")
        self.float_btn.clicked.connect(self.enter_float_mode)
        row.addWidget(self.float_btn)

        self.theme_btn = QPushButton("◐")
        self.theme_btn.setObjectName("Round")
        self.theme_btn.setToolTip("外观：跟随系统 / 浅色 / 深色")
        self.theme_btn.clicked.connect(self._show_theme_menu)
        row.addWidget(self.theme_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("Round")
        self.settings_btn.setToolTip("设置（⌘,）")
        self.settings_btn.clicked.connect(self.open_settings)
        row.addWidget(self.settings_btn)

        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("Round")
        self.more_btn.setToolTip("更多操作")
        self.more_btn.clicked.connect(
            lambda: self._show_more_menu(
                self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft())
            )
        )
        row.addWidget(self.more_btn)
        self._sync_theme_button()
        return bar

    def _show_theme_menu(self) -> None:
        menu = QMenu(self)
        items = [("跟随系统", "auto"), ("浅色", "light"), ("深色", "dark")]
        for text, value in items:
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(style.mode() == value)
            action.triggered.connect(lambda _=False, v=value: self.set_theme(v))
        menu.exec(self.theme_btn.mapToGlobal(self.theme_btn.rect().bottomLeft()))

    def _show_more_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("重新读取应用列表", lambda: self.load_apps(force=True))
        menu.addAction("重新提取名称与图标（较慢）",
                       lambda: self.load_appinfo(force=True))
        menu.addAction("整屏投屏", lambda: self.start_mirror())
        menu.addAction("进入悬浮球模式", self.enter_float_mode)
        menu.addSeparator()

        view = menu.addMenu("应用视图")
        for text, value in (("Launchpad 网格", "desktop"), ("紧凑列表", "list")):
            action = view.addAction(text)
            action.setCheckable(True)
            action.setChecked(self.state.view_mode == value)
            action.triggered.connect(
                lambda _=False, v=value: (self._set_state(view_mode=v),
                                          self.app_panel.set_view(v))
            )
        source = menu.addMenu("应用来源")
        for text, value in (("全部", "all"), ("仅第三方", "third"), ("仅系统", "system")):
            action = source.addAction(text)
            action.setCheckable(True)
            action.setChecked(self._source_filter == value)
            action.triggered.connect(
                lambda _=False, v=value: (setattr(self, "_source_filter", v),
                                          self.app_panel.set_filter(v))
            )
        group = menu.addAction("按类型分区")
        group.setCheckable(True)
        group.setChecked(self.state.group_by)
        group.triggered.connect(
            lambda checked: (self._set_state(group_by=checked),
                             self.app_panel.set_group_by(checked))
        )
        menu.addSeparator()
        menu.addAction("显示 / 隐藏日志", lambda: self.console.set_expanded(
            not self.console.output.isVisible()
        ))
        menu.addAction("USB 连接向导…", self.open_usb_dialog)
        menu.addSeparator()
        menu.addAction("关于 Scrcpy Studio", self._about)
        menu.exec(pos)

    def _about(self) -> None:
        QMessageBox.about(
            self, "关于 Scrcpy Studio",
            "Scrcpy Studio 0.6.2\n\n"
            "macOS 桌面投屏工作台：USB / 无线设备管理、真实应用图标、"
            "应用分类、设备文本输入、多窗口单应用投屏与悬浮球模式。\n\n"
            "基于 scrcpy 5.x 与 adb。",
        )

    # ---------- 悬浮球 ----------
    def enter_float_mode(self) -> None:
        if self._float_mode:
            return
        self._float_mode = True
        self.float_controller.set_apps(self.app_panel.all_apps())
        dev = next((d for d in self.devices if d.serial == self.current_serial), None)
        self.float_controller.set_device_label(
            dev.display_name if dev else self.current_serial.split(":")[0]
        )
        self.float_controller.show(self.state.float_ball_pos or None)
        self.float_controller.collapse_panel()
        self.hide()
        self.console.log("[悬浮球] 已进入悬浮球模式 · 点击小球展开应用")

    def exit_float_mode(self) -> None:
        if not self._float_mode:
            return
        self.state.float_ball_pos = list(self.float_controller.ball_pos())
        self.float_controller.hide()
        self._float_mode = False
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.persist()
        self.console.log("[悬浮球] 已返回主窗口")

    def toggle_float_mode(self) -> None:
        if self._float_mode:
            self.exit_float_mode()
        else:
            self.enter_float_mode()

    # ---------- 主题 ----------
    def set_theme(self, value: str) -> None:
        self.state.theme = value
        style.apply(QApplication.instance(), value)
        self._sync_theme_button()
        self._refresh_dynamic()
        self.persist()
        self.console.log(f"外观 → {dict(auto='跟随系统', light='浅色', dark='深色')[value]}")

    def _on_system_theme(self, *_args) -> None:
        if self.state.theme != "auto":
            return
        style.apply(QApplication.instance())
        self._refresh_dynamic()

    def _sync_theme_button(self) -> None:
        self.theme_btn.setText({"auto": "◐", "light": "☀", "dark": "☾"}[style.mode()])

    def _refresh_dynamic(self) -> None:
        """QSS 之外的 inline 样式需要在主题切换后重新生成。"""
        self._update_status()
        self.mirror_bar.set_windows([(w.id, w.label) for w in self.processes.values()])
        self.input_panel.retheme()
        self.device_panel.set_devices(self.devices, self.current_serial)
        self.app_panel.refresh()
        self.float_controller.apply_theme()
        for control in self.controls.values():
            control.set_theme()

    # ---------- 信号 ----------
    def _wire(self) -> None:
        self.search_box.textChanged.connect(self.app_panel.set_search)
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

        self.app_panel.launch_requested.connect(self.launch_app)
        self.app_panel.alias_requested.connect(self.edit_alias)
        self.app_panel.dock_toggled.connect(self.toggle_dock)
        self.app_panel.recategory_requested.connect(self.recategorize)
        self.app_panel.category_changed.connect(lambda k: self._set_state(category=k))
        self.app_panel.more_requested.connect(self._show_more_menu)
        self.app_panel.apps_changed.connect(self.float_controller.set_apps)

        self.float_controller.launch_requested.connect(self.launch_app)
        self.float_controller.main_window_requested.connect(self.exit_float_mode)
        self.float_controller.exit_requested.connect(self.exit_float_mode)
        self.float_controller.settings_requested.connect(self.open_settings)
        self.float_controller.reload_requested.connect(lambda: self.load_apps(force=True))
        self.float_controller.focus_requested.connect(self.focus_mirror)
        self.float_controller.control_visibility_requested.connect(
            self._toggle_control_visibility
        )
        self.float_controller.quit_requested.connect(self.close)

        self.input_panel.send_requested.connect(self.send_text)
        self.input_panel.copy_requested.connect(self.copy_text)
        self.input_panel.key_requested.connect(self.send_key)
        self.input_panel.mode_changed.connect(lambda m: self._set_state(input_mode=m))
        self.input_panel.enter_changed.connect(lambda e: self._set_state(input_enter=e))

    def _init_from_state(self) -> None:
        self._source_filter = "all"
        self.device_panel.set_auto_mirror(self.state.auto_mirror_usb)
        self.app_panel.set_dock(self.state.dock_packages)
        self.app_panel.set_overrides(self.state.category_overrides)
        self.app_panel.set_appinfo(apkinfo.all_cached())
        self.app_panel.set_group_by(self.state.group_by)
        self.app_panel.set_category(self.state.category)
        self.app_panel.set_view(self.state.view_mode)
        self.app_panel.set_columns(self.state.launchpad_columns)
        self.input_panel.set_mode(self.state.input_mode)
        self.input_panel.set_enter(self.state.input_enter)
        self.input_panel.set_history(self.state.input_history)
        self.input_panel.set_serial("")
        self.input_panel.set_expanded(self.state.input_visible)
        self.console.set_expanded(self.state.console_visible)

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
        for seq in ("Ctrl+F", "Meta+F"):
            QShortcut(QKeySequence(seq), self).activated.connect(
                self.search_box.setFocus
            )
        for seq in ("Ctrl+Comma", "Meta+Comma"):
            QShortcut(QKeySequence(seq), self).activated.connect(self.open_settings)
        for seq in ("Ctrl+Shift+F", "Meta+Shift+F"):
            QShortcut(QKeySequence(seq), self).activated.connect(
                self.toggle_float_mode
            )
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)

    def _on_escape(self) -> None:
        if self.input_panel.edit.hasFocus():
            self.input_panel.edit.clear()
        elif self.search_box.hasFocus():
            self.search_box.clear()

    def _set_state(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self.state, key, value)
        self.persist()

    # ---------- 设置对话框 ----------
    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.state)
        dialog.theme_changed.connect(
            lambda value: style.apply(QApplication.instance(), value)
        )
        if dialog.exec() == QDialog.Accepted:
            self.state.mirror = dialog.config()
            self.state.theme = dialog.theme()
            self.state.launchpad_columns = dialog.columns()
            self.state.prefer_usb = dialog.prefer_usb_value()
            self.state.auto_mirror_usb = dialog.auto_mirror_value()
            self.state.usb_port = dialog.usb_port_value()
            self.state.auto_float_on_connect = dialog.auto_float_value()
            self.state.auto_float_on_mirror = dialog.auto_float_mirror_value()
            self.state.remember_window_geometry = dialog.remember_geometry_value()
            self.state.control_follow_window = dialog.control_follow_value()
            self.state.show_control_bar = dialog.show_control_bar_value()
            self.state.control_items = dialog.control_items_value()
            self._controls_visible = self.state.show_control_bar
            for control in self.controls.values():
                control.set_following(self.state.control_follow_window)
                control.apply_items(self.state.control_items)
                control.setVisible(self._controls_visible)
            self.state.adb_path = dialog.adb_path_value()
            self.state.scrcpy_path = dialog.scrcpy_path_value()
            paths.set_overrides(self.state.adb_path, self.state.scrcpy_path)
            self.device_panel.set_auto_mirror(self.state.auto_mirror_usb)
            self.app_panel.set_columns(self.state.launchpad_columns)
            style.apply(QApplication.instance(), self.state.theme)
            self._sync_theme_button()
            self._refresh_dynamic()
            self.persist()
            self.console.log(
                f"设置已保存 · adb → {paths.ADB} · scrcpy → {paths.SCRCPY}"
            )
        else:
            paths.set_overrides(self.state.adb_path, self.state.scrcpy_path)
            style.apply(QApplication.instance(), self.state.theme)
            self._sync_theme_button()
            self._refresh_dynamic()

    # ---------- 设备 ----------
    def refresh_devices(self, silent: bool = False) -> None:
        def done(devices: list[adb.Device]) -> None:
            self.devices = devices
            online = [d for d in devices if d.online]
            serials = {d.serial for d in online}
            previous_serial = self.current_serial
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

            # 首次连接时设备往往还没完成授权，list_apps 会返回空；
            # 除自动重试外，每次轮询也补一次，避免空结果一直留在界面上。
            if target and target in serials:
                if target != self.current_serial:
                    self.on_device_selected(target)   # 会顺带触发 load_apps
                elif target == previous_serial \
                        and not self.app_cache.get(target) \
                        and target not in self._apps_loading \
                        and self._apps_retry.get(target, 0) < 5:
                    # 仅当设备本来就已选中时才补读，避免与 on_device_selected
                    # 刚发出的那次请求重复
                    self.load_apps(force=False)

            had_online, self._had_online = self._had_online, bool(online)
            if online and not had_online and self.state.auto_float_on_connect \
                    and not self._float_mode:
                QTimer.singleShot(700, self.enter_float_mode)

            pending, self._pending_auto_mirror = self._pending_auto_mirror, ""
            if pending and pending in serials and not self.processes \
                    and self.state.auto_mirror_usb:
                QTimer.singleShot(500, lambda: self.usb_mirror(pending))

        def fail(message: str) -> None:
            self.console.log(f"[错误] {message}")
            self._update_status()

        run_async(adb.list_devices, done, fail)

    def _pick_preferred(self, online: list[adb.Device]) -> str:
        if self.state.prefer_usb:
            usb = [d for d in online if not d.wireless]
            if usb:
                return usb[0].serial
        return online[0].serial

    def on_device_event(self, snapshot) -> None:
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
            if self.state.auto_mirror_usb and not self.processes:
                self._pending_auto_mirror = sorted(added)[0]
        self.refresh_devices(silent=True)

    def _update_status(self) -> None:
        p = style.P()
        online = [d for d in self.devices if d.online]
        dev = next((d for d in online if d.serial == self.current_serial), None)
        if dev is None and online:
            dev = online[0]
        windows = len(self.processes)
        suffix = f" · {windows} 个投屏窗口" if windows else ""
        if online:
            label = f"{dev.display_name} · {dev.label}" if dev else f"{len(online)} 台设备在线"
            self.status_pill.setText(f"● {label}{suffix}")
            fg, bg = p.ok, p.accent_soft
        else:
            self.status_pill.setText(f"未连接设备{suffix}")
            fg, bg = p.text2, p.glass_soft
        self.status_pill.setStyleSheet(
            f"font-size:11px; color:{fg}; background:{bg};"
            "border-radius:10px; padding:4px 10px;"
        )

    def on_device_selected(self, serial: str) -> None:
        if not serial or serial == self.current_serial:
            return
        self.current_serial = serial
        self.state.last_serial = serial
        self._apps_retry.pop(serial, None)
        self.persist()
        self.input_panel.set_serial(serial)
        self.app_panel.set_device_label(serial.split(":")[0])
        self.float_controller.set_device_label(serial.split(":")[0])
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
                self.float_controller.set_device_label(info.model)
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

    # ---------- USB / 无线 ----------
    def usb_mirror(self, serial: str | None = None) -> None:
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
        self.console.log(f"[USB] 启动投屏：{target}")
        self.start_mirror(serial=target)

    def open_usb_dialog(self) -> None:
        dialog = UsbDialog(self, port=self.state.usb_port,
                           prefer_usb=self.state.prefer_usb)
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

        run_async(adb.restart_server, done,
                  lambda m: self.console.log(f"[错误] 重启 adb 失败：{m}"))

    def to_wireless(self) -> None:
        dev = self.device_panel.current_device()
        if dev is None or dev.wireless or not dev.online:
            QMessageBox.information(self, "需要 USB 设备",
                                    "请先选中一台已通过 USB 连接并授权的设备。")
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
        run_async(adb.switch_to_wireless, self.on_switched,
                  lambda m: self.console.log(f"[错误] 切换失败：{m}"),
                  dev.serial, port)

    def on_switched(self, addr: str) -> None:
        self.console.log(f"[USB → 无线] 已连接 {addr}，现在可以拔掉数据线")
        self.device_panel.set_hint(f"已切换到无线 {addr}，可以拔掉数据线了。", "ok")
        self.state.last_serial = addr
        self.current_serial = addr
        self.persist()
        QTimer.singleShot(1200, lambda: self.refresh_devices())

    def open_wireless_dialog(self) -> None:
        dialog = WirelessDialog(self)
        dialog.connected.connect(lambda _a: QTimer.singleShot(600, self.refresh_devices))
        dialog.exec()

    def open_pair_dialog(self) -> None:
        dialog = WirelessDialog(self, start_tab=1)
        dialog.connected.connect(lambda _a: QTimer.singleShot(600, self.refresh_devices))
        dialog.exec()

    # ---------- 应用列表 / 图标 ----------
    def load_apps(self, force: bool = False) -> None:
        serial = self.current_serial
        if not serial:
            self.app_panel.set_data([], set(), self.state.aliases)
            self.app_panel.set_progress("")
            return
        if serial in self._apps_loading:
            return
        if force:
            self._apps_retry.pop(serial, None)
        if not force and self.app_cache.get(serial):
            self.app_panel.set_data(self.app_cache[serial],
                                    self.system_cache.get(serial, set()),
                                    self.state.aliases)
            self._info_timer.start()
            return

        self._apps_loading.add(serial)
        self.app_panel.set_progress("读取中…")

        def done(packages: list[tuple[str, str]]) -> None:
            self._apps_loading.discard(serial)
            if serial != self.current_serial:
                return
            if not packages:
                # 设备刚上线 / 未授权时 list_apps 常返回空。绝不缓存空列表，
                # 否则后续轮询因 current_serial 未变就不会再读，界面一直空白。
                self._schedule_retry(serial)
                return
            self.app_cache[serial] = packages
            self._apps_retry.pop(serial, None)
            self.app_panel.set_data(packages, self.system_cache.get(serial, set()),
                                    self.state.aliases)
            self.app_panel.set_progress("")
            self.console.log(f"读取到 {len(packages)} 个可投屏应用")
            if self._float_mode:
                self.float_controller.set_apps(self.app_panel.all_apps())
            # 与 system_packages / device_info 错开，少抢一点 adb
            QTimer.singleShot(300, lambda: self.load_appinfo(force=False))

        def fail(message: str) -> None:
            self._apps_loading.discard(serial)
            if serial != self.current_serial:
                return
            self.app_panel.set_progress("读取失败，重试中…")
            self.console.log(f"[错误] 读取应用列表：{message}")
            self._schedule_retry(serial)

        run_async(adb.list_apps, done, fail, serial)

        def system_done(pkgs: set[str]) -> None:
            self.system_cache[serial] = pkgs
            if serial == self.current_serial and serial in self.app_cache:
                self.app_panel.set_data(self.app_cache[serial], pkgs, self.state.aliases)

        run_async(adb.system_packages, system_done, lambda _m: None, serial)

    def _schedule_retry(self, serial: str) -> None:
        attempt = self._apps_retry.get(serial, 0) + 1
        self._apps_retry[serial] = attempt
        if attempt > 4:
            self.app_panel.set_progress("未读取到应用 · 点「重新读取应用」重试")
            return
        self.app_panel.set_progress(f"等待设备就绪 · 第 {attempt} 次重试")
        if attempt == 1:
            self.console.log("[应用] 设备尚未就绪，正在自动重试读取应用列表…")
        QTimer.singleShot((1200, 2200, 3500, 5000)[attempt - 1],
                          lambda: self._retry_apps(serial))

    def _retry_apps(self, serial: str) -> None:
        if not serial or serial != self.current_serial:
            return
        if not any(d.serial == serial and d.online for d in self.devices):
            return                       # 设备离线了，等下次轮询再补
        self.load_apps(force=False)       # 空结果没写缓存，因此会真的重读

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

        def worker(package: str, prefetched_path: str):
            if token != self._info_token:
                return package, None
            try:
                return package, apkinfo.fetch(
                    serial, package, force=force,
                    prefetched_path=prefetched_path,
                    # 常规加载不 pull 整包：设备没有 unzip 时这会拖垮界面
                    allow_full=force,
                )
            except Exception:  # noqa: BLE001
                return package, None

        def submitted(future) -> None:
            try:
                package, info = future.result()
            except Exception:  # noqa: BLE001
                package, info = "", None
            self.info_ready.emit((token, package, info))

        def start(paths: dict[str, str]) -> None:
            if token != self._info_token or serial != self.current_serial:
                return
            for package, _activity in packages:
                self._info_pool.submit(
                    worker, package, paths.get(package, "")
                ).add_done_callback(submitted)

        # 一条 adb 批量拿全部 APK 路径，省掉每个应用一次 pm path 往返
        run_async(lambda: apkinfo.prefetch_paths(serial), start,
                  lambda _m: start({}))

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
            self.app_panel.set_progress("")

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

        run_async(lambda: textinput.send(serial, text, self.state.input_mode, enter),
                  done, lambda m: (self.input_panel.set_status(m.splitlines()[0], ok=False),
                                   self.console.log(f"[输入失败] {m}")))

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

    # ---------- 多窗口投屏 ----------
    def launch_app(self, package: str) -> None:
        self.state.last_package = package
        self.start_mirror(package=package)

    def start_mirror(self, package: str | None = None,
                     serial: str | None = None) -> None:
        serial = serial or self.device_panel.current_serial() or self.current_serial
        if not serial:
            QMessageBox.information(self, "没有可用设备",
                                    "请先用 USB 连接或在「无线连接」里连上手机。")
            return

        # 同一应用已经开着投屏窗口：不再启动第二个进程，把已有窗口切到前台
        if package:
            existing = next(
                (w for w in self.processes.values()
                 if w.package == package and w.serial == serial
                 and w.proc.state() != QProcess.NotRunning),
                None,
            )
            if existing is not None:
                self.console.log(f"[去重] {existing.label} 已在投屏中，切换到该窗口")
                self.focus_mirror(existing.id)
                self.float_controller.collapse_panel()
                return

        # scrcpy < 5.0 没有 --new-display / --start-app：降级为整屏 + 设备端启动应用
        if package and not paths.supports_new_display(self.state.scrcpy_path):
            answer = QMessageBox.question(
                self, "scrcpy 版本过旧",
                f"检测到 {paths.version_text(self.state.scrcpy_path)}，"
                "单应用投屏（--new-display / --start-app）需要 scrcpy 5.0 或更高版本。\n\n"
                "是否改为「整屏投屏 + 在手机上打开该应用」？\n"
                "升级到 5.x 后可恢复独立窗口与多窗口同时投屏。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                self.console.log("[已取消] 请升级 scrcpy 到 5.x 后重试")
                return
            self._launch_on_device(serial, package)
            self.console.log(f"[兼容模式] {package} → 整屏投屏 + 设备端启动应用")
            package = None

        cfg = self.state.mirror.copy()
        if package:
            cfg.mode = "app"
            cfg.package = package
            label = display_name(package, self.state.aliases)
        else:
            cfg.mode = "screen"
            cfg.package = ""
            dev = next((d for d in self.devices if d.serial == serial), None)
            label = f"{(dev.display_name if dev else serial)} · 整屏"
            for window in self.processes.values():
                if window.serial == serial and not window.package \
                        and window.proc.state() != QProcess.NotRunning:
                    self.console.log("该设备已经在整屏投屏中，切换到该窗口")
                    self.focus_mirror(window.id)
                    self.float_controller.collapse_panel()
                    return

        self.state.mirror = cfg
        self.persist()
        config_key = package or "__screen__"
        geometry = (self.state.window_geometry.get(config_key)
                    if self.state.remember_window_geometry else None)
        args = build_args(cfg, serial, self.state.scrcpy_path or None, geometry)
        self.console.log("$ " + shlex.join(args))
        if geometry and geometry.get("x") is not None:
            self.console.log(
                f"[窗口] 恢复 {config_key} 上次位置 "
                f"{geometry.get('x')},{geometry.get('y')}"
            )

        window_id = uuid.uuid4().hex[:8]
        proc = QProcess(self)
        # Finder 启动的 .app 只有最小 PATH，必须显式把 adb 绝对路径交给 scrcpy
        child = paths.child_environment(self.state.adb_path, self.state.scrcpy_path)
        env = QProcessEnvironment.systemEnvironment()
        for key, value in child.items():
            env.insert(key, value)
        proc.setProcessEnvironment(env)
        self.console.log(f"[环境] ADB={child['ADB']}（已注入 scrcpy 子进程）")
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._drain(proc))
        proc.finished.connect(lambda *_: self._on_finished(window_id))
        proc.errorOccurred.connect(
            lambda err: self.console.log(f"[scrcpy 启动失败] {err}")
        )
        proc.start(args[0], args[1:])
        self.processes[window_id] = MirrorWindow(
            window_id, label, package or "", serial, proc, key=config_key
        )
        self._create_control(window_id, label, serial, geometry)
        if not self._geometry_timer.isActive():
            self._geometry_timer.start()
        self.console.log(f"投屏窗口 {window_id} → {label}（可继续打开其他应用）")
        self._refresh_mirror_ui()
        if self.state.auto_float_on_mirror:
            QTimer.singleShot(180, self._after_mirror_started)

    def _after_mirror_started(self) -> None:
        """投屏成功后进入悬浮球形态，并收起应用面板 / hover 列表。"""
        if not self.state.auto_float_on_mirror:
            return
        if self._float_mode:
            self.float_controller.collapse_panel()
        else:
            self.enter_float_mode()

    def focus_mirror(self, window_id: str) -> None:
        """把已存在的 scrcpy 窗口激活到前台，而不是再开一个。"""
        window = self.processes.get(window_id)
        if window is None:
            return
        pid = int(window.proc.processId() or 0)
        label = window.label
        # 点击悬浮球/列表时先确保本 App 是前台，macOS 才允许把别的进程激活
        self.float_controller.ball.activateWindow()
        # 窗口不在屏幕列表里通常意味着已最小化，需要走能取消 AXMinimized 的路径
        on_screen = bool(pid and nativewindow.window_bounds(pid))
        if pid and on_screen and nativewindow.focus_process(pid):
            self.console.log(f"[置前] {label}（pid {pid}）")
            self.input_panel.set_status(f"已切换到 {label}", ok=True)
            return

        if not on_screen:
            self.console.log(f"[置前] {label} 的窗口当前不在屏幕上，尝试恢复显示…")
        else:
            self.console.log(f"[去重] {label} 已在投屏中（pid {pid}），尝试备用方式置前…")

        def done(ok: bool) -> None:
            if ok:
                self.console.log(f"[置前] 已通过系统事件切换到 {label}")
                self.input_panel.set_status(f"已切换到 {label}", ok=True)
            else:
                self.console.log(
                    "[置前] 系统未允许自动前置（可在「系统设置 → 隐私与安全性 → 自动化」授权）；"
                    "该应用已在投屏中，可手动点击其窗口"
                )
                self.input_panel.set_status(f"{label} 已在投屏中", ok=True)

        if pid:
            run_async(lambda: nativewindow.focus_process_fallback(pid), done,
                      lambda _m: done(False))
        else:
            done(False)

    # ---------- 每个投屏窗口的控制条 ----------
    def _create_control(self, window_id: str, label: str, serial: str,
                        geometry: dict | None) -> None:
        control = MirrorControl(window_id, label, serial, self.state.control_items)
        control.key_requested.connect(self._control_key)
        control.text_requested.connect(self._control_text)
        control.copy_requested.connect(self._control_copy)
        control.close_requested.connect(self.stop_mirror)
        control.focus_requested.connect(self.focus_mirror)
        control.moved.connect(self._control_moved)
        control.follow_toggled.connect(self._on_control_follow_toggled)
        control.set_following(self.state.control_follow_window)

        pos: tuple[int, int] | None = None
        # 跟随模式下控制条位置由窗口决定，记忆位置只在固定模式生效
        if not self.state.control_follow_window and geometry \
                and geometry.get("control_x") is not None:
            pos = (int(geometry["control_x"]), int(geometry.get("control_y", 80)))
        if pos is None:
            screen = QGuiApplication.primaryScreen()
            area = screen.availableGeometry() if screen else None
            pos = (area.left() + 40,
                   area.top() + 28 + 66 * (len(self.controls) % 5)) if area else (80, 80)
        control.move(*pos)
        # 默认不显示控制条；跟随仍会持续计算位置，打开时立刻出现在正确位置
        control.setVisible(self._controls_visible)
        if self._controls_visible:
            control.raise_()
        QTimer.singleShot(
            0, lambda: nativewindow.pin(control, nativewindow.CONTROL_LEVEL)
        )
        self.controls[window_id] = control
        # 窗口刚创建时 CGWindowList 可能还读不到，主动补几次采样
        for delay in (300, 1000, 2500):
            QTimer.singleShot(delay, self._sample_geometry)

    def _control_key(self, serial: str, name: str) -> None:
        run_async(
            textinput.send_keyevent,
            lambda out: self.console.log(f"[控制] {name} → {out.strip() or '已发送'}"),
            lambda msg: self.console.log(f"[控制失败] {name}：{msg}"),
            serial, name,
        )

    def _control_text(self, serial: str, text: str, enter: bool) -> None:
        control = self.sender() if isinstance(self.sender(), MirrorControl) else None

        def done(result) -> None:
            channel = "ADBKeyBoard" if result.channel == "adbkeyboard" else "input text"
            self.console.log(f"[控制] 文本已推送 · {channel}")
            if control:
                control.set_status("已发送 ✓")

        def fail(message: str) -> None:
            self.console.log(f"[控制失败] 文本推送：{message}")
            if control:
                control.set_status("失败 · 可点复制后 ⌘V")

        run_async(
            lambda: textinput.send(serial, text, self.state.input_mode, enter),
            done, fail,
        )

    def _control_copy(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.console.log(f"已复制 {len(text)} 个字符 · 到投屏窗口按 ⌘V 粘贴")
        control = self.sender() if isinstance(self.sender(), MirrorControl) else None
        if control:
            control.set_status("已复制 · 窗口内 ⌘V")

    def _control_moved(self, window_id: str, x: int, y: int) -> None:
        # 手动拖动 = 解除跟随，保持用户放的位置
        control = self.controls.get(window_id)
        if control is not None:
            control.set_following(False)
            control.set_status("已固定位置")
        window = self.processes.get(window_id)
        if not window or not self.state.remember_window_geometry:
            return
        entry = self.state.window_geometry.setdefault(window.key, {})
        entry["control_x"], entry["control_y"] = int(x), int(y)
        self.persist()

    def _on_control_follow_toggled(self, window_id: str, following: bool) -> None:
        control = self.controls.get(window_id)
        if control is not None:
            control.set_status("恢复跟随" if following else "已固定位置")
        if following:
            self._sample_geometry()      # 立刻贴回当前窗口位置

    # ---------- 记住每个应用的窗口位置 / 控制条跟随 ----------
    def _sample_geometry(self) -> None:
        if not self.processes:
            self._geometry_timer.stop()
            return
        active: list[tuple[MirrorWindow, int]] = []
        for window in self.processes.values():
            pid = int(window.proc.processId() or 0)
            if pid and window.proc.state() != QProcess.NotRunning:
                active.append((window, pid))
        # 一次 CGWindowList 枚举覆盖所有投屏窗口，避免高频轮询放大 CPU 开销
        pids = {pid for _window, pid in active}
        bounds_map = nativewindow.window_bounds_map(pids)

        # 单窗口且 PID 完全未命中（包装脚本 / SDL 代理进程）时做一次兜底
        if len(active) == 1 and active[0][1] not in bounds_map:
            fallback = self._fallback_window_bounds(active[0][1])
            if fallback:
                bounds_map[active[0][1]] = fallback

        for window, pid in active:
            bounds = bounds_map.get(pid)
            control = self.controls.get(window.id)
            if bounds:
                window.missing_frames = 0
                window.ever_visible = True
                window.last_geometry = bounds
                if self._controls_visible and window.minimized_hidden:
                    if control is not None:
                        control.show()
                    window.minimized_hidden = False
                self._follow_control(window, bounds)
            elif window.ever_visible:
                # 窗口曾可见却连续读不到：多半是最小化或切到别的 Space
                window.missing_frames += 1
                if window.missing_frames >= 3 and control is not None \
                        and control.isVisible():
                    control.hide()
                    window.minimized_hidden = True

        # 长时间读不到窗口时给出一次性诊断，便于定位跟随失效
        if not self._follow_diagnosed and any(
                window.ever_visible and window.missing_frames >= 10
                for window in self.processes.values()):
            count = len(nativewindow.window_bounds_all())
            self.console.log(
                "[跟随诊断] 连续读不到投屏窗口；"
                f"屏幕普通窗口 {count} 个，跟随开关={self.state.control_follow_window}，"
                f"控制条显示={self._controls_visible}。"
                "请确认窗口仍在同一 Space，或开启 scrcpy 的无边框/置顶。"
            )
            self._follow_diagnosed = True

    def _fallback_window_bounds(self, pid: int) -> dict | None:
        """只有一个投屏窗口且 PID 对不上时，找唯一一个像手机画面的竖屏窗口。

        只在候选唯一时启用，避免误绑到别的 App 窗口；多窗口场景一律不猜。
        """
        own = os.getpid()
        candidates = []
        for owner_pid, bounds in nativewindow.window_bounds_all().items():
            if owner_pid in (own, pid):
                continue
            w, h = bounds["width"], bounds["height"]
            if w >= 240 and h >= 320 and 0.3 <= w / h <= 1.0:
                candidates.append(bounds)
        return candidates[0] if len(candidates) == 1 else None

    def _toggle_control_visibility(self) -> None:
        """悬浮球「更多操作」里的显示 / 隐藏控制条（临时切换，不写配置）。"""
        self._controls_visible = not self._controls_visible
        for control in self.controls.values():
            control.setVisible(self._controls_visible)
            if self._controls_visible:
                control.raise_()
        if self._controls_visible:
            self._sample_geometry()      # 显示时立刻贴到正确位置
        self.console.log(
            "[控制条] 已显示 · 跟随投屏窗口" if self._controls_visible
            else "[控制条] 已隐藏"
        )

    def _follow_control(self, window: MirrorWindow, bounds: dict) -> None:
        """把控制条贴到 scrcpy 窗口上方；只更新位置，不改变可见性。"""
        control = self.controls.get(window.id)
        if control is None:
            return
        if not self.state.control_follow_window or not control.is_following():
            return

        win_w = int(bounds.get("width", 660))
        win_h = int(bounds.get("height", 0))
        control.set_content_width(win_w)
        w, h = control.width(), control.height()
        center = QPoint(int(bounds["x"] + win_w / 2), int(bounds["y"]))
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area is None:
            area = QApplication.primaryScreen().availableGeometry()
        edge = 8
        # 水平居中对齐窗口，再 clamp 到窗口所在屏幕
        x = int(bounds["x"] + (win_w - w) / 2)
        x = min(max(x, area.left() + edge),
                max(area.left() + edge, area.right() - w - edge))
        # 优先贴在窗口上方，放不下就贴到下方，避免遮住画面
        y = int(bounds["y"]) - h - 6
        if y < area.top() + edge:
            y = int(bounds["y"]) + win_h + 6
        y = min(max(y, area.top() + edge),
                max(area.top() + edge, area.bottom() - h - edge))
        y = self._avoid_control_overlap(window.id, x, y, w, h, area, edge)
        if (control.x(), control.y()) != (x, y):
            control.move(x, y)

    def _avoid_control_overlap(self, window_id: str, x: int, y: int,
                               w: int, h: int, area, edge: int) -> int:
        """多个投屏窗口位置相近时，把后处理的控制条下移错开。"""
        for _ in range(4):
            clash = None
            for other_id, other in self.controls.items():
                if other_id == window_id or not other.isVisible():
                    continue
                ox, oy = other.x(), other.y()
                if x < ox + other.width() and x + w > ox \
                        and y < oy + other.height() and y + h > oy:
                    clash = oy + other.height() + 4
                    break
            if clash is None:
                break
            y = clash
        return min(y, max(area.top() + edge, area.bottom() - h - edge))

    def _save_window_geometry(self, window: MirrorWindow) -> None:
        if not self.state.remember_window_geometry:
            return
        control = self.controls.get(window.id)
        entry = dict(window.last_geometry or {})
        if control is not None:
            entry["control_x"], entry["control_y"] = control.x(), control.y()
        if not entry:
            return
        self.state.window_geometry[window.key] = entry
        self.persist()
        if window.last_geometry:
            self.console.log(
                f"[窗口] 已记住 {window.key} 的位置 "
                f"{entry['x']},{entry['y']} {entry['width']}×{entry['height']}"
            )

    def _launch_on_device(self, serial: str, package: str) -> None:
        """旧版 scrcpy 的降级路径：在手机上把应用拉到前台，再整屏投屏。"""
        activity = ""
        for pkg, act in self.app_cache.get(serial, []):
            if pkg == package:
                activity = act
                break
        if activity and "/" in activity:
            cmd = ["shell", "am", "start", "-n", activity]
        else:
            cmd = ["shell", "monkey", "-p", package,
                   "-c", "android.intent.category.LAUNCHER", "1"]
        run_async(adb.run,
                  lambda _out: self.console.log(f"[兼容模式] 已启动 {package}"),
                  lambda m: self.console.log(f"[兼容模式] 启动应用失败：{m}"),
                  cmd, 15, serial)

    def _drain(self, proc: QProcess) -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.console.log(data.rstrip())

    def stop_mirror(self, window_id: str | None = None) -> None:
        targets = ([self.processes[window_id]] if window_id
                   and window_id in self.processes else list(self.processes.values()))
        if not targets:
            return
        self.console.log(f"正在停止 {len(targets)} 个投屏窗口…")
        for window in targets:
            if window.proc.state() != QProcess.NotRunning:
                window.proc.terminate()
        QTimer.singleShot(2500, lambda: self._force_kill([w.id for w in targets]))

    def _force_kill(self, ids: list[str]) -> None:
        for wid in ids:
            window = self.processes.get(wid)
            if window and window.proc.state() != QProcess.NotRunning:
                window.proc.kill()

    def _on_finished(self, window_id: str) -> None:
        window = self.processes.pop(window_id, None)
        control = self.controls.get(window_id)
        if window:
            self.console.log(f"投屏窗口已退出：{window.label}")
            self._save_window_geometry(window)
        if control is not None:
            self.controls.pop(window_id, None)
            control.close()
            control.deleteLater()
        if not self.processes:
            self._geometry_timer.stop()
        self._refresh_mirror_ui()

    def _refresh_mirror_ui(self) -> None:
        windows = [(w.id, w.label) for w in self.processes.values()]
        self.mirror_bar.setVisible(bool(self.processes))
        self.mirror_bar.set_windows(windows)
        self.float_controller.set_running_windows(windows)
        self.app_panel.set_running({w.package for w in self.processes.values() if w.package})
        self._update_status()

    # ---------- 其他 ----------
    def persist(self) -> None:
        self.state.input_visible = self.input_panel.is_expanded()
        self.state.console_visible = self.console.output.isVisible()
        if self._float_mode:
            self.state.float_ball_pos = list(self.float_controller.ball_pos())
        save_state(self.state)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._info_token += 1
        self._info_timer.stop()
        self.timer.stop()
        self._geometry_timer.stop()
        self.watcher.stop()
        if self._float_mode:
            self.state.float_ball_pos = list(self.float_controller.ball_pos())
        self.float_controller.hide()
        for window in self.processes.values():
            self._save_window_geometry(window)
        for control in self.controls.values():
            control.close()
        self.persist()
        for window in self.processes.values():
            if window.proc.state() != QProcess.NotRunning:
                window.proc.terminate()
        self._info_pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
        QApplication.instance().quit()
