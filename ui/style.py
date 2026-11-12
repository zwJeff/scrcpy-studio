"""主题引擎：macOS 风格毛玻璃配色、深/浅色模式与全局样式表。

对外接口：
    set_mode("auto" | "light" | "dark")   设置主题模式（auto 跟随系统）
    apply(app)                            刷新全局 QSS 并 polish 所有窗口
    P()                                   当前色板
    paint_wallpaper(painter, rect)        绘制毛玻璃底图（由 Root.paintEvent 调用）
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QRadialGradient

AUTO, MODE_LIGHT, MODE_DARK = "auto", "light", "dark"
_MODES = (AUTO, MODE_LIGHT, MODE_DARK)


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    wall_a: str
    wall_b: str
    wall_c: str
    glow_1: str
    glow_2: str
    glow_3: str
    glass: str
    glass_strong: str
    glass_soft: str
    border: str
    border_soft: str
    text: str
    text2: str
    text3: str
    accent: str
    accent_dark: str
    accent_soft: str
    ok: str
    warn: str
    danger: str
    chip: str
    chip_hover: str
    icon_name: str
    console_bg: str
    field: str
    shadow: str

    # 兼容旧代码的常量名
    @property
    def BG(self): return self.bg
    @property
    def CARD(self): return self.glass
    @property
    def CARD_ALT(self): return self.glass_soft
    @property
    def BORDER(self): return self.border_soft
    @property
    def BORDER_STRONG(self): return self.border
    @property
    def TEXT(self): return self.text
    @property
    def TEXT2(self): return self.text2
    @property
    def TEXT3(self): return self.text3
    @property
    def ACCENT(self): return self.accent
    @property
    def ACCENT_DARK(self): return self.accent_dark
    @property
    def ACCENT_SOFT(self): return self.accent_soft
    @property
    def OK(self): return self.ok
    @property
    def WARN(self): return self.warn
    @property
    def DANGER(self): return self.danger


LIGHT = Palette(
    name="light",
    bg="#EEF1F6", wall_a="#DCE7F5", wall_b="#CFDDF2", wall_c="#E8E2F2",
    glow_1="#7FB6F5", glow_2="#B49BE8", glow_3="#7FD4C8",
    glass="rgba(255,255,255,0.56)", glass_strong="rgba(255,255,255,0.76)",
    glass_soft="rgba(255,255,255,0.36)",
    border="rgba(255,255,255,0.86)", border_soft="rgba(38,58,96,0.11)",
    text="#1B2534", text2="#5A6779", text3="#8995A6",
    accent="#2F6BFF", accent_dark="#1F52D6", accent_soft="rgba(47,107,255,0.13)",
    ok="#12855E", warn="#B5761A", danger="#C33F3A",
    chip="rgba(255,255,255,0.44)", chip_hover="rgba(255,255,255,0.72)",
    icon_name="#1B2534", console_bg="rgba(255,255,255,0.34)",
    field="rgba(255,255,255,0.62)", shadow="rgba(30,50,90,0.10)",
)

DARK = Palette(
    name="dark",
    bg="#0A1120", wall_a="#0B1C33", wall_b="#102A46", wall_c="#241B3B",
    glow_1="#1C6FA8", glow_2="#5A3E9B", glow_3="#176B70",
    glass="rgba(24,38,62,0.46)", glass_strong="rgba(16,28,48,0.78)",
    glass_soft="rgba(255,255,255,0.06)",
    border="rgba(255,255,255,0.16)", border_soft="rgba(255,255,255,0.09)",
    text="#EEF3FA", text2="#A8B5C8", text3="#77879E",
    accent="#4C8DFF", accent_dark="#3D77E0", accent_soft="rgba(76,141,255,0.20)",
    ok="#3FBF8F", warn="#E0A24A", danger="#ED6B63",
    chip="rgba(255,255,255,0.09)", chip_hover="rgba(255,255,255,0.16)",
    icon_name="#F0F4FB", console_bg="rgba(8,16,30,0.34)",
    field="rgba(12,22,38,0.48)", shadow="rgba(0,0,0,0.26)",
)

_MODE = AUTO
_OVERRIDE: str | None = None      # 测试/预览时强制某个 resolved 主题


def system_scheme() -> str:
    """读取 macOS 当前外观。"""
    app = QGuiApplication.instance()
    if app is None:
        return LIGHT
    try:
        scheme = app.styleHints().colorScheme()
        return MODE_DARK if scheme == Qt.ColorScheme.Dark else MODE_LIGHT
    except (AttributeError, TypeError):
        return MODE_LIGHT


def resolved() -> str:
    if _OVERRIDE:
        return _OVERRIDE
    return system_scheme() if _MODE == AUTO else _MODE


def is_dark() -> bool:
    return resolved() == MODE_DARK


def P() -> Palette:
    return DARK if is_dark() else LIGHT


def mode() -> str:
    return _MODE


def set_mode(value: str) -> None:
    global _MODE
    _MODE = value if value in _MODES else AUTO


def set_override(value: str | None) -> None:
    global _OVERRIDE
    _OVERRIDE = value


FONT = '"PingFang SC", "Helvetica Neue", -apple-system, sans-serif'
MONO = "Menlo"


def qss() -> str:
    p = P()
    return f"""
