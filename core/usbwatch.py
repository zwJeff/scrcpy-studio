"""USB 热插拔监视：订阅 adb track-devices 事件流，秒级感知设备变化。

adb 的 track-devices 是一个长连接协议：每次设备状态变化推送一帧
「4 位十六进制长度 + 内容」，内容形如 ``HA1R28RT\\tdevice\\n``。
相比 5 秒轮询，插入数据线的瞬间就能收到通知，也让「插入自动投屏」成为可能。

后台线程只负责读帧并通过 Qt 信号发回主线程，所有界面操作都在主线程完成。
adb server 重启或掉线时会自动重连（指数退避，最长 8 秒）。
"""
from __future__ import annotations

import subprocess
import threading

from PySide6.QtCore import QObject, Signal

from .paths import ADB


class DeviceWatcher(QObject):
    devices_changed = Signal(object)   # list[tuple[str, str]]：(serial, state)
    watcher_error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._last: tuple | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="adb-track-devices"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.5)
        self._thread = None

    # ---------- 后台线程 ----------
    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                proc = subprocess.Popen(
                    [ADB, "track-devices"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                self._proc = proc
                backoff = 1.0
                self._read_stream(proc)
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except OSError as exc:
                self.watcher_error.emit(f"设备监视中断：{exc}")
            if self._stop_event.is_set():
                break
            self._stop_event.wait(backoff)
            backoff = min(backoff * 2, 8.0)

    def _read_stream(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        while not self._stop_event.is_set():
            header = proc.stdout.read(4)
            if len(header) < 4:
                return
            try:
                size = int(header, 16)
            except ValueError:
                return
            payload = proc.stdout.read(size)
            if len(payload) < size:
                return
            snapshot: list[tuple[str, str]] = []
            for line in payload.decode("utf-8", "replace").splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    snapshot.append((parts[0], parts[1]))
            ordered = tuple(sorted(snapshot))
            if ordered != self._last:
                self._last = ordered
                self.devices_changed.emit(list(ordered))
