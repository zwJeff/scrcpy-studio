"""设备栏、Launchpad 应用舞台、投屏参数表单与运行日志。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QStackedWidget, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from core.aliases import display_name
from core.apkinfo import AppInfo
from core.categories import CATEGORIES, categorize
from core.config import MirrorConfig
from core.paths import HOME

from . import style
from .desktop import AppData
from .launchpad import Launchpad, app_pixmap, clear_pixmap_cache

AVATAR_COLORS = ["#7EA6F0", "#8FCBA8", "#E8B173", "#C9A0DC", "#7FC6C6", "#E39BA0", "#A9B5C8"]


def _hline() -> QFrame:
    line = QFrame()
    line.setObjectName("GlassDivider")
    line.setFixedHeight(1)
    return line


class Card(QWidget):
    """毛玻璃圆角容器。"""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 13, 16, 13)
        outer.setSpacing(10)

        self.head_widget = QWidget()
        head = QHBoxLayout(self.head_widget)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.head_extra = head
        outer.addWidget(self.head_widget)

        self.body = QVBoxLayout()
        self.body.setSpacing(9)
        outer.addLayout(self.body, 1)

    def set_head_visible(self, visible: bool) -> None:
        self.head_widget.setVisible(visible)


class AppDelegate(QStyledItemDelegate):
    """紧凑列表视图的一行：图标 + 名称 + 包名 + 系统徽标。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.aliases: dict[str, str] = {}
        self.system: set[str] = set()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(0, 46)

    def paint(self, painter: QPainter, option, index) -> None:
        p = style.P()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(4, 2, -4, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setBrush(QColor(p.accent_soft))
        elif hover:
            painter.setBrush(QColor(p.glass_soft))
        else:
            painter.setBrush(QColor("transparent"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 9, 9)

        pkg = index.data(Qt.UserRole)
        name = index.data(Qt.DisplayRole)
        circle = QRect(rect.left() + 10, rect.center().y() - 13, 26, 26)
        decoration = index.data(Qt.DecorationRole)
        pix = None
        if isinstance(decoration, QIcon):
            pix = decoration.pixmap(26, 26)
        elif isinstance(decoration, QPixmap):
            pix = decoration.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if pix is not None and not pix.isNull():
            painter.drawPixmap(circle.left(), circle.top(), pix)
        else:
            painter.setBrush(QColor(AVATAR_COLORS[abs(hash(pkg)) % len(AVATAR_COLORS)]))
            painter.drawRoundedRect(circle, 6, 6)

        name_font = QFont(painter.font())
        name_font.setPixelSize(13)
        painter.setFont(name_font)
        painter.setPen(QPen(QColor(p.accent if selected else p.text)))
        name_rect = QRect(rect.left() + 46, rect.top() + 6, rect.width() - 96, 17)
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(name, Qt.ElideRight, name_rect.width()))

        sub_font = QFont(painter.font())
        sub_font.setPixelSize(11)
        painter.setFont(sub_font)
        painter.setPen(QPen(QColor(p.text3)))
        pkg_rect = QRect(rect.left() + 46, rect.top() + 24, rect.width() - 96, 14)
        painter.drawText(pkg_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(pkg, Qt.ElideMiddle, pkg_rect.width()))

        if pkg in self.system:
            badge = QRect(rect.right() - 42, rect.center().y() - 8, 36, 16)
            painter.setBrush(QColor(p.glass_soft))
            painter.drawRoundedRect(badge, 5, 5)
            painter.setPen(QPen(QColor(p.text3)))
            painter.drawText(badge, Qt.AlignCenter, "系统")
        painter.restore()


class AppItem(QListWidgetItem):
    def __init__(self, package: str, name: str):
        super().__init__(name)
        self.package = package
        self.setData(Qt.UserRole, package)
        self.setData(Qt.UserRole + 1, name)


class DeviceRow(QWidget):
    DOT_COLORS = {"ok": "#2FAE7E", "unauthorized": "#E8A13C", "no_permissions": "#E8A13C",
                  "offline": "#D4675E", "recovery": "#D4675E", "other": "#9AA4B2"}

    def __init__(self, title: str, meta: str, online: bool, wireless: bool,
                 state_kind: str = "ok"):
        super().__init__()
        p = style.P()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{self.DOT_COLORS.get(state_kind, '#9AA4B2')};"
                          " font-size:10px; background:transparent;")
        top.addWidget(dot)
        name = QLabel(title)
        name.setStyleSheet(f"font-size:13px; font-weight:500; color:{p.text}; background:transparent;")
        top.addWidget(name)
        top.addStretch(1)
        tag = QLabel("无线" if wireless else "USB")
        tag.setStyleSheet(f"font-size:10px; color:{p.text3}; background:{p.glass_soft};"
                          "border-radius:5px; padding:1px 6px;")
        top.addWidget(tag)
        lay.addLayout(top)
        sub = QLabel(meta)
        sub.setStyleSheet(f"font-size:11px; color:{p.text3}; background:transparent;")
        sub.setContentsMargins(14, 0, 0, 0)
        lay.addWidget(sub)


