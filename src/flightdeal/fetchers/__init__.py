"""データ取得層。config.json の "fetcher" で実装を切り替える（要件3.2.2）。"""

from __future__ import annotations

from .base import FetchError, FlightFetcher
from .stub import FixtureFetcher, StubFetcher

__all__ = [
    "FlightFetcher",
    "FetchError",
    "StubFetcher",
    "FixtureFetcher",
    "build_fetcher",
]


def build_fetcher(name: str) -> FlightFetcher:
    """名前から取得器を生成するファクトリ。

    "fast_flights" -> FastFlightsFetcher（Phase 0 検証後に有効化）
    "stub"         -> StubFetcher（ドライラン既定）
    "fixture"      -> FixtureFetcher（回帰テスト用）
    "playwright"   -> 未実装（優先度2のフォールバック）
    """
    if name == "stub":
        return StubFetcher()
    if name == "fixture":
        return FixtureFetcher()
    if name == "fast_flights":
        from .fast_flights_fetcher import FastFlightsFetcher

        return FastFlightsFetcher()
    if name == "playwright":
        raise NotImplementedError(
            "Playwright フェッチャは優先度2のフォールバックです。"
            "fast-flights が Phase 0 で不採用/故障となった場合に実装します。"
        )
    raise ValueError(f"未知の fetcher です: {name}")
