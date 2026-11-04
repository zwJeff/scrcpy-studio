"""手机桌面风格的应用网格：外框 + 状态栏 + 图标网格 + 底部 Dock。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRectF, Qt, QTime, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from core.categories import CATEGORIES, CATEGORY_ORDER, color_of, label_of

_COLS = 4
_ICON_PX = 52
_PIX_CACHE: dict[tuple[str, int], QPixmap] = {}


@dataclass
class AppData:
    package: str
    name: str
    icon: str = ""
    category: str = "other"
    system: bool = False


# ---------- 图标处理 ----------

def rounded_pixmap(src: QPixmap, size: int, radius: int = 13) -> QPixmap:
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(int((size - scaled.width()) / 2),
                       int((size - scaled.height()) / 2), scaled)
    painter.end()
    return out


def placeholder(name: str, color: str, size: int = _ICON_PX) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, size, size)
    base = QColor(color)
    grad.setColorAt(0, base.lighter(118))
    grad.setColorAt(1, base.darker(118))
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), 13, 13)
    font = QFont("PingFang SC")
    font.setPixelSize(22)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(QColor("#FFFFFF")))
    painter.drawText(pix.rect(), Qt.AlignCenter, (name or "?").strip()[:1].upper())
    painter.end()
    return pix


def icon_for(app: AppData, size: int = _ICON_PX) -> QPixmap:
    key = (app.icon, size)
    if key in _PIX_CACHE:
        return _PIX_CACHE[key]
    pix: QPixmap | None = None
    if app.icon:
        raw = QPixmap(app.icon)
        if not raw.isNull():
            pix = rounded_pixmap(raw, size)
    if pix is None:
        pix = placeholder(app.name, color_of(app.category), size)
    _PIX_CACHE[key] = pix
    return pix


def clear_pixmap_cache() -> None:
    _PIX_CACHE.clear()


# ---------- 单个图标 ----------

class AppIcon(QFrame):
    launch_requested = Signal(str)
    context_requested = Signal(str, QPoint)
    focus_requested = Signal(str)

    def __init__(self, app: AppData, compact: bool = False):
        super().__init__()
        self.app = app
        self.compact = compact
        self._chosen = False
        self.setObjectName("AppIcon")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(64 if compact else 76)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 5, 2, 4)
        lay.setSpacing(3)
        size = 44 if compact else _ICON_PX

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(size, size)
        self.icon_label.setPixmap(icon_for(app, size))
        self.icon_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon_label, 0, Qt.AlignHCenter)

        self.name_label = QLabel(app.name)
        self.name_label.setObjectName("AppIconName")
        self.name_label.setAlignment(Qt.AlignHCenter)
        self.name_label.setFixedWidth(60 if compact else 72)
        metrics = self.name_label.fontMetrics()
        self.name_label.setText(metrics.elidedText(app.name, Qt.ElideRight,
                                                   60 if compact else 72))
        self.name_label.setToolTip(f"{app.name}\n{app.package}\n{label_of(app.category)}")
        lay.addWidget(self.name_label, 0, Qt.AlignHCenter)
        if compact:
            self.name_label.hide()
        self.setToolTip(f"{app.name}\n{app.package}")

    def set_chosen(self, value: bool) -> None:
        self._chosen = value
        self.repaint()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._chosen:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(255, 255, 255, 44))
        painter.setPen(QPen(QColor(255, 255, 255, 90)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.focus_requested.emit(self.app.package)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.launch_requested.emit(self.app.package)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.context_requested.emit(self.app.package, event.globalPos())


# ---------- 状态栏 ----------

class StatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(24)
        self._time = QTime.currentTime().toString("HH:mm")
        self._device = ""
        timer = QTimer(self)
        timer.setInterval(20_000)
        timer.timeout.connect(self._tick)
        timer.start()

    def _tick(self) -> None:
        self._time = QTime.currentTime().toString("HH:mm")
        self.update()

    def set_device(self, text: str) -> None:
        self._device = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        white = QColor(255, 255, 255, 225)
        font = QFont("Helvetica Neue")
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(white))
        painter.drawText(12, 0, 50, 24, Qt.AlignVCenter | Qt.AlignLeft, self._time)

        if self._device:
            sub = QFont("PingFang SC")
            sub.setPixelSize(10)
            painter.setFont(sub)
            painter.setPen(QPen(QColor(255, 255, 255, 160)))
            painter.drawText(64, 0, self.width() - 130, 24,
                             Qt.AlignVCenter | Qt.AlignLeft, self._device[:14])

        # 中间挖孔（摄像头）
        painter.setBrush(QColor(10, 11, 15, 190))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.width() / 2 - 4.5, 8, 9, 9)

        # 右侧信号 + 电池
        x = self.width() - 56
        painter.setBrush(QBrush(white))
        painter.setPen(Qt.NoPen)
        for i in range(4):
            h = 3 + i * 2.4
            painter.drawRoundedRect(QRectF(x + i * 5, 16 - h, 3, h), 1, 1)
        bx = x + 25
        painter.setPen(QPen(white, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(bx, 7, 20, 10), 2, 2)
        painter.setBrush(QBrush(white))
        painter.drawRoundedRect(QRectF(bx + 1.5, 8.5, 15, 7), 1, 1)
        painter.drawRoundedRect(QRectF(bx + 21, 10, 2, 4), 1, 1)
        painter.end()


# ---------- 桌面 ----------

class PhoneDesktop(QWidget):
    launch_requested = Signal(str)
    alias_requested = Signal(str)
    copy_requested = Signal(str)
    dock_toggled = Signal(str)
    recategory_requested = Signal(str, str)
    selection_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("PhoneFrame")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(360)
        self._apps: list[AppData] = []
        self._icons: list[AppIcon] = []
        self._dock: list[str] = []
        self._selected = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self.screen = QWidget()
        self.screen.setObjectName("PhoneScreen")
        self.screen.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self.screen)

        screen_lay = QVBoxLayout(self.screen)
        screen_lay.setContentsMargins(8, 6, 8, 8)
        screen_lay.setSpacing(4)

        self.status = StatusBar()
        screen_lay.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setObjectName("DesktopScroll")
        self.content = QWidget()
        self.content.setObjectName("DesktopContent")
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(2, 10, 2, 10)
        self.grid.setHorizontalSpacing(2)
        self.grid.setVerticalSpacing(8)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        for col in range(_COLS):
            self.grid.setColumnMinimumWidth(col, 76)
        self.scroll.setWidget(self.content)
        screen_lay.addWidget(self.scroll, 1)

        self.page_dots = QLabel("● ○ ○")
        self.page_dots.setObjectName("PageDots")
        self.page_dots.setAlignment(Qt.AlignCenter)
        screen_lay.addWidget(self.page_dots)

        self.dock = QFrame()
        self.dock.setObjectName("Dock")
        self.dock.setAttribute(Qt.WA_StyledBackground, True)
        self.dock_lay = QHBoxLayout(self.dock)
        self.dock_lay.setContentsMargins(6, 6, 6, 6)
        self.dock_lay.setSpacing(2)
        self.dock_lay.addStretch(1)
        screen_lay.addWidget(self.dock)

        self.setStyleSheet("""
            #PhoneFrame { background: #17181D; border: 1px solid #0B0C10;
                          border-radius: 34px; }
            #PhoneScreen { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 #26365E, stop:0.48 #40598C, stop:1 #6A4B79);
                           border-radius: 27px; }
            #DesktopScroll, #DesktopContent { background: transparent; border: none; }
            #AppIcon { background: transparent; border-radius: 12px; }
            #AppIconName { color: #FFFFFF; font-size: 11px; }
            #SectionLabel { color: rgba(255,255,255,0.82); font-size: 11px;
                            font-weight: 600; padding: 6px 4px 2px 4px; }
            #PageDots { color: rgba(255,255,255,0.75); font-size: 9px; }
            #Dock { background: rgba(255,255,255,0.14); border-radius: 20px; }
            #Dock #AppIcon { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 4px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.32);
                                          border-radius: 2px; min-height: 24px; }
        """)

    def set_device(self, text: str) -> None:
        self.status.set_device(text)

    def set_data(self, apps: list[AppData], category: str = "all",
                 group_by: bool = True, dock: list[str] | None = None) -> None:
        self._apps = apps
        self._dock = list(dock or [])
        self._rebuild(category, group_by)

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._icons = []

    def _add_icon(self, app: AppData, row: int, col: int, compact: bool = False) -> AppIcon:
        icon = AppIcon(app, compact)
        icon.launch_requested.connect(self.launch_requested)
        icon.context_requested.connect(self._context_menu)
        icon.focus_requested.connect(self._select)
        self.grid.addWidget(icon, row, col, Qt.AlignHCenter | Qt.AlignTop)
        self._icons.append(icon)
        return icon

    def _rebuild(self, category: str, group_by: bool) -> None:
        self._clear_grid()
        if not self._apps:
            empty = QLabel("连接设备后\n这里会显示手机上的应用")
            empty.setObjectName("SectionLabel")
            empty.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(empty, 0, 0, 1, _COLS)
        elif category != "all" or not group_by:
            for index, app in enumerate(self._apps):
                self._add_icon(app, index // _COLS, index % _COLS)
        else:
            buckets: dict[str, list[AppData]] = {}
            for app in self._apps:
                buckets.setdefault(app.category, []).append(app)
            row = 0
            for key in CATEGORY_ORDER:
                group = buckets.get(key)
                if not group:
                    continue
                header = QLabel(f"{label_of(key)}   {len(group)}")
                header.setObjectName("SectionLabel")
                self.grid.addWidget(header, row, 0, 1, _COLS)
                row += 1
                for index, app in enumerate(group):
                    self._add_icon(app, row + index // _COLS, index % _COLS)
                row += (len(group) + _COLS - 1) // _COLS + 1

        # Dock（每次重建，避免 stretch 累积）
        while self.dock_lay.count():
            item = self.dock_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        by_pkg = {app.package: app for app in self._apps}
        dock_apps = [by_pkg[p] for p in self._dock if p in by_pkg][:4]
        if not dock_apps:
            dock_apps = self._apps[:4]
        for index, app in enumerate(dock_apps):
            icon = AppIcon(app, compact=True)
            icon.launch_requested.connect(self.launch_requested)
            icon.context_requested.connect(self._context_menu)
            icon.focus_requested.connect(self._select)
            self.dock_lay.insertWidget(index, icon)
        self.dock_lay.addStretch(1)
        self.dock.setVisible(bool(dock_apps))
        self.page_dots.setText("● ○ ○" if len(self._apps) > 16 else "●")

    def _select(self, package: str) -> None:
        self._selected = package
        for icon in self._icons:
            icon.set_chosen(icon.app.package == package)
        self.selection_changed.emit(package)

    def _context_menu(self, package: str, global_pos: QPoint) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        act_launch = menu.addAction("在虚拟显示中投屏")
        menu.addSeparator()
        act_copy = menu.addAction("复制包名")
        act_alias = menu.addAction("设置显示名称…")
        pinned = package in self._dock
        act_dock = menu.addAction("从 Dock 移除" if pinned else "固定到 Dock")
        cat_menu = menu.addMenu("归类到…")
        cat_actions = {}
        for key, text, _color in CATEGORIES:
            cat_actions[cat_menu.addAction(text)] = key
        act_reset = menu.addAction("恢复自动分类")
        chosen = menu.exec(global_pos)
        if chosen == act_launch:
            self.launch_requested.emit(package)
        elif chosen == act_copy:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(package)
            self.copy_requested.emit(package)
        elif chosen == act_alias:
            self.alias_requested.emit(package)
        elif chosen == act_dock:
            self.dock_toggled.emit(package)
        elif chosen in cat_actions:
            self.recategory_requested.emit(package, cat_actions[chosen])
        elif chosen == act_reset:
            self.recategory_requested.emit(package, "")
