"""界面配色与全局样式表。"""
from __future__ import annotations

BG = "#F4F3F0"
CARD = "#FFFFFF"
CARD_ALT = "#FAFAF8"
BORDER = "#E4E2DB"
BORDER_STRONG = "#D3D0C8"
TEXT = "#1E1E1C"
TEXT2 = "#6D6B65"
TEXT3 = "#9C9A94"
ACCENT = "#2563EB"
ACCENT_DARK = "#1B4DC0"
ACCENT_SOFT = "#EAF0FE"
OK = "#1D9E75"
WARN = "#B4761A"
DANGER = "#C0392B"

FONT = '"PingFang SC", "Helvetica Neue", -apple-system, sans-serif'
MONO = "Menlo"

QSS = f"""
QWidget {{
    background: transparent;
    color: {TEXT};
    font-family: {FONT};
    font-size: 13px;
}}
QMainWindow, #Root {{ background: {BG}; }}

#HeaderTitle {{ font-size: 17px; font-weight: 600; color: {TEXT}; }}
#HeaderSub   {{ font-size: 12px; color: {TEXT3}; }}

#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
#CardTitle {{ font-size: 12px; font-weight: 600; color: {TEXT2}; }}
#GroupTitle {{ font-size: 12px; font-weight: 600; color: {TEXT2}; }}
#FieldLabel {{ font-size: 12px; color: {TEXT2}; }}
#Hint {{ font-size: 11px; color: {TEXT3}; }}
#MonoHint {{ font-family: {MONO}; font-size: 11px; color: {TEXT3}; }}

QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 5px 12px;
    color: {TEXT};
    font-size: 12px;
}}
QPushButton:hover  {{ background: {CARD_ALT}; border-color: {TEXT3}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT3}; border-color: {BORDER}; background: {CARD_ALT}; }}

QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 600;
    padding: 9px 16px;
    border-radius: 9px;
}}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
QPushButton#Primary:disabled {{ background: #C9D6F5; border-color: #C9D6F5; color: #FFFFFF; }}

QPushButton#Ghost {{
    background: {ACCENT_SOFT};
    border: 1px solid transparent;
    color: {ACCENT_DARK};
}}
QPushButton#Ghost:hover {{ border-color: {ACCENT}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 4px 8px;
    min-height: 20px;
    font-size: 12px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; border: none; background: transparent; }}

QCheckBox {{ spacing: 8px; font-size: 12px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    background: {CARD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}

QSlider::groove:horizontal {{
    height: 3px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {CARD}; border: 1px solid {BORDER_STRONG};
    width: 13px; height: 13px; margin: -6px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ border-color: {ACCENT}; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}

QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: 8px;
    margin: 2px 4px;
}}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; }}
QListWidget::item:hover {{ background: {CARD_ALT}; }}
QListWidget::item:selected:hover {{ background: {ACCENT_SOFT}; }}

#Console {{
    background: {CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 9px;
    font-family: {MONO};
    font-size: 11px;
    color: {TEXT2};
    padding: 6px;
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; border-radius: 4px; }}

QDialog {{ background: {BG}; }}
QToolTip {{
    background: #2C2C2A; color: #F4F3F0; border: none;
    padding: 5px 8px; border-radius: 6px; font-size: 11px;
}}
QMenu {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 5px 18px 5px 12px; border-radius: 5px; font-size: 12px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
"""
