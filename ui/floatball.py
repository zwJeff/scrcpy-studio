"""悬浮球模式：总在最前的可拖拽悬浮球 + 跟随定位的半透明 Launchpad 面板。"""
from __future__ import annotations

import math

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core import paths
from core.categories import CATEGORIES, label_of

from . import nativewindow, style
from .desktop import AppData
from .launchpad import app_pixmap

BALL_SIZE = 58
PANEL_W = 830
PANEL_H = 620
GRID_COLS = 7
GRID_MIN_ROWS = 4
EDGE = 12
GAP = 14


def _ball_icon(size: int) -> QPixmap:
    if not paths.ICON_PNG.exists():
        pix = QPixmap(size, size)
        pix.fill(QColor(style.P().accent))
        return pix
    return QPixmap(str(paths.ICON_PNG)).scaled(
        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


class FloatBall(QWidget):
    """圆形玻璃悬浮球，可拖拽；短按视为点击。"""
    clicked = Signal()
    moved = Signal()
    hovered = Signal(bool)
    context_requested = Signal(QPoint)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(BALL_SIZE, BALL_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("单击展开应用 · 悬停看投屏窗口 · 拖动可移动 · 右键更多")
        self._hover = False
        self._count = 0
        self._press_pos: QPoint | None = None
        self._drag_offset: QPoint | None = None
        self._dragged = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(3, 3, self.width() - 6, self.height() - 6)

        # 外圈阴影 / 玻璃底
        p = style.P()
        base = QColor(10, 26, 46, 205) if style.is_dark() else QColor(255, 255, 255, 225)
        if self._hover:
            base = QColor(24, 58, 100, 230) if style.is_dark() else QColor(255, 255, 255, 246)
        path = QPainterPath()
        path.addEllipse(rect)
        painter.fillPath(path, base)
        painter.setPen(QColor(255, 255, 255, 110 if self._hover else 70))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))

        icon = _ball_icon(38)
        painter.drawPixmap(int((self.width() - icon.width()) / 2),
                           int((self.height() - icon.height()) / 2), icon)
        if self._count > 0:
            text = str(self._count) if self._count < 100 else "99+"
            size = 23 if len(text) < 3 else 28
            badge = QRectF(self.width() - size - 1, 1, size, size)
            painter.setBrush(QColor(226, 74, 74))
            painter.setPen(QColor(255, 255, 255, 210))
            painter.drawEllipse(badge)
            font = QFont("Helvetica Neue")
            font.setPixelSize(12 if len(text) < 3 else 10)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge, Qt.AlignCenter, text)
        painter.end()

    def set_count(self, value: int) -> None:
        value = max(0, int(value))
        if value != self._count:
            self._count = value
            self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        self.hovered.emit(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPos()
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            if self._press_pos and (event.globalPos() - self._press_pos).manhattanLength() > 5:
                self._dragged = True
            self.move(event.globalPos() - self._drag_offset)
            self.moved.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and not self._dragged:
            self.clicked.emit()
        self._press_pos = None
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.context_requested.emit(event.globalPos())


class FloatAppIcon(QWidget):
    """半透明面板里的单个应用图标。"""
    clicked = Signal(str)

    def __init__(self, app: AppData, cell_w: int, cell_h: int, icon_size: int):
        super().__init__()
        self.app = app
        self._hover = False
        self.setFixedSize(cell_w, cell_h)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setPixmap(app_pixmap(app, icon_size))
        lay.addWidget(self.icon_label, 0, Qt.AlignHCenter)

        self.name_label = QLabel()
        self.name_label.setFixedWidth(cell_w)
        self.name_label.setAlignment(Qt.AlignHCenter)
        metrics = self.name_label.fontMetrics()
        self.name_label.setText(metrics.elidedText(app.name, Qt.ElideRight, cell_w - 8))
        self.name_label.setStyleSheet(
            "font-size:12px; color:#F2F7FF; background:transparent;"
            if style.is_dark() else
            "font-size:12px; color:#1B2534; background:transparent;"
        )
        lay.addWidget(self.name_label, 0, Qt.AlignHCenter)
        lay.addStretch(1)
        self.setToolTip(f"{app.name}\n{app.package}\n单击在新窗口投屏")

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._hover:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(255, 255, 255, 34))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app.package)
        super().mousePressEvent(event)