QWidget {{
    background: transparent;
    color: {p.text};
    font-family: {FONT};
    font-size: 13px;
}}
QMainWindow, #Root {{ background: transparent; }}
QDialog {{ background: {p.bg}; }}

/* ---------- 玻璃容器 ---------- */
#GlassCard, #Card {{
    background: {p.glass};
    border: 1px solid {p.border};
    border-radius: 18px;
}}
#Toolbar {{
    background: {p.glass_strong};
    border: 1px solid {p.border};
    border-radius: 16px;
}}
#MirrorBar {{
    background: {p.glass};
    border: 1px solid {p.border};
    border-radius: 14px;
}}
#GlassDivider {{ background: {p.border_soft}; }}
#Divider {{ background: {p.border_soft}; }}

/* ---------- 文字 ---------- */
#HeaderTitle {{ font-size: 17px; font-weight: 600; color: {p.text}; }}
#HeaderSub {{ font-size: 11px; color: {p.text3}; }}
#CardTitle {{ font-size: 12px; font-weight: 600; color: {p.text2}; }}
#GroupTitle {{ font-size: 12px; font-weight: 600; color: {p.text2}; }}
#FieldLabel {{ font-size: 12px; color: {p.text2}; }}
#Hint {{ font-size: 11px; color: {p.text3}; }}
#MonoHint {{ font-family: {MONO}; font-size: 11px; color: {p.text3}; }}
#LaunchpadTitle {{ font-size: 22px; font-weight: 600; color: {p.text}; }}
#LaunchpadSub {{ font-size: 12px; color: {p.text3}; }}
#SectionLabel {{ font-size: 12px; font-weight: 600; color: {p.text2}; }}
#IconName {{ font-size: 12px; color: {p.icon_name}; }}
#EmptyStage {{ font-size: 14px; color: {p.text2}; }}
#PageDots {{ font-size: 10px; color: {p.text3}; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {p.chip};
    border: 1px solid {p.border_soft};
    border-radius: 9px;
    padding: 5px 12px;
    color: {p.text};
    font-size: 12px;
}}
QPushButton:hover {{ background: {p.chip_hover}; border-color: {p.border}; }}
QPushButton:pressed {{ background: {p.accent_soft}; }}
QPushButton:disabled {{ color: {p.text3}; border-color: {p.border_soft}; background: transparent; }}
QPushButton#Primary {{
    background: {p.accent};
    border: 1px solid {p.accent};
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 10px;
}}
QPushButton#Primary:hover {{ background: {p.accent_dark}; border-color: {p.accent_dark}; }}
QPushButton#Primary:disabled {{ background: {p.glass_soft}; border-color: {p.border_soft}; color: {p.text3}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {p.border}; }}
QPushButton#Ghost:hover {{ background: {p.chip_hover}; }}
QPushButton#Round {{
    border-radius: 15px; padding: 0; min-width: 30px; max-width: 30px;
    min-height: 30px; max-height: 30px; font-size: 15px;
}}
QPushButton#CategoryPill, #CategoryPill {{
    background: {p.chip};
    border: 1px solid {p.border_soft};
    border-radius: 15px;
    padding: 4px 14px;
    color: {p.text2};
    font-size: 12px;
}}
#CategoryPill:hover {{ background: {p.chip_hover}; }}
#CategoryPill:checked {{
    background: {p.accent};
    border: 1px solid {p.accent};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#Chip {{
    background: {p.chip}; border: 1px solid {p.border_soft};
    border-radius: 11px; padding: 3px 9px; font-size: 11px;
}}
QPushButton#Chip:hover {{ background: {p.chip_hover}; }}
QPushButton#CloseChip {{
    background: transparent; border: none; border-radius: 8px;
    padding: 0; min-width: 18px; max-width: 18px;
    min-height: 18px; max-height: 18px; font-size: 13px; color: {p.text3};
}}
QPushButton#CloseChip:hover {{ background: {p.danger}; color: #FFFFFF; }}

/* ---------- 输入控件 ---------- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {p.field};
    border: 1px solid {p.border_soft};
    border-radius: 9px;
    padding: 5px 10px;
    min-height: 20px;
    font-size: 12px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {p.accent};
}}
QLineEdit#SearchBox {{
    border-radius: 16px;
    padding: 6px 14px;
    background: {p.chip};
    font-size: 13px;
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {p.glass_strong};
    border: 1px solid {p.border};
    border-radius: 10px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; border: none; background: transparent; }}

QCheckBox {{ spacing: 8px; font-size: 12px; color: {p.text}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {p.border};
    border-radius: 4px;
    background: {p.field};
}}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

QSlider::groove:horizontal {{ height: 3px; background: {p.border_soft}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {p.glass_strong}; border: 1px solid {p.border};
    width: 13px; height: 13px; margin: -6px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ border-color: {p.accent}; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}

QTabWidget::pane {{ border: 1px solid {p.border_soft}; border-radius: 12px; background: {p.glass_soft}; }}
QTabBar::tab {{
    background: transparent; border: none; padding: 6px 14px; margin-right: 4px;
    color: {p.text2}; font-size: 12px;
}}
QTabBar::tab:selected {{ color: {p.accent}; font-weight: 600; }}

/* ---------- 列表 / 滚动 / 菜单 ---------- */
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border-radius: 10px; margin: 2px 4px; }}
QListWidget::item:selected {{ background: {p.accent_soft}; }}
QListWidget::item:hover {{ background: {p.glass_soft}; }}

