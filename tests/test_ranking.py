"""ランク判定の境界値テスト（要件6.1）。

相場 35,000 / max_price 30,000 / S=0.70 / A=0.85 を前提とする。
  S 境界: 24,500
  A 境界: 29,750
  B 条件: 35,000 未満 かつ 30,000 以下
"""

from __future__ import annotations

import pytest

from flightdeal import ranking
from flightdeal.models import Rank

from .conftest import AUG1, AUG8 as AUG2, HIJ, MYJ, make_combination, make_flight



@pytest.mark.parametrize(
    "total,expected",
    [
        (24_499, Rank.S),
        (24_500, Rank.S),    # 相場×0.70 ちょうど -> 以下なので S
        (24_501, Rank.A),
        (29_750, Rank.A),    # 相場×0.85 ちょうど
        (29_751, Rank.B),    # A外だが max_price 以下・相場未満
        (30_000, Rank.B),    # max_price ちょうど
        (30_001, Rank.NONE), # max_price 超過
        (34_999, Rank.NONE),
        (35_000, Rank.NONE), # 相場と同額 -> B は「未満」なので該当しない
        (40_000, Rank.NONE),
    ],
)
def test_judge_rank_boundaries(total, expected, route_hij, cfg):
    assert ranking.judge_rank(total, route_hij, cfg) is expected


def test_top_n_per_route_sorted_and_limited():
    """同一路線・同一週末は安い順に上位3件まで（要件3.5）。"""
    combos = [
        make_combination(total=t, rank=Rank.B) for t in (29000, 25000, 27000, 26000, 28000)
    ]
    top = ranking.top_n_per_route(combos, 3)
    assert [c.total_price for c in top] == [25000, 26000, 27000]


def test_top_n_excludes_rank_none():
    combos = [
        make_combination(total=25000, rank=Rank.S),
        make_combination(total=24000, rank=Rank.NONE),  # 安いが対象外
    ]
    top = ranking.top_n_per_route(combos, 3)
    assert [c.total_price for c in top] == [25000]


def test_top_n_grouped_by_route_and_weekend():
    """路線・週末ごとに独立して上位N件を取る。"""
    combos = [
        make_combination(total=25000, rank=Rank.A, route=HIJ, weekend=AUG1),
        make_combination(total=26000, rank=Rank.A, route=HIJ, weekend=AUG1),
        make_combination(total=27000, rank=Rank.A, route=HIJ, weekend=AUG2),
        make_combination(total=20000, rank=Rank.S, route=MYJ, weekend=AUG1),
    ]
    top = ranking.top_n_per_route(combos, 1)
    keys = {(c.route.iata, c.weekend.index, c.total_price) for c in top}
    assert keys == {("HIJ", 1, 25000), ("HIJ", 2, 27000), ("MYJ", 1, 20000)}


def test_top_n_ties_broken_by_departure_time():
    combos = [
        make_combination(total=25000, rank=Rank.A, outbound=make_flight(dep="09:00")),
        make_combination(total=25000, rank=Rank.A, outbound=make_flight(dep="07:25")),
    ]
    top = ranking.top_n_per_route(combos, 2)
    assert [c.outbound.depart_time.hour for c in top] == [7, 9]


def test_threshold_price_truncates_float_error():
    """35000 × 0.7 = 24500.000000000004 の丸め誤差を吸収する。"""
    assert ranking.threshold_price(35000, 0.70) == 24500
    assert ranking.threshold_price(35000, 0.85) == 29750
    assert ranking.threshold_price(33000, 0.70) == 23100
