"""ドメインモデル定義。

要件 3.2.2「取得項目」/ 3.4「実質価格」/ 3.5「ランク判定」に対応する
データ構造をここに集約する。ロジックは持たせず、値の入れ物に徹する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum


class Direction(str, Enum):
    """検索方向。片道分解方式（要件3.2.1）で使用。"""

    OUTBOUND = "outbound"  # 往路: HND -> 目的地（土曜）
    RETURN = "return"      # 復路: 目的地 -> HND（日曜）


class AirlineClass(str, Enum):
    """手荷物補正の区分（要件3.4）。"""

    FSC = "fsc"          # +0円
    LCC = "lcc"          # +baggage_surcharge_oneway
    UNKNOWN = "unknown"   # リスト外 -> LCC扱い＋「補正額は仮」注記


class Rank(str, Enum):
    """安さランク（要件3.5）。"""

    S = "S"
    A = "A"
    B = "B"
    NONE = "-"  # ランク外（通知しない）


@dataclass(frozen=True)
class Flight:
    """片道1便。FlightFetcher の出力単位。"""

    origin: str            # IATA
    destination: str       # IATA
    flight_date: date
    airline: str           # 航空会社名（取得された生文字列）
    depart_time: time      # JST
    arrive_time: time      # JST
    price: int             # 片道価格（JPY, 整数）
    flight_number: str | None = None

    # TODO(Phase 1): 到着が翌日になるケース（国内線では基本発生しない）の扱いを決める


@dataclass(frozen=True)
class WeekendDates:
    """1つの週末（土曜・日曜のペア）。要件3.1。"""

    saturday: date
    sunday: date
    index: int  # 1 = 第1週末, 2 = 第2週末


@dataclass(frozen=True)
class RouteConfig:
    """config.json の destinations 1件分。"""

    iata: str
    name: str
    market_price: int
    max_price: int
    enabled: bool


@dataclass(frozen=True)
class Combination:
    """往路便×復路便の組み合わせと、その実質価格・ランク（要件3.4 / 3.5）。"""

    route: RouteConfig
    weekend: WeekendDates
    outbound: Flight
    inbound: Flight
    outbound_surcharge: int
    inbound_surcharge: int
    total_price: int          # 実質価格（往復）
    rank: Rank = Rank.NONE
    provisional_surcharge: bool = False  # 判定不能な航空会社を含む -> 通知に注記

    @property
    def discount_rate(self) -> float:
        """相場に対する割引率（0.35 = ▲35%）。"""
        if self.route.market_price <= 0:
            return 0.0
        return 1.0 - (self.total_price / self.route.market_price)


@dataclass
class RouteResult:
    """1路線・1週末分の処理結果。ログと失敗可視化（要件4.3）に使う。"""

    route: RouteConfig
    weekend: WeekendDates
    outbound_count: int = 0
    inbound_count: int = 0
    excluded_count: int = 0          # 取得項目欠損で除外した便数
    combinations: list[Combination] = field(default_factory=list)
    cheapest_total: int | None = None  # 時間帯フィルタ後の最安実質価格（ランク外含む・相場調整用）
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass
class RunResult:
    """1実行分の全体結果。"""

    results: list[RouteResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def all_failed(self) -> bool:
        """全路線失敗（要件4.3 サイレント障害防止のトリガー）。"""
        return bool(self.results) and all(r.failed for r in self.results)

    @property
    def notifiable(self) -> list[Combination]:
        """Bランク以上の組み合わせ（要件3.6 トリガー）。"""
        out: list[Combination] = []
        for r in self.results:
            out.extend(c for c in r.combinations if c.rank is not Rank.NONE)
        return out
