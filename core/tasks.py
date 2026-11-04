"""把阻塞调用丢到线程池，回到主线程再更新界面。"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple, kwargs: dict):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - 任何异常都要回报到界面
            self.signals.failed.emit(str(exc))
            return
        self.signals.done.emit(result)


_pool = QThreadPool.globalInstance()
_alive: set[_Job] = set()


def run_async(
    fn: Callable[..., Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    *args: Any,
    **kwargs: Any,
) -> None:
    job = _Job(fn, args, kwargs)
    if on_done:
        job.signals.done.connect(on_done)
    if on_error:
        job.signals.failed.connect(on_error)

    def _cleanup(*_: Any) -> None:
        _alive.discard(job)

    job.signals.done.connect(_cleanup)
    job.signals.failed.connect(_cleanup)
    _alive.add(job)
    _pool.start(job)