class FloatPanel(QWidget):
    """参考 macOS Launchpad 的半透明弹出面板：7 列 × 至少 4 行。"""
    launch_requested = Signal(str)
    menu_requested = Signal(QPoint)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(PANEL_W, PANEL_H)
        self._apps: list[AppData] = []
        self._category = "all"
        self._device = ""
        self._icons: list[FloatAppIcon] = []
        self._dirty = False          # 面板隐藏时只记数据，展开时再构建网格

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 16, 22, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(_ball_icon(30))
        header.addWidget(mark)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title = QLabel("应用程序")
        self.title.setObjectName("FloatTitle")
        self.subtitle = QLabel("连接设备后显示应用")
        self.subtitle.setObjectName("FloatSubtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.more = QPushButton("⋯")
        self.more.setObjectName("FloatRound")
        self.more.setFixedSize(28, 28)
        self.more.clicked.connect(
            lambda: self.menu_requested.emit(
                self.more.mapToGlobal(self.more.rect().bottomLeft())
            )
        )
        header.addWidget(self.more, 0, Qt.AlignTop)
        outer.addLayout(header)

        self.cat_scroll = QScrollArea()
        self.cat_scroll.setFixedHeight(36)
        self.cat_scroll.setWidgetResizable(True)
        self.cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        cat_widget = QWidget()
        cat_widget.setStyleSheet("background:transparent;")
        self.cat_lay = QHBoxLayout(cat_widget)
        self.cat_lay.setContentsMargins(0, 1, 0, 1)
        self.cat_lay.setSpacing(7)
        self._cat_buttons: dict[str, QPushButton] = {}
        for key in ["all"] + [k for k, _t, _c in CATEGORIES]:
            btn = QPushButton("全部" if key == "all" else label_of(key))
            btn.setObjectName("FloatPill")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _=False, k=key: self._set_category(k))
            self._cat_buttons[key] = btn
            self.cat_lay.addWidget(btn)
        self._restyle_pills()
        self.cat_lay.addStretch(1)
        self.cat_scroll.setWidget(cat_widget)
        outer.addWidget(self.cat_scroll)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:rgba(255,255,255,0.16);")
        outer.addWidget(divider)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.30);
                                          border-radius: 3px; min-height: 24px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        """)
        self.content = QWidget()
        self.content.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 8, 4, 10)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(4)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        self.footer = QLabel("●   ○")
        self.footer.setObjectName("FloatSubtitle")
        self.footer.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.footer)
        self._apply_palette()

    def _apply_palette(self) -> None:
        dark = style.is_dark()
        fg = "#EEF5FF" if dark else "#1B2534"
        fg2 = "rgba(226,238,255,0.62)" if dark else "rgba(40,60,90,0.62)"
        pill_bg = "rgba(255,255,255,0.10)" if dark else "rgba(30,70,130,0.10)"
        pill_fg = "#DCEBFF" if dark else "#274569"
        self.setStyleSheet(f"""
            #FloatTitle {{ font-size:21px; font-weight:600; color:{fg}; }}
            #FloatSubtitle {{ font-size:11px; color:{fg2}; }}
            #FloatRound {{
                background:{pill_bg}; border:1px solid rgba(255,255,255,0.22);
                border-radius:14px; color:{fg}; font-size:14px; padding:0;
            }}
            #FloatRound:hover {{ background:rgba(255,255,255,0.20); }}
            #FloatPill {{
                background:{pill_bg}; border:1px solid rgba(255,255,255,0.12);
                border-radius:14px; padding:3px 15px; color:{pill_fg}; font-size:12px;
            }}
            #FloatPill:hover {{ background:rgba(255,255,255,0.18); }}
        """)
        self._restyle_pills()

    def _style_pill(self, btn: QPushButton, active: bool) -> None:
        """手动上色，避免 QSS :checked 伪状态在深浅主题下对比度失控。"""
        dark = style.is_dark()
        if active:
            bg, fg, border = "rgba(72,140,255,0.88)", "#FFFFFF", "rgba(170,205,255,0.92)"
        else:
            bg = "rgba(255,255,255,0.10)" if dark else "rgba(30,70,130,0.08)"
            fg = "#DCEBFF" if dark else "#274569"
            border = "rgba(255,255,255,0.14)" if dark else "rgba(30,70,130,0.16)"
        btn.setChecked(active)
        btn.setStyleSheet(
            f"QPushButton{{background:{bg};border:1px solid {border};"
            f"border-radius:14px;padding:3px 15px;color:{fg};font-size:12px;}}"
        )

    def _restyle_pills(self) -> None:
        if not getattr(self, "_cat_buttons", None):
            return
        for key, btn in self._cat_buttons.items():
            self._style_pill(btn, key == self._category)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        dark = style.is_dark()
        bg = QColor(8, 30, 54, 226) if dark else QColor(247, 251, 255, 232)
        top = QColor(16, 58, 100, 226) if dark else QColor(255, 255, 255, 236)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 20, 20)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), bg)
        top_path = QPainterPath()
        top_path.addRect(QRectF(0, 0, self.width(), 96))
        painter.fillPath(top_path, top)
        painter.setPen(QColor(255, 255, 255, 78) if dark else QColor(30, 60, 100, 60))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 20, 20)
        painter.end()

    # ---------- 数据 ----------
    def set_device_label(self, text: str) -> None:
        self._device = text
        self._update_subtitle()

    def _update_subtitle(self) -> None:
        parts = [p for p in (self._device, f"{len(self._apps)} 个应用" if self._apps else "") if p]
        self.subtitle.setText(" · ".join(parts) if parts else "连接设备后显示应用")

    def set_apps(self, apps: list[AppData], *, defer_hidden: bool = True) -> None:
        """面板不可见时只保存数据：避免后台每批图标结果都重建 50+ 个 widget。"""
        self._apps = list(apps)
        self._update_subtitle()
        if defer_hidden and not self.isVisible():
            self._dirty = True
            return
        self._dirty = False
        self._rebuild()

    def ensure_built(self) -> None:
        if self._dirty:
            self._dirty = False
            self._rebuild()

    def set_theme(self) -> None:
        self._apply_palette()
        if not self.isVisible():
            self._dirty = True
        else:
            self._rebuild()
        self.update()

    def _set_category(self, key: str) -> None:
        self._category = key
        self._restyle_pills()
        self._rebuild()

    # ---------- 网格 ----------
    def _cell_metrics(self) -> tuple[int, int, int]:
        """固定 7 列；至少 4 行在可视区内完整显示。"""
        cell_w = max(64, (self.width() - 52) // GRID_COLS)
        icon_size = min(78, cell_w - 16)
        grid_h = max(240, self.scroll.viewport().height())
        max_cell_h = max(74, grid_h // GRID_MIN_ROWS)
        cell_h = min(icon_size + 26, max_cell_h)
        icon_size = min(icon_size, max(42, cell_h - 26))
        return cell_w, cell_h, icon_size

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._icons = []

    def _rebuild(self) -> None:
        self._clear_grid()
        cell_w, cell_h, icon_size = self._cell_metrics()
        for col in range(GRID_COLS):
            self.grid.setColumnMinimumWidth(col, cell_w)

        visible = [a for a in self._apps
                   if self._category == "all" or a.category == self._category]
        if not visible:
            empty = QLabel("连接设备后显示可投屏的应用")
            empty.setObjectName("FloatSubtitle")
            empty.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(empty, 0, 0, GRID_MIN_ROWS, GRID_COLS)
            self.footer.setText("等待设备连接")
            return
        # 分组时每组前面加一条细分隔线，风格贴近参考图
        for index, app in enumerate(visible):
            icon = FloatAppIcon(app, cell_w, cell_h, icon_size)
            icon.clicked.connect(self.launch_requested)
            self.grid.addWidget(icon, index // GRID_COLS, index % GRID_COLS,
                                Qt.AlignHCenter | Qt.AlignTop)
            self._icons.append(icon)
        pages = max(1, math.ceil(len(visible) / (GRID_COLS * GRID_MIN_ROWS)))
        self.footer.setText(
            "   ".join("●" if i == 0 else "○" for i in range(min(pages, 6)))
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if event.oldSize() == event.size():
            return
        if not self.isVisible():
            self._dirty = True
            return
        self._rebuild()


LIST_W = 232
ROW_H = 34


class FloatWindowList(QWidget):
    """悬停悬浮球时展示的「正在投屏」小列表；点击条目把对应窗口置前。"""
    focus_requested = Signal(str)
    entered = Signal()
    left = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(LIST_W)
        self._windows: list[tuple[str, str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 9, 12, 9)
        outer.setSpacing(3)
        self.title = QLabel("正在投屏")
        self.title.setObjectName("FloatListTitle")
        outer.addWidget(self.title)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(2)
        outer.addLayout(self.rows)
        self.hint = QLabel("点击名称切换到该投屏窗口")
        self.hint.setObjectName("FloatListHint")
        outer.addWidget(self.hint)
        self.set_windows([])

    def set_windows(self, windows: list[tuple[str, str]]) -> None:
        self._windows = list(windows)
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self.title.setText(f"正在投屏 · {len(self._windows)}")
        for window_id, label in self._windows:
            btn = QPushButton(label)
            btn.setObjectName("FloatWinRow")
            btn.setFixedHeight(ROW_H)
            btn.setToolTip(label)
            btn.clicked.connect(
                lambda _=False, wid=window_id: self.focus_requested.emit(wid)
            )
            self.rows.addWidget(btn)
        height = 20 + 3 + len(self._windows) * (ROW_H + 2) + 3 + 16 + 18
        self.setFixedHeight(max(72, height))
        self._apply_palette()

    def set_theme(self) -> None:
        self._apply_palette()
        self.update()

    def _apply_palette(self) -> None:
        dark = style.is_dark()
        fg = "#EEF5FF" if dark else "#1B2534"
        fg2 = "rgba(226,238,255,0.62)" if dark else "rgba(40,60,90,0.62)"
        row_bg = "rgba(255,255,255,0.09)" if dark else "rgba(30,70,130,0.07)"
        self.setStyleSheet(f"""
            #FloatListTitle {{ font-size:12px; font-weight:600; color:{fg}; }}
            #FloatListHint {{ font-size:10px; color:{fg2}; }}
            #FloatWinRow {{
                background:{row_bg}; border:1px solid rgba(255,255,255,0.10);
                border-radius:8px; color:{fg}; font-size:12px;
                text-align:left; padding:0 10px;
            }}
            #FloatWinRow:hover {{ background:rgba(72,140,255,0.42); color:#FFFFFF; }}
        """)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        dark = style.is_dark()
        bg = QColor(8, 30, 54, 236) if dark else QColor(247, 251, 255, 240)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), bg)
        painter.setPen(QColor(255, 255, 255, 78) if dark else QColor(30, 60, 100, 60))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 14, 14
        )
        painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.left.emit()
        super().leaveEvent(event)


class FloatController(QObject):
    """管理悬浮球、弹出面板与位置跟随。"""
    launch_requested = Signal(str)
    exit_requested = Signal()
    main_window_requested = Signal()
    settings_requested = Signal()
    reload_requested = Signal()
    quit_requested = Signal()
    focus_requested = Signal(str)          # 把已投屏窗口置前（window_id）

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.ball = FloatBall()
        self.panel = FloatPanel()
        self.window_list = FloatWindowList()
        self._apps: list[AppData] = []
        self._running_windows: list[tuple[str, str]] = []
        self._ball_hover = False

        self.ball.clicked.connect(self.toggle_panel)
        self.ball.moved.connect(self._on_ball_moved)
        self.ball.hovered.connect(self._on_hover)
        self.ball.context_requested.connect(self._show_ball_menu)
        self.panel.launch_requested.connect(self.launch_requested)
        self.panel.menu_requested.connect(self._show_panel_menu)
        self.window_list.focus_requested.connect(self._on_list_focus)

        self._show_list_timer = QTimer(self)
        self._show_list_timer.setSingleShot(True)
        self._show_list_timer.setInterval(160)
        self._show_list_timer.timeout.connect(self._show_window_list)
        self._hide_list_timer = QTimer(self)
        self._hide_list_timer.setSingleShot(True)
        self._hide_list_timer.setInterval(280)
        self._hide_list_timer.timeout.connect(self._hide_window_list)
        self.window_list.entered.connect(self._hide_list_timer.stop)
        self.window_list.left.connect(self._schedule_hide_list)

        # macOS 会在切换 Spaces / 别的 App 全屏 / 本 App 失活时重排窗口层级，
        # 周期性重新断言原生层级，保证悬浮球始终最前。
        self._top_timer = QTimer(self)
        self._top_timer.setInterval(1000)
        self._top_timer.timeout.connect(self._assert_on_top)
        app = QApplication.instance()
        if app is not None:
            try:
                app.applicationStateChanged.connect(
                    lambda *_: QTimer.singleShot(0, self._assert_on_top)
                )
            except (AttributeError, TypeError):
                pass

    # ---------- 生命周期 ----------
    def show(self, pos: tuple[int, int] | list[int] | None = None) -> None:
        if not self.ball.isVisible():
            x, y = self._default_pos() if not pos else (int(pos[0]), int(pos[1]))
            self.ball.move(x, y)
            self.ball.show()
        self.ball.raise_()
        # NSWindow 在 show() 之后才创建，下一帧与稍后再各断言一次
        QTimer.singleShot(0, self._assert_on_top)
        QTimer.singleShot(150, self._assert_on_top)
        if not self._top_timer.isActive():
            self._top_timer.start()

    def hide(self) -> None:
        self._top_timer.stop()
        self._hide_window_list()
        self.window_list.hide()
        self.panel.hide()
        self.ball.hide()

    # ---------- 始终最前 ----------
    def _pin_all(self) -> bool:
        # 对三个窗口无条件设置：Qt 的 Popup / Tool 随时可能隐藏/重建 NSWindow
        # 并重置 level，等「可见」才设置会漏掉刚显示出来的那一瞬间。
        ok = nativewindow.pin(self.ball, nativewindow.BALL_LEVEL)
        ok = nativewindow.pin(self.panel, nativewindow.PANEL_LEVEL) and ok
        ok = nativewindow.pin(self.window_list, nativewindow.LIST_LEVEL) and ok
        return ok

    def _assert_on_top(self) -> None:
        if not self.ball.isVisible():
            return
        pinned = self._pin_all()
        if not pinned:
            # 非 macOS 或原生调用失败时，退回 Qt 的置顶 flag + raise
            self.ball.raise_()
            if self.panel.isVisible():
                self.panel.raise_()

    def ball_pos(self) -> tuple[int, int]:
        return self.ball.x(), self.ball.y()

    @staticmethod
    def _default_pos() -> tuple[int, int]:
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area is None:
            return 80, 120
        return area.right() - BALL_SIZE - 70, area.top() + 120

    def set_apps(self, apps: list[AppData]) -> None:
        self._apps = list(apps)
        self.panel.set_apps(self._apps)

    def set_device_label(self, text: str) -> None:
        self.panel.set_device_label(text)

    def apply_theme(self) -> None:
        self.panel.set_theme()
        self.window_list.set_theme()
        self.ball.update()

    # ---------- 运行中窗口 / 角标 / hover 小列表 ----------
    def set_running_windows(self, windows: list[tuple[str, str]]) -> None:
        self._running_windows = list(windows)
        self.ball.set_count(len(self._running_windows))
        self.window_list.set_windows(self._running_windows)
        if not self._running_windows:
            self._hide_window_list()
        elif self.window_list.isVisible():
            self.place_window_list()

    def _on_hover(self, inside: bool) -> None:
        self._ball_hover = inside
        if inside:
            self._hide_list_timer.stop()
            if not self.panel.isVisible() and self._running_windows:
                self._show_list_timer.start()
        else:
            self._show_list_timer.stop()
            self._schedule_hide_list()

    def _schedule_hide_list(self) -> None:
        if self.window_list.isVisible():
            self._hide_list_timer.start()

    def _show_window_list(self) -> None:
        if not self._ball_hover or self.panel.isVisible() \
                or not self._running_windows or not self.ball.isVisible():
            return
        self.place_window_list()
        self.window_list.show()
        self.window_list.raise_()
        QTimer.singleShot(0, self._assert_on_top)

    def _hide_window_list(self) -> None:
        self._show_list_timer.stop()
        self._hide_list_timer.stop()
        self.window_list.hide()

    def _on_list_focus(self, window_id: str) -> None:
        self._hide_window_list()
        self.focus_requested.emit(window_id)

    def place_window_list(self) -> None:
        center = QPoint(self.ball.x() + BALL_SIZE // 2,
                        self.ball.y() + BALL_SIZE // 2)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area is None:
            area = QApplication.primaryScreen().availableGeometry()
        x, y = self._choose_origin(center.x(), center.y(), area,
                                    self.window_list.width(),
                                    self.window_list.height())
        self.window_list.move(x, y)

    def collapse_panel(self) -> None:
        """收起应用面板（投屏成功后调用），hover 小列表也一并收起。"""
        self.panel.hide()
        self._hide_window_list()

    # ---------- 面板定位 ----------
    def toggle_panel(self) -> None:
        self._hide_window_list()
        if self.panel.isVisible():
            self.panel.hide()
            return
        self.place_panel()
        self.panel.ensure_built()      # 延迟到真正展开时才构建网格
        self.panel.show()
        self.panel.raise_()
        self._pin_all()
        # Qt 的 Popup 会在 show 之后把 NSWindow level 改回自己的面板级别，
        # 且 NSWindow 可能尚未创建；分几次断言把层级压住。
        for delay in (0, 120, 400):
            QTimer.singleShot(delay, self._assert_on_top)

    def _on_ball_moved(self) -> None:
        self._hide_window_list()       # 拖动时列表位置失效，先收起
        if self.panel.isVisible():
            self.place_panel()

    @staticmethod
    def _choose_origin(cx: int, cy: int, area, w: int, h: int) -> tuple[int, int]:
        """球在左半 → 面板向右展开；右半 → 向左；上半 → 向下；下半 → 向上。"""
        radius = BALL_SIZE // 2
        if cx <= area.center().x():
            x = cx + radius + GAP
        else:
            x = cx - radius - GAP - w
        if cy <= area.center().y():
            y = cy - radius - 24
        else:
            y = cy + radius + GAP - h
        lower_x = area.left() + EDGE
        upper_x = max(lower_x, area.right() - w - EDGE)
        lower_y = area.top() + EDGE
        upper_y = max(lower_y, area.bottom() - h - EDGE)
        return min(max(int(x), lower_x), upper_x), min(max(int(y), lower_y), upper_y)

    def place_panel(self) -> QRectF:
        """按悬浮球所在屏幕与象限选择展开方向，并 clamp 保证完整可见。"""
        center = QPoint(self.ball.x() + BALL_SIZE // 2,
                        self.ball.y() + BALL_SIZE // 2)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area is None:
            area = QApplication.primaryScreen().availableGeometry()

        max_w = max(420, area.width() - 2 * EDGE)
        max_h = max(360, area.height() - 2 * EDGE)
        w, h = min(PANEL_W, max_w), min(PANEL_H, max_h)
        self.panel.setFixedSize(int(w), int(h))
        x, y = self._choose_origin(center.x(), center.y(), area, int(w), int(h))
        self.panel.move(x, y)
        return QRectF(x, y, w, h)

    # ---------- 菜单 ----------
    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction("展开 / 收起应用", self.toggle_panel)
        menu.addAction("重新读取应用列表", self.reload_requested.emit)
        menu.addSeparator()
        menu.addAction("显示主窗口", self.main_window_requested.emit)
        menu.addAction("设置…", self.settings_requested.emit)
        menu.addSeparator()
        menu.addAction("退出悬浮球模式", self.exit_requested.emit)
        menu.addSeparator()
        menu.addAction("退出 Scrcpy Studio", self.quit_requested.emit)
        return menu

    def _show_ball_menu(self, pos: QPoint) -> None:
        self._build_menu().exec(pos)

    def _show_panel_menu(self, pos: QPoint) -> None:
        self._build_menu().exec(pos)