class DevicePanel(Card):
    """设备栏：只保留高频操作，高级项收进「⋯」菜单。"""
    refresh_clicked = Signal()
    device_selected = Signal(str)
    wireless_clicked = Signal()
    pair_clicked = Signal()
    disconnect_clicked = Signal()
    usb_mirror_clicked = Signal()
    usb_setup_clicked = Signal()
    restart_adb_clicked = Signal()
    to_wireless_clicked = Signal()
    auto_mirror_changed = Signal(bool)

    def __init__(self):
        super().__init__("设备")
        self._device_map: dict[str, object] = {}

        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("Round")
        self.more_btn.setToolTip("更多设备操作")
        self.more_btn.clicked.connect(self._show_more)
        self.head_extra.addWidget(self.more_btn)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setUniformItemSizes(False)
        self.list.currentItemChanged.connect(self._on_change)
        self.empty = QLabel("未发现设备\n\n用数据线连接手机并开启 USB 调试，\n或点下方「无线连接…」")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Hint")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.list)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)
        self.stack.setMinimumHeight(110)
        self.body.addWidget(self.stack, 1)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        self.body.addWidget(self.hint)

        self.info = QLabel("尚未发现设备")
        self.info.setWordWrap(True)
        self.info.setObjectName("Hint")
        self.body.addWidget(self.info)

        self.body.addWidget(_hline())
        primary = QHBoxLayout()
        primary.setSpacing(7)
        self.btn_usb_mirror = QPushButton("USB 投屏")
        self.btn_usb_mirror.setObjectName("Primary")
        self.btn_usb_mirror.setToolTip("选中 USB 设备并立即以整屏模式投屏（⌘U）")
        self.btn_usb_mirror.clicked.connect(self.usb_mirror_clicked)
        self.btn_wireless = QPushButton("无线连接…")
        self.btn_wireless.clicked.connect(self.wireless_clicked)
        primary.addWidget(self.btn_usb_mirror, 1)
        primary.addWidget(self.btn_wireless, 1)
        self.body.addLayout(primary)

        self.auto_mirror = QCheckBox("插入 USB 自动投屏")
        self.auto_mirror.stateChanged.connect(
            lambda state: self.auto_mirror_changed.emit(state != 0)
        )
        self.body.addWidget(self.auto_mirror)

    def _show_more(self) -> None:
        menu = QMenu(self)
        menu.addAction("刷新设备", self.refresh_clicked.emit)
        menu.addAction("USB 连接向导…", self.usb_setup_clicked.emit)
        menu.addAction("无线配对（Android 11+）", self.pair_clicked.emit)
        menu.addSeparator()
        menu.addAction("USB → 无线", self.to_wireless_clicked.emit)
        menu.addAction("断开当前设备", self.disconnect_clicked.emit)
        menu.addAction("重启 adb 服务", self.restart_adb_clicked.emit)
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _on_change(self, current, _previous) -> None:
        if current is None:
            return
        self.device_selected.emit(current.data(Qt.UserRole))

    def set_devices(self, devices, selected_serial: str = "") -> None:
        self.list.blockSignals(True)
        self.list.clear()
        self._device_map = {dev.serial: dev for dev in devices}
        target_row = -1
        for index, dev in enumerate(devices):
            meta = dev.serial if dev.online else f"{dev.serial} · {dev.state}"
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dev.serial)
            item.setSizeHint(QSize(0, 48))
            self.list.addItem(item)
            self.list.setItemWidget(
                item,
                DeviceRow(dev.display_name, meta, dev.online, dev.wireless, dev.state_kind),
            )
            if dev.serial == selected_serial:
                target_row = index
        self.list.blockSignals(False)
        self.stack.setCurrentWidget(self.list if devices else self.empty)
        if target_row >= 0:
            self.list.setCurrentRow(target_row)
        elif self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.info.setText("尚未发现设备")

        usb_present = any(not dev.wireless for dev in devices)
        self.btn_usb_mirror.setEnabled(usb_present)
        self.btn_usb_mirror.setToolTip(
            "选中 USB 设备并立即以整屏模式投屏（⌘U）" if usb_present
            else "当前没有 USB 设备，请先用数据线连接手机"
        )
        problem = next((dev.problem for dev in devices if dev.problem), "")
        self.set_hint(problem, "warn")
        current = self.list.currentItem()
        if current is not None:
            self.device_selected.emit(current.data(Qt.UserRole))

    def set_hint(self, text: str, level: str = "warn") -> None:
        self.hint.setVisible(bool(text))
        if not text:
            return
        p = style.P()
        fg = {"warn": p.warn, "error": p.danger, "ok": p.ok}.get(level, p.warn)
        self.hint.setText(text)
        self.hint.setStyleSheet(
            f"font-size:11px; color:{fg}; background:{p.glass_soft};"
            "border-radius:7px; padding:6px 8px;"
        )

    def set_auto_mirror(self, enabled: bool) -> None:
        self.auto_mirror.blockSignals(True)
        self.auto_mirror.setChecked(enabled)
        self.auto_mirror.blockSignals(False)

    def set_info(self, html: str) -> None:
        self.info.setText(html)

    def current_serial(self) -> str:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def current_device(self):
        return self._device_map.get(self.current_serial())

    def select_serial(self, serial: str) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == serial:
                self.list.setCurrentRow(row)
                return True
        return False

    def usb_devices(self) -> list:
        return [d for d in self._device_map.values() if not d.wireless and d.online]