#Console {{
    background: {p.console_bg};
    border: 1px solid {p.border_soft};
    border-radius: 10px;
    font-family: {MONO};
    font-size: 11px;
    color: {p.text2};
    padding: 6px;
}}
#InputBox {{ font-size: 13px; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; }}

QToolTip {{
    background: {p.glass_strong}; color: {p.text};
    border: 1px solid {p.border}; padding: 5px 8px;
    border-radius: 7px; font-size: 11px;
}}
QMenu {{
    background: {p.glass_strong}; border: 1px solid {p.border};
    border-radius: 10px; padding: 5px;
}}
QMenu::item {{ padding: 6px 20px 6px 14px; border-radius: 6px; font-size: 12px; color: {p.text}; }}
QMenu::item:selected {{ background: {p.accent_soft}; }}
QMenu::separator {{ height: 1px; background: {p.border_soft}; margin: 4px 8px; }}
"""


def apply(app, value: str | None = None) -> None:
    """应用主题；切换后 polish 所有顶层窗口，让 QSS 属性选择器生效。"""
    if value is not None:
        set_mode(value)
    _sync_legacy()
    app.setStyleSheet(qss())
    for widget in app.topLevelWidgets():
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def paint_wallpaper(painter: QPainter, rect) -> None:
    """柔和光斑壁纸：Qt 无原生 backdrop blur，用径向渐变模拟毛玻璃底图。"""
    p = P()
    painter.setRenderHint(QPainter.Antialiasing, True)

    base = QLinearGradient(0, 0, rect.width(), rect.height())
    base.setColorAt(0, QColor(p.wall_a))
    base.setColorAt(0.55, QColor(p.wall_b))
    base.setColorAt(1, QColor(p.wall_c))
    painter.fillRect(rect, base)

    w, h = rect.width(), rect.height()
    spots = [
        (w * 0.16, h * 0.14, max(w, h) * 0.62, p.glow_1),
        (w * 0.88, h * 0.30, max(w, h) * 0.52, p.glow_2),
        (w * 0.55, h * 0.96, max(w, h) * 0.58, p.glow_3),
    ]
    for cx, cy, radius, color in spots:
        glow = QRadialGradient(cx, cy, radius)
        c = QColor(color)
        c.setAlpha(150 if is_dark() else 108)
        glow.setColorAt(0, c)
        c2 = QColor(color)
        c2.setAlpha(0)
        glow.setColorAt(1, c2)
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

    vignette = QLinearGradient(0, 0, 0, h)
    edge = QColor("#000000")
    edge.setAlpha(48 if is_dark() else 16)
    vignette.setColorAt(0, edge)
    vignette.setColorAt(0.25, QColor(0, 0, 0, 0))
    vignette.setColorAt(0.80, QColor(0, 0, 0, 0))
    vignette.setColorAt(1, edge)
    painter.fillRect(rect, vignette)


# 兼容旧模块：这些名字在主题切换时同步更新，供 `import style; style.TEXT` 使用
ACCENT = LIGHT.ACCENT
TEXT = LIGHT.TEXT
TEXT2 = LIGHT.TEXT2
TEXT3 = LIGHT.TEXT3
OK = LIGHT.OK
WARN = LIGHT.WARN
BORDER = LIGHT.BORDER
ACCENT_SOFT = LIGHT.ACCENT_SOFT
ACCENT_DARK = LIGHT.ACCENT_DARK
CARD_ALT = LIGHT.CARD_ALT
BG = LIGHT.BG
CARD = LIGHT.CARD
DANGER = LIGHT.DANGER


def _sync_legacy() -> None:
    global ACCENT, TEXT, TEXT2, TEXT3, OK, WARN, BORDER, ACCENT_SOFT
    global ACCENT_DARK, CARD_ALT, BG, CARD, DANGER
    p = P()
    ACCENT, TEXT, TEXT2, TEXT3 = p.ACCENT, p.TEXT, p.TEXT2, p.TEXT3
    OK, WARN, BORDER = p.OK, p.WARN, p.BORDER
    ACCENT_SOFT, ACCENT_DARK = p.ACCENT_SOFT, p.ACCENT_DARK
    CARD_ALT, BG, CARD, DANGER = p.CARD_ALT, p.BG, p.CARD, p.DANGER


def _refresh(app=None) -> None:
    _sync_legacy()
    if app is not None:
        apply(app)


QSS = qss()   # 兼容 app.py 的旧导入；实际主题由 apply() 刷新
