"""コンソール通知（Phase 1 のドライラン用。要件2 フェーズ表）。

外部送信を伴わないため、判定ロジックの妥当性確認に使う。
骨組み段階でも動作する必要があるため実装済み。
"""

from __future__ import annotations

import sys

from .base import Notifier


class ConsoleNotifier(Notifier):
    name = "console"

    def send(self, text: str) -> None:
        print("=" * 60, file=sys.stdout)
        print("[DRY-RUN] 通知本文", file=sys.stdout)
        print("=" * 60, file=sys.stdout)
        print(text, file=sys.stdout)
        print("=" * 60, file=sys.stdout)