class AppPanel(Card):
    """应用舞台：Launchpad 网格 / 紧凑列表 + 空状态。"""
    reload_clicked = Signal()
    info_refresh_clicked = Signal()
    launch_requested = Signal(str)
    alias_requested = Signal(str)
    dock_toggled = Signal(str)
    recategory_requested = Signal(str, str)
    category_changed = Signal(str)
    view_changed = Signal(str)
    group_changed = Signal(bool)
    more_requested = Signal(QPoint)

    def __init__(self):
        super().__init__("应用")
        self.set_head_visible(False)
        self._packages: list[tuple[str, str]] = []
        self._system: set[str] = set()
        self.aliases: dict[str, str] = {}
        self._appinfo: dict[str, AppInfo] = {}
        self._overrides: dict[str, str] = {}
        self._dock: list[str] = []
        self._filter = "all"
        self._category = "all"
        self._view = "desktop"
        self._group_by = True
        self._keyword = ""
        self._all: list[AppData] = []
        self._running: set[str] = set()
        self._count_text = "—"
        self._progress_text = ""

        self.launchpad = Launchpad()
        self.launchpad.launch_requested.connect(self.launch_requested)
        self.launchpad.alias_requested.connect(self.alias_requested)
        self.launchpad.copy_requested.connect(lambda p: None)
        self.launchpad.dock_toggled.connect(self.dock_toggled)
        self.launchpad.recategory_requested.connect(self.recategory_requested)
        self.launchpad.category_changed.connect(self._on_category)
        self.launchpad.more_requested.connect(self.more_requested)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.delegate = AppDelegate(self.list)
        self.list.setItemDelegate(self.delegate)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

        self.empty = QLabel("连接设备后，这里会列出所有\n带桌面入口、可以投屏的应用")
        self.empty.setObjectName("EmptyStage")
        self.empty.setAlignment(Qt.AlignCenter)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.launchpad)
        self.stack.addWidget(self.list)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.launchpad)
        self.body.addWidget(self.stack, 1)

    # ---------- 状态接口 ----------
    def set_dock(self, packages: list[str]) -> None:
        self._dock = list(packages)

    def set_overrides(self, overrides: dict[str, str]) -> None:
        self._overrides = dict(overrides)
        self._apply_filter()

    def set_appinfo(self, mapping: dict[str, AppInfo]) -> None:
        self._appinfo = dict(mapping)
        self._apply_filter()

    def merge_appinfo(self, mapping: dict[str, AppInfo]) -> None:
        self._appinfo.update(mapping)
        clear_pixmap_cache()
        self._apply_filter()

    def refresh(self) -> None:
        self._apply_filter()

    def set_progress(self, text: str) -> None:
        self._progress_text = text
        self.launchpad.footer.setText(text or self.footer_text())

    def set_count(self, text: str) -> None:
        self._count_text = text
        self.launchpad.set_count(len(self._all))

    def footer_text(self) -> str:
        return self.launchpad.dots()

    def set_device_label(self, text: str) -> None:
        self.launchpad.set_device_label(text)

    def set_category(self, key: str) -> None:
        self._category = key
        self.launchpad.set_category(key)

    def set_view(self, key: str) -> None:
        self._view = key
        self._apply_filter()

    def set_group_by(self, value: bool) -> None:
        self._group_by = value
        self._apply_filter()

    def set_columns(self, value: int) -> None:
        self.launchpad.set_columns(value)

    def set_search(self, text: str) -> None:
        self._keyword = text.strip().lower()
        self._apply_filter()

    def set_filter(self, key: str) -> None:
        self._filter = key
        self._apply_filter()

    def set_running(self, packages: set[str]) -> None:
        self._running = set(packages)
        self.launchpad.set_running(self._running)

    def _on_category(self, key: str) -> None:
        self._category = key
        self.category_changed.emit(key)
        self._apply_filter()

    # ---------- 数据与筛选 ----------
    def set_data(self, packages: list[tuple[str, str]], system: set[str],
                 aliases: dict[str, str]) -> None:
        self._packages = packages
        self._system = system
        self.aliases = aliases
        self.delegate.system = system
        self.delegate.aliases = aliases
        self._apply_filter()

    def _build_all(self) -> None:
        self._all = []
        for pkg, _activity in self._packages:
            info = self._appinfo.get(pkg)
            if pkg in self.aliases:
                name = self.aliases[pkg]
            elif info and info.label:
                name = info.label
            else:
                name = display_name(pkg, {})
            self._all.append(AppData(
                package=pkg, name=name,
                icon=info.icon if info else "",
                category=categorize(pkg, pkg in self._system, self._overrides),
                system=pkg in self._system,
            ))

    def _apply_filter(self) -> None:
        self._build_all()
        visible: list[AppData] = []
        for app in self._all:
            if self._filter == "third" and app.system:
                continue
            if self._filter == "system" and not app.system:
                continue
            if self._category != "all" and app.category != self._category:
                continue
            if self._keyword and self._keyword not in app.package.lower() \
                    and self._keyword not in app.name.lower():
                continue
            visible.append(app)

        self.set_count(f"{len(visible)} / {len(self._all)} 个应用" if self._all else "—")
        if self._view == "desktop":
            self.launchpad.set_data(visible, self._category, self._group_by, self._dock)
            self.launchpad.set_running(self._running)
            if not self._progress_text:
                self.launchpad.footer.setText(self.footer_text())
            self.stack.setCurrentWidget(self.launchpad)
        elif not visible:
            self.empty.setText("连接设备后，这里会列出所有\n带桌面入口、可以投屏的应用"
                               if not self._all else "没有匹配的应用")
            self.stack.setCurrentWidget(self.empty)
        else:
            self._fill_list(visible)
            self.stack.setCurrentWidget(self.list)

    def _fill_list(self, apps: list[AppData]) -> None:
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        for app in apps:
            item = AppItem(app.package, app.name)
            item.setIcon(QIcon(app_pixmap(app, 26)))
            item.setSizeHint(QSize(0, 46))
            self.list.addItem(item)
        self.list.setUpdatesEnabled(True)

    def _on_double_click(self, item: AppItem) -> None:
        if isinstance(item, AppItem):
            self.launch_requested.emit(item.package)

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not isinstance(item, AppItem):
            return
        menu = QMenu(self)
        act_launch = menu.addAction("在新窗口投屏")
        act_copy = menu.addAction("复制包名")
        act_alias = menu.addAction("设置显示名称…")
        cat_menu = menu.addMenu("归类到…")
        cat_actions = {cat_menu.addAction(text): key for key, text, _ in CATEGORIES}
        act_reset = menu.addAction("恢复自动分类")
        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen == act_launch:
            self.launch_requested.emit(item.package)
        elif chosen == act_copy:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(item.package)
        elif chosen == act_alias:
            self.alias_requested.emit(item.package)
        elif chosen in cat_actions:
            self.recategory_requested.emit(item.package, cat_actions[chosen])
        elif chosen == act_reset:
            self.recategory_requested.emit(item.package, "")


