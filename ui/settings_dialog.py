"""设置对话框：把复杂参数收进「投屏 / 外观 / 连接」三个标签页。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget, QCheckBox,
)

from core import paths
from core.config import AppState, MirrorConfig

from . import style
from .panels import SettingsPanel


class SettingsDialog(QDialog):
    theme_changed = Signal(str)     # 切换主题时实时预览

    def __init__(self, parent: QWidget | None, state: AppState):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(520, 600)
        self.setMinimumWidth(480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        title = QLabel("设置")
        title.setObjectName("HeaderTitle")
        outer.addWidget(title)

        tabs = QTabWidget()
        self.tabs = tabs
        self.form = SettingsPanel()
        self.form.set_config(state.mirror)
        tabs.addTab(self.form, "投屏参数")
        tabs.addTab(self._build_appearance(state), "外观")
        tabs.addTab(self._build_connection(state), "设备连接")
        outer.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            | QDialogButtonBox.RestoreDefaults
        )
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("恢复默认")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self._restore_defaults
        )
        outer.addWidget(buttons)

    def _build_appearance(self, state: AppState) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.theme_combo = QComboBox()
        for text, value in (("跟随系统", "auto"), ("浅色", "light"), ("深色", "dark")):
            self.theme_combo.addItem(text, value)
        index = max(0, self.theme_combo.findData(state.theme))
        self.theme_combo.setCurrentIndex(index)
        self.theme_combo.currentIndexChanged.connect(
            lambda: self.theme_changed.emit(self.theme_combo.currentData())
        )
        form.addRow("外观", self.theme_combo)

        self.columns = QSpinBox()
        self.columns.setRange(0, 12)
        self.columns.setSpecialValueText("按窗口宽度自适应")
        self.columns.setValue(state.launchpad_columns)
        form.addRow("应用网格列数", self.columns)
        lay.addLayout(form)

        hint = QLabel(
            "毛玻璃效果使用柔和光斑壁纸 + 半透明材质层模拟；"
            "选择「跟随系统」时，切换 macOS 深色模式会自动同步。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        return page

    def _build_connection(self, state: AppState) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(12)

        self.prefer_usb = QCheckBox("USB 与无线同时在线时优先使用 USB")
        self.prefer_usb.setChecked(state.prefer_usb)
        form.addRow("", self.prefer_usb)

        self.auto_mirror = QCheckBox("插入 USB 设备后自动开始整屏投屏")
        self.auto_mirror.setChecked(state.auto_mirror_usb)
        form.addRow("", self.auto_mirror)

        self.usb_port = QSpinBox()
        self.usb_port.setRange(1, 65535)
        self.usb_port.setValue(state.usb_port)
        form.addRow("USB → 无线端口", self.usb_port)

        self.adb_path = QLineEdit(state.adb_path)
        self.adb_path.setPlaceholderText("留空自动查找（PATH / ~/.local/opt / Homebrew）")
        form.addRow("adb 路径", self.adb_path)

        self.scrcpy_path = QLineEdit(state.scrcpy_path)
        self.scrcpy_path.setPlaceholderText("留空自动查找；单应用投屏需 scrcpy 5.x")
        form.addRow("scrcpy 路径", self.scrcpy_path)
        lay.addLayout(form)

        self.env_label = QLabel("")
        self.env_label.setObjectName("MonoHint")
        self.env_label.setWordWrap(True)
        self.env_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.env_label)

        detect = QPushButton("重新检测")
        detect.setFixedHeight(26)
        detect.clicked.connect(self._refresh_env_label)
        lay.addWidget(detect)
        self._refresh_env_label()

        hint = QLabel(
            "从 Finder 双击启动时 PATH 很短，程序会自动把 adb 绝对路径传给 scrcpy；"
            "若仍报找不到 adb，在这里手动填写完整路径。\n"
            "无线调试开关需要在手机上手动打开，手机重启后会关闭。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        return page

    def _refresh_env_label(self) -> None:
        paths.scrcpy_version.cache_clear()
        adb_path = paths.resolve_adb(self.adb_path.text())
        scrcpy_path = paths.resolve_scrcpy(self.scrcpy_path.text())
        version = paths.scrcpy_version(self.scrcpy_path.text())
        lines = [f"adb    → {adb_path}",
                 f"scrcpy → {scrcpy_path}",
                 f"版本   → {paths.version_text(self.scrcpy_path.text())}"]
        if version and version[0] < 5:
            lines.append("⚠ 当前 scrcpy < 5.0，单应用投屏将降级为整屏模式")
        self.env_label.setText("\n".join(lines))

    def _restore_defaults(self) -> None:
        self.form.set_config(MirrorConfig())
        self.theme_combo.setCurrentIndex(0)
        self.columns.setValue(0)
        self.prefer_usb.setChecked(True)
        self.auto_mirror.setChecked(False)
        self.usb_port.setValue(5555)
        self.adb_path.clear()
        self.scrcpy_path.clear()
        self._refresh_env_label()
        self.theme_changed.emit("auto")

    # ---------- 读取结果 ----------
    def config(self) -> MirrorConfig:
        return self.form.config()

    def theme(self) -> str:
        return self.theme_combo.currentData()

    def columns(self) -> int:
        return self.columns.value()

    def prefer_usb_value(self) -> bool:
        return self.prefer_usb.isChecked()

    def auto_mirror_value(self) -> bool:
        return self.auto_mirror.isChecked()

    def usb_port_value(self) -> int:
        return self.usb_port.value()

    def adb_path_value(self) -> str:
        return self.adb_path.text().strip()

    def scrcpy_path_value(self) -> str:
        return self.scrcpy_path.text().strip()
