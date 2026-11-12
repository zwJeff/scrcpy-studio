"""macOS Launchpad 风格的应用舞台：大图标网格 + 分类胶囊 + 分组标题。"""
from __future__ import annotations

import math
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core.categories import CATEGORIES, CATEGORY_ORDER, color_of, label_of

from . import style
from .desktop import AppData

_ICON = 84
_CELL_W = 128
_CELL_H = 118
_PIX_CACHE: dict[tuple[str, int], QPixmap] = {}


def clear_pixmap_cache() -> None:
    _PIX_CACHE.clear()


def _rounded(src: QPixmap, size: int) -> QPixmap:
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.225, size * 0.225)
    painter.setClipPath(path)
    painter.drawPixmap(int((size - scaled.width()) / 2),
                       int((size - scaled.height()) / 2), scaled)
    painter.end()
    return out


def app_pixmap(app: AppData, size: int = _ICON) -> QPixmap:
    key = (f"{app.icon}|{app.name}|{app.category}", size)
    if key in _PIX_CACHE:
        return _PIX_CACHE[key]
    pix: QPixmap | None = None
    if app.icon:
        raw = QPixmap(app.icon)
        if not raw.isNull():
            pix = _rounded(raw, size)
    if pix is None:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        grad = QLinearGradient(0, 0, size, size)
        base = QColor(color_of(app.category))
        grad.setColorAt(0, base.lighter(116))
        grad.setColorAt(1, base.darker(120))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, size, size),
                                size * 0.225, size * 0.225)
        font = QFont("PingFang SC")
        font.setPixelSize(int(size * 0.42))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#FFFFFF")))
        painter.drawText(pix.rect(), Qt.AlignCenter, (app.name or "?").strip()[:1].upper())
        painter.end()
    _PIX_CACHE[key] = pix
    return pix


class LaunchpadIcon(QFrame):
    launch_requested = Signal(str)
    context_requested = Signal(str, QPoint)
    focus_requested = Signal(str)

    def __init__(self, app: AppData, running: bool = False):
        super().__init__()
        self.app = app
        self.setObjectName("LaunchpadIcon")
        self.setFixedSize(_CELL_W, _CELL_H)
        self.setMouseTracking(True)
        self._hover = False
        self._chosen = False
        self._running = running

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 2)
        lay.setSpacing(7)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(_ICON, _ICON)
        self.icon_label.setPixmap(app_pixmap(app, _ICON))
        self.icon_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon_label, 0, Qt.AlignHCenter)

        self.name_label = QLabel()
        self.name_label.setObjectName("IconName")
        self.name_label.setAlignment(Qt.AlignHCenter)
        self.name_label.setFixedWidth(_CELL_W - 6)
        metrics = self.name_label.fontMetrics()
        self.name_label.setText(metrics.elidedText(app.name, Qt.ElideRight, _CELL_W - 12))
        lay.addWidget(self.name_label, 0, Qt.AlignHCenter)
        lay.addStretch(1)

        self.setToolTip(f"{app.name}\n{app.package}\n{label_of(app.category)}\n双击投屏")

    def set_chosen(self, value: bool) -> None:
        self._chosen = value
        self.update()

    def set_running(self, value: bool) -> None:
        self._running = value
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = style.P()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._hover or self._chosen:
            fill = QColor(p.accent)
            fill.setAlpha(28 if self._hover else 40)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(QColor(p.border)))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 14, 14)
        if self._running:
            dot = QColor(p.ok)
            painter.setBrush(QBrush(dot))
            painter.setPen(QPen(QColor(p.glass_strong)))
            x = self.width() / 2 + _ICON / 2 - 5
            painter.drawEllipse(QRectF(x - 5, 8, 11, 11))
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.focus_requested.emit(self.app.package)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.launch_requested.emit(self.app.package)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.context_requested.emit(self.app.package, event.globalPos())


