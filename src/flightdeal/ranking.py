"""安さランク判定と上位N件の抽出（要件3.5）。

判定は上から順に、最初に該当したランクを採用する。
  S: 実質価格 <= 相場 × 0.70
  A: 実質価格 <= 相場 × 0.85
  B: 実質価格 <  相場  かつ  実質価格 <= max_price
  それ以外: ランク外（通知しない）
"""

from __future__ import annotations

from .config import Config
from .models import Combination, Rank, RouteConfig


def threshold_price(market_price: int, ratio: float) -> int:
    """相場×係数を整数に丸める。

    float の丸め誤差（35000 × 0.7 = 24500.000000000004）で境界値判定が
    ぶれるのを防ぐため、切り捨てて整数にしてから比較する。
    """
    return int(market_price * ratio)


def judge_rank(total_price: int, route: RouteConfig, cfg: Config) -> Rank:
    """実質価格から安さランクを判定する。上から順に最初に該当したランクを返す。"""
    if total_price <= threshold_price(route.market_price, cfg.rank_thresholds["S"]):
        return Rank.S
    if total_price <= threshold_price(route.market_price, cfg.rank_thresholds["A"]):
        return Rank.A
    if total_price < route.market_price and total_price <= route.max_price:
        return Rank.B
    return Rank.NONE


def _sort_key(combo: Combination) -> tuple[int, object]:
    return combo.total_price, combo.outbound.depart_time


def top_n_per_route(combinations: list[Combination], n: int) -> list[Combination]:
    """同一路線・同一週末でランク入りが複数ある場合、安い順に上位N件へ絞る。

    - ランク外（Rank.NONE）は除外する
    - 並び順は実質価格の昇順、同額なら往路出発時刻の昇順
    - グループの出現順（＝路線・週末の処理順）は保持する
    """
    if n <= 0:
        return []

    groups: dict[tuple[str, int], list[Combination]] = {}
    for combo in combinations:
        if combo.rank is Rank.NONE:
            continue
        groups.setdefault((combo.route.iata, combo.weekend.index), []).append(combo)

    result: list[Combination] = []
    for members in groups.values():
        members.sort(key=_sort_key)
        result.extend(members[:n])
    return result
