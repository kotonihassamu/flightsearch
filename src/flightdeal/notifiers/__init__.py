"""通知層。config.json の "notifier" で切り替える（要件3.6）。"""

from __future__ import annotations

from .base import Notifier, NotifyError
from .console import ConsoleNotifier

__all__ = ["Notifier", "NotifyError", "ConsoleNotifier", "build_notifier"]


def build_notifier(name: str) -> Notifier:
    """名前から通知器を生成するファクトリ。

    "console" -> ConsoleNotifier（Phase 1 ドライラン既定）
    "line"    -> LineNotifier（Phase 2）
    """
    if name == "console":
        return ConsoleNotifier()
    if name == "line":
        from .line import LineNotifier

        return LineNotifier()
    raise ValueError(f"未知の notifier です: {name}")
