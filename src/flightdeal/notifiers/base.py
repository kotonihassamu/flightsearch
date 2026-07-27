"""通知インターフェース（要件3.6）。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotifyError(RuntimeError):
    """通知送信の失敗。"""


class Notifier(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, text: str) -> None:
        """本文を送信する。5,000文字超の分割は呼び出し側（formatter）で行う。"""