class SettingsPanel(QWidget):
    """投屏参数表单（供设置对话框使用，不再常驻主界面）。"""
    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(2, 2, 8, 2)
        self.content_layout.setSpacing(10)
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        self._build_mode()
        self._build_display()
        self._build_audio()
        self._build_window()
        self._build_behavior()
        self._build_virtual_display()
        self.content_layout.addStretch(1)

    def _touch(self, *_) -> None:
        self.changed.emit()

    def _group(self, title: str) -> QVBoxLayout:
        self.content_layout.addSpacing(2)
        label = QLabel(title)
        label.setObjectName("GroupTitle")
        self.content_layout.addWidget(label)
        lay = QVBoxLayout()
        lay.setSpacing(7)
        self.content_layout.addLayout(lay)
        return lay

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _line_row(self, label_text: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = self._label(label_text)
        label.setFixedWidth(72)
        row.addWidget(label)
        row.addWidget(widget, 1)
        return row

    def _combo(self, options: list[str], values: list[str] | None = None) -> QComboBox:
        combo = QComboBox()
        for index, text in enumerate(options):
            combo.addItem(text, values[index] if values else text)
        combo.currentIndexChanged.connect(self._touch)
        return combo

    def _check(self, text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.stateChanged.connect(self._touch)
        return box

    def _build_mode(self) -> None:
        lay = self._group("投屏模式")
        self.mode = self._combo(["整屏投屏", "单应用（虚拟显示）"], ["screen", "app"])
        lay.addLayout(self._line_row("模式", self.mode))

    def _build_display(self) -> None:
        lay = self._group("画面")
        self.max_size = QSlider(Qt.Horizontal)
        self.max_size.setRange(0, 2560)
        self.max_size.setSingleStep(120)
        self.max_size_value = QLabel("原始")
        self.max_size_value.setFixedWidth(52)
        self.max_size_value.setObjectName("Hint")
        self.max_size.valueChanged.connect(self._on_size)
        row = self._line_row("分辨率上限", self.max_size)
        row.addWidget(self.max_size_value)
        lay.addLayout(row)
        self.bit_rate = self._combo(["4 Mbps", "8 Mbps", "16 Mbps", "24 Mbps"],
                                    ["4M", "8M", "16M", "24M"])
        self.bit_rate.setCurrentIndex(1)
        lay.addLayout(self._line_row("码率", self.bit_rate))
        self.max_fps = self._combo(["不限", "30 fps", "60 fps", "90 fps"],
                                   ["0", "30", "60", "90"])
        lay.addLayout(self._line_row("帧率", self.max_fps))
        self.codec = self._combo(["H.264", "H.265", "AV1"], ["h264", "h265", "av1"])
        lay.addLayout(self._line_row("编码", self.codec))

    def _build_audio(self) -> None:
        lay = self._group("声音")
        self.audio = self._check("转发手机音频到 Mac")
        self.audio.setChecked(True)
        lay.addWidget(self.audio)
        self.audio_bit_rate = self._combo(["64 Kbps", "128 Kbps", "192 Kbps"],
                                          ["64K", "128K", "192K"])
        self.audio_bit_rate.setCurrentIndex(1)
        lay.addLayout(self._line_row("音频码率", self.audio_bit_rate))
        self.audio_dup = self._check("同时保留手机外放（Android 13+）")
        lay.addWidget(self.audio_dup)

    def _build_window(self) -> None:
        lay = self._group("窗口")
        row = QHBoxLayout()
        row.setSpacing(14)
        self.borderless = self._check("无边框")
        self.on_top = self._check("置顶")
        self.fullscreen = self._check("全屏")
        for box in (self.borderless, self.on_top, self.fullscreen):
            row.addWidget(box)
        row.addStretch(1)
        lay.addLayout(row)
        self.window_title = QLineEdit()
        self.window_title.setPlaceholderText("留空则显示设备名")
        self.window_title.textChanged.connect(self._touch)
        lay.addLayout(self._line_row("标题", self.window_title))

    def _build_behavior(self) -> None:
        lay = self._group("行为")
        self.turn_off = self._check("投屏时关闭手机屏幕")
        self.stay_awake = self._check("保持设备唤醒")
        self.stay_awake.setChecked(True)
        self.show_touches = self._check("显示触摸轨迹")
        self.no_control = self._check("只观看，不控制设备")
        self.power_off = self._check("关闭窗口时设备关机")
        for box in (self.turn_off, self.stay_awake, self.show_touches,
                    self.no_control, self.power_off):
            lay.addWidget(box)
        self.keyboard = self._combo(["默认", "UHID", "AOA", "关闭键盘"],
                                    ["default", "uhid", "aoa", "disabled"])
        lay.addLayout(self._line_row("键盘", self.keyboard))
        self.mouse = self._combo(["SDK", "UHID", "AOA", "关闭鼠标"],
                                 ["sdk", "uhid", "aoa", "disabled"])
        lay.addLayout(self._line_row("鼠标", self.mouse))
        self.record = self._check("录制为 MP4")
        lay.addWidget(self.record)
        self.record_path = QLineEdit(str(HOME / "Movies/scrcpy-record.mp4"))
        self.record_path.textChanged.connect(self._touch)
        lay.addLayout(self._line_row("保存到", self.record_path))

    def _build_virtual_display(self) -> None:
        lay = self._group("虚拟显示（仅单应用模式）")
        self.display_size = QLineEdit()
        self.display_size.setPlaceholderText("例如 1080x1920，留空沿用主屏")
        self.display_size.textChanged.connect(self._touch)
        lay.addLayout(self._line_row("尺寸", self.display_size))
        self.display_dpi = QSpinBox()
        self.display_dpi.setRange(0, 640)
        self.display_dpi.setSpecialValueText("默认")
        self.display_dpi.valueChanged.connect(self._touch)
        lay.addLayout(self._line_row("DPI", self.display_dpi))

    def _on_size(self, value: int) -> None:
        self.max_size_value.setText("原始" if value == 0 else str(value))
        self.changed.emit()

    def config(self) -> MirrorConfig:
        return MirrorConfig(
            mode=self.mode.currentData(),
            max_size=self.max_size.value(),
            video_bit_rate=self.bit_rate.currentData(),
            max_fps=int(self.max_fps.currentData()),
            video_codec=self.codec.currentData(),
            audio=self.audio.isChecked(),
            audio_bit_rate=self.audio_bit_rate.currentData(),
            audio_dup=self.audio_dup.isChecked(),
            borderless=self.borderless.isChecked(),
            always_on_top=self.on_top.isChecked(),
            fullscreen=self.fullscreen.isChecked(),
            window_title=self.window_title.text(),
            turn_screen_off=self.turn_off.isChecked(),
            stay_awake=self.stay_awake.isChecked(),
            show_touches=self.show_touches.isChecked(),
            keyboard=self.keyboard.currentData(),
            mouse=self.mouse.currentData(),
            no_control=self.no_control.isChecked(),
            power_off_on_close=self.power_off.isChecked(),
            record=self.record.isChecked(),
            record_path=self.record_path.text(),
            new_display_size=self.display_size.text(),
            new_display_dpi=self.display_dpi.value(),
        )

    def set_config(self, cfg: MirrorConfig) -> None:
        widgets = [self.mode, self.bit_rate, self.max_fps, self.codec,
                   self.audio_bit_rate, self.keyboard, self.mouse]
        for widget in widgets:
            widget.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg.mode)))
        self.bit_rate.setCurrentIndex(max(0, self.bit_rate.findData(cfg.video_bit_rate)))
        self.max_fps.setCurrentIndex(max(0, self.max_fps.findData(str(cfg.max_fps))))
        self.codec.setCurrentIndex(max(0, self.codec.findData(cfg.video_codec)))
        self.audio_bit_rate.setCurrentIndex(
            max(0, self.audio_bit_rate.findData(cfg.audio_bit_rate))
        )
        self.keyboard.setCurrentIndex(max(0, self.keyboard.findData(cfg.keyboard)))
        self.mouse.setCurrentIndex(max(0, self.mouse.findData(cfg.mouse)))
        for widget in widgets:
            widget.blockSignals(False)
        self.max_size.setValue(cfg.max_size)
        self.audio.setChecked(cfg.audio)
        self.audio_dup.setChecked(cfg.audio_dup)
        self.borderless.setChecked(cfg.borderless)
        self.on_top.setChecked(cfg.always_on_top)
        self.fullscreen.setChecked(cfg.fullscreen)
        self.window_title.setText(cfg.window_title)
        self.turn_off.setChecked(cfg.turn_screen_off)
        self.stay_awake.setChecked(cfg.stay_awake)
        self.show_touches.setChecked(cfg.show_touches)
        self.no_control.setChecked(cfg.no_control)
        self.power_off.setChecked(cfg.power_off_on_close)
        self.record.setChecked(cfg.record)
        self.record_path.setText(cfg.record_path)
        self.display_size.setText(cfg.new_display_size)
        self.display_dpi.setValue(cfg.new_display_dpi)


class ConsolePanel(Card):
    def __init__(self):
        super().__init__("运行日志")
        self.output = QPlainTextEdit()
        self.output.setObjectName("Console")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setFixedHeight(104)
        self.output.setVisible(False)
        self.body.addWidget(self.output)

        self.toggle_btn = QPushButton("展开")
        self.toggle_btn.setFixedHeight(24)
        self.toggle_btn.clicked.connect(self._toggle)
        self.head_extra.addWidget(self.toggle_btn)
        clear = QPushButton("清空")
        clear.setFixedHeight(24)
        clear.clicked.connect(self.output.clear)
        self.head_extra.addWidget(clear)
        self.body.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def set_expanded(self, value: bool) -> None:
        self.output.setVisible(value)
        self.toggle_btn.setText("收起" if value else "展开")

    def _toggle(self) -> None:
        self.set_expanded(not self.output.isVisible())

    def log(self, text: str) -> None:
        if not text:
            return
        for line in text.rstrip().splitlines():
            self.output.appendPlainText(line)
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())
