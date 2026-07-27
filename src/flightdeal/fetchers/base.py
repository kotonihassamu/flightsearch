"""FlightFetcher 抽象インターフェース（要件3.2.2）。

データ取得部はこのインターフェースの背後に閉じ込め、実装を差し替え可能にする。
これにより Phase 0 の技術検証結果に応じて fast-flights / Playwright / 将来の
公式API（Amadeus等）へ、上位ロジックを変更せず移行できる（要件R1）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..models import Flight


class FetchError(RuntimeError):
    """取得失敗。路線単位の隔離（要件4.3）のため、上位はこれを捕捉して継続する。"""


class FlightFetcher(ABC):
    """片道1検索を担う取得器。"""

    name: str = "base"

    @abstractmethod
    def fetch(self, origin: str, destination: str, flight_date: date) -> list[Flight]:
        """指定区間・指定日の直行片道便リストを返す。

        Raises:
            FetchError: 取得に失敗した場合（リトライ判断は呼び出し側）
        """

    def close(self) -> None:
        """リソース解放。ブラウザ系実装でオーバーライドする。"""
        return None

    def __enter__(self) -> "FlightFetcher":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
