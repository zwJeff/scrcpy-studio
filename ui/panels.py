"""左侧设备栏、中间应用栏、右侧参数栏与控制台。"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QScrollArea, QSlider,
    QSpinBox, QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from core.aliases import display_name
from core.apkinfo import AppInfo
from core.categories import CATEGORIES, CATEGORY_ORDER, categorize, label_of
from core.config import MirrorConfig
from core.paths import HOME

from .desktop import AppData, PhoneDesktop, clear_pixmap_cache, icon_for
from .style import ACCENT, ACCENT_DARK, ACCENT_SOFT, BORDER, CARD_ALT, TEXT, TEXT2, TEXT3

AVATAR_COLORS = ["#7EA6F0", "#8FCBA8", "#E8B173", "#C9A0DC", "#7FC6C6", "#E39BA0", "#A9B5C8"]


def _hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{BORDER};")
    return line


class Card(QWidget):
    """统一的白底圆角容器。"""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.head_extra = head
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body, 1)


class AppDelegate(QStyledItemDelegate):
    """应用列表的一行：头像 + 名称 + 包名 + 系统标记。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.aliases: dict[str, str] = {}
        self.system: set[str] = set()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(0, 46)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = option.rect.adjusted(4, 2, -4, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setBrush(QColor(ACCENT_SOFT))
        elif hover:
            painter.setBrush(QColor(CARD_ALT))
        else:
            painter.setBrush(QColor("transparent"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 8, 8)

        pkg = index.data(Qt.UserRole)
        name = index.data(Qt.DisplayRole)

        circle = QRect(rect.left() + 8, rect.center().y() - 11, 22, 22)
        decoration = index.data(Qt.DecorationRole)
        pix = None
        if isinstance(decoration, QIcon):
            pix = decoration.pixmap(22, 22)
        elif isinstance(decoration, QPixmap):
            pix = decoration.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if pix is not None and not pix.isNull():
            painter.drawPixmap(circle.left(), circle.top(), pix)
        else:
            color = AVATAR_COLORS[abs(hash(pkg)) % len(AVATAR_COLORS)]
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(circle)
            initial_font = QFont(painter.font())
            initial_font.setPixelSize(11)
            initial_font.setBold(True)
            painter.setFont(initial_font)
            painter.setPen(QPen(QColor("#FFFFFF")))
            painter.drawText(circle, Qt.AlignCenter, (name or pkg)[:1].upper())

        name_font = QFont(painter.font())
        name_font.setPixelSize(13)
        name_font.setBold(False)
        painter.setFont(name_font)
        painter.setPen(QPen(QColor(ACCENT_DARK if selected else TEXT)))
        name_rect = QRect(rect.left() + 40, rect.top() + 7, rect.width() - 90, 17)
        metrics = painter.fontMetrics()
        painter.drawText(
            name_rect, Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(name, Qt.ElideRight, name_rect.width()),
        )

        pkg_font = QFont(painter.font())
        pkg_font.setPixelSize(11)
        painter.setFont(pkg_font)
        painter.setPen(QPen(QColor(TEXT3)))
        pkg_rect = QRect(rect.left() + 40, rect.top() + 24, rect.width() - 90, 14)
        painter.drawText(
            pkg_rect, Qt.AlignLeft | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(pkg, Qt.ElideMiddle, pkg_rect.width()),
        )

        if pkg in self.system:
            badge_font = QFont(painter.font())
            badge_font.setPixelSize(10)
            painter.setFont(badge_font)
            badge_rect = QRect(rect.right() - 40, rect.center().y() - 8, 34, 16)
            painter.setBrush(QColor("#F1EFE8"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QPen(QColor(TEXT3)))
            painter.drawText(badge_rect, Qt.AlignCenter, "系统")

        painter.restore()


class AppItem(QListWidgetItem):
    def __init__(self, package: str, name: str):
        super().__init__(name)
        self.package = package
        self.setData(Qt.UserRole, package)
        self.setData(Qt.UserRole + 1, name)


class DeviceRow(QWidget):
    DOT_COLORS = {
        "ok": "#1D9E75",
        "unauthorized": "#E8A13C",
        "no_permissions": "#E8A13C",
        "offline": "#D4675E",
        "recovery": "#D4675E",
        "other": "#B4B2A9",
    }

    def __init__(self, title: str, meta: str, online: bool, wireless: bool,
                 state_kind: str = "ok"):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 10, 6)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{self.DOT_COLORS.get(state_kind, '#B4B2A9')};"
            " font-size:10px; background:transparent;"
        )
        top.addWidget(dot)
        name = QLabel(title)
        name.setStyleSheet(f"font-size:13px; font-weight:500; color:{TEXT}; background:transparent;")
        top.addWidget(name)
        top.addStretch(1)
        tag = QLabel("无线" if wireless else "USB")
        tag.setStyleSheet(
            f"font-size:10px; color:{TEXT3}; background:#F1EFE8;"
            "border-radius:4px; padding:1px 5px;"
        )
        top.addWidget(tag)
        lay.addLayout(top)

        sub = QLabel(meta)
        sub.setStyleSheet(f"font-size:11px; color:{TEXT3}; background:transparent;")
        sub.setContentsMargins(14, 0, 0, 0)
        lay.addWidget(sub)


class DevicePanel(Card):
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
        from .style import TEXT3 as T3  # 局部别名，避免循环引用歧义

        restart = QPushButton("重启 adb")
        restart.setFixedHeight(24)
        restart.setToolTip("设备显示 offline / 未授权时，用这个重置 USB 调试连接")
        restart.clicked.connect(self.restart_adb_clicked)
        self.head_extra.addWidget(restart)
        refresh = QPushButton("刷新")
        refresh.setFixedHeight(24)
        refresh.clicked.connect(self.refresh_clicked)
        self.head_extra.addWidget(refresh)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setUniformItemSizes(False)
        self.list.currentItemChanged.connect(self._on_change)
        self.empty = QLabel(
            "未发现设备\n\n用数据线连接手机并开启 USB 调试，\n"
            "或点下方「无线连接…」"
        )
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"font-size:12px; color:{TEXT3};")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.list)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)
        self.stack.setMinimumHeight(118)
        self.stack.setMaximumHeight(240)
        self.body.addWidget(self.stack)

        self.body.addWidget(_hline())

        primary_row = QHBoxLayout()
        primary_row.setSpacing(6)
        self.btn_usb_mirror = QPushButton("USB 投屏")
        self.btn_usb_mirror.setObjectName("Primary")
        self.btn_usb_mirror.setToolTip("选中 USB 设备并立即以整屏模式投屏（⌘U）")
        self.btn_usb_mirror.clicked.connect(self.usb_mirror_clicked)
        self.btn_wireless = QPushButton("无线连接…")
        self.btn_wireless.setObjectName("Ghost")
        self.btn_wireless.clicked.connect(self.wireless_clicked)
        primary_row.addWidget(self.btn_usb_mirror, 1)
        primary_row.addWidget(self.btn_wireless, 1)
        self.body.addLayout(primary_row)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_usb_setup = QPushButton("USB 连接…")
        self.btn_usb_setup.setToolTip("查看 USB 连接状态、授权引导与无线切换")
        self.btn_usb_setup.clicked.connect(self.usb_setup_clicked)
        self.btn_pair = QPushButton("配对")
        self.btn_pair.clicked.connect(self.pair_clicked)
        row.addWidget(self.btn_usb_setup, 1)
        row.addWidget(self.btn_pair, 1)
        self.body.addLayout(row)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        self.body.addWidget(self.hint)

        options = QHBoxLayout()
        options.setSpacing(6)
        self.auto_mirror = QCheckBox("插入 USB 自动投屏")
        self.auto_mirror.setToolTip("检测到新插入的 USB 设备且当前没有投屏时，自动开始整屏投屏")
        self.auto_mirror.stateChanged.connect(
            lambda state: self.auto_mirror_changed.emit(state != 0)
        )
        options.addWidget(self.auto_mirror, 1)
        self.body.addLayout(options)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_to_wireless = QPushButton("USB → 无线")
        self.btn_to_wireless.setToolTip("借当前 USB 连接切到 TCP/IP，之后可以拔掉数据线")
        self.btn_to_wireless.clicked.connect(self.to_wireless_clicked)
        self.btn_disconnect = QPushButton("断开当前设备")
        self.btn_disconnect.clicked.connect(self.disconnect_clicked)
        self.btn_disconnect.setEnabled(False)
        actions.addWidget(self.btn_to_wireless, 1)
        actions.addWidget(self.btn_disconnect, 1)
        self.body.addLayout(actions)

        self.info = QLabel("尚未发现设备")
        self.info.setWordWrap(True)
        self.info.setStyleSheet(f"font-size:11px; color:{T3};")
        self.body.addWidget(self.info)
        self.body.addStretch(1)

        self._device_map: dict[str, object] = {}

    def _on_change(self, current, _previous) -> None:
        if current is None:
            self.btn_disconnect.setEnabled(False)
            return
        serial = current.data(Qt.UserRole)
        dev = self._device_map.get(serial)
        wireless = bool(dev and getattr(dev, "wireless", False))
        self.btn_disconnect.setEnabled(wireless)
        self.btn_disconnect.setText("断开当前设备" if wireless else "USB 请拔线")
        self.btn_to_wireless.setEnabled(bool(dev and not wireless and dev.online))
        self.device_selected.emit(serial)

    def set_devices(self, devices, selected_serial: str = "") -> None:
        self.list.blockSignals(True)
        self.list.clear()
        self._device_map = {dev.serial: dev for dev in devices}
        target_row = -1
        for index, dev in enumerate(devices):
            meta = dev.serial if dev.online else f"{dev.serial} · {dev.state}"
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dev.serial)
            item.setSizeHint(QSize(0, 50))
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
            self.btn_disconnect.setEnabled(False)
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
        palette = {
            "warn": ("#FDF3E2", "#A2691C"),
            "error": ("#FBECEA", "#A8443C"),
            "ok": ("#E6F5EE", "#1D7D5E"),
        }
        bg, fg = palette.get(level, palette["warn"])
        self.hint.setText(text)
        self.hint.setStyleSheet(
            f"font-size:11px; color:{fg}; background:{bg};"
            "border-radius:6px; padding:6px 8px;"
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
        """选中指定设备；返回是否找到。"""
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == serial:
                self.list.setCurrentRow(row)
                return True
        return False

    def usb_devices(self) -> list:
        """当前在线的 USB 设备（按列表顺序）。"""
        return [
            dev for dev in self._device_map.values()
            if not dev.wireless and dev.online
        ]


class AppPanel(Card):
    reload_clicked = Signal()
    info_refresh_clicked = Signal()
    launch_requested = Signal(str)
    alias_requested = Signal(str)
    dock_toggled = Signal(str)
    recategory_requested = Signal(str, str)
    category_changed = Signal(str)
    view_changed = Signal(str)
    group_changed = Signal(bool)

    def __init__(self):
        super().__init__("应用")
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
        self._all: list[AppData] = []

        self.count = QLabel("—")
        self.count.setStyleSheet(f"font-size:11px; color:{TEXT3};")
        self.head_extra.addWidget(self.count)

        self.progress = QLabel("")
        self.progress.setObjectName("Hint")
        self.head_extra.addWidget(self.progress)

        self.view_combo = QComboBox()
        self.view_combo.addItem("手机桌面", "desktop")
        self.view_combo.addItem("紧凑列表", "list")
        self.view_combo.setFixedWidth(104)
        self.view_combo.currentIndexChanged.connect(self._on_view_combo)
        self.head_extra.addWidget(self.view_combo)

        btn_info = QPushButton("重载图标")
        btn_info.setFixedHeight(24)
        btn_info.setToolTip("重新从设备提取应用名称与图标")
        btn_info.clicked.connect(self.info_refresh_clicked)
        self.head_extra.addWidget(btn_info)

        reload_btn = QPushButton("重新读取")
        reload_btn.setFixedHeight(24)
        reload_btn.clicked.connect(self.reload_clicked)
        self.head_extra.addWidget(reload_btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索应用名或包名…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.body.addWidget(self.search)

        # 分类筛选：8 列 × 2 行，全部可见，无需横向滚动
        cat_grid = QGridLayout()
        cat_grid.setContentsMargins(0, 0, 0, 0)
        cat_grid.setSpacing(5)
        self._cat_buttons: dict[str, QPushButton] = {}
        for index, key in enumerate(["all"] + CATEGORY_ORDER):
            btn = QPushButton("全部" if key == "all" else label_of(key))
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _=False, k=key: self._set_category(k))
            self._cat_buttons[key] = btn
            cat_grid.addWidget(btn, index // 8, index % 8)
        for column in range(8):
            cat_grid.setColumnStretch(column, 1)
        self.body.addLayout(cat_grid)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_buttons: dict[str, QPushButton] = {}
        for key, label in (("all", "全部来源"), ("third", "第三方"), ("system", "系统")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._chip_buttons[key] = btn
            chips.addWidget(btn)
        self.group_box = QCheckBox("按类型分区")
        self.group_box.setChecked(True)
        self.group_box.stateChanged.connect(
            lambda: self._set_group(self.group_box.isChecked())
        )
        chips.addWidget(self.group_box)
        chips.addStretch(1)
        self.body.addLayout(chips)

        self.desktop = PhoneDesktop()
        self.desktop.setFixedWidth(340)
        self.desktop.setMinimumHeight(300)
        desktop_host = QWidget()
        host_lay = QHBoxLayout(desktop_host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        host_lay.addStretch(1)
        host_lay.addWidget(self.desktop, 0)   # 垂直填满，底部圆角不会被裁
        host_lay.addStretch(1)
        self.desktop_host = desktop_host
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
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"font-size:12px; color:{TEXT3};")

        self.stack = QStackedWidget()
        self.stack.addWidget(desktop_host)
        self.stack.addWidget(self.list)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)
        self.body.addWidget(self.stack, 1)

        hint = QLabel("双击图标 → 在独立虚拟显示中单独投屏；右键可复制包名、改名、固定到 Dock")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self.body.addWidget(hint)

        self.desktop.launch_requested.connect(lambda p: self.launch_requested.emit(p))
        self.desktop.alias_requested.connect(lambda p: self.alias_requested.emit(p))
        self.desktop.dock_toggled.connect(lambda p: self.dock_toggled.emit(p))
        self.desktop.recategory_requested.connect(
            lambda p, k: self.recategory_requested.emit(p, k)
        )
        self._update_chip_style()

    # ---------- 状态设置 ----------
    def set_dock(self, packages: list[str]) -> None:
        self._dock = list(packages)

    def set_overrides(self, overrides: dict[str, str]) -> None:
        self._overrides = dict(overrides)

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
        self.progress.setText(text)

    def set_device_label(self, text: str) -> None:
        self.desktop.set_device(text)

    def set_category(self, key: str) -> None:
        self._set_category(key)

    def set_view(self, key: str) -> None:
        self._view = key
        index = self.view_combo.findData(key)
        if index >= 0:
            self.view_combo.blockSignals(True)
            self.view_combo.setCurrentIndex(index)
            self.view_combo.blockSignals(False)
        self._apply_filter()

    def set_group_by(self, value: bool) -> None:
        self._group_by = value
        self.group_box.blockSignals(True)
        self.group_box.setChecked(value)
        self.group_box.blockSignals(False)

    # ---------- 筛选 ----------
    def _update_chip_style(self) -> None:
        for buttons in (self._cat_buttons, self._chip_buttons):
            for btn in buttons.values():
                if btn.isChecked():
                    btn.setStyleSheet(
                        f"QPushButton{{background:{ACCENT}; border:1px solid {ACCENT};"
                        f"color:#FFFFFF; border-radius:6px; padding:2px 10px; font-size:11px;}}"
                    )
                else:
                    btn.setStyleSheet(
                        f"QPushButton{{background:transparent; border:1px solid {BORDER};"
                        f"color:{TEXT2}; border-radius:6px; padding:2px 10px; font-size:11px;}}"
                    )

    def _set_filter(self, key: str) -> None:
        self._filter = key
        for k, btn in self._chip_buttons.items():
            btn.setChecked(k == key)
        self._update_chip_style()
        self._apply_filter()

    def _set_category(self, key: str) -> None:
        self._category = key
        for k, btn in self._cat_buttons.items():
            btn.setChecked(k == key)
        self._update_chip_style()
        self.category_changed.emit(key)
        self._apply_filter()

    def _on_view_combo(self) -> None:
        self._view = self.view_combo.currentData()
        self.view_changed.emit(self._view)
        self._apply_filter()

    def _set_group(self, value: bool) -> None:
        self._group_by = value
        self.group_changed.emit(value)
        self._apply_filter()

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
        for pkg, activity in self._packages:
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
        keyword = self.search.text().strip().lower()
        visible: list[AppData] = []
        for app in self._all:
            if self._filter == "third" and app.system:
                continue
            if self._filter == "system" and not app.system:
                continue
            if self._category != "all" and app.category != self._category:
                continue
            if keyword and keyword not in app.package.lower() and keyword not in app.name.lower():
                continue
            visible.append(app)

        total = len(self._all)
        self.count.setText(f"{len(visible)} / {total} 个应用" if total else "—")
        if self._view == "desktop":
            # 即使没有设备也让手机外框常驻，空数据时由桌面内部显示引导语
            self.desktop.set_data(visible, self._category, self._group_by, self._dock)
            self.stack.setCurrentWidget(self.desktop_host)
        elif not visible:
            self.empty.setText("连接设备后，这里会列出所有\n带桌面入口、可以投屏的应用"
                               if not total else "没有匹配的应用")
            self.stack.setCurrentWidget(self.empty)
        else:
            self._fill_list(visible)
            self.stack.setCurrentWidget(self.list)

    def _fill_list(self, apps: list[AppData]) -> None:
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        for app in apps:
            item = AppItem(app.package, app.name)
            item.setIcon(QIcon(icon_for(app, 22)))
            item.setSizeHint(QSize(0, 46))
            self.list.addItem(item)
        self.list.setUpdatesEnabled(True)

    def _on_double_click(self, item: AppItem) -> None:
        if isinstance(item, AppItem):
            self.launch_requested.emit(item.package)

    def _on_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        item = self.list.itemAt(pos)
        if not isinstance(item, AppItem):
            return
        menu = QMenu(self)
        act_launch = menu.addAction("在虚拟显示中投屏")
        act_copy = menu.addAction("复制包名")
        act_alias = menu.addAction("设置显示名称…")
        cat_menu = menu.addMenu("归类到…")
        cat_actions = {}
        for key, text, _color in CATEGORIES:
            cat_actions[cat_menu.addAction(text)] = key
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


class SettingsPanel(Card):
    start_clicked = Signal()
    stop_clicked = Signal()
    changed = Signal()

    def __init__(self):
        super().__init__("投屏参数")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(10)
        scroll.setWidget(content)
        self.body.addWidget(scroll, 1)

        self._build_mode()
        self._build_display()
        self._build_audio()
        self._build_window()
        self._build_behavior()
        self._build_virtual_display()
        self.content_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.btn_start = QPushButton("开始投屏")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.clicked.connect(self.start_clicked)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_clicked)
        footer.addWidget(self.btn_start, 1)
        footer.addWidget(self.btn_stop)
        self.body.addLayout(footer)

    def _touch(self, *_) -> None:
        self.changed.emit()

    # ---------- 构建工具 ----------
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
        label.setFixedWidth(62)
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

    # ---------- 各分组 ----------
    def _build_mode(self) -> None:
        lay = self._group("投屏模式")
        self.mode = self._combo(["整屏投屏", "单应用（虚拟显示）"], ["screen", "app"])
        lay.addLayout(self._line_row("模式", self.mode))

    def _build_display(self) -> None:
        lay = self._group("画面")
        self.max_size = QSlider(Qt.Horizontal)
        self.max_size.setRange(0, 2560)
        self.max_size.setSingleStep(120)
        self.max_size.setValue(0)
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
        for box in (self.turn_off, self.stay_awake, self.show_touches, self.no_control, self.power_off):
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

    # ---------- 读写 ----------
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
        widgets = [self.mode, self.bit_rate, self.max_fps, self.codec, self.audio_bit_rate,
                   self.keyboard, self.mouse]
        for widget in widgets:
            widget.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg.mode)))
        self.bit_rate.setCurrentIndex(max(0, self.bit_rate.findData(cfg.video_bit_rate)))
        self.max_fps.setCurrentIndex(max(0, self.max_fps.findData(str(cfg.max_fps))))
        self.codec.setCurrentIndex(max(0, self.codec.findData(cfg.video_codec)))
        self.audio_bit_rate.setCurrentIndex(max(0, self.audio_bit_rate.findData(cfg.audio_bit_rate)))
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

    def set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)


class ConsolePanel(Card):
    def __init__(self):
        super().__init__("运行日志")
        self.toggle_btn = QPushButton("收起")
        self.toggle_btn.setFixedHeight(24)
        self.head_extra.addWidget(self.toggle_btn)

        self.output = QPlainTextEdit()
        self.output.setObjectName("Console")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self.output.setFixedHeight(96)
        self.body.addWidget(self.output)

        clear = QPushButton("清空")
        clear.setFixedHeight(24)
        clear.clicked.connect(self.output.clear)
        self.head_extra.addWidget(clear)

        self.toggle_btn.clicked.connect(self._toggle)

    def _toggle(self) -> None:
        visible = self.output.isVisible()
        self.output.setVisible(not visible)
        self.toggle_btn.setText("展开" if visible else "收起")

    def log(self, text: str) -> None:
        if not text:
            return
        for line in text.rstrip().splitlines():
            self.output.appendPlainText(line)
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())