class Launchpad(QWidget):
    launch_requested = Signal(str)
    alias_requested = Signal(str)
    copy_requested = Signal(str)
    dock_toggled = Signal(str)
    recategory_requested = Signal(str, str)
    category_changed = Signal(str)
    more_requested = Signal(QPoint)
    selection_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Launchpad")
        self._apps: list[AppData] = []
        self._icons: list[LaunchpadIcon] = []
        self._category = "all"
        self._group_by = True
        self._dock: list[str] = []
        self._running: set[str] = set()
        self._cols = 7
        self._forced_cols = 0
        self._selected = ""
        self._device = ""
        self._count = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 16, 22, 12)
        outer.setSpacing(10)

        # 顶部标题栏
        head = QHBoxLayout()
        head.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("应用程序")
        self.title.setObjectName("LaunchpadTitle")
        self.subtitle = QLabel("连接设备后显示可投屏的应用")
        self.subtitle.setObjectName("LaunchpadSub")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch(1)
        self.more = QPushButton("⋯")
        self.more.setObjectName("Round")
        self.more.setToolTip("更多操作")
        self.more.clicked.connect(
            lambda: self.more_requested.emit(
                self.more.mapToGlobal(self.more.rect().bottomLeft())
            )
        )
        head.addWidget(self.more, 0, Qt.AlignTop)
        outer.addLayout(head)

        # 分类胶囊（单行可滚动）
        self.cat_scroll = QScrollArea()
        self.cat_scroll.setFixedHeight(38)
        self.cat_scroll.setWidgetResizable(True)
        self.cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cat_widget = QWidget()
        self.cat_lay = QHBoxLayout(cat_widget)
        self.cat_lay.setContentsMargins(1, 2, 1, 2)
        self.cat_lay.setSpacing(7)
        self._cat_buttons: dict[str, QPushButton] = {}
        for key in ["all"] + CATEGORY_ORDER:
            btn = QPushButton("全部" if key == "all" else label_of(key))
            btn.setObjectName("CategoryPill")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda _=False, k=key: self._set_category(k))
            self._cat_buttons[key] = btn
            self.cat_lay.addWidget(btn)
        self.cat_lay.addStretch(1)
        self.cat_scroll.setWidget(cat_widget)
        outer.addWidget(self.cat_scroll)

        divider = QFrame()
        divider.setObjectName("GlassDivider")
        divider.setFixedHeight(1)
        outer.addWidget(divider)

        # 图标网格
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(4, 12, 4, 14)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(6)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        self.footer = QLabel("双击图标 → 在独立虚拟显示中单独投屏")
        self.footer.setObjectName("PageDots")
        self.footer.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.footer)

    # ---------- 对外接口 ----------
    def set_device_label(self, text: str) -> None:
        self._device = text
        self._update_subtitle()

    def set_count(self, value: int) -> None:
        self._count = value
        self._update_subtitle()

    def _update_subtitle(self) -> None:
        parts = [p for p in (self._device, f"{self._count} 个应用" if self._count else "") if p]
        self.subtitle.setText(
            " · ".join(parts) + " · 双击图标投屏" if parts
            else "连接设备后显示可投屏的应用"
        )

    def dots(self) -> str:
        pages = max(1, math.ceil(len(self._apps) / max(1, self._cols * 3)))
        return "   ".join("●" if i == 0 else "○" for i in range(min(pages, 6)))

    def set_columns(self, value: int) -> None:
        self._forced_cols = max(0, min(12, int(value)))
        self._recalc_cols()
        self._rebuild()

    def set_data(self, apps: list[AppData], category: str = "all",
                 group_by: bool = True, dock: list[str] | None = None) -> None:
        self._apps = list(apps)
        self._category = category
        self._group_by = group_by
        self._dock = list(dock or [])
        self._recalc_cols()
        self._rebuild()

    def set_running(self, packages: set[str]) -> None:
        self._running = set(packages)
        for icon in self._icons:
            icon.set_running(icon.app.package in self._running)

    def set_category(self, key: str) -> None:
        self._set_category(key)

    def _recalc_cols(self) -> bool:
        if self._forced_cols:
            columns = self._forced_cols
        else:
            # 用舞台自身宽度估算；viewport 在构造阶段宽度尚未确定
            available = max(360, self.width() - 60)
            columns = max(4, min(10, available // _CELL_W))
        if columns != self._cols:
            self._cols = columns
            return True
        return False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._recalc_cols():
            self._rebuild()

    def _set_category(self, key: str) -> None:
        self._category = key
        for k, btn in self._cat_buttons.items():
            btn.setChecked(k == key)
        self.category_changed.emit(key)
        self._rebuild()

    # ---------- 网格构建 ----------
    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._icons = []

    def _add_icon(self, app: AppData, row: int, col: int) -> None:
        icon = LaunchpadIcon(app, app.package in self._running)
        icon.launch_requested.connect(self.launch_requested)
        icon.context_requested.connect(self._context_menu)
        icon.focus_requested.connect(self._select)
        self.grid.addWidget(icon, row, col, Qt.AlignCenter)
        self._icons.append(icon)
        icon.set_chosen(app.package == self._selected)

    def _separator(self, row: int) -> None:
        line = QFrame()
        line.setObjectName("GlassDivider")
        line.setFixedHeight(1)
        self.grid.addWidget(line, row, 0, 1, self._cols)
        self.grid.setRowMinimumHeight(row, 6)

    def _rebuild(self) -> None:
        self._clear_grid()
        for col in range(self._cols):
            self.grid.setColumnStretch(col, 1)

        if not self._apps:
            empty = QLabel("连接设备后，这里会显示手机上\n所有带桌面入口、可以投屏的应用")
            empty.setObjectName("EmptyStage")
            empty.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(empty, 0, 0, 3, self._cols)
            self.footer.setText("等待设备连接")
            return

        if self._group_by and self._category == "all":
            buckets: dict[str, list[AppData]] = {}
            for app in self._apps:
                buckets.setdefault(app.category, []).append(app)
            row = 0
            total_rows = 0
            for key in CATEGORY_ORDER:
                group = buckets.get(key)
                if not group:
                    continue
                header = QLabel(f"{label_of(key)}   {len(group)}")
                header.setObjectName("SectionLabel")
                self.grid.addWidget(header, row, 0, 1, self._cols)
                row += 1
                for index, app in enumerate(group):
                    self._add_icon(app, row + index // self._cols, index % self._cols)
                rows = (len(group) + self._cols - 1) // self._cols
                row += rows
                total_rows += rows
                self._separator(row)
                row += 1
        else:
            for index, app in enumerate(self._apps):
                self._add_icon(app, index // self._cols, index % self._cols)

        self.footer.setText(self.dots())

    def _select(self, package: str) -> None:
        self._selected = package
        for icon in self._icons:
            icon.set_chosen(icon.app.package == package)
        self.selection_changed.emit(package)

    # ---------- 右键菜单 ----------
    def _context_menu(self, package: str, global_pos: QPoint) -> None:
        menu = QMenu(self)
        act_launch = menu.addAction("在新窗口投屏")
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
